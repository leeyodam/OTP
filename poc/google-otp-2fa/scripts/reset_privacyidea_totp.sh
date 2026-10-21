#!/usr/bin/env bash
# Remove all TOTP tokens for a PoC user so /mfa/setup shows a fresh QR (demo only).
set -euo pipefail
USER="${1:?usage: reset_privacyidea_totp.sh <username>}"
PI_URL="${PRIVACYIDEA_URL:-http://127.0.0.1:18081}"
REALM="${PRIVACYIDEA_REALM:-poc}"
ADMIN_USER="${PRIVACYIDEA_ADMIN_USER:-admin}"
ADMIN_PASS="${PRIVACYIDEA_ADMIN_PASSWORD:-admin}"

TOKEN=$(curl -sf "$PI_URL/auth" -d "username=$ADMIN_USER&password=$ADMIN_PASS" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['value']['token'])")

serial_list=$(curl -sf -H "Authorization: $TOKEN" \
  "$PI_URL/token/?username=$USER&realm=$REALM" \
  | python3 -c "import sys,json; print(' '.join(t['serial'] for t in json.load(sys.stdin)['result']['value']['tokens']))")

for serial in $serial_list; do
  curl -sf -H "Authorization: $TOKEN" -X DELETE "$PI_URL/token/$serial" >/dev/null
  echo "Deleted token $serial for $USER@$REALM"
done

if [[ -z "$serial_list" ]]; then
  echo "No TOTP tokens for $USER@$REALM"
fi
