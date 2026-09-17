"""Phase 1: cross-tenant access through the API is prevented.

Retailer OTHER deliberately re-uses DEMO's barcode 111111 and receipt number
RCP-1001 (see the ``tenants`` fixture)."""
from app import db
from app.models import AuditLog, Kiosk, Refund, Store
from tests.conftest import login
from tests.test_workflows import _item


def _use_kiosk(app, code):
    app.config["KIOSK_ID"] = code


def _receipt(client, number="RCP-1001"):
    r = client.get(f"/api/transactions/{number}")
    return r.status_code, (r.get_json().get("transaction") if r.status_code == 200 else None)


def _return(client, app, tx, item, grams, **extra):
    app.mock_scale.set_weight(grams)
    return client.post("/api/refunds/start", json={
        "transaction_id": tx["transaction_id"], "item_id": item["item_id"], **extra})


# --- kiosk side -----------------------------------------------------------------------
def test_product_lookup_uses_kiosk_retailer_catalog(client, app, tenants):
    assert client.get("/api/products/lookup/111111").get_json()["product"]["name"] == "Coca Cola Can"
    _use_kiosk(app, "KIOSK-OTHER-1")
    assert client.get("/api/products/lookup/111111").get_json()["product"]["name"] == "Other Retailer Soda"
    # DEMO-only barcode is unknown to OTHER's kiosk
    assert client.get("/api/products/lookup/222222").status_code == 404


def test_same_receipt_number_returns_each_retailers_own_receipt(client, app, tenants):
    _, demo_tx = _receipt(client)
    _use_kiosk(app, "KIOSK-OTHER-1")
    _, other_tx = _receipt(client)
    assert demo_tx["transaction_id"] != other_tx["transaction_id"]
    assert {i["name"] for i in demo_tx["items"]} == {"Coca Cola Can", "Potato Chips"}
    assert [i["name"] for i in other_tx["items"]] == ["Other Retailer Soda"]


def test_other_retailers_receipt_is_not_found(client, app, tenants):
    from app.tenancy import setup
    setup.create_receipt(tenants["other_store"], "RCP-ONLY-OTHER", [(tenants["other_product"], 1)])
    db.session.commit()
    assert _receipt(client, "RCP-ONLY-OTHER")[0] == 404


def test_kiosk_cannot_return_other_retailers_items_by_id(client, app, tenants):
    _use_kiosk(app, "KIOSK-OTHER-1")
    _, other_tx = _receipt(client)
    other_item = other_tx["items"][0]

    _use_kiosk(app, "KIOSK-001")
    r = _return(client, app, other_tx, other_item, 400, product_id=other_item["product_id"])
    assert r.status_code == 404 and r.get_json()["code"] == "RECEIPT_NOT_FOUND"

    # own receipt, but another retailer's product id
    _, demo_tx = _receipt(client)
    r = client.post("/api/refunds/start", json={"transaction_id": demo_tx["transaction_id"],
                                                "product_id": other_item["product_id"]})
    assert r.status_code == 404 and r.get_json()["code"] == "PRODUCT_NOT_FOUND"
    assert Refund.query.count() == 0


def test_duplicate_rules_are_per_retailer(client, app, tenants):
    _, demo_tx = _receipt(client)
    assert _return(client, app, demo_tx, _item(demo_tx, "111111"), 250).status_code == 201

    _use_kiosk(app, "KIOSK-OTHER-1")
    _, other_tx = _receipt(client)
    item = _item(other_tx, "111111")
    assert item["is_refundable"] is True
    r = _return(client, app, other_tx, item, 400)
    assert r.status_code == 201 and r.get_json()["refund"]["decision_status"] == "approved"
    assert r.get_json()["refund"]["refund_amount"] == 9.99


def test_idempotency_key_from_other_retailer_is_not_replayed(client, app, tenants):
    _, demo_tx = _receipt(client)
    key = {"Idempotency-Key": "shared-key-across-tenants"}
    app.mock_scale.set_weight(250)
    assert client.post("/api/refunds/start", headers=key, json={
        "transaction_id": demo_tx["transaction_id"],
        "item_id": _item(demo_tx, "111111")["item_id"]}).status_code == 201

    _use_kiosk(app, "KIOSK-OTHER-1")
    _, other_tx = _receipt(client)
    app.mock_scale.set_weight(400)
    r = client.post("/api/refunds/start", headers=key, json={
        "transaction_id": other_tx["transaction_id"], "item_id": other_tx["items"][0]["item_id"]})
    assert r.status_code == 422 and "refund" not in r.get_json()


def test_return_records_kiosk_store_and_retailer(client, app, tenants):
    _use_kiosk(app, "KIOSK-002")  # DEMO store 2; receipt was bought at STORE-001
    _, tx = _receipt(client)
    refund_id = _return(client, app, tx, _item(tx, "111111"), 250).get_json()["refund"]["refund_id"]
    refund = db.session.get(Refund, refund_id)
    assert refund.retailer_id == tenants["demo"].retailer_id
    assert refund.store_id == tenants["demo_store2"].store_id
    assert db.session.get(Kiosk, refund.kiosk_id).code == "KIOSK-002"
    assert refund.kiosk_code == "KIOSK-002"
    audit = AuditLog.query.filter_by(event_type="refund_started").one()
    assert (audit.retailer_id, audit.store_id) == (refund.retailer_id, refund.store_id)


# --- staff side -------------------------------------------------------------------------
def _other_pending_refund(client, app):
    _use_kiosk(app, "KIOSK-OTHER-1")
    _, tx = _receipt(client)
    body = _return(client, app, tx, tx["items"][0], 5).get_json()["refund"]
    assert body["decision_status"] == "pending_review"
    _use_kiosk(app, "KIOSK-001")
    return body["refund_id"]


def test_staff_cannot_see_or_act_on_other_retailers_returns(client, app, tenants):
    other_id = _other_pending_refund(client, app)
    demo = login(client)

    assert client.get("/api/refunds/pending", headers=demo).get_json()["refunds"] == []
    assert client.get("/api/refunds/logs", headers=demo).get_json()["refunds"] == []
    for action in ("approve", "reject"):
        r = client.post(f"/api/refunds/{other_id}/{action}", headers=demo)
        assert r.status_code == 404, action
    assert client.post(f"/api/refunds/{other_id}/mark-refunded", headers=demo,
                       json={"payment_reference": "X"}).status_code == 404
    assert client.get(f"/api/refunds/{other_id}/image", headers=demo).status_code == 404

    filename = db.session.get(Refund, other_id).image_path.split("/")[-1]
    assert client.get(f"/api/captures/{filename}", headers=demo).status_code == 404
    assert db.session.get(Refund, other_id).decision_status == "pending_review"

    # the owning retailer's staff can
    other = login(client, "other_admin", "other123")
    pending = client.get("/api/refunds/pending", headers=other).get_json()["refunds"]
    assert [p["refund_id"] for p in pending] == [other_id]
    assert pending[0]["kiosk_code"] == "KIOSK-OTHER-1" and pending[0]["store_code"] == "O-001"
    assert client.get(f"/api/captures/{filename}", headers=other).status_code == 200
    assert client.post(f"/api/refunds/{other_id}/approve", headers=other).status_code == 200


def test_store_limited_staff_only_see_their_store(client, app, tenants):
    _, tx = _receipt(client)
    store1_id = _return(client, app, tx, _item(tx, "222222"), 999).get_json()["refund"]["refund_id"]
    _use_kiosk(app, "KIOSK-002")
    store2_id = _return(client, app, tx, _item(tx, "111111"), 1).get_json()["refund"]["refund_id"]

    clerk = login(client, "store2_clerk", "clerk123")
    pending = {p["refund_id"] for p in
               client.get("/api/refunds/pending", headers=clerk).get_json()["refunds"]}
    assert pending == {store2_id}
    assert client.post(f"/api/refunds/{store1_id}/approve", headers=clerk).status_code == 404
    assert client.post(f"/api/refunds/{store2_id}/approve", headers=clerk).status_code == 200
    me = client.get("/api/staff/me", headers=clerk).get_json()["staff"]
    assert me["store_code"] == "STORE-002"

    # retailer-wide admin sees both stores
    admin = login(client)
    logs = {r["refund_id"] for r in client.get("/api/refunds/logs", headers=admin).get_json()["refunds"]}
    assert logs == {store1_id, store2_id}


def test_staff_audit_events_carry_tenant(client, app, tenants):
    _, tx = _receipt(client)
    refund_id = _return(client, app, tx, _item(tx, "222222"), 999).get_json()["refund"]["refund_id"]
    admin = login(client)
    client.post(f"/api/refunds/{refund_id}/reject", headers=admin, json={"reason": "x"})
    event = AuditLog.query.filter_by(event_type="refund_rejected_by_staff").one()
    store = db.session.get(Store, event.store_id)
    assert event.retailer_id == tenants["demo"].retailer_id and store.code == "STORE-001"
    login_event = AuditLog.query.filter_by(event_type="staff_login").first()
    assert login_event.retailer_id == tenants["demo"].retailer_id
