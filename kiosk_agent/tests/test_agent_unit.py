"""Kiosk agent behaviour without a database or real Core API."""
import sqlite3
from datetime import timedelta

import pytest
import requests

from agent import captures
from agent.core_client import CoreApiClient, CoreUnavailable, RequestsTransport
from agent.identity import DevelopmentKeyIdentity
from agent.store import AgentStore, now

RETURN = ("POST", "/api/kiosk/returns")
CREATED = (201, {"success": True, "refund": {"refund_id": "r-1", "decision_status": "approved"}})


def submit(agent, key="unit-key-0001", **body):
    body = {"transaction_id": "t-1", "item_id": "i-1", **body}
    headers = {"Idempotency-Key": key} if key else {}
    return agent.test_client().post("/api/refunds/start", json=body, headers=headers)


def store_of(agent):
    return agent.extensions["agent_store"]


# --- Core API client -------------------------------------------------------------------
@pytest.mark.parametrize("failure", [requests.ConnectionError("down"), requests.ReadTimeout("slow")])
def test_client_turns_network_errors_into_core_unavailable(fake_core, failure):
    fake_core.routes[("GET", "/x")] = failure
    with pytest.raises(CoreUnavailable):
        CoreApiClient(transport=fake_core).call(DevelopmentKeyIdentity("K", "ardev_k"), "GET", "/x")


@pytest.mark.parametrize("answer", [(500, {"message": "boom"}), (502, None), (200, None), (200, ["list"])])
def test_client_treats_server_errors_and_non_json_as_unavailable(fake_core, answer):
    fake_core.routes[("GET", "/x")] = answer
    with pytest.raises(CoreUnavailable):
        CoreApiClient(transport=fake_core).call(DevelopmentKeyIdentity("K", "ardev_k"), "GET", "/x")


def test_requests_transport_has_a_timeout():
    transport = RequestsTransport("http://127.0.0.1:9", timeout=0.5)
    with pytest.raises(requests.RequestException):
        transport.send("GET", "/api/health")


def test_identity_never_prints_its_key():
    identity = DevelopmentKeyIdentity("KIOSK-001", "ardev_secret-value")
    assert "secret" not in repr(identity)
    assert identity.auth_headers() == {"Authorization": "AutoRefund-Dev-Key ardev_secret-value"}
    assert DevelopmentKeyIdentity("KIOSK-001", "").configured is False


# --- submission safety -----------------------------------------------------------------
def test_successful_submission_records_outbox_and_deletes_photo(agent, fake_core, tmp_path):
    fake_core.routes[RETURN] = CREATED
    r = submit(agent)
    assert r.status_code == 201
    row = store_of(agent).outbox_get("unit-key-0001")
    assert (row["status"], row["refund_id"], row["attempts"]) == ("accepted", "r-1", 1)
    assert list((tmp_path / "captures").glob("*.jpg")) == []  # local photo removed after upload
    call = next(c for c in fake_core.calls if c["path"] == "/api/kiosk/returns")
    assert call["headers"]["Idempotency-Key"] == "unit-key-0001"
    assert call["headers"]["Authorization"] == "AutoRefund-Dev-Key ardev_unit-test-key"


@pytest.mark.parametrize("failure", [requests.ConnectionError("down"), requests.ReadTimeout("slow"),
                                     (500, None), (503, {"message": "maintenance"})])
def test_core_failure_is_never_success(agent, fake_core, failure):
    submit(agent, key="warm-up-key-01")  # identity verified while the API worked
    fake_core.routes[RETURN] = failure
    r = submit(agent)
    body = r.get_json()
    assert r.status_code == 503 and body["success"] is False and "refund" not in body
    assert body["code"] == "CORE_UNAVAILABLE" and "Nothing has been refunded" in body["message"]
    assert store_of(agent).outbox_get("unit-key-0001")["status"] == "unconfirmed"


def test_retry_after_outage_reuses_the_same_key(agent, fake_core):
    fake_core.routes[RETURN] = requests.ConnectionError("down")
    submit(agent)
    fake_core.routes[RETURN] = CREATED
    assert submit(agent).status_code == 201
    keys = [c["headers"]["Idempotency-Key"] for c in fake_core.calls if c["path"] == "/api/kiosk/returns"]
    assert keys == ["unit-key-0001", "unit-key-0001"]
    assert store_of(agent).outbox_get("unit-key-0001")["attempts"] == 2


def test_agent_generates_a_key_when_the_browser_sends_none(agent, fake_core):
    fake_core.routes[RETURN] = CREATED
    submit(agent, key=None)
    call = next(c for c in fake_core.calls if c["path"] == "/api/kiosk/returns")
    assert call["headers"]["Idempotency-Key"].startswith("agent-")


def test_core_business_answer_is_passed_through_and_final(agent, fake_core):
    fake_core.routes[RETURN] = (400, {"success": False, "code": "DUPLICATE_RETURN",
                                      "message": "This item has already been submitted for refund."})
    r = submit(agent)
    assert r.status_code == 400 and r.get_json()["code"] == "DUPLICATE_RETURN"
    assert store_of(agent).outbox_get("unit-key-0001")["status"] == "rejected"


def test_scale_unavailable_or_unstable_never_calls_core(agent, fake_core, devices):
    camera, scale = devices
    scale.connected = False
    assert submit(agent).get_json()["code"] == "SCALE_UNAVAILABLE"
    scale.connected = True
    scale.set_weight(0)
    assert submit(agent).get_json()["code"] == "SCALE_NOT_READY"
    assert [c for c in fake_core.calls if c["path"] == "/api/kiosk/returns"] == []
    assert store_of(agent).outbox_counts() == {}


def test_camera_failure_still_submits_without_photo(agent, fake_core, devices):
    devices[0].connected = False
    fake_core.routes[RETURN] = CREATED
    submit(agent)
    call = next(c for c in fake_core.calls if c["path"] == "/api/kiosk/returns")
    assert call["files"] == {}


def test_browser_values_are_not_forwarded(agent, fake_core, devices):
    import json
    devices[1].set_weight(42)
    fake_core.routes[RETURN] = CREATED
    submit(agent, measured_weight_grams=250, kiosk_id="OTHER", image_path="C:/x.jpg",
           retailer_id="r", store_id="s", scale={"weight_grams": 250})
    metadata = json.loads(next(c for c in fake_core.calls if c["path"] == "/api/kiosk/returns")
                          ["data"]["metadata"])
    assert metadata["scale"]["weight_grams"] == 42
    assert set(metadata) <= {"transaction_id", "item_id", "quantity", "scale", "camera",
                             "receipt_number", "product_id", "barcode"}


@pytest.mark.parametrize("answer,code", [
    ((401, {"code": "DEVICE_AUTH_FAILED"}), "KIOSK_NOT_CONFIGURED"),
    ((403, {"code": "KIOSK_DISABLED"}), "KIOSK_DISABLED"),
    ((200, {"success": True, "kiosk": {"kiosk_code": "KIOSK-999"}}), "KIOSK_IDENTITY_MISMATCH"),
])
def test_identity_problems_block_everything(agent, fake_core, answer, code):
    fake_core.routes[("GET", "/api/kiosk/me")] = answer
    fake_core.routes[RETURN] = CREATED
    for response in (agent.test_client().get("/api/transactions/RCP-1"), submit(agent)):
        assert response.status_code == 503 and response.get_json()["code"] == code
    assert [c for c in fake_core.calls if c["path"] == "/api/kiosk/returns"] == []


def test_core_down_during_identity_check_is_safe(agent, fake_core):
    fake_core.routes[("GET", "/api/kiosk/me")] = requests.ConnectionError("down")
    assert submit(agent).get_json()["code"] == "CORE_UNAVAILABLE"
    status = agent.test_client().get("/api/kiosk/status").get_json()
    assert status["kiosk"]["state"] == "CORE_UNAVAILABLE"


def test_reconcile_never_resends(agent, fake_core):
    fake_core.routes[RETURN] = requests.ConnectionError("down")
    submit(agent, key="unit-key-a001")
    submit(agent, key="unit-key-b001")
    fake_core.routes[("GET", "/api/kiosk/returns/by-key/unit-key-a001")] = (200, {"refund": {"refund_id": "r-9"}})
    before = len([c for c in fake_core.calls if c["path"] == "/api/kiosk/returns"])
    result = agent.test_client().post("/api/outbox/reconcile").get_json()
    assert (result["accepted"], result["not_received"]) == (1, 1)
    assert len([c for c in fake_core.calls if c["path"] == "/api/kiosk/returns"]) == before
    assert store_of(agent).outbox_get("unit-key-a001")["refund_id"] == "r-9"


# --- captures ----------------------------------------------------------------------------
def test_capture_is_single_use_and_expires(agent, fake_core, tmp_path):
    fake_core.routes[RETURN] = CREATED
    client = agent.test_client()
    cap = client.post("/api/camera/capture").get_json()
    store = store_of(agent)
    capture_dir = agent.config["CAPTURE_DIR"]
    assert captures.usable_capture(cap["capture_id"], capture_dir, store, 900)

    submit(agent, capture_id=cap["capture_id"])
    assert store.get_capture(cap["capture_id"])["used_at"] is not None
    assert captures.usable_capture(cap["capture_id"], capture_dir, store, 900) is None

    cap2 = client.post("/api/camera/capture").get_json()
    store.set_capture_created(cap2["capture_id"], now() - timedelta(seconds=901))
    assert captures.usable_capture(cap2["capture_id"], capture_dir, store, 900) is None
    for bad in ("../../x", "ABC", None, "0" * 31):
        assert captures.usable_capture(bad, capture_dir, store, 900) is None


# --- local store and HTTP safety ---------------------------------------------------------------
def test_store_schema_has_no_customer_data_columns(tmp_path):
    AgentStore(tmp_path / "s.sqlite3")
    with sqlite3.connect(tmp_path / "s.sqlite3") as conn:
        columns = {row[1] for table in ("kiosk_config", "sessions", "captures", "outbox")
                   for row in conn.execute(f"PRAGMA table_info({table})")}
    for forbidden in ("email", "full_name", "customer", "payment", "price", "amount", "card", "phone"):
        assert not any(forbidden in c for c in columns), forbidden


def test_session_expires(tmp_path):
    store = AgentStore(tmp_path / "s.sqlite3")
    store.touch_session(900, receipt_number="RCP-1")
    assert store.current_session(900)["receipt_number"] == "RCP-1"
    assert store.current_session(0) is None


def test_cross_origin_posts_are_refused(agent):
    client = agent.test_client()
    assert client.post("/api/session/end", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/session/end", headers={"Origin": "http://127.0.0.1:5173"}).status_code == 200
    assert client.get("/api/health", headers={"Origin": "https://evil.example"}).status_code == 200


def test_agent_only_listens_on_loopback(tmp_path):
    from agent import create_agent_app
    for host in ("0.0.0.0", "192.168.1.5"):
        with pytest.raises(RuntimeError):
            create_agent_app({"AGENT_HOST": host, "AGENT_DB_PATH": str(tmp_path / "a.db"),
                              "LOG_DIR": str(tmp_path), "CAPTURE_DIR": tmp_path})
