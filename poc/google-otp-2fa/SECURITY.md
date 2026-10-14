# Security notes — Google OTP 2FA PoC

This document separates **design intent** from **what was actually verified** in the Cursor Agent environment.

## Authentication states

| State | Meaning |
|--------|---------|
| `PRIMARY_AUTHENTICATED` | Legacy ID/PW succeeded; `legacy_session` cookie issued |
| `MFA_PENDING` | Legacy session valid; MFA not verified for this session binding |
| `MFA_VERIFIED` | TOTP verified; MFA state bound to legacy session fingerprint |
| `LOGGED_OUT` | Legacy and MFA sessions cleared / invalidated |

State transitions:

1. `/login` → legacy validates password → `PRIMARY_AUTHENTICATED`
2. `/mfa/setup` or `/mfa/verify` → `MFA_PENDING` until valid TOTP
3. Successful TOTP → `MFA_VERIFIED` for `(username, legacy_binding)`
4. `/logout` or legacy session invalidation → `LOGGED_OUT`

## Proxy access control

Nginx is the intended public entrypoint (`nginx/nginx.conf`):

- `/dashboard` and `/api/protected` use `auth_request` to `mfa-service` `/internal/auth-check`
- Client headers such as `X-2FA-Verified` are **not** trusted; they are cleared on proxy pass
- Unauthenticated users → 302 to `/login` (HTML) or 401 JSON (API)
- Primary-authenticated but MFA incomplete → 302 to `/mfa/verify` or 403 `mfa_required`

**Verified (pytest via Python proxy harness):** MFA gate on `/dashboard` and `/api/protected`.

**Verified (static):** `docker-compose.yml` does not publish `legacy-web` or `mfa-service` host ports.

**Not verified in this environment:** Live Docker + Nginx integration (Docker daemon unavailable).

**Test-only endpoint:** When `MFA_TEST_MODE=true`, `/internal/test/totp-secret` exposes the TOTP secret for automated tests. Never enable in production.

## Binding legacy session to MFA

Legacy login code was **not** modified for MFA. The MFA service learns the authenticated user by:

1. Reading the `legacy_session` cookie from the browser request
2. Server-side call to `LEGACY_INTERNAL_URL/api/protected` with that cookie
3. Deriving `legacy_binding = HMAC(SERVICE_SHARED_SECRET, raw_session_cookie)`

MFA completion is stored in the MFA service keyed by `mfa_sid` (Flask signed session) and checked against `username` + `legacy_binding`.

### Limitations (important)

- **Network exposure:** If `legacy-web` is reachable without the proxy, ID/PW alone grants access to protected APIs. Automated test `test_direct_legacy_api_bypasses_mfa_when_exposed` demonstrates this. Production requires firewall rules or binding legacy to an internal interface only (as in Compose).
- **No cryptographic proof from legacy:** MFA infers identity from a successful `/api/protected` response. Legacy does not sign a dedicated session assertion. A minimal production hardening would be a dedicated internal session-introspection endpoint with mutual TLS or HMAC — that would be a small **non-login** change to legacy.
- **Shared secret:** `SERVICE_SHARED_SECRET` protects binding derivation; compromise allows guessing bindings if cookie values leak.

## Bypass resistance (tested)

| Threat | Mitigation | Tested |
|--------|------------|--------|
| Legacy cookie only via proxy | `auth_request` MFA check | Yes |
| Forged MFA headers | Ignored in MFA `auth-check` | Yes |
| Forged `mfa_session` cookie | Invalid signature / no verified state | Yes |
| Reuse MFA across new legacy session | New `legacy_binding` | Yes |
| OTP replay same time step | `used_totp_steps` per user+binding | Yes |
| CSRF on MFA forms | Signed CSRF token | Yes |
| OTP brute force | Failure counter + lockout | Partially (logic present; full rate-limit load not tested) |

## Secrets and storage

- TOTP secrets: in-memory `MfaStore` (PoC only; lost on restart)
- Flask `SECRET_KEY` / session cookies: environment variables
- OTP secrets are not logged; QR uses standard `otpauth://` URIs

## Production gaps

- HTTPS (`Secure` cookies), Redis/DB for MFA state, hardware/security module for secrets
- Account recovery, device management, auditing, WAF
- Mutual TLS between nginx, legacy, and MFA
- Formal threat model and penetration test
