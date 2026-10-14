import requests

from utils import enroll_and_verify_mfa, login


def test_legacy_cookie_alone_cannot_access_protected_via_proxy(base_url, creds):
    s = requests.Session()
    login(s, base_url, creds["user"], creds["password"])
    r = s.get(f"{base_url}/api/protected")
    assert r.status_code == 403


def test_forged_mfa_header_on_auth_check(mfa_server, creds):
    s = requests.Session()
    # no legacy session
    r = requests.get(
        f"{mfa_server}/internal/auth-check",
        headers={"X-2FA-Verified": "true", "X-MFA-User": creds["user"]},
    )
    assert r.status_code in (401, 403)


def test_forged_mfa_cookie_without_valid_session(base_url, creds):
    s = requests.Session()
    s.cookies.set("mfa_session", "forged-value")
    r = s.get(f"{base_url}/dashboard", allow_redirects=False)
    assert r.status_code in (302, 403)
    assert r.status_code != 200


def test_other_user_mfa_state_not_reused(base_url, creds):
    s1 = requests.Session()
    login(s1, base_url, creds["user"], creds["password"])
    enroll_and_verify_mfa(s1, base_url, creds["user"])

    s2 = requests.Session()
    login(s2, base_url, creds["user"], creds["password"])
    r = s2.get(f"{base_url}/dashboard", allow_redirects=False)
    assert r.status_code == 302
    assert "mfa" in r.headers.get("Location", "").lower()


def test_logout_invalidates_reuse(base_url, creds):
    s = requests.Session()
    login(s, base_url, creds["user"], creds["password"])
    enroll_and_verify_mfa(s, base_url, creds["user"])
    assert s.get(f"{base_url}/dashboard").status_code == 200
    s.get(f"{base_url}/logout", allow_redirects=True)
    r = s.get(f"{base_url}/dashboard", allow_redirects=False)
    assert r.status_code in (302, 401, 403)


def test_direct_legacy_api_bypasses_mfa_when_exposed(legacy_server, creds):
    """Documents risk: legacy without proxy is reachable if port is exposed."""
    s = requests.Session()
    r = s.post(
        f"{legacy_server}/login",
        data={"username": creds["user"], "password": creds["password"]},
        allow_redirects=False,
    )
    assert r.status_code in (302, 303)
    api = s.get(f"{legacy_server}/api/protected")
    assert api.status_code == 200
