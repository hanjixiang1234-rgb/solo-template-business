#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env.openai-cloud-hub.local"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  source "$ENV_FILE"
  set +a
fi

HOST="${MINDER_CLOUD_HOST:-0.0.0.0}"
PORT="${MINDER_CLOUD_PORT:-8787}"

cd "$PROJECT_ROOT"
/usr/bin/python3 "$PROJECT_ROOT/scripts/openai_cloud_hub_server.py" --host "$HOST" --port "$PORT"
