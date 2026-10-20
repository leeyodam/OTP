"""In-process TOTP (original PoC). Used for pytest and demo without privacyIDEA."""
import base64
import io
import os
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional, Set

import pyotp
import qrcode

from backends.base import MfaBackend


@dataclass
class _UserRec:
    username: str
    totp_secret: str
    enrolled: bool = False
    failure_count: int = 0
    locked_until: float = 0.0


class EmbeddedBackend(MfaBackend):
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._users: Dict[str, _UserRec] = {}
        self._used_steps: Dict[str, Set[int]] = {}
        self._max_failures = int(os.environ.get("MFA_MAX_OTP_FAILURES", "5"))
        self._lock_seconds = int(os.environ.get("MFA_LOCK_SECONDS", "300"))
        self._otp_window = int(os.environ.get("MFA_OTP_WINDOW", "1"))

    def _user(self, username: str) -> _UserRec:
        with self._lock:
            rec = self._users.get(username)
            if rec is None:
                rec = _UserRec(username=username, totp_secret=pyotp.random_base32())
                self._users[username] = rec
            return rec

    def is_locked(self, username: str) -> bool:
        rec = self._users.get(username)
        return bool(rec and time.time() < rec.locked_until)

    def record_failure(self, username: str) -> None:
        with self._lock:
            rec = self._users.get(username)
            if not rec:
                return
            rec.failure_count += 1
            if rec.failure_count >= self._max_failures:
                rec.locked_until = time.time() + self._lock_seconds

    def clear_failures(self, username: str) -> None:
        with self._lock:
            rec = self._users.get(username)
            if rec:
                rec.failure_count = 0
                rec.locked_until = 0.0

    def is_enrolled(self, username: str) -> bool:
        rec = self._users.get(username)
        return bool(rec and rec.enrolled)

    def totp_secret_for_tests(self, username: str) -> Optional[str]:
        rec = self._users.get(username)
        return rec.totp_secret if rec else None

    def provisioning_qr_b64(self, username: str) -> str:
        rec = self._user(username)
        totp = pyotp.TOTP(rec.totp_secret)
        uri = totp.provisioning_uri(name=username, issuer_name="LegacyPoC")
        img = qrcode.make(uri)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()

    def _step_used(self, username: str, binding_key: str, step: int) -> bool:
        return step in self._used_steps.get(f"{username}:{binding_key}", set())

    def mark_step_used(self, username: str, binding_key: str, step: int) -> None:
        with self._lock:
            self._used_steps.setdefault(f"{username}:{binding_key}", set()).add(step)

    def verify_otp(
        self, username: str, otp: str, *, enroll_step: bool = False, binding_key: str = ""
    ) -> bool:
        if self.is_locked(username):
            return False
        rec = self._user(username)
        totp = pyotp.TOTP(rec.totp_secret)
        step = int(time.time() // 30)
        if binding_key and self._step_used(username, binding_key, step):
            return False
        if not totp.verify(otp, valid_window=self._otp_window):
            self.record_failure(username)
            return False
        if binding_key:
            self.mark_step_used(username, binding_key, step)
        if enroll_step:
            with self._lock:
                rec.enrolled = True
        self.clear_failures(username)
        return True

    def demo_otp(self, username: str) -> Optional[str]:
        if os.environ.get("MFA_TEST_MODE", "").lower() != "true":
            return None
        rec = self._users.get(username)
        if not rec:
            return None
        return pyotp.TOTP(rec.totp_secret).now()
