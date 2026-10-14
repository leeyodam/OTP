import re

import pyotp
import requests


def login(session: requests.Session, base_url: str, user: str, password: str) -> None:
    r = session.post(
        f"{base_url}/login",
        data={"username": user, "password": password},
        allow_redirects=False,
    )
    assert r.status_code in (302, 303), r.text


def extract_csrf(html: str) -> str:
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert m, "csrf token missing"
    return m.group(1)


def _fetch_totp_secret(session: requests.Session, mfa_url: str) -> tuple[str, bool]:
    r = session.get(f"{mfa_url}/internal/test/totp-secret")
    assert r.status_code == 200, r.text
    data = r.json()
    return data.get("secret"), data.get("enrolled", False)


def enroll_and_verify_mfa(
    session: requests.Session, base_url: str, username: str, mfa_url: str = "http://127.0.0.1:5001"
) -> None:
    r = session.get(f"{base_url}/mfa/setup", allow_redirects=True)
    assert r.status_code == 200
    secret, enrolled = _fetch_totp_secret(session, mfa_url)
    assert secret, "TOTP secret not provisioned after /mfa/setup"

    if "Register Google Authenticator" in r.text:
        csrf = extract_csrf(r.text)
        otp = pyotp.TOTP(secret).now()
        r2 = session.post(
            f"{base_url}/mfa/setup",
            data={"csrf_token": csrf, "otp": otp},
            allow_redirects=False,
        )
        assert r2.status_code in (302, 303), r2.text
        return

    r = session.get(f"{base_url}/mfa/verify")
    csrf = extract_csrf(r.text)
    otp = pyotp.TOTP(secret).now()
    r2 = session.post(
        f"{base_url}/mfa/verify",
        data={"csrf_token": csrf, "otp": otp},
        allow_redirects=False,
    )
    assert r2.status_code in (302, 303), r2.text
