# Google OTP 2FA PoC

레거시(ID/PW) + **mfa-adapter** + **privacyIDEA** + 리버스 프록시 PoC.

**설계·컨설팅 보고 (통합):** [DESIGN_REPORT.md](DESIGN_REPORT.md)

```bash
# privacyIDEA LAN 시연
LAN_PUBLISH=1 PROXY_BIND_HOST=0.0.0.0 ./scripts/run_privacyidea_demo.sh
# 검증
PRIVACYIDEA_E2E_URL=http://127.0.0.1:18081 ./scripts/verify_all.sh
```
