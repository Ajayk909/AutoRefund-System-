"""
HTTP endpoints the React kiosk UI calls (http://127.0.0.1:5100/api).

Paths match what the kiosk screens used before Phase 2, so the UI only
changed its base URL.

    GET  /health                   agent alive
    GET  /kiosk/status             identity, Core API reachability, hardware, outbox
    GET  /transactions/<receipt>   receipt via Core API (starts a kiosk session)
    GET  /products/lookup/<code>   product via Core API
    POST /refunds/start            submit a return (agent reads scale + photo)
    POST /session/end              customer finished / left
    + hardware_routes.py: /scale/*, /camera/*, /receipt/scan, /hardware/status

The browser can only choose WHICH receipt line to return and how many. The
agent never forwards browser headers or hardware values to the Core API.
"""
import logging
from urllib.parse import quote

from flask import Blueprint, current_app, jsonify, request

from agent import identity_check
from agent.core_client import CoreUnavailable

agent_bp = Blueprint("agent", __name__)
log = logging.getLogger("autorefund.agent")

CORE_UNAVAILABLE_BODY = {
    "success": False,
    "code": "CORE_UNAVAILABLE",
    "message": "We can't reach the returns service right now. Nothing has been refunded. "
               "Please try again in a moment or ask an employee for help.",
}


def store():
    return current_app.extensions["agent_store"]


def core():
    return current_app.extensions["core_client"]


def kiosk_identity():
    return current_app.extensions["agent_identity"]


@agent_bp.before_request
def _only_our_kiosk_page_may_change_things():
    """Block other web pages open in the kiosk browser from using the agent."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    origin = request.headers.get("Origin")
    if origin and origin not in current_app.config["ALLOWED_ORIGINS"]:
        log.warning("Rejected %s %s from origin %s", request.method, request.path, origin)
        return jsonify({"success": False, "code": "ORIGIN_NOT_ALLOWED",
                        "message": "Request not allowed."}), 403
    return None


def passthrough(response):
    """Return a Core API answer to the UI, translating kiosk-auth failures
    into customer-safe messages."""
    mapped = identity_check.map_device_error(response)
    if mapped:
        return jsonify(mapped[1]), mapped[0]
    return jsonify(response.body), response.status


@agent_bp.get("/health")
def health():
    return jsonify({"status": "ok", "message": "Kiosk agent is running"})


@agent_bp.get("/kiosk/status")
def kiosk_status():
    import hardware

    status = identity_check.status()
    return jsonify({
        "success": True,
        "kiosk": status,
        "hardware": {"camera": hardware.get_camera().status(),
                     "scale": hardware.get_scale().status()},
        "outbox": store().outbox_counts(),
        "session": store().current_session(current_app.config["SESSION_TIMEOUT_SECONDS"]),
    })


@agent_bp.get("/transactions/<receipt_number>")
def transaction(receipt_number):
    blocked = identity_check.require_verified()
    if blocked:
        return blocked
    try:
        response = core().call(kiosk_identity(), "GET",
                               f"/api/kiosk/receipts/{quote(receipt_number, safe='')}")
    except CoreUnavailable:
        return jsonify(CORE_UNAVAILABLE_BODY), 503
    if response.ok:
        tx = response.body.get("transaction", {})
        store().touch_session(current_app.config["SESSION_TIMEOUT_SECONDS"],
                              receipt_number=tx.get("receipt_number"),
                              transaction_id=tx.get("transaction_id"))
    return passthrough(response)


@agent_bp.get("/products/lookup/<barcode>")
def product(barcode):
    blocked = identity_check.require_verified()
    if blocked:
        return blocked
    try:
        response = core().call(kiosk_identity(), "GET",
                               f"/api/kiosk/products/{quote(barcode, safe='')}")
    except CoreUnavailable:
        return jsonify(CORE_UNAVAILABLE_BODY), 503
    return passthrough(response)


@agent_bp.post("/refunds/start")
def start_refund():
    from agent import submissions

    status, body = submissions.submit(request.get_json(silent=True) or {},
                                      request.headers.get("Idempotency-Key"))
    return jsonify(body), status


@agent_bp.post("/outbox/reconcile")
def reconcile_outbox():
    """Check unconfirmed submissions with the Core API (status only)."""
    from agent import submissions

    blocked = identity_check.require_verified()
    if blocked:
        return blocked
    return jsonify({"success": True, **submissions.reconcile_unconfirmed()})


@agent_bp.post("/session/end")
def end_session():
    store().end_sessions()
    return jsonify({"success": True})


from agent import hardware_routes  # noqa: E402,F401  (register hardware routes)
