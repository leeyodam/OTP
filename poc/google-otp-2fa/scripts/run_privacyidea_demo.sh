#!/usr/bin/env bash
# Interactive demo: privacyIDEA (Docker) + real Google Authenticator — no PoC OTP buttons.
# Host runs legacy + mfa-adapter + proxy on http://127.0.0.1:18080 (hybrid; reliable in Cloud Agent).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if docker info >/dev/null 2>&1; then
  COMPOSE="docker compose -f $ROOT/docker-compose.yml -f $ROOT/docker-compose.privacyidea.yml"
elif sudo docker info >/dev/null 2>&1; then
  COMPOSE="sudo docker compose -f $ROOT/docker-compose.yml -f $ROOT/docker-compose.privacyidea.yml"
else
  echo "Docker required for privacyIDEA. Start dockerd first."
  exit 1
fi

mkdir -p "$ROOT/logs"

echo "==> privacyIDEA (Docker, 127.0.0.1:18081)..."
$COMPOSE up -d privacyidea

echo "==> Waiting for privacyIDEA admin auth..."
for i in $(seq 1 40); do
  if curl -sf http://127.0.0.1:18081/auth -d 'username=admin&password=admin' >/dev/null 2>&1; then
    break
  fi
  sleep 3
done
curl -sf http://127.0.0.1:18081/auth -d 'username=admin&password=admin' >/dev/null || {
  echo "privacyIDEA not ready on :18081"
  exit 1
}

export PRIVACYIDEA_URL=http://127.0.0.1:18081
export PRIVACYIDEA_REALM="${PRIVACYIDEA_REALM:-poc}"
"$ROOT/scripts/bootstrap_privacyidea_poc.sh"

if [[ ! -x "$ROOT/.venv/bin/python3" ]]; then
  python3 -m venv "$ROOT/.venv"
  "$ROOT/.venv/bin/pip" install -q -r "$ROOT/legacy-web/requirements.txt" \
    -r "$ROOT/mfa-adapter/requirements.txt" \
    -r "$ROOT/tests/requirements.txt"
fi
PY="$ROOT/.venv/bin/python3"

fuser -k 5000/tcp 5001/tcp 18080/tcp 2>/dev/null || true
sleep 1

export MFA_BACKEND=privacyidea
export MFA_TEST_MODE=false
export PRIVACYIDEA_URL=http://127.0.0.1:18081
export PRIVACYIDEA_REALM="${PRIVACYIDEA_REALM:-poc}"
export PRIVACYIDEA_ADMIN_USER="${PRIVACYIDEA_ADMIN_USER:-admin}"
export PRIVACYIDEA_ADMIN_PASSWORD="${PRIVACYIDEA_ADMIN_PASSWORD:-admin}"
export LEGACY_INTERNAL_URL=http://127.0.0.1:5000
export SERVICE_SHARED_SECRET="${SERVICE_SHARED_SECRET:-demo-shared-secret}"
export LEGACY_SECRET_KEY="${LEGACY_SECRET_KEY:-demo-legacy-key}"
export MFA_SECRET_KEY="${MFA_SECRET_KEY:-demo-mfa-key}"

echo "==> legacy-web :5000, mfa-adapter :5001, proxy :18080..."
cd "$ROOT/legacy-web" && $PY app.py >>"$ROOT/logs/legacy-pi.log" 2>&1 &
cd "$ROOT/mfa-adapter" && $PY app.py >>"$ROOT/logs/mfa-pi.log" 2>&1 &
cd "$ROOT/tests" && TEST_LEGACY_URL=http://127.0.0.1:5000 TEST_MFA_URL=http://127.0.0.1:5001 \
  $PY proxy_harness.py >>"$ROOT/logs/proxy-pi.log" 2>&1 &

for i in $(seq 1 40); do
  if curl -sf http://127.0.0.1:18080/health >/dev/null && \
     curl -sf http://127.0.0.1:5001/health | grep -q privacyidea; then
    break
  fi
  sleep 0.5
done

curl -sf http://127.0.0.1:5001/health | grep -q privacyidea || {
  echo "mfa-adapter failed; see $ROOT/logs/mfa-pi.log"
  exit 1
}

echo ""
echo "=============================================="
echo " privacyIDEA + Google Authenticator demo ready"
echo "=============================================="
echo " URL:    http://127.0.0.1:18080/login"
echo " Account: testuser / TestPassword123!  (or test1..test5 / test1!..test5!)"
echo " MFA:    Scan QR on /mfa/setup with Google Authenticator, enter 6-digit code"
echo " Logs:   $ROOT/logs/legacy-pi.log mfa-pi.log proxy-pi.log"
echo " Stop:   fuser -k 5000/tcp 5001/tcp 18080/tcp; $COMPOSE stop privacyidea"
echo "=============================================="
