import os

from backends.base import MfaBackend
from backends.embedded import EmbeddedBackend
from backends.privacyidea_backend import PrivacyIDEABackend

_embedded_singleton: EmbeddedBackend | None = None
_pi_singleton: PrivacyIDEABackend | None = None


def get_backend() -> MfaBackend:
    mode = os.environ.get("MFA_BACKEND", "embedded").lower()
    global _pi_singleton
    if mode == "privacyidea":
        if _pi_singleton is None:
            _pi_singleton = PrivacyIDEABackend(
                base_url=os.environ["PRIVACYIDEA_URL"],
                admin_user=os.environ.get("PRIVACYIDEA_ADMIN_USER", "admin"),
                admin_password=os.environ["PRIVACYIDEA_ADMIN_PASSWORD"],
                realm=os.environ.get("PRIVACYIDEA_REALM", ""),
                totp_pin=os.environ.get("PRIVACYIDEA_TOTP_PIN", ""),
            )
        return _pi_singleton
    global _embedded_singleton
    if _embedded_singleton is None:
        _embedded_singleton = EmbeddedBackend()
    return _embedded_singleton
