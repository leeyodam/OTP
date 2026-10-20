"""Session binding store (adapter). TOTP secrets live in embedded or privacyIDEA."""
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional, Set


@dataclass
class SessionMfaState:
    username: str
    legacy_binding: str
    status: str  # MFA_PENDING | MFA_VERIFIED
    verified_at: float = 0.0


class SessionStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.sessions: Dict[str, SessionMfaState] = {}
        self.used_otp_steps: Dict[str, Set[int]] = {}

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

    def set_verified(self, mfa_session_id: str, username: str, legacy_binding: str) -> None:
        with self._lock:
            state = self.sessions.get(mfa_session_id)
            if not state:
                return
            state.status = "MFA_VERIFIED"
            state.verified_at = time.time()

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


session_store = SessionStore()
