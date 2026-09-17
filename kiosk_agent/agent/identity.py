"""
Kiosk identity: who this kiosk is and how it proves it to the Core API.

    KioskIdentity (interface)
      └─ DevelopmentKeyIdentity   Phase 2: KIOSK_ID + KIOSK_DEV_KEY from .env
      └─ (later) EnrolledDeviceIdentity: key pair in the Windows key store,
                 enrollment, short-lived tokens, revocation

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


def identity_from_config(config):
    return DevelopmentKeyIdentity(config["KIOSK_ID"], config["KIOSK_DEV_KEY"])
