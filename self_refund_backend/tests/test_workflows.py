"""End-to-end API tests of the AutoRefund business workflows (mock hardware)."""
from app.models import AuditLog, Refund


def _transaction(client):
    r = client.get("/api/transactions/RCP-1001")
    assert r.status_code == 200
    return r.get_json()["transaction"]


def _item(tx, barcode):
    return next(i for i in tx["items"] if i["barcode"] == barcode)


def _capture(client):
    r = client.post("/api/camera/capture")
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def _submit(client, tx, item, weight, image_path=None):
    return client.post("/api/refunds/start", json={
        "transaction_id": tx["transaction_id"],
        "item_id": item["item_id"],
        "product_id": item["product_id"],
        "measured_weight_grams": weight,
        "image_path": image_path,
    })


def test_health(client):
    assert client.get("/api/health").get_json()["status"] == "ok"


def test_product_lookup(client):
    r = client.get("/api/products/lookup/111111")
    assert r.status_code == 200
    assert r.get_json()["product"]["name"] == "Coca Cola Can"
    assert client.get("/api/products/lookup/000").status_code == 404


def test_unknown_receipt(client):
    assert client.get("/api/transactions/NOPE").status_code == 404


def test_normal_return_is_approved_with_image(client, app):
    tx = _transaction(client)
    item = _item(tx, "111111")
    assert item["is_refundable"] is True

    weight = client.get("/api/scale/live").get_json()
    assert weight["success"] and weight["weight_grams"] == 250.0

    cap = _capture(client)
    assert (app.config["CAPTURE_DIR"] / cap["filename"]).is_file()

    r = _submit(client, tx, item, weight["weight_grams"], cap["image_path"])
    assert r.status_code == 201
    refund = r.get_json()["refund"]
    assert refund["decision_status"] == "approved"
    assert refund["weight_match"] is True
    assert refund["refund_amount"] == 2.99
    assert refund["image_path"] == cap["image_path"]

    # evidence image is served back
    img = client.get(cap["image_url"])
    assert img.status_code == 200 and img.mimetype == "image/jpeg"

    # audit trail recorded
    logs = AuditLog.query.filter_by(event_type="refund_started").all()
    assert len(logs) == 1 and logs[0].details["image_captured"] is True

    # item no longer refundable
    assert _item(_transaction(client), "111111")["is_refundable"] is False


def test_weight_tolerance_boundaries(client):
    tx = _transaction(client)
    # 150 g +/-10% -> 135..165 inclusive
    r = _submit(client, tx, _item(tx, "222222"), 165)
    assert r.get_json()["refund"]["decision_status"] == "approved"


def test_weight_mismatch_goes_to_review(client):
    tx = _transaction(client)
    r = _submit(client, tx, _item(tx, "222222"), 400)
    assert r.status_code == 201
    refund = r.get_json()["refund"]
    assert refund["decision_status"] == "pending_review"
    assert refund["weight_match"] is False

    pending = client.get("/api/refunds/pending").get_json()["refunds"]
    assert [p["refund_id"] for p in pending] == [refund["refund_id"]]


def test_duplicate_return_is_blocked_and_logged(client):
    tx = _transaction(client)
    item = _item(tx, "111111")
    assert _submit(client, tx, item, 250).status_code == 201

    r = _submit(client, tx, item, 250)
    assert r.status_code == 400
    assert r.get_json()["existing_refund_status"] == "approved"
    assert Refund.query.count() == 1
    assert AuditLog.query.filter_by(event_type="duplicate_refund_blocked").count() == 1


def test_wrong_product_rejected(client):
    r = client.post("/api/refunds/start", json={
        "receipt_number": "RCP-1001", "barcode": "999999",
        "measured_weight_grams": 100,
    })
    assert r.status_code == 400
    assert "not part" in r.get_json()["message"]


def test_missing_or_invalid_weight(client):
    tx = _transaction(client)
    item = _item(tx, "111111")
    assert client.post("/api/refunds/start", json={
        "transaction_id": tx["transaction_id"], "product_id": item["product_id"],
    }).status_code == 400
    assert _submit(client, tx, item, "abc").status_code == 400
    assert _submit(client, tx, item, -5).status_code == 400
    assert Refund.query.count() == 0


def test_fake_image_path_is_not_stored(client):
    tx = _transaction(client)
    r = _submit(client, tx, _item(tx, "111111"), 250, "mock_images/test.jpg")
    assert r.status_code == 201
    assert r.get_json()["refund"]["image_path"] is None


def test_employee_approve_and_reject(client):
    tx = _transaction(client)
    a = _submit(client, tx, _item(tx, "111111"), 10).get_json()["refund"]
    b = _submit(client, tx, _item(tx, "222222"), 10).get_json()["refund"]
    assert a["decision_status"] == b["decision_status"] == "pending_review"

    assert client.post(f"/api/refunds/{a['refund_id']}/approve").status_code == 200
    assert client.post(f"/api/refunds/{b['refund_id']}/reject").status_code == 200

    statuses = {r["refund_id"]: r["decision_status"]
                for r in client.get("/api/refunds/logs").get_json()["refunds"]}
    assert statuses == {a["refund_id"]: "approved", b["refund_id"]: "rejected"}
    assert client.get("/api/refunds/pending").get_json()["refunds"] == []
    assert Refund.query.filter_by(refund_id=a["refund_id"]).first().staff_override is True


def test_logs_date_filter_validation(client):
    assert client.get("/api/refunds/logs?start_date=bad").status_code == 400
    assert client.get("/api/refunds/logs?start_date=2020-01-01&end_date=2099-01-01").status_code == 200


def test_staff_login(client):
    ok = client.post("/api/staff/login", json={"username": "admin1", "password": "admin123"})
    assert ok.status_code == 200 and ok.get_json()["staff"]["role"] == "admin"
    assert client.post("/api/staff/login", json={"username": "admin1", "password": "x"}).status_code == 401
    assert client.post("/api/staff/login", json={"username": "ghost", "password": "x"}).status_code == 401
    assert client.post("/api/staff/login", json={}).status_code == 400


def test_camera_failure_is_graceful(client, app):
    app.mock_camera.connected = False
    r = client.post("/api/camera/capture")
    assert r.status_code == 503
    assert r.get_json()["message"] == "Camera unavailable. Please try again."
    assert client.get("/api/camera/health").status_code == 500


def test_scale_failure_is_graceful(client, app):
    app.mock_scale.connected = False
    r = client.get("/api/scale/live")
    assert r.status_code == 503
    body = r.get_json()
    assert body["connected"] is False and body["weight_grams"] == 0
    assert client.get("/api/scale/read").status_code == 503


def test_receipt_scan_via_camera(client, app):
    assert client.get("/api/receipt/scan").get_json()["found"] is False
    app.mock_camera.next_barcode = "RCP-1001"
    body = client.get("/api/receipt/scan").get_json()
    assert body["found"] is True and body["barcode"] == "RCP-1001"


def test_camera_preview_and_hardware_status(client):
    r = client.get("/api/camera/preview")
    assert r.status_code == 200 and r.mimetype == "image/jpeg"
    status = client.get("/api/hardware/status").get_json()
    assert status["camera"]["mock"] is True and status["scale"]["mock"] is True
