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
        self._admin_user = admin_user
        self._admin_password = admin_password
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

    def _auth_failed(self, body: Dict[str, Any]) -> bool:
        err = body.get("result", {}).get("error", {})
        if err.get("code") == 4304:
            return True
        msg = str(err.get("message", ""))
        return "Authorization token" in msg or "Signature verification" in msg

    def _refresh_admin_token(self) -> None:
        # privacyIDEA JWT expires; also invalid after container recreate.
        self._authenticate_admin(self._admin_user, self._admin_password)

    def _admin_request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = f"{self.base_url}{path}"
        timeout = kwargs.pop("timeout", 15)
        for attempt in range(2):
            resp = requests.request(
                method, url, headers=self._headers(), timeout=timeout, **kwargs
            )
            if resp.status_code == 401:
                self._refresh_admin_token()
                continue
            try:
                body = resp.json()
            except ValueError:
                return resp
            if self._auth_failed(body):
                self._refresh_admin_token()
                continue
            return resp
        return resp

    def user_has_totp(self, username: str) -> bool:
        # privacyIDEA filters by "user", not "username" (wrong param returns unrelated tokens).
        params = {"user": username, "tokentype": "totp"}
        if self.realm:
            params["realm"] = self.realm
        resp = self._admin_request("GET", "/token/", params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        tokens = data.get("result", {}).get("value", {}).get("tokens", [])
        return any(
            (t.get("username") or t.get("user") or "") == username for t in tokens
        )

    def enroll_totp(self, username: str) -> Dict[str, Any]:
        # Users come from the configured realm resolver (e.g. passwd file).
        data = {"user": username, "type": "totp", "genkey": "1"}
        if self.realm:
            data["realm"] = self.realm
        resp = self._admin_request("POST", "/token/init", data=data, timeout=30)
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
