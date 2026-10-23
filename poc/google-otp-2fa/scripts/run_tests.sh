#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
python3 -m venv "$ROOT/.venv"
source "$ROOT/.venv/bin/activate"
pip install -q -r "$ROOT/legacy-web/requirements.txt" \
  -r "$ROOT/mfa-adapter/requirements.txt" \
  -r "$ROOT/tests/requirements.txt"
cd "$ROOT/tests"
pytest -v --tb=short --ignore=test_privacyidea_integration.py "$@"
