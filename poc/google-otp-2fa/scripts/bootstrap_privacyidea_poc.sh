#!/usr/bin/env bash
# Idempotent PoC setup: passwd resolver + realm "poc" (matches legacy test accounts).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PI_URL="${PRIVACYIDEA_URL:-http://127.0.0.1:18081}"
ADMIN_USER="${PRIVACYIDEA_ADMIN_USER:-admin}"
ADMIN_PASS="${PRIVACYIDEA_ADMIN_PASSWORD:-admin}"
RESOLVER_NAME="${PRIVACYIDEA_RESOLVER:-poc_passwd}"
REALM="${PRIVACYIDEA_REALM:-poc}"
PASSWD_IN_CONTAINER="${PRIVACYIDEA_PASSWD_PATH:-/privacyidea/etc/persistent/poc-passwd}"

TOKEN=$(curl -sf "$PI_URL/auth" -d "username=$ADMIN_USER&password=$ADMIN_PASS" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['value']['token'])")

existing=$(curl -sf -H "Authorization: $TOKEN" "$PI_URL/resolver/" \
  | python3 -c "import sys,json; print('$RESOLVER_NAME' in json.load(sys.stdin).get('result',{}).get('value',{}))")

if [[ "$existing" != "True" ]]; then
  curl -sf -H "Authorization: $TOKEN" -H "Content-Type: application/json" \
    -X POST "$PI_URL/resolver/$RESOLVER_NAME" \
    -d "{\"type\":\"passwdresolver\",\"fileName\":\"$PASSWD_IN_CONTAINER\"}" >/dev/null
  echo "Created resolver $RESOLVER_NAME"
fi

realm_body=$(curl -sf -H "Authorization: $TOKEN" "$PI_URL/realm/")
has_realm=$(echo "$realm_body" | python3 -c "import sys,json; print('$REALM' in json.load(sys.stdin).get('result',{}).get('value',{}))")
if [[ "$has_realm" != "True" ]]; then
  curl -sf -H "Authorization: $TOKEN" -X POST "$PI_URL/realm/$REALM" \
    -d "resolvers=$RESOLVER_NAME" >/dev/null
  echo "Created realm $REALM"
fi

echo "privacyIDEA PoC bootstrap OK (realm=$REALM, resolver=$RESOLVER_NAME)"
