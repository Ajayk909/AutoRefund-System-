"""Staff authentication, authorization, state transitions and evidence access."""
from datetime import timedelta

import pytest

from app import db
from app.models import AuditLog, Refund, StaffSession
from app.timeutil import utcnow
from tests.conftest import login


def _pending_refund(client):
    """Create a refund that goes to review (weight far outside tolerance)."""
    from tests.test_workflows import _item, _submit, _transaction
    tx = _transaction(client)
    r = _submit(client, tx, _item(tx, "222222"), 999)
    assert r.status_code == 201, r.get_json()
    refund = r.get_json()["refund"]
    assert refund["decision_status"] == "pending_review"
    return refund["refund_id"]


PROTECTED = [
    ("get", "/api/refunds/pending"),
    ("get", "/api/refunds/logs"),
    ("get", "/api/staff/me"),
    ("get", "/api/captures/anything.jpg"),
]


@pytest.mark.parametrize("method,url", PROTECTED)
def test_staff_endpoints_require_login(client, method, url):
    r = getattr(client, method)(url)
    assert r.status_code == 401
    assert r.get_json()["code"] == "AUTH_REQUIRED"


def test_decision_endpoints_require_login(client):
    rid = _pending_refund(client)
    for action in ("approve", "reject", "mark-refunded"):
        assert client.post(f"/api/refunds/{rid}/{action}").status_code == 401
    assert client.get(f"/api/refunds/{rid}/image").status_code == 401
    assert db.session.get(Refund, rid).decision_status == "pending_review"


def test_garbage_and_forged_tokens_rejected(client):
    for header in ("Bearer nope", "Basic abc", "Bearer ", "token"):
        assert client.get("/api/refunds/pending",
                          headers={"Authorization": header}).status_code == 401


def test_logout_revokes_token(client):
    h = login(client)
    assert client.get("/api/staff/me", headers=h).status_code == 200
    assert client.post("/api/staff/logout", headers=h).status_code == 200
    assert client.get("/api/staff/me", headers=h).status_code == 401


def test_expired_session_rejected(client):
    h = login(client)
    session = StaffSession.query.one()
    session.expires_at = utcnow() - timedelta(minutes=1)
    db.session.commit()
    assert client.get("/api/staff/me", headers=h).status_code == 401


def test_token_is_not_stored_in_plain_text(client):
    token = login(client)["Authorization"].split(" ", 1)[1]
    stored = StaffSession.query.one().token_hash
    assert token not in stored and len(stored) == 64


def test_login_rate_limited_after_repeated_failures(client):
    for _ in range(5):
        assert client.post("/api/staff/login", json={
            "username": "admin1", "password": "wrong"}).status_code == 401
    r = client.post("/api/staff/login", json={"username": "admin1", "password": "admin123"})
    assert r.status_code == 429
    assert AuditLog.query.filter_by(event_type="staff_login_failed").count() == 5


def test_approve_records_staff_reason_and_audit(client, staff_headers):
    rid = _pending_refund(client)
    r = client.post(f"/api/refunds/{rid}/approve", headers=staff_headers,
                    json={"reason": "Box was opened but item intact"})
    assert r.status_code == 200
    body = r.get_json()["refund"]
    assert body["reviewed_by"] == "Demo Admin"

    refund = db.session.get(Refund, rid)
    assert refund.staff_id is not None
    assert refund.decided_at is not None
    assert refund.decision_reason == "Box was opened but item intact"
    audit = AuditLog.query.filter_by(event_type="refund_approved_by_staff").one()
    assert audit.staff_id == refund.staff_id
    assert audit.details["previous_status"] == "pending_review"


def test_illegal_transitions_are_blocked(client, staff_headers):
    h = staff_headers
    rid = _pending_refund(client)
    assert client.post(f"/api/refunds/{rid}/reject", headers=h).status_code == 200
    # a rejected return can't be approved, re-rejected or refunded
    for action in ("approve", "reject"):
        r = client.post(f"/api/refunds/{rid}/{action}", headers=h)
        assert r.status_code == 409 and r.get_json()["code"] == "INVALID_STATE"
    r = client.post(f"/api/refunds/{rid}/mark-refunded", headers=h,
                    json={"payment_reference": "POS-1"})
    assert r.status_code == 409
    assert db.session.get(Refund, rid).decision_status == "rejected"


def test_auto_approved_return_cannot_be_rejected(client, staff_headers):
    from tests.test_workflows import _item, _submit, _transaction
    tx = _transaction(client)
    rid = _submit(client, tx, _item(tx, "111111"), 250).get_json()["refund"]["refund_id"]
    assert client.post(f"/api/refunds/{rid}/reject", headers=staff_headers).status_code == 409


def test_refund_execution_is_separate_from_approval(client, staff_headers):
    h = staff_headers
    rid = _pending_refund(client)
    # cannot mark refunded before approval
    assert client.post(f"/api/refunds/{rid}/mark-refunded", headers=h,
                       json={"payment_reference": "POS-1"}).status_code == 409
    client.post(f"/api/refunds/{rid}/approve", headers=h)
    assert db.session.get(Refund, rid).refunded_at is None
    # payment reference is required
    r = client.post(f"/api/refunds/{rid}/mark-refunded", headers=h, json={})
    assert r.status_code == 400
    r = client.post(f"/api/refunds/{rid}/mark-refunded", headers=h,
                    json={"payment_reference": "POS-778"})
    assert r.status_code == 200
    refund = db.session.get(Refund, rid)
    assert refund.decision_status == "refunded"
    assert refund.payment_reference == "POS-778"
    assert refund.refunded_by_staff_id is not None
    # terminal
    assert client.post(f"/api/refunds/{rid}/mark-refunded", headers=h,
                       json={"payment_reference": "again"}).status_code == 409


def test_unknown_or_malformed_refund_id(client, staff_headers):
    for rid in ("not-a-uuid", "00000000-0000-0000-0000-000000000000"):
        assert client.post(f"/api/refunds/{rid}/approve",
                           headers=staff_headers).status_code == 404


def test_capture_path_traversal_blocked(client, staff_headers):
    r = client.get("/api/captures/..%2F..%2Fconfig.py", headers=staff_headers)
    assert r.status_code == 404
