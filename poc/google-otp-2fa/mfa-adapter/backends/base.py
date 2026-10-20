from abc import ABC, abstractmethod
from typing import Optional, Tuple


class MfaBackend(ABC):
    @abstractmethod
    def is_enrolled(self, username: str) -> bool:
        ...

    @abstractmethod
    def provisioning_qr_b64(self, username: str) -> str:
        """Return base64 PNG for enrollment QR."""

    @abstractmethod
    def verify_otp(self, username: str, otp: str, *, enroll_step: bool = False) -> bool:
        ...

    def demo_otp(self, username: str) -> Optional[str]:
        """PoC test hint; only when MFA_TEST_MODE."""
        return None
