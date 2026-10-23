"""
privacyIDEA feature coverage for this PoC (requires live PI + optional proxy).

Set PRIVACYIDEA_E2E_URL (e.g. http://127.0.0.1:18081).
For end-to-end via mfa-adapter + proxy, also set PRIVACYIDEA_E2E_BASE (e.g. http://127.0.0.1:18080)
and ensure legacy + mfa-adapter + proxy are running with MFA_BACKEND=privacyidea.
"""
import os
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pyotp
import pytest
import requests

PI_URL = os.environ.get("PRIVACYIDEA_E2E_URL", "")
PROXY_BASE = os.environ.get("PRIVACYIDEA_E2E_BASE", "")
ADMIN_USER = os.environ.get("PRIVACYIDEA_ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("PRIVACYIDEA_ADMIN_PASSWORD", "admin")
REALM = os.environ.get("PRIVACYIDEA_REALM", "poc")
E2E_USER = os.environ.get("PRIVACYIDEA_E2E_USER", "testuser")
E2E_PASS = os.environ.get("PRIVACYIDEA_E2E_PASSWORD", "TestPassword123!")
OTHER_USER = os.environ.get("PRIVACYIDEA_E2E_OTHER_USER", "test2")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mfa-adapter"))
from privacyidea_client import PrivacyIDEAClient  # noqa: E402

pytestmark = pytest.mark.skipif(not PI_URL, reason="Set PRIVACYIDEA_E2E_URL")


def _admin_token() -> str:
    r = requests.post(
        f"{PI_URL}/auth",
        data={"username": ADMIN_USER, "password": ADMIN_PASS},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["result"]["value"]["token"]


def _list_totp(username: str, admin_tok: str) -> list:
    r = requests.get(
        f"{PI_URL}/token/",
        headers={"Authorization": admin_tok},
        params={"user": username, "tokentype": "totp", "realm": REALM},
        timeout=15,
    )
    r.raise_for_status()
    return r.json().get("result", {}).get("value", {}).get("tokens", [])


def _delete_user_totp(username: str, admin_tok: str) -> None:
    for tok in _list_totp(username, admin_tok):
        serial = tok.get("serial")
        if serial:
            requests.delete(
                f"{PI_URL}/token/{serial}",
                headers={"Authorization": admin_tok},
                timeout=15,
            )


def _secret_from_enroll_detail(detail: dict) -> str:
    raw = detail.get("googleurl")
    if isinstance(raw, dict):
        url = raw.get("value") or ""
    elif isinstance(raw, str):
        url = raw
    else:
        url = detail.get("otpkey", {}).get("url") or ""
    if not url:
        raise ValueError(f"no otpauth url in {detail}")
    if "secret=" in url:
        return parse_qs(urlparse(url).query)["secret"][0]
    m = re.search(r"secret=([A-Z2-7]+)", url, re.I)
    assert m, url
    return m.group(1)


def test_pi_realm_and_resolver_exist():
    tok = _admin_token()
    realms = requests.get(
        f"{PI_URL}/realm/", headers={"Authorization": tok}, timeout=15
    ).json()
    assert REALM in realms.get("result", {}).get("value", {})
    resolvers = requests.get(
        f"{PI_URL}/resolver/", headers={"Authorization": tok}, timeout=15
    ).json()
    assert "poc_passwd" in resolvers.get("result", {}).get("value", {})


def test_pi_token_enroll_validate_delete_lifecycle():
    admin = _admin_token()
    _delete_user_totp(E2E_USER, admin)
    client = PrivacyIDEAClient(PI_URL, ADMIN_USER, ADMIN_PASS, realm=REALM)
    assert client.user_has_totp(E2E_USER) is False
    detail = client.enroll_totp(E2E_USER)
    assert client.user_has_totp(E2E_USER) is True
    secret = _secret_from_enroll_detail(detail)
    good = pyotp.TOTP(secret).now()
    assert client.validate_user_otp(E2E_USER, good) is True
    assert client.validate_user_otp(E2E_USER, "000000") is False
    _delete_user_totp(E2E_USER, admin)
    assert client.user_has_totp(E2E_USER) is False


def test_pi_per_user_token_isolation():
    admin = _admin_token()
    _delete_user_totp(E2E_USER, admin)
    _delete_user_totp(OTHER_USER, admin)
    client = PrivacyIDEAClient(PI_URL, ADMIN_USER, ADMIN_PASS, realm=REALM)
    client.enroll_totp(E2E_USER)
    assert client.user_has_totp(E2E_USER) is True
    assert client.user_has_totp(OTHER_USER) is False
    _delete_user_totp(E2E_USER, admin)


def test_pi_validate_check_public_endpoint():
    r = requests.post(
        f"{PI_URL}/validate/check",
        data={"user": "no_such_pi_user", "pass": "000000", "realm": REALM},
        timeout=15,
    )
    body = r.json()
    result = body.get("result", {})
    assert result.get("status") is False
    assert result.get("value") is not True


def test_mfa_adapter_backend_enroll_and_verify():
    """PrivacyIDEABackend used by mfa-adapter (same code path as /mfa/setup)."""
    from backends.privacyidea_backend import PrivacyIDEABackend

    admin = _admin_token()
    _delete_user_totp(E2E_USER, admin)
    backend = PrivacyIDEABackend(PI_URL, ADMIN_USER, ADMIN_PASS, realm=REALM)
    assert backend.is_enrolled(E2E_USER) is False
    backend.provisioning_qr_b64(E2E_USER)
    assert backend.is_enrolled(E2E_USER) is True
    assert _list_totp(E2E_USER, admin)
    _delete_user_totp(E2E_USER, admin)


@pytest.mark.skipif(not PROXY_BASE, reason="Set PRIVACYIDEA_E2E_BASE for proxy E2E")
def test_proxy_login_mfa_verify_dashboard_refresh():
    admin = _admin_token()
    _delete_user_totp(E2E_USER, admin)
    client = PrivacyIDEAClient(PI_URL, ADMIN_USER, ADMIN_PASS, realm=REALM)
    detail = client.enroll_totp(E2E_USER)
    secret = _secret_from_enroll_detail(detail)
    otp = pyotp.TOTP(secret).now()

    s = requests.Session()
    r = s.post(
        f"{PROXY_BASE}/login",
        data={"username": E2E_USER, "password": E2E_PASS},
        allow_redirects=False,
    )
    assert r.status_code in (302, 303)
    r = s.get(f"{PROXY_BASE}/mfa/verify", allow_redirects=True)
    assert r.status_code == 200
    assert "Two-factor verification" in r.text or "Verify" in r.text
    m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    assert m
    r2 = s.post(
        f"{PROXY_BASE}/mfa/verify",
        data={"csrf_token": m.group(1), "otp": otp},
        allow_redirects=False,
    )
    assert r2.status_code in (302, 303)
    assert s.get(f"{PROXY_BASE}/dashboard").status_code == 200
    assert s.get(f"{PROXY_BASE}/dashboard").status_code == 200
    assert s.get(f"{PROXY_BASE}/api/protected").status_code == 200
    assert s.get(f"{PROXY_BASE}/api/protected", allow_redirects=False).status_code == 200
    _delete_user_totp(E2E_USER, admin)


@pytest.mark.skipif(not PROXY_BASE, reason="Set PRIVACYIDEA_E2E_BASE for proxy E2E")
def test_proxy_setup_enroll_flow_when_not_enrolled():
    admin = _admin_token()
    _delete_user_totp(E2E_USER, admin)
    s = requests.Session()
    s.post(
        f"{PROXY_BASE}/login",
        data={"username": E2E_USER, "password": E2E_PASS},
        allow_redirects=False,
    )
    r = s.get(f"{PROXY_BASE}/mfa/setup", allow_redirects=True)
    assert r.status_code == 200
    assert "Register Google Authenticator" in r.text
    client = PrivacyIDEAClient(PI_URL, ADMIN_USER, ADMIN_PASS, realm=REALM)
    assert client.user_has_totp(E2E_USER) is True
    _delete_user_totp(E2E_USER, admin)
