#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "[$(/bin/date '+%Y-%m-%d %H:%M:%S %z')] cloud_hub_sync start"
/usr/bin/python3 "$PROJECT_ROOT/scripts/sync_cloud_hub_to_local.py" --pull --trigger-label launchd
exit_code=$?
echo "[$(/bin/date '+%Y-%m-%d %H:%M:%S %z')] cloud_hub_sync exit status: $exit_code"
exit "$exit_code"
