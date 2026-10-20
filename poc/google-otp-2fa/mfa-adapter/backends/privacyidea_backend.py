"""privacyIDEA-backed TOTP (open-source MFA server)."""
import base64
import io
import logging
from typing import Optional

import qrcode
import requests

from backends.base import MfaBackend
from privacyidea_client import PrivacyIDEAClient, PrivacyIDEAError

log = logging.getLogger(__name__)


class PrivacyIDEABackend(MfaBackend):
    def __init__(
        self,
        base_url: str,
        admin_user: str,
        admin_password: str,
        realm: str = "",
        totp_pin: str = "",
    ) -> None:
        self._client = PrivacyIDEAClient(
            base_url, admin_user, admin_password, realm=realm, totp_pin=totp_pin
        )
        self._qr_cache: dict[str, str] = {}

    def is_enrolled(self, username: str) -> bool:
        try:
            return self._client.user_has_totp(username)
        except (requests.RequestException, PrivacyIDEAError) as exc:
            log.warning("privacyIDEA is_enrolled failed: %s", exc)
            return False

    def provisioning_qr_b64(self, username: str) -> str:
        if username in self._qr_cache:
            return self._qr_cache[username]
        detail = self._client.enroll_totp(username)
        googleurl = detail.get("googleurl") or detail.get("otpkey", {}).get("url")
        if not googleurl:
            raise PrivacyIDEAError(f"no googleurl in enroll response: {detail}")
        img = qrcode.make(googleurl)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        self._qr_cache[username] = b64
        return b64

    def verify_otp(self, username: str, otp: str, *, enroll_step: bool = False) -> bool:
        try:
            return self._client.validate_user_otp(username, otp)
        except (requests.RequestException, PrivacyIDEAError) as exc:
            log.warning("privacyIDEA validate failed: %s", exc)
            return False
