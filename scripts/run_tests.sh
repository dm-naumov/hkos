#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo "=== Running all tests ==="
python -m pytest tests/ -v --tb=short "$@"
