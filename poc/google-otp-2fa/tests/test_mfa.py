import pyotp
import requests

from utils import enroll_and_verify_mfa, extract_csrf, login


def test_mfa_success_allows_dashboard_and_api(base_url, creds):
    s = requests.Session()
    login(s, base_url, creds["user"], creds["password"])
    enroll_and_verify_mfa(s, base_url, creds["user"])
    dash = s.get(f"{base_url}/dashboard")
    assert dash.status_code == 200
    assert "Protected Dashboard" in dash.text
    api = s.get(f"{base_url}/api/protected")
    assert api.status_code == 200
    assert api.json().get("user") == creds["user"]


def test_invalid_otp_rejected(base_url, creds):
    s = requests.Session()
    login(s, base_url, creds["user"], creds["password"])
    r = s.get(f"{base_url}/mfa/setup")
    csrf = extract_csrf(r.text)
    r2 = s.post(
        f"{base_url}/mfa/verify" if "/verify" in r.url else f"{base_url}/mfa/setup",
        data={"csrf_token": csrf, "otp": "000000"},
        allow_redirects=True,
    )
    assert r2.status_code == 400 or "Invalid OTP" in r2.text


def test_api_blocked_without_mfa(base_url, creds):
    s = requests.Session()
    login(s, base_url, creds["user"], creds["password"])
    r = s.get(f"{base_url}/api/protected")
    assert r.status_code == 403
    assert r.json().get("error") == "mfa_required"
