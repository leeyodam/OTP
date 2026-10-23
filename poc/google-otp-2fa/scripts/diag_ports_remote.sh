#!/bin/bash
set -eu
ASK=/tmp/ask_otp.sh
printf '%s\n' '#!/bin/sh' 'echo fmghqht326!' > "$ASK"
chmod +x "$ASK"
export DISPLAY=:0 SSH_ASKPASS="$ASK" SSH_ASKPASS_REQUIRE=force
ssh -o StrictHostKeyChecking=no -o PreferredAuthentications=password -o PubkeyAuthentication=no wiki@192.168.20.107 bash -s <<'REMOTE'
echo "=== listeners 18080 18081 5000 5001 ==="
ss -tlnp 2>/dev/null | grep -E ':18080|:18081|:5000|:5001' || true
echo "=== docker privacyidea ==="
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null | grep -i privacy || docker ps -a | grep -i privacy || true
echo "=== curl local ==="
curl -sf -m 3 http://127.0.0.1:18080/health 2>&1 || echo "18080 FAIL"
curl -sf -m 3 http://127.0.0.1:18081/  -o /dev/null -w "18081:%{http_code}\n" 2>&1 || echo "18081 FAIL"
curl -sf -m 3 http://127.0.0.1:5001/health 2>&1 || echo "5001 FAIL"
echo "=== processes ==="
pgrep -af 'proxy_harness|legacy-web|mfa-adapter|app.py' 2>/dev/null | head -10 || true
echo "=== ufw ==="
sudo ufw status 2>/dev/null | head -5 || echo "no ufw or no sudo"
REMOTE
rm -f "$ASK"
