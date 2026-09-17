"""
Confirm with the Core API that this agent is the kiosk it expects to be.

The confirmed identity (kiosk -> store -> retailer) is cached in the local
store for a few minutes. If the Core API says the credential belongs to a
different kiosk, the agent refuses to take returns.
"""
import logging
from datetime import timedelta

from flask import current_app, jsonify

from agent.core_client import CoreUnavailable
from agent.store import now

log = logging.getLogger("autorefund.agent.identity")
VERIFY_TTL = timedelta(minutes=5)

NOT_CONFIGURED = {"success": False, "code": "KIOSK_NOT_CONFIGURED",
                  "message": "This kiosk is not set up yet. Please ask an employee for help."}
DISABLED = {"success": False, "code": "KIOSK_DISABLED",
            "message": "This kiosk is not accepting returns right now. Please visit customer service."}
MISMATCH = {"success": False, "code": "KIOSK_IDENTITY_MISMATCH",
            "message": "This kiosk is not set up correctly. Please ask an employee for help."}


def map_device_error(response):
    """(status, body) for kiosk-auth failures from the Core API, else None."""
    code = response.body.get("code")
    if response.status == 401 and code in ("DEVICE_AUTH_REQUIRED", "DEVICE_AUTH_FAILED"):
        log.error("Core API rejected this kiosk's credential (%s)", code)
        return 503, NOT_CONFIGURED
    if response.status == 403 and code == "KIOSK_DISABLED":
        return 503, DISABLED
    return None


def _identity():
    return current_app.extensions["agent_identity"]


def status():
    """Identity status for /kiosk/status (never raises)."""
    identity = _identity()
    if not identity.configured:
        return {"state": "NOT_CONFIGURED", "expected_kiosk_code": identity.expected_kiosk_code}
    try:
        response = current_app.extensions["core_client"].call(identity, "GET", "/api/kiosk/me")
    except CoreUnavailable:
        cached, verified_at = current_app.extensions["agent_store"].get_config("identity")
        return {"state": "CORE_UNAVAILABLE", "expected_kiosk_code": identity.expected_kiosk_code,
                "last_verified": cached, "last_verified_at": verified_at.isoformat() if verified_at else None}
    mapped = map_device_error(response)
    if mapped:
        return {"state": mapped[1]["code"], "expected_kiosk_code": identity.expected_kiosk_code}
    kiosk = response.body.get("kiosk", {})
    if kiosk.get("kiosk_code") != identity.expected_kiosk_code:
        return {"state": "KIOSK_IDENTITY_MISMATCH", "expected_kiosk_code": identity.expected_kiosk_code,
                "credential_kiosk_code": kiosk.get("kiosk_code")}
    current_app.extensions["agent_store"].set_config("identity", kiosk)
    return {"state": "OK", **kiosk}


def require_verified():
    """None if this kiosk's identity is confirmed; else (Flask response, status)."""
    identity = _identity()
    if not identity.configured:
        return jsonify(NOT_CONFIGURED), 503
    store = current_app.extensions["agent_store"]
    cached, verified_at = store.get_config("identity")
    if (cached and verified_at and verified_at > now() - VERIFY_TTL
            and cached.get("kiosk_code") == identity.expected_kiosk_code):
        return None
    try:
        response = current_app.extensions["core_client"].call(identity, "GET", "/api/kiosk/me")
    except CoreUnavailable:
        from agent.routes import CORE_UNAVAILABLE_BODY
        return jsonify(CORE_UNAVAILABLE_BODY), 503
    mapped = map_device_error(response)
    if mapped:
        return jsonify(mapped[1]), mapped[0]
    kiosk = response.body.get("kiosk", {})
    if not response.ok or kiosk.get("kiosk_code") != identity.expected_kiosk_code:
        log.error("Kiosk identity mismatch: expected %s, credential belongs to %s",
                  identity.expected_kiosk_code, kiosk.get("kiosk_code"))
        return jsonify(MISMATCH), 503
    store.set_config("identity", kiosk)
    return None
