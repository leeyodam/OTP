#!/bin/bash
ASK=/tmp/ask_otp.sh
printf '%s\n' '#!/bin/sh' 'echo fmghqht326!' > "$ASK"
chmod +x "$ASK"
export DISPLAY=:0 SSH_ASKPASS="$ASK" SSH_ASKPASS_REQUIRE=force
ssh -o StrictHostKeyChecking=no -o PreferredAuthentications=password -o PubkeyAuthentication=no wiki@192.168.20.107 "tail -40 ~/OTP/poc/google-otp-2fa/logs/pi-test-mfa.log 2>/dev/null; tail -20 ~/OTP/poc/google-otp-2fa/logs/pi-test-proxy.log 2>/dev/null"
rm -f "$ASK"
