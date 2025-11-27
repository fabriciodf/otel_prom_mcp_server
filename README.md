# OpenTelemetry + Prometheus MCP Server

Ambiente completo para experimentar Prometheus + OpenTelemetry com dois microsserviços em FastAPI, geração de PromQL com Llama3 e o servidor [prometheus-mcp-server](./prometheus-mcp-server) ligado ao mesmo Prometheus.

## Componentes
- **Prometheus** (`docker-compose`): armazena e expõe métricas.
- **OpenTelemetry Collector**: recebe OTLP (gRPC/HTTP) e expõe as métricas convertidas para o Prometheus raspar (`:9464`).
- **Demo Metrics API** (`services/app`): FastAPI instrumentada com OTel Metrics e middleware de latência, exposta em `:8000` (Swagger em `/docs`).
- **Prompt UI** (`services/ui`): FastAPI + Jinja2 com formulário para escrever perguntas em linguagem natural, gerar PromQL via Llama3 (Ollama) e consultar o Prometheus.
- **Ollama + Llama3**: modelo lightweight `llama3.2:1b` por padrão, hospedado no contêiner `ollama`.
- **prometheus-mcp-server**: serviço MCP com transporte HTTP apontando para o Prometheus deste stack (porta `8082` por padrão) para uso em IDEs/assistentes compatíveis.

## Pré-requisitos
- Docker + Docker Compose
- Espaço em disco para baixar o modelo do Ollama (~1-2 GB para `llama3.2:1b`).

## Como subir
1. Vá até a pasta do projeto:  
   `cd prometheus-ai`
2. Opcional: prepare `.env`, baixe imagens e garanta o modelo:  
   `./scripts/install.sh` (use `--skip-model-pull` para pular o modelo)
3. Ou use o reset completo:  
   `./run.sh` (derruba, puxa, builda, sobe e baixa o modelo do Ollama)
4. Suba tudo (se não usou o passo anterior):  
   `docker compose up -d`
5. Se pulou o modelo:  
   `docker exec prometheus-ai-ollama ollama pull llama3.2:1b`

## Endpoints principais
- Demo API: `http://localhost:8000/docs` (`/health`, `/items/{id}`, `/orders`).
- Prompt UI: `http://localhost:8080` (gera PromQL com Llama3, mostra JSON e resumo em PT-BR).
- Prometheus: `http://localhost:9090`.
- OTel Collector: OTLP gRPC `http://localhost:4317`, HTTP `http://localhost:4318`, métricas `http://localhost:9464/metrics`.
- MCP Server (HTTP): `http://localhost:8082`.

## Fluxo de métricas
`Demo API -> (OTLP gRPC) -> OTel Collector -> (endpoint /metrics em :9464) -> Prometheus`  
O Prometheus já vem configurado para raspar o collector e a si mesmo.

## Variáveis de ambiente
Veja `.env` / `.env.example` para portas e nomes de modelo. Ajuste `LLAMA_MODEL` se quiser outro modelo Ollama.

## Usando o UI + LLM
1. Abra `http://localhost:8080`.
2. Escreva algo como:  
   - “Taxa de requisições 5xx no último minuto”  
   - “P95 de latência do endpoint /items nos últimos 5 minutos”  
3. A tela mostra: PromQL gerada, JSON bruto do Prometheus e interpretação em linguagem natural (PT-BR).

## Usando o prometheus-mcp-server
O contêiner `prometheus-ai-mcp-server` já sobe com:
```
PROMETHEUS_URL=http://prometheus:9090
PROMETHEUS_MCP_SERVER_TRANSPORT=http
PROMETHEUS_MCP_BIND_HOST=0.0.0.0
PROMETHEUS_MCP_BIND_PORT=8082
```
Em um cliente MCP, aponte para `http://localhost:8082` (ou use stdio/stdio+docker conforme o README do projeto original em `prometheus-mcp-server/README.md`).

## Desenvolvimento rápido
- Ajuste a API ou UI e rode somente o serviço desejado:  
  `docker compose up --build app-service`  
  `docker compose up --build ui-service`
- Logs ao vivo: `docker compose logs -f app-service ui-service otel-collector`

## Observabilidade extra
- Métricas do app: `demo_requests_total`, `demo_request_latency_ms{bucket,sum,count}`, `demo_pending_orders`.
- Métricas HTTP/semconv: `http_server_duration_milliseconds_{sum,count}` e correlatas, se instrumentadas.
- Métricas de runtime/processo: `process_cpu_seconds_total`, `process_resident_memory_bytes`, `up`, etc.
- Teste carga simples: `curl "http://localhost:8000/items/1?slow=1"` para criar latência.

## Estrutura
- `docker-compose.yml`: orquestra serviços.
- `otel-collector-config.yaml`: pipeline OTLP -> Prometheus exporter.
- `prometheus/prometheus.yml`: scrape do collector e do próprio Prometheus.
- `services/app`: FastAPI + OTel métricas.
- `services/ui`: FastAPI + Jinja2 + Ollama (Llama3) para geração de PromQL.
- `prometheus-mcp-server`: cópia do repositório oficial, já integrada no compose.
- `scripts/install.sh`: ajuda a baixar imagens e garantir o modelo do Ollama.
- `run.sh`: reseta tudo (down -v), remove imagens, pull, build --no-cache, up -d e puxa o modelo.
