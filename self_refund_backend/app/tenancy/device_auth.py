"""
Kiosk device authentication: how the Core API knows which kiosk is calling.

The kiosk's identity comes ONLY from the credential. Nothing in the request
body, query string or other headers can choose or change the kiosk.

    DeviceAuthenticator (interface)
      └─ DevelopmentKeyAuthenticator   Phase 2, local development only
      └─ (later) enrolled device key pair + short-lived tokens

Development keys - deliberately unfit for production:
* header ``Authorization: AutoRefund-Dev-Key ardev_<random>``
* random 256-bit value, only its SHA-256 hash is stored
* bound to one kiosk, expire (DEV_KEY_MAX_DAYS, default 30), revocable
* the Core API refuses to START with DEVICE_AUTH_MODE=development unless it
  listens on a loopback address (127.0.0.1 / localhost / ::1)
"""
import hashlib
import secrets
from abc import ABC, abstractmethod
from datetime import timedelta
from functools import wraps

from flask import current_app, g, jsonify, request

from app import db
from app.errors import DomainError
from app.models import KioskCredential
from app.tenancy import repository
from app.tenancy.context import KioskContext
from app.timeutil import utcnow

DEV_SCHEME = "AutoRefund-Dev-Key"
DEV_KEY_PREFIX = "ardev_"
DEVELOPMENT = "development"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _hash(secret):
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


class DeviceAuthError(DomainError):
    pass


class DeviceAuthenticator(ABC):
    @abstractmethod
    def authenticate(self, req) -> KioskContext:
        """Return the calling kiosk's context or raise DeviceAuthError."""


class DevelopmentKeyAuthenticator(DeviceAuthenticator):
    def authenticate(self, req):
        scheme, _, secret = req.headers.get("Authorization", "").partition(" ")
        secret = secret.strip()
        if scheme != DEV_SCHEME or not secret.startswith(DEV_KEY_PREFIX):
            raise DeviceAuthError("DEVICE_AUTH_REQUIRED", "Kiosk authentication required.", 401)

        credential = KioskCredential.query.filter_by(secret_hash=_hash(secret),
                                                     credential_type=DEVELOPMENT).first()
        now = utcnow()
        if (not credential or credential.revoked_at is not None
                or credential.expires_at <= now):
            raise DeviceAuthError("DEVICE_AUTH_FAILED", "Kiosk authentication failed.", 401)

        row = repository.find_kiosk_with_tenant_by_id(credential.kiosk_id)
        if not row:
            raise DeviceAuthError("DEVICE_AUTH_FAILED", "Kiosk authentication failed.", 401)
        kiosk, store, retailer = row
        if not (kiosk.is_active and store.is_active and retailer.is_active):
            raise DeviceAuthError("KIOSK_DISABLED",
                                  "This kiosk is not accepting returns right now. "
                                  "Please visit customer service.", 403)
        credential.last_used_at = now
        db.session.commit()
        return KioskContext(retailer.retailer_id, store.store_id, kiosk.kiosk_id, kiosk.code)


def authenticator_for(config):
    mode = config.get("DEVICE_AUTH_MODE", DEVELOPMENT)
    if mode == DEVELOPMENT:
        return DevelopmentKeyAuthenticator()
    raise RuntimeError(f"Unsupported DEVICE_AUTH_MODE={mode!r}. "
                       "Only 'development' exists in this version.")


def check_startup_safety(config):
    """Refuse to run development device auth anywhere but loopback."""
    if config.get("DEVICE_AUTH_MODE", DEVELOPMENT) == DEVELOPMENT and \
            str(config.get("HOST", "127.0.0.1")).strip().lower() not in LOOPBACK_HOSTS:
        raise RuntimeError(
            "DEVICE_AUTH_MODE=development is only allowed when FLASK_HOST is 127.0.0.1, "
            "localhost or ::1. Development kiosk keys must never be exposed on a network.")


def require_kiosk_device(view):
    """Protect a Core API route: only an authenticated kiosk agent may call it.
    Sets ``g.kiosk_context``."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        try:
            g.kiosk_context = authenticator_for(current_app.config).authenticate(request)
        except DeviceAuthError as err:
            db.session.rollback()
            return jsonify(err.body()), err.status
        return view(*args, **kwargs)
    return wrapped


def issue_development_key(kiosk, days=None):
    """Create a development key for a kiosk. The plain key is returned ONCE."""
    days = days or current_app.config.get("DEV_KEY_MAX_DAYS", 30)
    secret = DEV_KEY_PREFIX + secrets.token_urlsafe(32)
    now = utcnow()
    db.session.add(KioskCredential(kiosk_id=kiosk.kiosk_id, credential_type=DEVELOPMENT,
                                   secret_hash=_hash(secret), created_at=now,
                                   expires_at=now + timedelta(days=days)))
    return secret


def revoke_kiosk_credentials(kiosk):
    now = utcnow()
    count = 0
    for credential in KioskCredential.query.filter_by(kiosk_id=kiosk.kiosk_id, revoked_at=None):
        credential.revoked_at = now
        count += 1
    return count
