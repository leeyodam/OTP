import requests

from utils import login


def test_login_success_issues_legacy_cookie(base_url, creds):
    s = requests.Session()
    login(s, base_url, creds["user"], creds["password"])
    assert "legacy_session" in s.cookies


def test_login_failure(base_url, creds):
    s = requests.Session()
    r = s.post(
        f"{base_url}/login",
        data={"username": creds["user"], "password": "wrong"},
        allow_redirects=False,
    )
    assert r.status_code == 200
    assert "legacy_session" not in s.cookies or not s.cookies.get("legacy_session")


def test_protected_dashboard_blocked_without_mfa(base_url, creds):
    s = requests.Session()
    login(s, base_url, creds["user"], creds["password"])
    r = s.get(f"{base_url}/dashboard", allow_redirects=False)
    assert r.status_code == 302
    assert "/mfa/verify" in r.headers.get("Location", "")
