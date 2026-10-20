# privacyIDEA (open source) in this PoC

This stack runs **open-source privacyIDEA** inside Docker. The upstream project does **not** publish an official image on Docker Hub; this PoC uses **`gpappsoft/privacyidea-docker`** (third-party image bundling privacyIDEA + SQLite for lab use). For production, build from [privacyIDEA Dockerfile](https://github.com/privacyidea/privacyidea/tree/master/deploy/docker) or use vendor support.

## Start with privacyIDEA

```bash
cd poc/google-otp-2fa
./scripts/run_privacyidea_stack.sh
# or: docker compose -f docker-compose.yml -f docker-compose.privacyidea.yml up --build
```

Public entry: `http://localhost:8080` (nginx only).

## Admin credentials (first boot)

The gpappsoft image creates admin from environment variables (defaults in compose overlay):

```env
PRIVACYIDEA_ADMIN_USER=admin
PRIVACYIDEA_ADMIN_PASSWORD=admin
```

Change before any real environment.

## Cursor Cloud / partial Docker

Some Cloud VMs allow Docker only on the host socket (use `sudo dockerd` first) but **container-to-container DNS may fail**. Use the hybrid script:

```bash
sudo /workspace/poc/google-otp-2fa/scripts/run_privacyidea_cloud_test.sh
```

This runs **privacyIDEA in Docker** (`127.0.0.1:18081`) and **legacy + mfa-adapter + proxy on the host** with `MFA_BACKEND=privacyidea`.

## Automated E2E (full Docker required)

```bash
./scripts/test_privacyidea_e2e.sh
```

Integration pytest (privacyIDEA API + adapter health):

```bash
export PRIVACYIDEA_E2E_URL=http://127.0.0.1:8080  # if PI port published; else internal URL via docker network
# With adapter published on host during dev:
export PRIVACYIDEA_E2E_URL=http://localhost:<pi-port>
pytest tests/test_privacyidea_integration.py -v
```

## How it connects

- **`mfa-adapter`** (`MFA_BACKEND=privacyidea`) keeps the same `/mfa/setup`, `/mfa/verify`, `/internal/auth-check` URLs for nginx.
- TOTP enrollment uses privacyIDEA **`/token/init`**; validation uses **`/validate/check`**.
- Legacy ID/PW flow is unchanged.

## Embedded fallback (no privacyIDEA container)

```bash
docker compose up --build
# MFA_BACKEND defaults to embedded (original PoC TOTP in adapter)
```

pytest always uses `MFA_BACKEND=embedded`.
