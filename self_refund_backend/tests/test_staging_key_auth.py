"""Phase 3: staging-key device authentication for the cloud dev/staging kiosk.

Mirrors test_device_auth.py's development-key tests but for the cloud-only
mode: same hashed/per-kiosk/revocable keys, shorter maximum lifetime, and an
HTTPS requirement enforced via the trusted proxy header.
"""
import pytest

from app import db
from app.models import Kiosk, KioskCredential
from app.tenancy import device_auth
from app.timeutil import utcnow


def _core(app):
    from flask.testing import FlaskClient
    return FlaskClient(app)


def _staging_key(code="KIOSK-001", days=None):
    key = device_auth.issue_staging_key(Kiosk.query.filter_by(code=code).one(), days=days)
    db.session.commit()
    return key


def test_staging_key_refused_over_plain_http(app):
    app.config["DEVICE_AUTH_MODE"] = "staging-key"
    key = _staging_key()
    core = _core(app)
    headers = {"Authorization": f"AutoRefund-Staging-Key {key}"}

    r = core.get("/api/kiosk/me", headers=headers)  # no X-Forwarded-Proto at all
    assert r.status_code == 401 and r.get_json()["code"] == "DEVICE_AUTH_REQUIRES_HTTPS"

    r = core.get("/api/kiosk/me", headers={**headers, "X-Forwarded-Proto": "http"})
    assert r.status_code == 401 and r.get_json()["code"] == "DEVICE_AUTH_REQUIRES_HTTPS"


def test_staging_key_accepted_over_https(app):
    app.config["DEVICE_AUTH_MODE"] = "staging-key"
    key = _staging_key()
    core = _core(app)
    headers = {"Authorization": f"AutoRefund-Staging-Key {key}", "X-Forwarded-Proto": "https"}

    r = core.get("/api/kiosk/me", headers=headers)
    assert r.status_code == 200
    assert r.get_json()["kiosk"]["kiosk_code"] == "KIOSK-001"


def test_development_key_is_not_accepted_in_staging_key_mode(app):
    from app.tenancy.device_auth import issue_development_key
    dev_key = issue_development_key(Kiosk.query.filter_by(code="KIOSK-001").one())
    db.session.commit()
    app.config["DEVICE_AUTH_MODE"] = "staging-key"
    core = _core(app)
    headers = {"Authorization": f"AutoRefund-Dev-Key {dev_key}", "X-Forwarded-Proto": "https"}
    r = core.get("/api/kiosk/me", headers=headers)
    assert r.status_code == 401


def test_kiosk_id_alone_is_not_accepted_as_authentication(app):
    app.config["DEVICE_AUTH_MODE"] = "staging-key"
    core = _core(app)
    r = core.get("/api/kiosk/me",
                headers={"X-Kiosk-Id": "KIOSK-001", "X-Forwarded-Proto": "https"})
    assert r.status_code == 401
    assert r.get_json()["code"] in ("DEVICE_AUTH_REQUIRED", "DEVICE_AUTH_FAILED")


def test_staging_key_max_lifetime_is_capped(app):
    app.config["DEVICE_AUTH_MODE"] = "staging-key"
    app.config["STAGING_KEY_MAX_DAYS"] = 14
    _staging_key(days=999)  # a caller asking for more than the cap is capped, not honoured
    credential = KioskCredential.query.filter_by(credential_type="staging-key").one()
    assert (credential.expires_at - utcnow()).days <= 14


def test_expired_and_revoked_staging_keys_are_rejected(app):
    from datetime import timedelta
    app.config["DEVICE_AUTH_MODE"] = "staging-key"
    key = _staging_key()
    core = _core(app)
    headers = {"Authorization": f"AutoRefund-Staging-Key {key}", "X-Forwarded-Proto": "https"}

    credential = KioskCredential.query.filter_by(credential_type="staging-key").one()
    credential.expires_at = utcnow() - timedelta(seconds=1)
    db.session.commit()
    assert core.get("/api/kiosk/me", headers=headers).status_code == 401

    key = _staging_key()
    headers = {"Authorization": f"AutoRefund-Staging-Key {key}", "X-Forwarded-Proto": "https"}
    assert core.get("/api/kiosk/me", headers=headers).status_code == 200
    device_auth.revoke_kiosk_credentials(Kiosk.query.filter_by(code="KIOSK-001").one())
    db.session.commit()
    assert core.get("/api/kiosk/me", headers=headers).status_code == 401


def test_staging_key_mode_refused_at_startup_in_production():
    with pytest.raises(RuntimeError, match="not allowed when ENVIRONMENT=production"):
        device_auth.check_startup_safety(
            {"DEVICE_AUTH_MODE": "staging-key", "ENVIRONMENT": "production"})


def test_staging_key_mode_allowed_at_startup_in_dev_and_staging():
    for environment in ("dev", "staging"):
        device_auth.check_startup_safety(
            {"DEVICE_AUTH_MODE": "staging-key", "ENVIRONMENT": environment, "HOST": "0.0.0.0"})
