import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
LEGACY_DIR = ROOT / "legacy-web"
MFA_DIR = ROOT / "mfa-service"


def _wait(url: str, timeout: float = 30) -> None:
    start = time.time()
    while time.time() - start < timeout:
        try:
            if requests.get(url, timeout=1).status_code < 500:
                return
        except requests.RequestException:
            pass
        time.sleep(0.2)
    raise RuntimeError(f"Service not ready: {url}")


@pytest.fixture(scope="session")
def env_defaults():
    os.environ.setdefault("SERVICE_SHARED_SECRET", "test-shared-secret-for-poc")
    os.environ.setdefault("LEGACY_SECRET_KEY", "test-legacy-key")
    os.environ.setdefault("MFA_SECRET_KEY", "test-mfa-key")
    os.environ.setdefault("LEGACY_TEST_USER", "testuser")
    os.environ.setdefault("LEGACY_TEST_PASSWORD", "TestPassword123!")
    os.environ.setdefault("LEGACY_INTERNAL_URL", "http://127.0.0.1:5000")
    os.environ.setdefault("MFA_TEST_MODE", "true")
    return {
        "user": os.environ["LEGACY_TEST_USER"],
        "password": os.environ["LEGACY_TEST_PASSWORD"],
    }


@pytest.fixture(scope="session")
def legacy_server(env_defaults):
    env = os.environ.copy()
    proc = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=LEGACY_DIR,
        env=env,
    )
    _wait("http://127.0.0.1:5000/health")
    yield "http://127.0.0.1:5000"
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(scope="session")
def mfa_server(env_defaults, legacy_server):
    env = os.environ.copy()
    env["LEGACY_INTERNAL_URL"] = legacy_server
    proc = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=MFA_DIR,
        env=env,
    )
    _wait("http://127.0.0.1:5001/health")
    yield "http://127.0.0.1:5001"
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(scope="session")
def proxy_server(legacy_server, mfa_server):
    os.environ["TEST_LEGACY_URL"] = legacy_server
    os.environ["TEST_MFA_URL"] = mfa_server
    proc = subprocess.Popen(
        [sys.executable, "proxy_harness.py"],
        cwd=Path(__file__).parent,
        env=os.environ.copy(),
    )
    _wait("http://127.0.0.1:18080/health")
    yield "http://127.0.0.1:18080"
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture
def base_url(proxy_server):
    return proxy_server


@pytest.fixture
def creds(env_defaults):
    return env_defaults
