#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo "=== Ruff Check ==="
python -m ruff check . "$@"
