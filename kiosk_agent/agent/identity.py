"""
Kiosk identity: who this kiosk is and how it proves it to the Core API.

    KioskIdentity (interface)
      └─ DevelopmentKeyIdentity   Phase 2: KIOSK_ID + KIOSK_DEV_KEY from .env
      └─ StagingKeyIdentity       Phase 3: KIOSK_ID + a cloud staging key
      └─ (later) EnrolledDeviceIdentity: key pair in the Windows key store,
                 enrollment, short-lived tokens, revocation

identity_from_config() picks the class from the key's own prefix (arstg_ vs
ardev_) - an unrecognized or empty value never gets guessed into either
scheme, it comes back not configured instead.

The Core API decides the kiosk from the credential alone. KIOSK_ID here is
only what the agent EXPECTS to be; the agent compares it with /api/kiosk/me
and refuses to take returns if they differ.
"""
from abc import ABC, abstractmethod


class KioskIdentity(ABC):
    @property
    @abstractmethod
    def expected_kiosk_code(self) -> str: ...

    @abstractmethod
    def auth_headers(self) -> dict:
        """Headers that authenticate this kiosk to the Core API."""

    @property
    def configured(self) -> bool:
        return True


class DevelopmentKeyIdentity(KioskIdentity):
    SCHEME = "AutoRefund-Dev-Key"

    def __init__(self, kiosk_code, dev_key):
        self._code = kiosk_code
        self._key = (dev_key or "").strip()

    @property
    def expected_kiosk_code(self):
        return self._code

    @property
    def configured(self):
        return bool(self._code and self._key)

    def auth_headers(self):
        return {"Authorization": f"{self.SCHEME} {self._key}"} if self._key else {}

    def __repr__(self):  # never print the key
        return f"DevelopmentKeyIdentity(kiosk={self._code!r}, key={'set' if self._key else 'missing'})"


class StagingKeyIdentity(KioskIdentity):
    """Phase 3: KIOSK_ID + a cloud staging key (arstg_ prefix) from .env."""
    SCHEME = "AutoRefund-Staging-Key"

    def __init__(self, kiosk_code, staging_key):
        self._code = kiosk_code
        self._key = (staging_key or "").strip()

    @property
    def expected_kiosk_code(self):
        return self._code

    @property
    def configured(self):
        return bool(self._code and self._key)

    def auth_headers(self):
        return {"Authorization": f"{self.SCHEME} {self._key}"} if self._key else {}

    def __repr__(self):  # never print the key
        return f"StagingKeyIdentity(kiosk={self._code!r}, key={'set' if self._key else 'missing'})"


DEV_KEY_PREFIX = "ardev_"
STAGING_KEY_PREFIX = "arstg_"


def identity_from_config(config):
    kiosk_code = config["KIOSK_ID"]
    key = (config["KIOSK_DEV_KEY"] or "").strip()
    if key.startswith(STAGING_KEY_PREFIX):
        return StagingKeyIdentity(kiosk_code, key)
    if key.startswith(DEV_KEY_PREFIX):
        return DevelopmentKeyIdentity(kiosk_code, key)
    return DevelopmentKeyIdentity(kiosk_code, "")
