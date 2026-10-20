# Deprecated

The standalone `mfa-service` was replaced by **`mfa-adapter/`**, which supports:

- `MFA_BACKEND=embedded` — original in-process TOTP (tests, local demo)
- `MFA_BACKEND=privacyidea` — [privacyIDEA](https://github.com/privacyidea/privacyidea) open-source MFA server

Docker Compose and nginx now use `mfa-adapter`. This directory is kept for reference only.
