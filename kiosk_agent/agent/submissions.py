"""
Submitting a return from the kiosk.

    1. confirm this kiosk's identity with the Core API
    2. read the scale HERE (the browser's weight is never used)
    3. use the customer's fresh, unused photo, or take one now
    4. record the attempt in the outbox (idempotency key, no customer data)
    5. send metadata + photo to the Core API, which decides everything
    6. record the Core API's answer; delete the local photo

If the Core API cannot be reached or gives no usable answer, the attempt is
marked "unconfirmed" and the customer is told NOTHING HAS BEEN REFUNDED and
to try again. The agent never creates, approves or refunds anything on its
own, and never retries without the customer. Retrying with the same
idempotency key is safe: if the first attempt did reach the Core API, the
same return is returned instead of a second one.
"""
import json
import logging
import secrets

from flask import current_app

from agent import captures, identity_check
from agent.core_client import CoreUnavailable
from hardware import HardwareError, get_camera, get_scale

log = logging.getLogger("autorefund.agent.submissions")

# The only things the browser may choose: which receipt line and how many.
ALLOWED_FIELDS = ("receipt_number", "transaction_id", "item_id", "product_id", "barcode", "quantity")
IGNORED_FIELDS = ("measured_weight_grams", "kiosk_id", "image_path", "store_id", "retailer_id")


def _err(status, code, message, **extra):
    return status, {"success": False, "code": code, "message": message, **extra}


def submit(body, browser_key):
    from agent.routes import CORE_UNAVAILABLE_BODY

    cfg = current_app.config
    store = current_app.extensions["agent_store"]
    identity = current_app.extensions["agent_identity"]

    for field in IGNORED_FIELDS:
        if field in body:
            log.warning("Ignoring browser-supplied %s on /refunds/start", field)

    blocked = identity_check.require_verified()
    if blocked:
        response, status = blocked
        return status, response.get_json()

    key = (browser_key or "").strip() or f"agent-{secrets.token_hex(16)}"

    # --- scale (authoritative reading is taken here) -------------------------------
    scale = get_scale()
    try:
        reading = scale.read_live()
    except HardwareError as exc:
        log.warning("Scale unavailable during submission: %s", exc)
        return _err(503, "SCALE_UNAVAILABLE",
                    "The scale isn't responding. Please ask an employee for help.")
    if not reading.stable or reading.weight_grams <= 0:
        return _err(409, "SCALE_NOT_READY",
                    "Place your item on the scale and keep it still, then try again.",
                    measured_weight_grams=float(reading.weight_grams), stable=bool(reading.stable))

    # --- photo ------------------------------------------------------------------------------
    camera = get_camera()
    capture_id = body.get("capture_id")
    path = captures.usable_capture(capture_id, cfg["CAPTURE_DIR"], store, cfg["CAPTURE_MAX_AGE_SECONDS"])
    auto_capture = False
    if not path:
        if capture_id:
            log.warning("Capture id not usable (unknown, expired or already used); taking a new photo")
        capture_id = None
        try:
            photo = captures.take_photo(camera, cfg["CAPTURE_DIR"], store)
            capture_id = photo["capture_id"]
            path = f"{cfg['CAPTURE_DIR']}/{photo['file_name']}"
            auto_capture = True
        except Exception as exc:  # no photo -> the Core API sends it to employee review
            log.warning("Camera capture failed during submission: %s", exc)
            path = None

    # --- send ----------------------------------------------------------------------------
    session_id = store.touch_session(cfg["SESSION_TIMEOUT_SECONDS"])
    store.outbox_start(key, "return", session_id, body.get("transaction_id"), body.get("item_id"),
                       body.get("quantity", 1))
    metadata = {field: body[field] for field in ALLOWED_FIELDS if field in body}
    metadata.setdefault("quantity", 1)
    metadata["scale"] = {"weight_grams": reading.weight_grams, "stable": bool(reading.stable),
                         "device": scale.name, "mock": bool(scale.is_mock)}
    metadata["camera"] = {"device": camera.name, "mock": bool(camera.is_mock)}

    files = None
    if path:
        with open(path, "rb") as fh:
            files = {"image": ("item.jpg", fh.read(), "image/jpeg")}

    try:
        response = current_app.extensions["core_client"].call(
            identity, "POST", "/api/kiosk/returns", headers={"Idempotency-Key": key},
            data={"metadata": json.dumps(metadata)}, files=files)
    except CoreUnavailable as exc:
        store.outbox_finish(key, "unconfirmed", error=str(exc)[:200])
        log.error("Return %s not confirmed: Core API unavailable. Nothing refunded by the agent.", key)
        if auto_capture:  # the customer did not see this photo; don't keep it
            captures.consume(capture_id, path, store)
        return 503, dict(CORE_UNAVAILABLE_BODY, idempotency_key=key)

    # The Core API answered: its decision is final for this attempt.
    captures.consume(capture_id, path, store)
    mapped = identity_check.map_device_error(response)
    if mapped:
        store.outbox_finish(key, "rejected", response_code=mapped[1]["code"])
        return mapped
    if response.ok:
        refund = response.body.get("refund", {})
        store.outbox_finish(key, "accepted", response_code=str(response.status),
                            refund_id=refund.get("refund_id"))
    else:
        store.outbox_finish(key, "rejected", response_code=response.body.get("code"))
    return response.status, response.body


def reconcile_unconfirmed():
    """Ask the Core API about submissions that could not be confirmed.

    Only records what the Core API says. Never re-sends a return.
    Returns {"accepted": n, "not_received": n, "still_unconfirmed": n}.
    """
    store = current_app.extensions["agent_store"]
    identity = current_app.extensions["agent_identity"]
    result = {"accepted": 0, "not_received": 0, "still_unconfirmed": 0}
    for row in store.outbox_by_status("unconfirmed"):
        key = row["idempotency_key"]
        try:
            response = current_app.extensions["core_client"].call(
                identity, "GET", f"/api/kiosk/returns/by-key/{key}")
        except CoreUnavailable:
            result["still_unconfirmed"] += 1
            continue
        if response.ok:
            store.outbox_finish(key, "accepted", response_code="reconciled",
                                refund_id=response.body.get("refund", {}).get("refund_id"))
            result["accepted"] += 1
        elif response.status == 404:
            store.outbox_finish(key, "not_received", response_code="reconciled")
            result["not_received"] += 1
        else:
            result["still_unconfirmed"] += 1
    return result
