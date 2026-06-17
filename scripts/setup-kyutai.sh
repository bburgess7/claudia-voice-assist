#!/usr/bin/env bash
# Set up the Kyutai voice sidecar (.venv-kyutai). First run of scripts/kyutai.sh downloads the model.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
PY="${PY:-/opt/homebrew/bin/python3.12}"
"$PY" -m venv .venv-kyutai
./.venv-kyutai/bin/pip -q install --upgrade pip
./.venv-kyutai/bin/pip -q install "moshi-mlx>=0.2.6" soundfile numpy
echo "✅ kyutai ready. Run: bash scripts/kyutai.sh   (first run downloads ~3GB; HF_HUB_DISABLE_XET=1 set in script)"
