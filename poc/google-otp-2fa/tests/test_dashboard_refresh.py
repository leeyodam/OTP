"""MFA must survive repeated dashboard loads (legacy session cookie refresh)."""

from utils import enroll_and_verify_mfa, login


def test_dashboard_survives_refresh(base_url, creds):
    s = __import__("requests").Session()
    login(s, base_url, creds["user"], creds["password"])
    enroll_and_verify_mfa(s, base_url, creds["user"])
    assert s.get(f"{base_url}/dashboard").status_code == 200
    assert s.get(f"{base_url}/dashboard").status_code == 200
    assert s.get(f"{base_url}/api/protected").status_code == 200
