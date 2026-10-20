"""
privacyIDEA integration tests — run only when PRIVACYIDEA_E2E_URL is set
(e.g. after docker compose -f ... privacyidea.yml up).
"""
import os

import pytest
import requests

PI_URL = os.environ.get("PRIVACYIDEA_E2E_URL", "")
BASE = os.environ.get("PRIVACYIDEA_E2E_BASE", "http://127.0.0.1:8080")
ADMIN_USER = os.environ.get("PRIVACYIDEA_ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("PRIVACYIDEA_ADMIN_PASSWORD", "admin")

pytestmark = pytest.mark.skipif(
    not PI_URL,
    reason="Set PRIVACYIDEA_E2E_URL to run privacyIDEA integration tests",
)


def _admin_token() -> str:
    r = requests.post(
        f"{PI_URL}/auth",
        data={"username": ADMIN_USER, "password": ADMIN_PASS},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["result"]["value"]["token"]


def test_privacyidea_auth_endpoint():
    token = _admin_token()
    assert len(token) > 10


def test_privacyidea_validate_rejects_garbage_otp():
    r = requests.post(
        f"{PI_URL}/validate/check",
        data={"user": "pi_e2e_nonexistent_user", "pass": "000000"},
        timeout=15,
    )
    body = r.json()
    result = body.get("result", {})
    assert result.get("status") is False or result.get("value") is False


def test_mfa_adapter_health_reports_privacyidea():
    r = requests.get("http://127.0.0.1:5001/health", timeout=5)
    if r.status_code != 200:
        pytest.skip("mfa-adapter not exposed on host:5001")
    body = r.json()
    assert body.get("mfa_backend") == "privacyidea"
