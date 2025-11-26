#!/usr/bin/env bash
set -euo pipefail

# Reset and recreate the entire stack from scratch (containers, volumes, images) and run it.
# Also garantee the Ollama model is pulled (unless --skip-model-pull).

usage() {
  cat <<'EOF'
Uso: ./run.sh [--skip-model-pull]

Recria o stack (down -v, remove imagens, pull, build --no-cache, up -d) e garante o modelo do Ollama.
EOF
}

SKIP_MODEL_PULL=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-model-pull) SKIP_MODEL_PULL=1 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Argumento desconhecido: $1" >&2; usage; exit 1 ;;
  esac
  shift
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

echo "[1/6] Derrubando stack anterior (containers, volumes, órfãos)..."
docker compose down -v --remove-orphans || true

echo "[2/6] Removendo imagens locais do stack para rebuild limpo..."
docker images "prometheus-ai-*" --format "{{.Repository}}:{{.Tag}}" | xargs -r docker rmi -f || true

echo "[3/6] Baixando imagens do compose..."
docker compose pull

echo "[4/6] Buildando imagens (sem cache)..."
docker compose build --no-cache

echo "[5/6] Subindo stack em segundo plano..."
docker compose up -d

if [[ "${SKIP_MODEL_PULL}" -eq 0 ]]; then
  echo "[6/6] Garantindo modelo do Ollama (usa LLAMA_MODEL em .env)..."
  docker compose up -d ollama
  MODEL="$(grep -E '^LLAMA_MODEL=' .env | head -n1 | cut -d= -f2-)"
  MODEL="${MODEL:-llama3.2:1b}"
  docker exec prometheus-ai-ollama ollama pull "${MODEL}"
else
  echo "[6/6] Pulando download do modelo (use 'docker exec prometheus-ai-ollama ollama pull <modelo>' depois)."
fi

echo "Pronto! Verifique serviços com 'docker compose ps' e logs com 'docker compose logs -f'."
