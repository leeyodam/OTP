import requests

from utils import login


def test_test2_can_login(base_url):
    s = requests.Session()
    login(s, base_url, "test2", "test2!")
    assert s.cookies.get("legacy_session")


def test_test5_can_login(base_url):
    s = requests.Session()
    login(s, base_url, "test5", "test5!")
    assert s.cookies.get("legacy_session")


def test_unknown_user_fails(base_url):
    s = requests.Session()
    r = s.post(
        f"{base_url}/login",
        data={"username": "test6", "password": "test6!"},
        allow_redirects=False,
    )
    assert r.status_code == 200
    assert "legacy_session" not in s.cookies or not s.cookies.get("legacy_session")
