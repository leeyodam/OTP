#!/bin/bash
# Run from dev machine (WSL): sync poc tree to demo server and run verify_all.sh
set -eu
HOST="${1:-wiki@192.168.20.107}"
SRC="$(cd "$(dirname "$0")/.." && pwd)"
TAR="/tmp/otp-poc-sync.tar.gz"
tar -czf "$TAR" -C "$SRC" \
  mfa-adapter legacy-web tests scripts privacyidea nginx \
  docker-compose.yml docker-compose.privacyidea.yml docker-compose.lan.yml \
  .env.example DESIGN_REPORT.md README.md
SCP_OPTS=(-o StrictHostKeyChecking=accept-new)
SSH_OPTS=(-o StrictHostKeyChecking=accept-new)
if [[ -n "${OTP_SSH_ASKPASS:-}" ]]; then
  export DISPLAY="${DISPLAY:-:0}" SSH_ASKPASS="$OTP_SSH_ASKPASS" SSH_ASKPASS_REQUIRE=force
  SCP_OPTS+=(-o PreferredAuthentications=password -o PubkeyAuthentication=no)
  SSH_OPTS+=(-o PreferredAuthentications=password -o PubkeyAuthentication=no)
fi
scp "${SCP_OPTS[@]}" "$TAR" "$HOST:/tmp/otp-poc-sync.tar.gz"
ssh "${SSH_OPTS[@]}" "$HOST" bash -s <<'REMOTE'
set -eu
POC=~/OTP/poc/google-otp-2fa
mkdir -p "$POC"
tar -xzf /tmp/otp-poc-sync.tar.gz -C "$POC"
chmod +x "$POC"/scripts/*.sh
export PRIVACYIDEA_E2E_URL=http://127.0.0.1:18081
cd "$POC"
./scripts/verify_all.sh
echo "==> Restart LAN demo stack..."
export LAN_PUBLISH=1 PROXY_BIND_HOST=0.0.0.0
./scripts/run_privacyidea_demo.sh
REMOTE
rm -f "$TAR"
