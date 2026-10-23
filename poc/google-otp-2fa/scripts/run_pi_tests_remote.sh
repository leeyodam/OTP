#!/bin/bash
set -eu
HOST="${1:-wiki@192.168.20.107}"
SRC="$(cd "$(dirname "$0")/.." && pwd)"
TAR="/tmp/otp-pi-sync.tar.gz"
tar -czf "$TAR" -C "$SRC" mfa-adapter tests scripts privacyidea legacy-web
ASK=/tmp/ask_otp.sh
printf '%s\n' '#!/bin/sh' 'echo fmghqht326!' > "$ASK"
chmod +x "$ASK"
export DISPLAY=:0 SSH_ASKPASS="$ASK" SSH_ASKPASS_REQUIRE=force
scp -o StrictHostKeyChecking=no -o PreferredAuthentications=password -o PubkeyAuthentication=no "$TAR" "$HOST:/tmp/otp-pi-sync.tar.gz"
ssh -o StrictHostKeyChecking=no -o PreferredAuthentications=password -o PubkeyAuthentication=no "$HOST" bash -s <<'REMOTE'
set -eu
POC=~/OTP/poc/google-otp-2fa
tar -xzf /tmp/otp-pi-sync.tar.gz -C "$POC"
chmod +x "$POC"/scripts/*.sh
cd "$POC"
./scripts/verify_privacyidea.sh
REMOTE
rm -f "$ASK" "$TAR"
