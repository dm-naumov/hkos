#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo "=== Cleaning ==="
rm -rf __pycache__ .pytest_cache .mypy_cache .ruff_cache
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete
echo "=== Clean ==="
