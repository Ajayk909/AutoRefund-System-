"""Phase 0 return rules: trusted inputs, quantity, retries, window,
idempotency, concurrency and evidence handling."""
import os
import threading
import time

from app import db, returns
from app.models import AuditLog, Refund
from tests.conftest import login
from tests.test_workflows import _capture, _item, _submit, _transaction


def _tx(client, receipt):
    r = client.get(f"/api/transactions/{receipt}")
    assert r.status_code == 200
    return r.get_json()["transaction"]


# --- trusted inputs -------------------------------------------------------
def test_receipt_response_has_no_customer_details(client):
    tx = _transaction(client)
    assert "customer_email" not in tx and "payment_method" not in tx
    assert tx["within_return_window"] is True and tx["return_deadline"]


def test_client_supplied_weight_is_ignored(client):
    tx = _transaction(client)
    # scale says 10 g; the request claims a perfect 250 g
    r = _submit(client, tx, _item(tx, "111111"), 10, measured_weight_grams=250)
    body = r.get_json()["refund"]
    assert body["measured_weight_grams"] == 10.0
    assert body["decision_status"] == "pending_review"


def test_kiosk_id_comes_from_configuration(client, app):
    tx = _transaction(client)
    r = _submit(client, tx, _item(tx, "111111"), 250, kiosk_id="EVIL-KIOSK")
    refund = db.session.get(Refund, r.get_json()["refund"]["refund_id"])
    assert refund.kiosk_id == app.config["KIOSK_ID"] != "EVIL-KIOSK"


def test_scale_disconnected_creates_no_refund(client, app):
    tx = _transaction(client)
    app.mock_scale.connected = False
    r = client.post("/api/refunds/start", json={
        "transaction_id": tx["transaction_id"], "item_id": _item(tx, "111111")["item_id"]})
    assert r.status_code == 503 and r.get_json()["code"] == "SCALE_UNAVAILABLE"
    assert Refund.query.count() == 0


def test_audit_records_hardware_source(client):
    tx = _transaction(client)
    _submit(client, tx, _item(tx, "111111"), 250)
    details = AuditLog.query.filter_by(event_type="refund_started").one().details
    assert details["weight_source"] == "mock-scale" and details["hardware_mock"] is True


# --- quantity -------------------------------------------------------------
def test_quantity_greater_than_one(client):
    tx = _tx(client, "RCP-2002")
    item = _item(tx, "444444")
    assert item["quantity"] == 3 and item["returnable_quantity"] == 3

    r = _submit(client, tx, item, 100)  # one cup
    assert r.status_code == 201 and r.get_json()["refund"]["refund_amount"] == 1.25

    item = _item(_tx(client, "RCP-2002"), "444444")
    assert item["returned_quantity"] == 1 and item["returnable_quantity"] == 2
    assert item["is_refundable"] is True

    # more than remain
    r = _submit(client, tx, item, 300, quantity=3)
    assert r.status_code == 400 and r.get_json()["code"] == "QUANTITY_EXCEEDS_REMAINING"

    # two cups together: expected weight and amount scale with quantity
    r = _submit(client, tx, item, 200, quantity=2)
    body = r.get_json()["refund"]
    assert r.status_code == 201
    assert body["decision_status"] == "approved"
    assert body["expected_weight_grams"] == 200.0 and body["refund_amount"] == 2.5

    item = _item(_tx(client, "RCP-2002"), "444444")
    assert item["returnable_quantity"] == 0 and item["ineligible_reason"] == "ALREADY_RETURNED"
    r = _submit(client, tx, item, 100)
    assert r.get_json()["code"] == "DUPLICATE_RETURN"


def test_invalid_quantity(client):
    tx = _tx(client, "RCP-2002")
    item = _item(tx, "444444")
    for bad in (0, -1, "x", 1.5, True, None):
        r = _submit(client, tx, item, 100, quantity=bad)
        assert r.status_code == 400 and r.get_json()["code"] == "INVALID_QUANTITY", bad
    assert Refund.query.count() == 0


# --- rejection and retries -------------------------------------------------
def test_pending_review_blocks_resubmission(client):
    tx = _transaction(client)
    item = _item(tx, "222222")
    _submit(client, tx, item, 999)
    r = _submit(client, tx, item, 150)
    assert r.status_code == 400 and r.get_json()["existing_refund_status"] == "pending_review"
    assert "waiting for an employee" in r.get_json()["message"]


def test_rejected_return_can_be_retried_within_limit(client, app):
    h = login(client)
    tx = _transaction(client)
    item = _item(tx, "222222")

    first = _submit(client, tx, item, 999).get_json()["refund"]["refund_id"]
    client.post(f"/api/refunds/{first}/reject", headers=h, json={"reason": "wrong item"})
    assert _item(_transaction(client), "222222")["is_refundable"] is True

    second = _submit(client, tx, item, 999)  # retry allowed (limit 1)
    assert second.status_code == 201
    client.post(f"/api/refunds/{second.get_json()['refund']['refund_id']}/reject", headers=h)

    listing = _item(_transaction(client), "222222")
    assert listing["is_refundable"] is False and listing["ineligible_reason"] == "TOO_MANY_ATTEMPTS"
    r = _submit(client, tx, item, 150)
    assert r.status_code == 400 and r.get_json()["code"] == "TOO_MANY_ATTEMPTS"
    assert AuditLog.query.filter_by(event_type="return_attempt_limit_reached").count() == 1


def test_no_retry_when_policy_disallows(client, app):
    app.config["RETURN_RETRY_LIMIT_AFTER_REJECTION"] = 0
    h = login(client)
    tx = _transaction(client)
    item = _item(tx, "222222")
    rid = _submit(client, tx, item, 999).get_json()["refund"]["refund_id"]
    client.post(f"/api/refunds/{rid}/reject", headers=h)
    assert _submit(client, tx, item, 150).get_json()["code"] == "TOO_MANY_ATTEMPTS"


# --- return window --------------------------------------------------------
def test_return_window_enforced(client):
    tx = _tx(client, "RCP-OLD")
    assert tx["within_return_window"] is False
    item = _item(tx, "111111")
    assert item["is_refundable"] is False and item["ineligible_reason"] == "OUTSIDE_RETURN_WINDOW"
    r = _submit(client, tx, item, 250)
    assert r.status_code == 400 and r.get_json()["code"] == "OUTSIDE_RETURN_WINDOW"
    assert Refund.query.count() == 0


def test_return_window_is_configurable(client, app):
    app.config["RETURN_WINDOW_DAYS"] = 60
    tx = _tx(client, "RCP-OLD")
    assert _submit(client, tx, _item(tx, "111111"), 250).status_code == 201


# --- idempotency ----------------------------------------------------------
def test_idempotent_retry_returns_same_refund(client):
    tx = _transaction(client)
    item = _item(tx, "111111")
    key = {"Idempotency-Key": "kiosk-attempt-0001"}
    first = _submit(client, tx, item, 250, headers=key)
    again = _submit(client, tx, item, 250, headers=key)
    assert first.status_code == 201 and again.status_code == 200
    assert again.get_json()["refund"]["refund_id"] == first.get_json()["refund"]["refund_id"]
    assert again.get_json()["refund"]["idempotent_replay"] is True
    assert Refund.query.count() == 1
    assert AuditLog.query.filter_by(event_type="duplicate_refund_blocked").count() == 0


def test_idempotency_key_cannot_be_reused_for_other_item(client):
    tx = _transaction(client)
    key = {"Idempotency-Key": "kiosk-attempt-0002"}
    assert _submit(client, tx, _item(tx, "111111"), 250, headers=key).status_code == 201
    r = _submit(client, tx, _item(tx, "222222"), 150, headers=key)
    assert r.status_code == 422 and r.get_json()["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_invalid_idempotency_key(client):
    tx = _transaction(client)
    r = _submit(client, tx, _item(tx, "111111"), 250, headers={"Idempotency-Key": "bad key!"})
    assert r.status_code == 400 and r.get_json()["code"] == "INVALID_IDEMPOTENCY_KEY"


# --- concurrency (real PostgreSQL row locks) --------------------------------
def _race(client, app, monkeypatch, submissions):
    """Fire submissions simultaneously; the rule check is slowed down so that
    without the row lock every request would pass it."""
    original = returns.count_line_usage

    def slow(line):
        result = original(line)
        time.sleep(0.3)
        return result

    monkeypatch.setattr(returns, "count_line_usage", slow)
    barrier = threading.Barrier(len(submissions))
    results = []

    def worker(body, headers):
        c = app.test_client()
        barrier.wait()
        results.append(c.post("/api/refunds/start", json=body, headers=headers).status_code)

    threads = [threading.Thread(target=worker, args=s) for s in submissions]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return sorted(results)


def test_parallel_submissions_cannot_double_refund(client, app, monkeypatch):
    tx = _transaction(client)
    item = _item(tx, "111111")
    body = {"transaction_id": tx["transaction_id"], "item_id": item["item_id"]}
    statuses = _race(client, app, monkeypatch,
                     [(body, {"Idempotency-Key": f"parallel-{i:04d}"}) for i in range(5)])
    db.session.expire_all()
    assert statuses.count(201) == 1, statuses
    assert Refund.query.count() == 1


def test_parallel_same_key_creates_one_refund(client, app, monkeypatch):
    tx = _tx(client, "RCP-2002")
    item = _item(tx, "444444")
    app.mock_scale.set_weight(100)
    body = {"transaction_id": tx["transaction_id"], "item_id": item["item_id"]}
    key = {"Idempotency-Key": "same-key-parallel"}
    statuses = _race(client, app, monkeypatch, [(body, key)] * 4)
    db.session.expire_all()
    assert statuses.count(201) == 1 and statuses.count(200) == 3, statuses
    assert Refund.query.count() == 1


# --- evidence ---------------------------------------------------------------
def test_capture_cannot_be_reused_for_another_return(client):
    tx = _transaction(client)
    cap = _capture(client)
    a = _submit(client, tx, _item(tx, "111111"), 250, cap["capture_id"]).get_json()["refund"]
    b = _submit(client, tx, _item(tx, "222222"), 150, cap["capture_id"]).get_json()["refund"]
    img_a = db.session.get(Refund, a["refund_id"]).image_path
    img_b = db.session.get(Refund, b["refund_id"]).image_path
    assert img_a and img_b and img_a != img_b  # second return got its own photo


def test_expired_capture_is_not_used(client, app):
    tx = _transaction(client)
    cap = _capture(client)
    path = app.config["CAPTURE_DIR"] / cap["file_name"]
    old = time.time() - app.config["CAPTURE_MAX_AGE_SECONDS"] - 5
    os.utime(path, (old, old))
    r = _submit(client, tx, _item(tx, "111111"), 250, cap["capture_id"]).get_json()["refund"]
    assert db.session.get(Refund, r["refund_id"]).image_path != f"captures/{cap['file_name']}"


def test_photo_required_for_auto_approval_is_configurable(client, app):
    app.mock_camera.connected = False
    app.config["REQUIRE_PHOTO_FOR_AUTO_APPROVAL"] = False
    tx = _transaction(client)
    r = _submit(client, tx, _item(tx, "111111"), 250).get_json()["refund"]
    assert r["decision_status"] == "approved" and r["image_captured"] is False
