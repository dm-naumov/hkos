#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo "=== Compile All ==="
python -m compileall .
echo "=== Done ==="
