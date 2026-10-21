#!/usr/bin/env bash
# privacyIDEA integration test for Cursor Cloud / dev:
# - privacyIDEA in Docker on 127.0.0.1:18081
# - legacy + mfa-adapter + proxy harness on host (avoids broken inter-container DNS in some clouds)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if docker info >/dev/null 2>&1; then
  COMPOSE="docker compose -f $ROOT/docker-compose.yml -f $ROOT/docker-compose.privacyidea.yml"
elif sudo docker info >/dev/null 2>&1; then
  COMPOSE="sudo docker compose -f $ROOT/docker-compose.yml -f $ROOT/docker-compose.privacyidea.yml"
else
  echo "Docker daemon not available. Start dockerd or use a host with Docker."
  exit 1
fi

echo "==> privacyIDEA container only..."
$COMPOSE up -d privacyidea

echo "==> Waiting for privacyIDEA on :18081..."
for i in $(seq 1 40); do
  if curl -sf http://127.0.0.1:18081/auth -d 'username=admin&password=admin' >/dev/null 2>&1; then break; fi
  sleep 3
done

export MFA_BACKEND=privacyidea
export PRIVACYIDEA_URL=http://127.0.0.1:18081
export PRIVACYIDEA_REALM="${PRIVACYIDEA_REALM:-poc}"
"$ROOT/scripts/bootstrap_privacyidea_poc.sh"
export PRIVACYIDEA_ADMIN_USER=admin
export PRIVACYIDEA_ADMIN_PASSWORD=admin
export LEGACY_INTERNAL_URL=http://127.0.0.1:5000
export SERVICE_SHARED_SECRET="${SERVICE_SHARED_SECRET:-demo-shared-secret}"

fuser -k 5000/tcp 5001/tcp 18080/tcp 2>/dev/null || true
sleep 1

mkdir -p "$ROOT/logs"
if [[ ! -x "$ROOT/.venv/bin/python3" ]]; then
  python3 -m venv "$ROOT/.venv"
  "$ROOT/.venv/bin/pip" install -q -r "$ROOT/legacy-web/requirements.txt" \
    -r "$ROOT/mfa-adapter/requirements.txt" \
    -r "$ROOT/tests/requirements.txt"
fi
PY="$ROOT/.venv/bin/python3"

cd "$ROOT/legacy-web" && $PY app.py >>"$ROOT/logs/legacy-pi.log" 2>&1 &
cd "$ROOT/mfa-adapter" && MFA_TEST_MODE=false $PY app.py >>"$ROOT/logs/mfa-pi.log" 2>&1 &
cd "$ROOT/tests" && TEST_LEGACY_URL=http://127.0.0.1:5000 TEST_MFA_URL=http://127.0.0.1:5001 \
  $PY proxy_harness.py >>"$ROOT/logs/proxy-pi.log" 2>&1 &

sleep 3
curl -sf http://127.0.0.1:5001/health | grep -q privacyidea

export PRIVACYIDEA_E2E_URL=http://127.0.0.1:18081
python3 -m pytest "$ROOT/tests/test_privacyidea_integration.py" -v

J=$(mktemp)
curl -sf -c "$J" -b "$J" -X POST http://127.0.0.1:18080/login \
  -d "username=testuser&password=TestPassword123!" -o /dev/null
HTML=$(curl -sf -b "$J" http://127.0.0.1:18080/mfa/setup)
echo "$HTML" | grep -q "Backend: privacyidea" && echo "OK: /mfa/setup uses privacyIDEA backend"

echo ""
echo "Manual: open http://127.0.0.1:18080/login — enroll TOTP (QR), then /dashboard"
echo "Stop: fuser -k 5000/tcp 5001/tcp 18080/tcp; $COMPOSE stop privacyidea"
