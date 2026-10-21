# privacyIDEA (open source) in this PoC

This stack runs **open-source privacyIDEA** inside Docker. The upstream project does **not** publish an official image on Docker Hub; this PoC uses **`gpappsoft/privacyidea-docker`** (third-party image bundling privacyIDEA + SQLite for lab use). For production, build from [privacyIDEA Dockerfile](https://github.com/privacyidea/privacyidea/tree/master/deploy/docker) or use vendor support.

**See also:** [README.md](../README.md) · [HANDOVER.md](../HANDOVER.md) · [SECURITY.md](../SECURITY.md)

## Start with privacyIDEA

```bash
cd poc/google-otp-2fa
./scripts/run_privacyidea_stack.sh
# or: docker compose -f docker-compose.yml -f docker-compose.privacyidea.yml up --build
```

Public entry: `http://localhost:8080` (nginx only).

`MFA_BACKEND=privacyidea` is set in the overlay. **`MFA_TEST_MODE=false`** — no PoC “test OTP” buttons on MFA pages.

## Admin credentials (first boot)

The gpappsoft image creates admin from environment variables (defaults in compose overlay):

```env
PRIVACYIDEA_ADMIN_USER=admin
PRIVACYIDEA_ADMIN_PASSWORD=admin
```

Change before any real environment. The **mfa-adapter** uses these credentials for `/token/init` and validate flows — scope and rotate in production.

## Cursor Cloud / partial Docker

Some Cloud VMs allow Docker only on the host socket (use `sudo dockerd &` first) but **container-to-container DNS may fail**. Use the hybrid script:

```bash
sudo /workspace/poc/google-otp-2fa/scripts/run_privacyidea_cloud_test.sh
```

This runs:

- **privacyIDEA in Docker** → `http://127.0.0.1:18081`
- **legacy-web + mfa-adapter + proxy on the host** with `MFA_BACKEND=privacyidea` and `PRIVACYIDEA_URL` pointing at that URL

Browser entry is typically **http://127.0.0.1:18080** (see script output).

## Automated tests

### Integration pytest (privacyIDEA API + adapter health)

Start privacyIDEA first (hybrid script or `docker compose` with PI published on `18081`), then:

```bash
cd poc/google-otp-2fa
source .venv/bin/activate   # after ./scripts/run_tests.sh once, or use your venv
export PRIVACYIDEA_E2E_URL=http://127.0.0.1:18081
pytest tests/test_privacyidea_integration.py -v
```

Expected: **3 passed** (`test_privacyidea_auth_endpoint`, validate rejection, adapter `/health` reports `privacyidea`).

`PRIVACYIDEA_E2E_URL` must be the **privacyIDEA base URL**, not nginx `:8080`.

### Full Docker E2E script

```bash
./scripts/test_privacyidea_e2e.sh
```

Requires a working Docker daemon and reliable inter-container networking.

### Main regression (no privacyIDEA required)

```bash
./scripts/run_tests.sh
```

Always uses **`MFA_BACKEND=embedded`** — **21 tests**.

## How it connects

- **`mfa-adapter`** (`MFA_BACKEND=privacyidea`) keeps the same `/mfa/setup`, `/mfa/verify`, `/internal/auth-check` URLs for nginx.
- TOTP enrollment uses privacyIDEA **`/token/init`**; validation uses **`/validate/check`**.
- Legacy ID/PW flow is unchanged.
- **`MFA_VERIFIED`** (login session bound after OTP) is still stored in the adapter **`SessionStore`**, not in privacyIDEA.

## Embedded fallback (no privacyIDEA container)

```bash
docker compose up --build
# MFA_BACKEND defaults to embedded (in-process TOTP in mfa-adapter)
```

Use this for the same behavior as `./scripts/run_tests.sh` and `./scripts/run_demo_stack.sh`.
