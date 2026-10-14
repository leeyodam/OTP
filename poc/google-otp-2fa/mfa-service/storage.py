"""
In-memory storage for PoC. Not durable across restarts; documented in SECURITY.md.
"""
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Set


@dataclass
class UserMfaRecord:
    username: str
    totp_secret: str
    enrolled: bool = False
    failure_count: int = 0
    locked_until: float = 0.0


@dataclass
class SessionMfaState:
    username: str
    legacy_binding: str
    status: str  # MFA_PENDING | MFA_VERIFIED
    verified_at: float = 0.0
    last_totp_step: Optional[int] = None


class MfaStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.users: Dict[str, UserMfaRecord] = {}
        self.sessions: Dict[str, SessionMfaState] = {}
        self.used_totp_steps: Dict[str, Set[int]] = {}

    def get_user(self, username: str) -> Optional[UserMfaRecord]:
        with self._lock:
            return self.users.get(username)

    def upsert_user_secret(self, username: str, secret: str) -> UserMfaRecord:
        with self._lock:
            rec = self.users.get(username)
            if rec is None:
                rec = UserMfaRecord(username=username, totp_secret=secret)
                self.users[username] = rec
            else:
                rec.totp_secret = secret
            return rec

    def mark_enrolled(self, username: str) -> None:
        with self._lock:
            rec = self.users.get(username)
            if rec:
                rec.enrolled = True
                rec.failure_count = 0

    def record_failure(self, username: str, max_failures: int, lock_seconds: int) -> None:
        with self._lock:
            rec = self.users.get(username)
            if not rec:
                return
            rec.failure_count += 1
            if rec.failure_count >= max_failures:
                rec.locked_until = time.time() + lock_seconds

    def clear_failures(self, username: str) -> None:
        with self._lock:
            rec = self.users.get(username)
            if rec:
                rec.failure_count = 0
                rec.locked_until = 0.0

    def is_locked(self, username: str) -> bool:
        with self._lock:
            rec = self.users.get(username)
            if not rec:
                return False
            return time.time() < rec.locked_until

    def bind_session(
        self, mfa_session_id: str, username: str, legacy_binding: str, status: str
    ) -> SessionMfaState:
        with self._lock:
            state = SessionMfaState(
                username=username, legacy_binding=legacy_binding, status=status
            )
            self.sessions[mfa_session_id] = state
            return state

    def get_session(self, mfa_session_id: str) -> Optional[SessionMfaState]:
        with self._lock:
            return self.sessions.get(mfa_session_id)

    def set_verified(self, mfa_session_id: str, totp_step: int) -> None:
        with self._lock:
            state = self.sessions.get(mfa_session_id)
            if not state:
                return
            state.status = "MFA_VERIFIED"
            state.verified_at = time.time()
            state.last_totp_step = totp_step
            key = f"{state.username}:{state.legacy_binding}"
            self.used_totp_steps.setdefault(key, set()).add(totp_step)

    def invalidate_session(self, mfa_session_id: str) -> None:
        with self._lock:
            self.sessions.pop(mfa_session_id, None)

    def invalidate_by_legacy_binding(self, legacy_binding: str) -> None:
        with self._lock:
            to_remove = [
                sid
                for sid, st in self.sessions.items()
                if st.legacy_binding == legacy_binding
            ]
            for sid in to_remove:
                self.sessions.pop(sid, None)

    def totp_step_used(self, username: str, legacy_binding: str, step: int) -> bool:
        with self._lock:
            key = f"{username}:{legacy_binding}"
            return step in self.used_totp_steps.get(key, set())

    def clear_user_sessions(self, username: str) -> None:
        with self._lock:
            to_remove = [
                sid for sid, st in self.sessions.items() if st.username == username
            ]
            for sid in to_remove:
                self.sessions.pop(sid, None)


store = MfaStore()
