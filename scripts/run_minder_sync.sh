#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"
/usr/bin/python3 "$PROJECT_ROOT/scripts/sync_cloud_hub_to_local.py" --pull --trigger-label "${1:-manual}"
