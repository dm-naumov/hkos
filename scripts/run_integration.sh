#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo "=== Integration Tests ==="
python -m pytest tests/integration/ -v --tb=short "$@"
