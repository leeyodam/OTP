#!/usr/bin/env bash
# Start legacy + MFA + proxy harness for interactive browser testing (no Docker).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export SERVICE_SHARED_SECRET="${SERVICE_SHARED_SECRET:-demo-shared-secret}"
export LEGACY_SECRET_KEY="${LEGACY_SECRET_KEY:-demo-legacy-key}"
export MFA_SECRET_KEY="${MFA_SECRET_KEY:-demo-mfa-key}"
export LEGACY_INTERNAL_URL="http://127.0.0.1:5000"
export LEGACY_TEST_USER="${LEGACY_TEST_USER:-testuser}"
export LEGACY_TEST_PASSWORD="${LEGACY_TEST_PASSWORD:-TestPassword123!}"
export MFA_TEST_MODE="${MFA_TEST_MODE:-true}"
export MFA_BACKEND="${MFA_BACKEND:-embedded}"

if [[ ! -x "$ROOT/.venv/bin/python3" ]]; then
  python3 -m venv "$ROOT/.venv"
  "$ROOT/.venv/bin/pip" install -q -r "$ROOT/legacy-web/requirements.txt" \
    -r "$ROOT/mfa-service/requirements.txt" \
    -r "$ROOT/tests/requirements.txt"
fi
PY="$ROOT/.venv/bin/python3"

for port in 5000 5001 18080; do
  if curl -sf "http://127.0.0.1:${port}/health" >/dev/null 2>&1; then
    echo "Port $port already serving /health — skipping start for that service"
  fi
done

start_if_down() {
  local url="$1"
  local name="$2"
  local cmd="$3"
  if curl -sf "$url" >/dev/null 2>&1; then
    echo "$name already up ($url)"
    return
  fi
  echo "Starting $name..."
  eval "$cmd"
}

start_if_down "http://127.0.0.1:5000/health" "legacy-web" \
  "cd '$ROOT/legacy-web' && $PY app.py >> /tmp/legacy-web.log 2>&1 &"
sleep 0.5
start_if_down "http://127.0.0.1:5001/health" "mfa-service" \
  "cd '$ROOT/mfa-service' && $PY app.py >> /tmp/mfa-service.log 2>&1 &"
sleep 0.5
start_if_down "http://127.0.0.1:18080/health" "proxy" \
  "cd '$ROOT/tests' && TEST_LEGACY_URL=http://127.0.0.1:5000 TEST_MFA_URL=http://127.0.0.1:5001 $PY proxy_harness.py >> /tmp/proxy.log 2>&1 &"

for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:18080/health >/dev/null; then
    echo ""
    echo "=== Demo ready ==="
    echo "Open in browser: http://127.0.0.1:18080/login"
    echo "Accounts: testuser / TestPassword123!  |  test1..test5 / test1! .. test5!"
    echo "Logs: /tmp/legacy-web.log /tmp/mfa-service.log /tmp/proxy.log"
    exit 0
  fi
  sleep 0.3
done
echo "Stack failed to become ready; check logs in /tmp/*.log"
exit 1
