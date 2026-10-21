# Security notes — Google OTP 2FA PoC

This document separates **design intent** from **what was actually verified**. It covers **`mfa-adapter`** with two TOTP backends: **`embedded`** (in-process PoC) and **`privacyidea`** (open-source server).

## Authentication states

| State | Meaning |
|--------|---------|
| `PRIMARY_AUTHENTICATED` | Legacy ID/PW succeeded; `legacy_session` cookie issued |
| `MFA_PENDING` | Legacy session valid; OTP not verified for this login session |
| `MFA_VERIFIED` | TOTP verified; adapter recorded completion for `(username, legacy_binding)` |
| `LOGGED_OUT` | Legacy and MFA adapter sessions cleared / invalidated |

State transitions:

1. `/login` → legacy validates password → `PRIMARY_AUTHENTICATED`
2. `/mfa/setup` or `/mfa/verify` → `MFA_PENDING` until valid TOTP
3. Successful TOTP → `MFA_VERIFIED` for `(username, legacy_binding)`
4. `/logout` or legacy session invalidation → `LOGGED_OUT`

## Components and trust boundaries

| Component | Role |
|-----------|------|
| **nginx-proxy** | Public entry; `auth_request` before protected routes |
| **legacy-web** | ID/PW only; no MFA |
| **mfa-adapter** | UI (`/mfa/*`), session binding, `/internal/auth-check`; delegates TOTP to a backend |
| **privacyIDEA** (optional) | Open-source MFA engine when `MFA_BACKEND=privacyidea` |

Legacy login code was **not** modified for MFA.

## Proxy access control

Nginx (`nginx/nginx.conf`):

- `/dashboard` and `/api/protected` use `auth_request` → **`mfa-adapter`** `/internal/auth-check`
- Client headers such as `X-2FA-Verified` are **not** trusted; cleared on proxy pass
- Unauthenticated → 302 `/login` (HTML) or 401 JSON (API)
- Primary-authenticated but MFA incomplete → 302 `/mfa/verify` or 403 `mfa_required`

**Verified (pytest + proxy harness, `MFA_BACKEND=embedded`):** MFA gate on `/dashboard` and `/api/protected`; bypass scenarios in `tests/test_bypass.py`.

**Verified (static):** `docker-compose.yml` does not publish `legacy-web`, `mfa-adapter`, or `privacyidea` host ports (only `nginx-proxy` `8080`). Overlay may publish `privacyidea` on `127.0.0.1:18081` for lab tests only.

**Verified (privacyIDEA API, when Docker available):** `tests/test_privacyidea_integration.py` with `PRIVACYIDEA_E2E_URL` — admin auth, failed validate, adapter health reports `privacyidea`.

**Partially verified:** Full Docker Compose with all services on one bridge network (some Cloud VMs have broken container-to-container networking). **Hybrid** test: privacyIDEA in Docker + adapter on host — see `scripts/run_privacyidea_cloud_test.sh`.

**Not verified everywhere:** Live Nginx + all containers on every host.

## Binding legacy session to MFA

The **adapter** (not legacy) determines the logged-in user by:

1. Reading `legacy_session` from the browser request
2. Server-side `GET LEGACY_INTERNAL_URL/api/protected` with that cookie
3. `legacy_binding = HMAC(SERVICE_SHARED_SECRET, raw_session_cookie)`

**MFA completion** (same for both backends):

- Browser: signed Flask cookie `mfa_session` containing `mfa_sid`
- Server: `mfa-adapter/storage.py` → `SessionStore.sessions[mfa_sid]` with `status == MFA_VERIFIED`, tied to `username` + `legacy_binding`

**TOTP secrets and enrollment**

| Backend | Who stores `enrolled` / TOTP secret |
|---------|-----------------------------------|
| `embedded` | `mfa-adapter/backends/embedded.py` (in-memory) |
| `privacyidea` | **privacyIDEA** DB (`/token/init`, `/validate/check`); adapter only calls API |

### Limitations (important)

- **Network exposure:** If legacy is reachable without the proxy, ID/PW alone may access protected APIs (`test_direct_legacy_api_bypasses_mfa_when_exposed`).
- **No signed session assertion from legacy:** Adapter infers user from `/api/protected`. Production should add internal session introspection + mTLS/HMAC (non-login endpoint).
- **Shared secret:** `SERVICE_SHARED_SECRET` protects binding derivation.
- **privacyIDEA image:** PoC uses third-party `gpappsoft/privacyidea-docker` for labs; not NetKnights official image. Production: build from upstream Dockerfile or supported deployment.
- **Admin API:** Adapter uses privacyIDEA admin credentials for enroll/validate — protect and scope minimally in production.

## Bypass resistance (tested)

Applies to **adapter session binding** + proxy gate. OTP checks use **embedded** or **privacyIDEA** depending on `MFA_BACKEND`.

| Threat | Mitigation | Tested (embedded harness) |
|--------|------------|---------------------------|
| Legacy cookie only via proxy | `auth_request` | Yes |
| Forged MFA headers | Ignored in `auth-check` | Yes |
| Forged `mfa_session` cookie | Invalid signature / no verified state | Yes |
| Reuse MFA across new legacy session | New `legacy_binding` | Yes |
| OTP replay (embedded) | `used_otp_steps` per user+binding | Yes |
| CSRF on MFA forms | Signed CSRF token | Yes |
| OTP brute force (embedded) | Failure counter + lockout + rate limit | Partially |

privacyIDEA mode adds privacyIDEA’s own lockout/policies when configured; not fully regression-tested in this repo.

## Secrets and storage

| Data | `embedded` | `privacyidea` |
|------|------------|---------------|
| TOTP secrets | In-memory in adapter | privacyIDEA database |
| `MFA_VERIFIED` session | `SessionStore` in adapter (RAM) | Same — still adapter RAM in PoC |
| Flask / PI secrets | Env vars | Env vars + PI admin password |

**Test-only (never production):**

- `MFA_TEST_MODE=true` — OTP hints and PoC buttons on MFA pages; `/internal/test/totp-secret` only when `MFA_BACKEND=embedded`.

## Production gaps

- HTTPS (`Secure` cookies), persistent `SessionStore`, HA privacyIDEA cluster
- Account recovery, device management, auditing, WAF
- mTLS between nginx, legacy, adapter, privacyIDEA
- Formal threat model and penetration test
- Remove PoC test accounts and demo OTP UI
