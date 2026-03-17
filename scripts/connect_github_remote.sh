#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <github-remote-url>"
  echo "Example: $0 git@github.com:yourname/solo-template-business.git"
  exit 1
fi

REMOTE_URL="$1"
GIT_CMD=(git "--git-dir=$PROJECT_ROOT/.git" "--work-tree=$PROJECT_ROOT")

cd "$PROJECT_ROOT"

if [[ ! -d .git ]]; then
  git init -b main
fi

if "${GIT_CMD[@]}" remote get-url origin >/dev/null 2>&1; then
  "${GIT_CMD[@]}" remote set-url origin "$REMOTE_URL"
else
  "${GIT_CMD[@]}" remote add origin "$REMOTE_URL"
fi

echo "GitHub remote configured for $PROJECT_ROOT"
echo "origin -> $REMOTE_URL"
