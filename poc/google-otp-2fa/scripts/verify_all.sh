#!/usr/bin/env bash
# Consultant / CI: embedded regression + optional privacyIDEA integration.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> Stop demo/hybrid processes on test ports (5000/5001/18080)..."
fuser -k 5000/tcp 5001/tcp 18080/tcp 2>/dev/null || true
sleep 1

echo "==> Embedded regression (pytest + proxy harness)..."
chmod +x scripts/run_tests.sh
./scripts/run_tests.sh

if [[ -n "${PRIVACYIDEA_E2E_URL:-}" ]]; then
  echo "==> privacyIDEA integration ($PRIVACYIDEA_E2E_URL)..."
  source "$ROOT/.venv/bin/activate"
  export MFA_BACKEND=privacyidea MFA_TEST_MODE=false
  export PRIVACYIDEA_URL="${PRIVACYIDEA_E2E_URL}"
  export PRIVACYIDEA_REALM="${PRIVACYIDEA_REALM:-poc}"
  export PRIVACYIDEA_ADMIN_USER="${PRIVACYIDEA_ADMIN_USER:-admin}"
  export PRIVACYIDEA_ADMIN_PASSWORD="${PRIVACYIDEA_ADMIN_PASSWORD:-admin}"
  export LEGACY_INTERNAL_URL=http://127.0.0.1:5000
  export SERVICE_SHARED_SECRET="${SERVICE_SHARED_SECRET:-test-shared-secret-for-poc}"
  export LEGACY_SECRET_KEY="${LEGACY_SECRET_KEY:-test-legacy-key}"
  export MFA_SECRET_KEY="${MFA_SECRET_KEY:-test-mfa-key}"
  mkdir -p "$ROOT/logs"
  cd "$ROOT/legacy-web" && python3 app.py >>"$ROOT/logs/verify-legacy.log" 2>&1 &
  cd "$ROOT/mfa-adapter" && python3 app.py >>"$ROOT/logs/verify-mfa.log" 2>&1 &
  export TEST_LEGACY_URL=http://127.0.0.1:5000 TEST_MFA_URL=http://127.0.0.1:5001
  export PROXY_BIND_HOST=127.0.0.1 PROXY_BIND_PORT=18080
  cd "$ROOT/tests" && python3 proxy_harness.py >>"$ROOT/logs/verify-proxy.log" 2>&1 &
  sleep 2
  export PRIVACYIDEA_E2E_BASE="${PRIVACYIDEA_E2E_BASE:-http://127.0.0.1:18080}"
  pytest tests/test_privacyidea_integration.py tests/test_privacyidea_full.py -v --tb=short
  fuser -k 5000/tcp 5001/tcp 18080/tcp 2>/dev/null || true
else
  echo "==> Skip privacyIDEA integration (set PRIVACYIDEA_E2E_URL to enable)"
fi

echo "==> All requested checks passed."
