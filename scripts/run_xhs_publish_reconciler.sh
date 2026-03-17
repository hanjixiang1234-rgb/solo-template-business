#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "[$(/bin/date '+%Y-%m-%d %H:%M:%S %z')] xhs_reconciler start args: $*"

/usr/bin/python3 "$PROJECT_ROOT/scripts/sync_xhs_mobile_inbox.py" "$@" || \
  echo "[$(/bin/date '+%Y-%m-%d %H:%M:%S %z')] mobile inbox sync failed, continuing with local queue reconcile"

/usr/bin/python3 "$PROJECT_ROOT/scripts/run_xiaohongshu_publish_queue.py" \
  --mode reconcile \
  --lookahead 6 \
  --minimum-lead-minutes 180 \
  "$@"
exit_code=$?

echo "[$(/bin/date '+%Y-%m-%d %H:%M:%S %z')] xhs_reconciler exit status: $exit_code"
exit "$exit_code"
