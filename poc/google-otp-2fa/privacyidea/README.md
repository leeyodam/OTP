# privacyIDEA (open source) in this PoC

This stack uses the official Docker image **`privacyidea/privacyidea`** — not a custom MFA engine.

## Start with privacyIDEA

```bash
cd poc/google-otp-2fa
docker compose -f docker-compose.yml -f docker-compose.privacyidea.yml up --build
```

Public entry: `http://localhost:8080` (nginx only).

## First-time admin (required once)

After `privacyidea` is healthy, create an admin account (example):

```bash
docker compose -f docker-compose.yml -f docker-compose.privacyidea.yml \
  exec privacyidea pi-manage admin create admin admin
```

Set matching credentials in `.env`:

```env
PRIVACYIDEA_ADMIN_USER=admin
PRIVACYIDEA_ADMIN_PASSWORD=admin
```

Change passwords before any real environment.

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
