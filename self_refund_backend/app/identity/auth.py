"""
Server-side staff authentication and authorization (Phase 0 foundation).

* Login issues a random bearer token. Only its SHA-256 hash is stored in
  ``staff_sessions``; sessions expire and can be revoked (logout).
* ``@require_staff(...)`` protects a route. The frontend hiding a button is
  never treated as security.
* Login itself (checking the password) lives in ``identity/service.py``.
* A small in-memory limiter slows password guessing. It is per process,
  which is fine for a single kiosk PC; the cloud version will use WAF/Cognito.

Phase 4 replaces the token issuer with Amazon Cognito; the decorator and the
role checks stay the same shape.
"""
import hashlib
import secrets
import threading
from collections import defaultdict, deque
from datetime import timedelta
from functools import wraps

from flask import current_app, g, jsonify, request

from app import db
from app.models import Staff, StaffSession
from app.timeutil import utcnow

ALL_STAFF_ROLES = ("admin", "manager", "customer_service")
# Roles allowed to approve/reject/mark refunded. Kept explicit so it can be
# narrowed per retailer policy later.
REVIEW_ROLES = ALL_STAFF_ROLES


def _hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(staff):
    token = secrets.token_urlsafe(32)
    now = utcnow()
    hours = current_app.config["STAFF_SESSION_HOURS"]
    session = StaffSession(staff_id=staff.staff_id, token_hash=_hash_token(token),
                           created_at=now, expires_at=now + timedelta(hours=hours))
    db.session.add(session)
    return token, session


def _bearer_token():
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def current_session():
    token = _bearer_token()
    if not token:
        return None
    session = StaffSession.query.filter_by(token_hash=_hash_token(token)).first()
    if not session or session.revoked_at is not None or session.expires_at <= utcnow():
        return None
    return session


def require_staff(*roles):
    allowed = roles or ALL_STAFF_ROLES

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            session = current_session()
            staff = db.session.get(Staff, session.staff_id) if session else None
            if not staff:
                return jsonify({"success": False, "code": "AUTH_REQUIRED",
                                "message": "Please sign in again."}), 401
            if staff.role not in allowed:
                return jsonify({"success": False, "code": "FORBIDDEN",
                                "message": "You do not have permission for this action."}), 403
            session.last_used_at = utcnow()
            db.session.commit()
            g.staff = staff
            g.staff_session = session
            return view(*args, **kwargs)
        return wrapped
    return decorator


class LoginRateLimiter:
    """At most ``max_failures`` failed logins per username per window."""

    def __init__(self, max_failures=5, window_seconds=900):
        self.max_failures = max_failures
        self.window = timedelta(seconds=window_seconds)
        self._failures = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key, now):
        q = self._failures[key]
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def is_blocked(self, username):
        key = (username or "").strip().lower()
        with self._lock:
            return len(self._prune(key, utcnow())) >= self.max_failures

    def record_failure(self, username):
        key = (username or "").strip().lower()
        with self._lock:
            self._prune(key, utcnow()).append(utcnow())

    def reset(self, username=None):
        with self._lock:
            if username is None:
                self._failures.clear()
            else:
                self._failures.pop(username.strip().lower(), None)


login_limiter = LoginRateLimiter()

