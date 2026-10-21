# OTP

Google Authenticator TOTP 2FA proof of concept:

- **Legacy** ID/PW only (`legacy-web/`)
- **MFA gateway** (`mfa-adapter/`) — TOTP via **`embedded`** (tests/demo) or **[privacyIDEA](https://github.com/privacyidea/privacyidea)** (open source)
- **Nginx** reverse proxy with `auth_request` on protected routes

Full documentation: **[poc/google-otp-2fa/README.md](poc/google-otp-2fa/README.md)**

| Doc | Purpose |
|-----|---------|
| [HANDOVER.md](poc/google-otp-2fa/HANDOVER.md) | 운영 인수인계 |
| [SECURITY.md](poc/google-otp-2fa/SECURITY.md) | 보안·검증 범위 |
| [TEST_ACCOUNTS.md](poc/google-otp-2fa/TEST_ACCOUNTS.md) | PoC 계정 |
| [privacyidea/README.md](poc/google-otp-2fa/privacyidea/README.md) | privacyIDEA 연동 |
