import json
import os
import re
from typing import Any, Dict, Optional

import dotenv
import httpx
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

dotenv.load_dotenv()

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
LLAMA_MODEL = os.getenv("LLAMA_MODEL", "llama3.2:1b")
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "")

templates = Jinja2Templates(directory="templates")
templates.env.filters["tojson"] = lambda value, **kwargs: json.dumps(value, **kwargs)
app = FastAPI(title="Prometheus Prompt UI", version="0.1.0")

SYSTEM_PROMPT = """Você é um especialista em PromQL.
Responda com APENAS uma consulta PromQL, sem texto extra e sem cercas de código.
O Prometheus raspa métricas de um Collector OpenTelemetry.
Prefira rate() para contadores, histogram_quantile para histogramas e faça group by por serviço quando relevante.
Escolha métricas que correspondam ao pedido do usuário; se não houver correspondência clara, priorize métricas do app (demo_*) e de HTTP antes de métricas de runtime (go_* ou process_*).
Se a métrica citada pelo usuário não existir, retorne uma consulta simples que deixe isso claro (ex: sum(nonexistent_metric)).
Métricas conhecidas (amostra):
- demo_requests_total (contador)
- demo_request_latency_ms_bucket / _sum / _count (histograma)
- demo_pending_orders (gauge)
- http_server_duration_milliseconds_sum / _count
- process_cpu_seconds_total
- process_resident_memory_bytes
- up
"""


async def fetch_metric_names(limit: int = 30) -> list[str]:
    """Fetch a sample of metric names from Prometheus to ground the LLM."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{PROMETHEUS_URL}/api/v1/label/__name__/values")
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") != "success":
                return []
            values = data.get("data", [])
            values = [v for v in values if isinstance(v, str)]
            return values[:limit]
    except Exception:
        return []


def _filter_metrics_by_prompt(metric_names: list[str], prompt: str, limit: int = 10) -> list[str]:
    keywords = {w.lower() for w in re.findall(r"[a-zA-Z0-9_]+", prompt) if len(w) > 3}
    if not keywords:
        return metric_names[:limit]
    filtered = [m for m in metric_names if any(k in m.lower() for k in keywords)]
    if not filtered:
        return metric_names[:limit]
    return filtered[:limit]


def _prioritize_otel_metrics(metric_names: list[str]) -> list[str]:
    """Ordena colocando métricas do app/HTTP/OTel antes das de runtime."""
    preferred_prefixes = ("demo_", "http_", "otelcol_", "scrape_", "up")
    def sort_key(name: str) -> tuple[int, str]:
        score = 1
        if name.startswith(preferred_prefixes):
            score = 0
        return (score, name)
    return sorted(metric_names, key=sort_key)


async def call_ollama(prompt: str) -> str:
    """Chama o modelo llama3 via Ollama e extrai apenas a consulta."""
    metric_names = _prioritize_otel_metrics(await fetch_metric_names())
    filtered_metrics = _filter_metrics_by_prompt(metric_names, prompt) if metric_names else []
    metric_hint = ""
    if filtered_metrics:
        metric_hint = f"\nMétricas relacionadas ao pedido (amostra): {', '.join(filtered_metrics)}\n"
    elif metric_names:
        metric_hint = f"\nMétricas disponíveis (amostra): {', '.join(metric_names[:10])}\n"
    payload = {
        "model": LLAMA_MODEL,
        "prompt": f"{SYSTEM_PROMPT}{metric_hint}\nPedido do usuário: {prompt}\n\nPromQL:",
        "stream": False,
        "options": {"temperature": 0.2},
    }
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
        response.raise_for_status()
        data = response.json()
        query_text = data.get("response", "").strip()
        return re.sub(r"^`+|`+$", "", query_text)


async def query_prometheus(promql: str) -> Dict[str, Any]:
    """Dispara a consulta gerada contra o Prometheus."""
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{PROMETHEUS_URL}/api/v1/query", params={"query": promql}
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("status") != "success":
            raise HTTPException(status_code=502, detail="Prometheus query failed")
        return payload


async def explain_result(prompt: str, promql: str, result: Dict[str, Any]) -> str:
    """Interpreta o resultado em linguagem natural usando o mesmo LLM."""
    summary_prompt = f"""
Você é um assistente de observabilidade.
Explique em uma frase curta, em português, o que o resultado abaixo diz, considerando o pedido do usuário e a PromQL gerada.
- Seja direto, sem cercas de código.
- Se não houver dados, diga isso de forma clara.

Pedido do usuário: {prompt}
PromQL: {promql}
Resultado bruto: {json.dumps(result)[:2000]}
"""
    payload = {
        "model": LLAMA_MODEL,
        "prompt": summary_prompt,
        "stream": False,
        "options": {"temperature": 0.2},
    }
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
        response.raise_for_status()
        data = response.json()
        return data.get("response", "").strip()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "prometheus": PROMETHEUS_URL, "mcp_server": MCP_SERVER_URL}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "query": None,
            "result": None,
            "error": None,
            "prompt": "",
            "prometheus_url": PROMETHEUS_URL,
            "mcp_server_url": MCP_SERVER_URL,
            "model": LLAMA_MODEL,
        },
    )


@app.post("/prompt", response_class=HTMLResponse)
async def handle_prompt(request: Request, prompt: str = Form(...)) -> HTMLResponse:
    query: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    natural_answer: Optional[str] = None

    try:
        query = await call_ollama(prompt)
        if not query:
            raise HTTPException(status_code=500, detail="O LLM não retornou uma consulta")
        # Opcionalmente, poderíamos validar sintaxe simples aqui
        result = await query_prometheus(query)
        natural_answer = await explain_result(prompt, query, result)
    except Exception as exc:  # noqa: BLE001 - surface readable error to the UI
        error = str(exc)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "query": query,
            "result": result,
            "error": error,
            "prompt": prompt,
            "natural_answer": natural_answer,
            "prometheus_url": PROMETHEUS_URL,
            "mcp_server_url": MCP_SERVER_URL,
            "model": LLAMA_MODEL,
        },
    )
