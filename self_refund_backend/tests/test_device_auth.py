"""Phase 2: kiosk agent -> Core API device authentication and the trusted
kiosk boundary (called directly, without an agent)."""
import io
import json
from datetime import timedelta

import pytest

from app import create_app, db
from app.models import Kiosk, KioskCredential, Refund
from app.tenancy import device_auth, setup
from app.timeutil import utcnow

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 200


def _key(code="KIOSK-001"):
    key = device_auth.issue_development_key(Kiosk.query.filter_by(code=code).one())
    db.session.commit()
    return {"Authorization": f"AutoRefund-Dev-Key {key}"}


def _core(app):
    """A plain Core API client (no agent in between)."""
    from flask.testing import FlaskClient
    return FlaskClient(app)


def _receipt(core, headers, number="RCP-1001"):
    return core.get(f"/api/kiosk/receipts/{number}", headers=headers)


def _submit(core, headers, tx, barcode, grams, key="device-key-0001", stable=True, image=JPEG,
            **meta):
    item = next(i for i in tx["items"] if i["barcode"] == barcode)
    metadata = {"transaction_id": tx["transaction_id"], "item_id": item["item_id"],
                "scale": {"weight_grams": grams, "stable": stable, "device": "test-scale"},
                "camera": {"device": "test-camera"}, **meta}
    data = {"metadata": json.dumps(metadata)}
    if image is not None:
        data["image"] = (io.BytesIO(image), "anything.jpg")
    h = dict(headers)
    if key:
        h["Idempotency-Key"] = key
    return core.post("/api/kiosk/returns", data=data, headers=h, content_type="multipart/form-data")


# --- authentication ---------------------------------------------------------------
@pytest.mark.parametrize("header", [None, "Bearer abc", "AutoRefund-Dev-Key", "AutoRefund-Dev-Key nope",
                                    "AutoRefund-Dev-Key ardev_unknown"])
def test_kiosk_endpoints_reject_missing_or_bad_credentials(app, header):
    core = _core(app)
    headers = {"Authorization": header} if header else {}
    for method, path in (("get", "/api/kiosk/me"), ("get", "/api/kiosk/receipts/RCP-1001"),
                         ("get", "/api/kiosk/products/111111"), ("post", "/api/kiosk/returns")):
        r = getattr(core, method)(path, headers=headers)
        assert r.status_code == 401, (path, header)
        assert r.get_json()["code"] in ("DEVICE_AUTH_REQUIRED", "DEVICE_AUTH_FAILED")
    assert Refund.query.count() == 0


def test_staff_token_is_not_a_kiosk_credential(app):
    core = _core(app)
    token = core.post("/api/staff/login", json={"username": "admin1", "password": "admin123"}
                      ).get_json()["token"]
    assert core.get("/api/kiosk/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_key_is_hashed_prefixed_and_resolves_kiosk_store_retailer(app):
    core = _core(app)
    headers = _key()
    plain = headers["Authorization"].split(" ", 1)[1]
    assert plain.startswith("ardev_")
    stored = KioskCredential.query.one()
    assert plain not in stored.secret_hash and len(stored.secret_hash) == 64
    me = core.get("/api/kiosk/me", headers=headers).get_json()["kiosk"]
    assert (me["kiosk_code"], me["store_code"], me["retailer_code"]) == \
        ("KIOSK-001", "STORE-001", "DEMO")
    assert KioskCredential.query.one().last_used_at is not None


def test_expired_and_revoked_keys_are_rejected(app):
    core = _core(app)
    headers = _key()
    credential = KioskCredential.query.one()
    credential.expires_at = utcnow() - timedelta(seconds=1)
    db.session.commit()
    assert core.get("/api/kiosk/me", headers=headers).status_code == 401

    headers = _key()
    assert core.get("/api/kiosk/me", headers=headers).status_code == 200
    device_auth.revoke_kiosk_credentials(Kiosk.query.filter_by(code="KIOSK-001").one())
    db.session.commit()
    assert core.get("/api/kiosk/me", headers=headers).status_code == 401


def test_disabled_kiosk_key_is_refused(app):
    core = _core(app)
    headers = _key()
    Kiosk.query.filter_by(code="KIOSK-001").one().is_active = False
    db.session.commit()
    r = core.get("/api/kiosk/receipts/RCP-1001", headers=headers)
    assert r.status_code == 403 and r.get_json()["code"] == "KIOSK_DISABLED"


def test_agent_cannot_impersonate_another_kiosk(app, tenants):
    """Identity comes only from the key: claims in headers/body are ignored."""
    core = _core(app)
    headers = _key("KIOSK-001")
    headers["X-Kiosk-Id"] = "KIOSK-OTHER-1"
    me = core.get("/api/kiosk/me?kiosk=KIOSK-OTHER-1", headers=headers).get_json()["kiosk"]
    assert me["kiosk_code"] == "KIOSK-001"

    tx = _receipt(core, headers).get_json()["transaction"]
    assert {i["name"] for i in tx["items"]} == {"Coca Cola Can", "Potato Chips"}  # DEMO's receipt
    r = _submit(core, headers, tx, "111111", 250, kiosk_id="KIOSK-OTHER-1", kiosk_code="KIOSK-002",
                store_id=str(tenants["other_store"].store_id))
    refund = db.session.get(Refund, r.get_json()["refund"]["refund_id"])
    assert refund.kiosk_code == "KIOSK-001" and refund.retailer_id == tenants["demo"].retailer_id


# --- the trusted boundary ------------------------------------------------------------
def test_device_return_is_created_with_uploaded_evidence(app):
    core = _core(app)
    headers = _key()
    tx = _receipt(core, headers).get_json()["transaction"]
    r = _submit(core, headers, tx, "111111", 250)
    assert r.status_code == 201, r.get_json()
    body = r.get_json()["refund"]
    assert body["decision_status"] == "approved" and body["image_captured"] is True
    refund = db.session.get(Refund, body["refund_id"])
    assert refund.image_path.startswith("captures/evidence_")  # name chosen by the Core API
    assert refund.image_path != "captures/anything.jpg"
    assert len(refund.image_sha256) == 64
    assert (app.config["CAPTURE_DIR"] / refund.image_path.split("/")[1]).read_bytes() == JPEG

    again = _submit(core, headers, tx, "111111", 250)  # same idempotency key
    assert again.status_code == 200 and again.get_json()["refund"]["idempotent_replay"] is True
    by_key = core.get("/api/kiosk/returns/by-key/device-key-0001", headers=headers)
    assert by_key.get_json()["refund"]["refund_id"] == body["refund_id"]


def test_device_return_requires_idempotency_key(app):
    core = _core(app)
    headers = _key()
    tx = _receipt(core, headers).get_json()["transaction"]
    r = _submit(core, headers, tx, "111111", 250, key=None)
    assert r.status_code == 400 and r.get_json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"


@pytest.mark.parametrize("grams,stable", [(0, True), (-5, True), (250, False), ("abc", True),
                                          (None, True), ("NaN", True)])
def test_core_refuses_unusable_scale_readings(app, grams, stable):
    core = _core(app)
    headers = _key()
    tx = _receipt(core, headers).get_json()["transaction"]
    r = _submit(core, headers, tx, "111111", grams, stable=stable)
    assert r.status_code == 409 and r.get_json()["code"] == "SCALE_NOT_READY"
    assert Refund.query.count() == 0


def test_core_validates_evidence_bytes(app):
    core = _core(app)
    headers = _key()
    tx = _receipt(core, headers).get_json()["transaction"]
    r = _submit(core, headers, tx, "111111", 250, image=b"<html>not a photo</html>")
    assert r.status_code == 400 and r.get_json()["code"] == "INVALID_EVIDENCE"
    app.config["MAX_EVIDENCE_BYTES"] = 50
    r = _submit(core, headers, tx, "111111", 250, key="device-key-0002")
    assert r.status_code == 413
    assert Refund.query.count() == 0
    assert list(app.config["CAPTURE_DIR"].glob("evidence_*")) == []


def test_blocked_return_stores_no_evidence(app):
    core = _core(app)
    headers = _key()
    tx = _receipt(core, headers, "RCP-OLD").get_json()["transaction"]
    r = _submit(core, headers, tx, "111111", 250)
    assert r.get_json()["code"] == "OUTSIDE_RETURN_WINDOW"
    assert list(app.config["CAPTURE_DIR"].glob("evidence_*")) == []


def test_malformed_metadata_is_refused(app):
    core = _core(app)
    headers = dict(_key(), **{"Idempotency-Key": "device-key-0003"})
    r = core.post("/api/kiosk/returns", data={"metadata": "{not json"}, headers=headers,
                  content_type="multipart/form-data")
    assert r.status_code == 400 and r.get_json()["code"] == "INVALID_REQUEST"


def test_by_key_lookup_is_limited_to_the_calling_kiosk(app, tenants):
    core = _core(app)
    demo = _key("KIOSK-001")
    tx = _receipt(core, demo).get_json()["transaction"]
    _submit(core, demo, tx, "111111", 250, key="demo-private-key")
    other = _key("KIOSK-OTHER-1")
    assert core.get("/api/kiosk/returns/by-key/demo-private-key", headers=other).status_code == 404


def test_development_auth_refuses_non_loopback_host(app):
    with pytest.raises(RuntimeError, match="only allowed"):
        create_app({"SQLALCHEMY_DATABASE_URI": app.config["SQLALCHEMY_DATABASE_URI"],
                    "HOST": "0.0.0.0"})
    with pytest.raises(RuntimeError, match="Unsupported"):
        device_auth.authenticator_for({"DEVICE_AUTH_MODE": "production"})


def test_manage_tenancy_issues_and_revokes_keys(app, tmp_path, capsys, monkeypatch):
    import manage_tenancy

    monkeypatch.setattr(manage_tenancy, "create_app", lambda: app)
    env = tmp_path / "agent.env"
    env.write_text("AGENT_PORT=5100\nKIOSK_DEV_KEY=old\n")
    assert manage_tenancy.main(["issue-dev-key", "KIOSK-001", "--write-env", str(env)]) == 0
    text = env.read_text()
    assert "AGENT_PORT=5100" in text and "KIOSK_ID=KIOSK-001" in text
    key = next(line.split("=", 1)[1] for line in text.splitlines() if line.startswith("KIOSK_DEV_KEY="))
    core = _core(app)
    assert core.get("/api/kiosk/me", headers={"Authorization": f"AutoRefund-Dev-Key {key}"}).status_code == 200
    assert manage_tenancy.main(["revoke-keys", "KIOSK-001"]) == 0
    assert core.get("/api/kiosk/me", headers={"Authorization": f"AutoRefund-Dev-Key {key}"}).status_code == 401
    assert manage_tenancy.main(["issue-dev-key", "NOPE"]) == 1
