#!/usr/bin/env bash
# E2E: legacy login + privacyIDEA-backed MFA via nginx (requires Docker).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.privacyidea.yml"
BASE="${BASE_URL:-http://127.0.0.1:8080}"

echo "==> Starting stack (privacyIDEA overlay)..."
$COMPOSE up -d --build

echo "==> Waiting for nginx..."
for i in $(seq 1 60); do
  if curl -sf "$BASE/health" >/dev/null; then break; fi
  sleep 2
done
curl -sf "$BASE/health" >/dev/null || { echo "nginx not ready"; $COMPOSE logs; exit 1; }

echo "==> Waiting for mfa-adapter (privacyidea backend)..."
for i in $(seq 1 60); do
  if curl -sf http://127.0.0.1:8080/login >/dev/null 2>&1; then break; fi
  sleep 2
done

# Login via published nginx (use host network curl to 8080)
COOKIE_JAR="$(mktemp)"
echo "==> Legacy login (testuser)..."
curl -sf -c "$COOKIE_JAR" -b "$COOKIE_JAR" -X POST "$BASE/login" \
  -d "username=testuser&password=TestPassword123!" -o /dev/null -w "%{http_code}\n" | grep -q 30

echo "==> MFA setup page (privacyIDEA enroll)..."
SETUP_HTML=$(curl -sf -b "$COOKIE_JAR" -c "$COOKIE_JAR" "$BASE/mfa/setup" || true)
if echo "$SETUP_HTML" | grep -q "Backend: privacyidea"; then
  echo "OK: mfa-adapter reports privacyidea backend"
else
  echo "WARN: expected privacyidea backend on setup page"
fi

echo "==> Check protected API blocked before MFA..."
CODE=$(curl -s -o /dev/null -w "%{http_code}" -b "$COOKIE_JAR" "$BASE/api/protected")
if [[ "$CODE" == "403" ]]; then
  echo "OK: API returns 403 before MFA"
else
  echo "FAIL: expected 403, got $CODE"; exit 1
fi

echo ""
echo "Manual step: open $BASE/login in a browser, complete MFA enrollment with Google Authenticator"
echo "              (privacyIDEA stores the token; PoC test OTP buttons are disabled)."
echo ""
echo "Stack is running. Stop with: $COMPOSE down"
