#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo "=== Ruff Format ==="
python -m ruff format . "$@"
