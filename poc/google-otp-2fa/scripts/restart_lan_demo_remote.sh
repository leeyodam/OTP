#!/bin/bash
set -eu
ASK=/tmp/ask_otp.sh
printf '%s\n' '#!/bin/sh' 'echo fmghqht326!' > "$ASK"
chmod +x "$ASK"
export DISPLAY=:0 SSH_ASKPASS="$ASK" SSH_ASKPASS_REQUIRE=force
ssh -o StrictHostKeyChecking=no -o PreferredAuthentications=password -o PubkeyAuthentication=no wiki@192.168.20.107 bash -s <<'REMOTE'
set -eu
POC=~/OTP/poc/google-otp-2fa
cd "$POC"
# Publish privacyIDEA on all interfaces (hybrid demo)
sed -i 's|127.0.0.1:18081:8080|0.0.0.0:18081:8080|' docker-compose.privacyidea.yml 2>/dev/null || true
grep -q '0.0.0.0:18081' docker-compose.privacyidea.yml || sed -i 's|"18081:8080"|"0.0.0.0:18081:8080"|' docker-compose.privacyidea.yml
fuser -k 5000/tcp 5001/tcp 18080/tcp 2>/dev/null || true
sleep 1
export LAN_PUBLISH=1
export PROXY_BIND_HOST=0.0.0.0
./scripts/run_privacyidea_demo.sh
echo "=== listen check ==="
ss -tlnp | grep -E '18080|18081' || true
REMOTE
rm -f "$ASK"
