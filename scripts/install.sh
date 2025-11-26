#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Uso: ./scripts/install.sh [--skip-model-pull]

- Cria .env (se não existir) a partir de .env.example
- Faz pull das imagens do docker compose
- Opcionalmente sobe o serviço ollama e baixa o modelo definido em LLAMA_MODEL
EOF
}

SKIP_MODEL_PULL=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-model-pull|-s) SKIP_MODEL_PULL=1 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Argumento desconhecido: $1" >&2; usage; exit 1 ;;
  esac
  shift
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

if [[ ! -f ".env" ]]; then
  echo "Criando .env a partir de .env.example"
  cp .env.example .env
fi

echo "Baixando imagens (prometheus, otel-collector, ui, app, mcp, ollama)..."
docker compose pull

if [[ "${SKIP_MODEL_PULL}" -eq 0 ]]; then
  echo "Subindo Ollama e baixando modelo configurado..."
  docker compose up -d ollama
  MODEL="$(grep -E '^LLAMA_MODEL=' .env | head -n1 | cut -d= -f2-)"
  MODEL="${MODEL:-llama3.2:1b}"
  docker exec prometheus-ai-ollama ollama pull "${MODEL}"
  echo "Modelo '${MODEL}' presente no cache do Ollama."
else
  echo "Pulei o download do modelo (rode docker exec prometheus-ai-ollama ollama pull <modelo> depois)."
fi

echo "Pronto. Use 'docker compose up -d' para subir o stack completo."
