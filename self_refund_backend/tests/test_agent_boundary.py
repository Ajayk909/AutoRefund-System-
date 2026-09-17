"""Phase 2: React -> kiosk agent -> Core API, end to end (real agent, real
Core API, mock hardware). Includes outage, lost-response and impersonation
cases: a communication failure must never become a refund."""
import json
import sqlite3

import pytest

from app import db
from app.models import Kiosk, Refund
from app.tenancy import device_auth
from tests.conftest import login
from tests.test_workflows import _item, _submit, _transaction

NOTHING_REFUNDED = "Nothing has been refunded"


def _returns_calls(app):
    return [c for c in app.core_transport.calls if c["path"] == "/api/kiosk/returns"]


def _outbox(app, key):
    return app.kiosk_agent.extensions["agent_store"].outbox_get(key)


# --- the boundary exists ----------------------------------------------------------------
def test_core_api_no_longer_serves_browser_kiosk_or_hardware_routes(app):
    from flask.testing import FlaskClient
    core = FlaskClient(app)  # straight to the Core API, bypassing the agent
    for method, path in (("post", "/api/refunds/start"), ("get", "/api/transactions/RCP-1001"),
                         ("get", "/api/products/lookup/111111"), ("get", "/api/scale/live"),
                         ("get", "/api/scale/read"), ("post", "/api/camera/capture"),
                         ("get", "/api/camera/stream"), ("get", "/api/receipt/scan"),
                         ("get", "/api/hardware/status")):
        assert getattr(core, method)(path).status_code in (404, 405), path
    assert Refund.query.count() == 0


def test_successful_return_goes_through_agent_with_device_credential(client, app):
    tx = _transaction(client)
    r = client.post("/api/refunds/start", headers={"Idempotency-Key": "ui-attempt-0001",
                                                   "Authorization": "Bearer browser-token"},
                    json={"transaction_id": tx["transaction_id"],
                          "item_id": _item(tx, "111111")["item_id"]})
    assert r.status_code == 201 and r.get_json()["refund"]["decision_status"] == "approved"

    [call] = _returns_calls(app)
    assert call["headers"]["Authorization"].startswith("AutoRefund-Dev-Key ardev_")
    assert "browser-token" not in json.dumps(call["headers"])  # browser headers not forwarded
    assert call["headers"]["Idempotency-Key"] == "ui-attempt-0001"
    assert call["files"] == ["image"]
    assert _outbox(app, "ui-attempt-0001")["status"] == "accepted"


def test_browser_cannot_supply_hardware_or_identity_values(client, app):
    tx = _transaction(client)
    app.mock_scale.set_weight(10)
    client.post("/api/refunds/start", json={
        "transaction_id": tx["transaction_id"], "item_id": _item(tx, "111111")["item_id"],
        "measured_weight_grams": 250, "kiosk_id": "KIOSK-OTHER-1", "image_path": "x.jpg",
        "store_id": "s", "retailer_id": "r", "scale": {"weight_grams": 250, "stable": True},
        "camera": {"mock": False}})
    metadata = json.loads(_returns_calls(app)[0]["data"]["metadata"])
    assert metadata["scale"]["weight_grams"] == 10 and metadata["scale"]["device"] == "mock-scale"
    assert metadata["camera"]["mock"] is True
    for field in ("measured_weight_grams", "kiosk_id", "image_path", "store_id", "retailer_id"):
        assert field not in metadata
    refund = Refund.query.one()
    assert float(refund.measured_weight_grams) == 10 and refund.kiosk_code == "KIOSK-001"
    assert refund.decision_status == "pending_review"


def test_kiosk_status_shows_kiosk_store_retailer(client, app):
    status = client.get("/api/kiosk/status").get_json()
    assert status["kiosk"]["state"] == "OK"
    assert (status["kiosk"]["kiosk_code"], status["kiosk"]["store_code"],
            status["kiosk"]["retailer_code"]) == ("KIOSK-001", "STORE-001", "DEMO")
    assert status["hardware"]["scale"]["mock"] is True


# --- Core API unavailable ----------------------------------------------------------------
def test_receipt_lookup_when_core_api_is_down(client, app):
    app.core_transport.down = True
    r = client.get("/api/transactions/RCP-1001")
    assert r.status_code == 503 and r.get_json()["code"] == "CORE_UNAVAILABLE"


def test_submission_when_core_api_is_down_creates_nothing_then_retry_succeeds(client, app):
    tx = _transaction(client)  # identity confirmed while the API was up
    item = _item(tx, "111111")
    key = {"Idempotency-Key": "outage-attempt-0001"}
    app.core_transport.down = True
    r = _submit(client, tx, item, 250, headers=key)
    assert r.status_code == 503
    body = r.get_json()
    assert body["code"] == "CORE_UNAVAILABLE" and NOTHING_REFUNDED in body["message"]
    assert "refund" not in body and body.get("success") is False
    assert Refund.query.count() == 0
    assert _outbox(app, "outage-attempt-0001")["status"] == "unconfirmed"

    app.core_transport.down = False
    r = _submit(client, tx, item, 250, headers=key)  # customer taps Submit again
    assert r.status_code == 201
    assert Refund.query.count() == 1
    row = _outbox(app, "outage-attempt-0001")
    assert row["status"] == "accepted" and row["attempts"] == 2


def test_broken_core_api_is_a_safe_failure(client, app):
    tx = _transaction(client)
    app.core_transport.fail_status = 500
    r = _submit(client, tx, _item(tx, "111111"), 250)
    assert r.status_code == 503 and r.get_json()["code"] == "CORE_UNAVAILABLE"
    assert Refund.query.count() == 0


def test_lost_response_is_not_success_and_retry_does_not_double_refund(client, app):
    tx = _transaction(client)
    item = _item(tx, "111111")
    key = {"Idempotency-Key": "lost-response-0001"}
    app.core_transport.lose_response_once = True
    r = _submit(client, tx, item, 250, headers=key)
    assert r.status_code == 503 and NOTHING_REFUNDED in r.get_json()["message"]
    assert Refund.query.count() == 1  # the Core API did create it...
    assert _outbox(app, "lost-response-0001")["status"] == "unconfirmed"  # ...agent doesn't know

    r = _submit(client, tx, item, 250, headers=key)
    assert r.status_code == 200 and r.get_json()["refund"]["idempotent_replay"] is True
    assert Refund.query.count() == 1


def test_reconciliation_only_records_what_the_core_api_says(client, app):
    tx = _transaction(client)
    app.core_transport.lose_response_once = True
    _submit(client, tx, _item(tx, "111111"), 250, headers={"Idempotency-Key": "reached-core-01"})
    app.core_transport.down = True
    _submit(client, tx, _item(tx, "222222"), 150, headers={"Idempotency-Key": "never-reached-01"})
    app.core_transport.down = False

    result = client.post("/api/outbox/reconcile").get_json()
    assert (result["accepted"], result["not_received"]) == (1, 1)
    assert _outbox(app, "reached-core-01")["status"] == "accepted"
    assert _outbox(app, "never-reached-01")["status"] == "not_received"
    assert Refund.query.count() == 1  # reconciliation never re-sends a return


# --- hardware unavailable -------------------------------------------------------------
def test_scale_unavailable_never_contacts_core_or_creates_refund(client, app):
    tx = _transaction(client)
    app.mock_scale.connected = False
    r = _submit(client, tx, _item(tx, "111111"), 250)
    assert r.status_code == 503 and r.get_json()["code"] == "SCALE_UNAVAILABLE"
    assert _returns_calls(app) == [] and Refund.query.count() == 0


def test_camera_unavailable_sends_return_to_review(client, app):
    tx = _transaction(client)
    app.mock_camera.connected = False
    r = _submit(client, tx, _item(tx, "111111"), 250)
    assert r.get_json()["refund"]["decision_status"] == "pending_review"
    assert _returns_calls(app)[0]["files"] == []


# --- identity ------------------------------------------------------------------------------
def test_agent_with_another_kiosks_key_refuses_to_operate(client, app, tenants):
    """The agent expects KIOSK-OTHER-1 but holds KIOSK-001's key."""
    identity = app.kiosk_agent.extensions["agent_identity"]
    key_headers = identity.auth_headers()  # KIOSK-001's key

    class WrongKey(type(identity)):
        @property
        def expected_kiosk_code(self):
            return "KIOSK-OTHER-1"

        def auth_headers(self):
            return key_headers

    app.kiosk_agent.extensions["agent_identity"] = WrongKey(app)
    r = client.get("/api/transactions/RCP-1001")
    assert r.status_code == 503 and r.get_json()["code"] == "KIOSK_IDENTITY_MISMATCH"
    r = client.post("/api/refunds/start", json={"receipt_number": "RCP-1001", "barcode": "111111"})
    assert r.status_code == 503 and Refund.query.count() == 0
    assert client.get("/api/kiosk/status").get_json()["kiosk"]["state"] == "KIOSK_IDENTITY_MISMATCH"


def test_revoked_key_stops_the_kiosk(client, app):
    assert _transaction(client)
    device_auth.revoke_kiosk_credentials(Kiosk.query.filter_by(code="KIOSK-001").one())
    db.session.commit()
    app.kiosk_agent.extensions["agent_store"].set_config("identity", {})  # drop cached identity
    r = client.get("/api/transactions/RCP-1001")
    assert r.status_code == 503 and r.get_json()["code"] == "KIOSK_NOT_CONFIGURED"


def test_missing_dev_key_is_not_configured(app, tmp_path):
    from agent import create_agent_app
    from agent.core_client import CoreApiClient
    from tests.kiosk_harness import FlaskTestTransport
    agent = create_agent_app({"AGENT_DB_PATH": str(tmp_path / "a.db"), "LOG_DIR": str(tmp_path),
                              "CAPTURE_DIR": tmp_path, "KIOSK_ID": "KIOSK-001", "KIOSK_DEV_KEY": ""},
                             core_client=CoreApiClient(transport=FlaskTestTransport(app)))
    r = agent.test_client().get("/api/transactions/RCP-1001")
    assert r.status_code == 503 and r.get_json()["code"] == "KIOSK_NOT_CONFIGURED"


# --- local safety -----------------------------------------------------------------------------
def test_other_websites_cannot_post_to_the_agent(client, app):
    tx = _transaction(client)
    body = {"transaction_id": tx["transaction_id"], "item_id": _item(tx, "111111")["item_id"]}
    r = client.post("/api/refunds/start", json=body, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and Refund.query.count() == 0
    r = client.post("/api/refunds/start", json=body, headers={"Origin": "http://127.0.0.1:5173"})
    assert r.status_code == 201


def test_agent_refuses_non_loopback_host(tmp_path):
    from agent import create_agent_app
    with pytest.raises(RuntimeError, match="127.0.0.1"):
        create_agent_app({"AGENT_HOST": "0.0.0.0", "AGENT_DB_PATH": str(tmp_path / "a.db"),
                          "LOG_DIR": str(tmp_path), "CAPTURE_DIR": tmp_path})


def test_session_and_local_store_hold_no_customer_data(client, app):
    tx = _transaction(client)
    assert client.get("/api/kiosk/status").get_json()["session"]["receipt_number"] == "RCP-1001"
    _submit(client, tx, _item(tx, "111111"), 250, headers={"Idempotency-Key": "pii-check-0001"})
    staff = login(client)
    client.get("/api/refunds/logs", headers=staff)

    path = app.kiosk_agent.config["AGENT_DB_PATH"]
    with sqlite3.connect(path) as conn:
        dump = "\n".join(conn.iterdump())
    for secret in ("c@test.com", "Card", "Coca Cola", "2.99", "ardev_", "admin123"):
        assert secret not in dump, secret
    assert client.post("/api/session/end").status_code == 200
    assert client.get("/api/kiosk/status").get_json()["session"] is None


def test_employee_flow_is_unchanged_after_agent_return(client, app):
    tx = _transaction(client)
    refund_id = _submit(client, tx, _item(tx, "222222"), 999).get_json()["refund"]["refund_id"]
    staff = login(client)
    [pending] = client.get("/api/refunds/pending", headers=staff).get_json()["refunds"]
    assert pending["refund_id"] == refund_id and pending["has_image"] is True
    assert client.get(pending["image_url"], headers=staff).status_code == 200
    assert client.post(f"/api/refunds/{refund_id}/approve", headers=staff).status_code == 200
    r = client.post(f"/api/refunds/{refund_id}/mark-refunded", headers=staff,
                    json={"payment_reference": "POS-P2"})
    assert r.get_json()["refund"]["decision_status"] == "refunded"
