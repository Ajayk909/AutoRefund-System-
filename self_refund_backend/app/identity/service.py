"""Staff login and logout."""
import logging

from werkzeug.security import check_password_hash

from app import db
from app.audit import service as audit
from app.errors import DomainError
from app.identity.auth import create_session, current_session, login_limiter
from app.models import Staff
from app.timeutil import utcnow

log = logging.getLogger("autorefund.identity")


def login(username, password):
    """Return (staff, token, session) or raise DomainError."""
    if not username or not password:
        raise DomainError("CREDENTIALS_REQUIRED", "username and password are required")

    if login_limiter.is_blocked(username):
        log.warning("Staff login temporarily locked for username=%s", username)
        raise DomainError("TOO_MANY_ATTEMPTS",
                          "Too many failed attempts. Please wait a few minutes and try again.",
                          429)

    staff = Staff.query.filter_by(username=username).first()
    if not staff or not check_password_hash(staff.password_hash, password):
        login_limiter.record_failure(username)
        log.warning("Failed staff login for username=%s", username)
        audit.record("staff_login_failed", username=str(username)[:100])
        db.session.commit()
        raise DomainError("INVALID_CREDENTIALS", "Invalid credentials", 401)

    login_limiter.reset(username)
    token, session = create_session(staff)
    audit.record("staff_login", staff_id=staff.staff_id, retailer_id=staff.retailer_id)
    db.session.commit()
    log.info("Staff login: %s", staff.username)
    return staff, token, session


def logout():
    session = current_session()
    if session:
        session.revoked_at = utcnow()
        staff = db.session.get(Staff, session.staff_id)
        audit.record("staff_logout", staff_id=session.staff_id,
                     retailer_id=staff.retailer_id if staff else None)
        db.session.commit()
