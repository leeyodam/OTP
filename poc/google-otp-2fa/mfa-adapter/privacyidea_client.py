"""Minimal privacyIDEA REST client for TOTP enroll + validate/check."""
import logging
from typing import Any, Dict, Optional

import requests

log = logging.getLogger(__name__)


class PrivacyIDEAError(Exception):
    pass


class PrivacyIDEAClient:
    def __init__(
        self,
        base_url: str,
        admin_user: str,
        admin_password: str,
        realm: str = "",
        totp_pin: str = "",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.realm = realm
        self.totp_pin = totp_pin
        self._admin_token: Optional[str] = None
        self._authenticate_admin(admin_user, admin_password)

    def _authenticate_admin(self, username: str, password: str) -> None:
        resp = requests.post(
            f"{self.base_url}/auth",
            data={"username": username, "password": password},
            timeout=15,
        )
        resp.raise_for_status()
        body = resp.json()
        if not body.get("result", {}).get("status"):
            raise PrivacyIDEAError(f"admin auth failed: {body}")
        self._admin_token = body.get("result", {}).get("value", {}).get("token")
        if not self._admin_token:
            raise PrivacyIDEAError("admin auth missing token")

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": self._admin_token or ""}

    def ensure_user(self, username: str) -> None:
        params: Dict[str, Any] = {"username": username}
        if self.realm:
            params["realm"] = self.realm
        resp = requests.post(
            f"{self.base_url}/user/",
            params=params,
            headers=self._headers(),
            timeout=15,
        )
        if resp.status_code == 200:
            return
        body = resp.json()
        # already exists
        if body.get("result", {}).get("error", {}).get("code") == 303:
            return
        if not body.get("result", {}).get("status"):
            raise PrivacyIDEAError(f"create user failed: {body}")

    def user_has_totp(self, username: str) -> bool:
        params = {"username": username, "tokentype": "totp"}
        if self.realm:
            params["realm"] = self.realm
        resp = requests.get(
            f"{self.base_url}/token/",
            params=params,
            headers=self._headers(),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        tokens = data.get("result", {}).get("value", {}).get("tokens", [])
        return len(tokens) > 0

    def enroll_totp(self, username: str) -> Dict[str, Any]:
        self.ensure_user(username)
        data = {"user": username, "type": "totp", "genkey": "1"}
        if self.realm:
            data["realm"] = self.realm
        resp = requests.post(
            f"{self.base_url}/token/init",
            data=data,
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        if not body.get("result", {}).get("status"):
            raise PrivacyIDEAError(f"token init failed: {body}")
        return body.get("detail", {})

    def validate_user_otp(self, username: str, otp: str) -> bool:
        data = {"user": username, "pass": f"{self.totp_pin}{otp}"}
        if self.realm:
            data["realm"] = self.realm
        resp = requests.post(
            f"{self.base_url}/validate/check",
            data=data,
            timeout=15,
        )
        resp.raise_for_status()
        body = resp.json()
        return bool(body.get("result", {}).get("value"))
