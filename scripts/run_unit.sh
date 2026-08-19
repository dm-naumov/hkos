#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo "=== Unit Tests ==="
python -m pytest tests/unit/ -v --tb=short "$@"
