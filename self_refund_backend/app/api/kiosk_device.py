"""
Core API endpoints for the kiosk agent (the trusted kiosk boundary).

Every route requires device authentication. The kiosk, store and retailer
come only from the credential (``g.kiosk_context``); anything a request says
about its identity is ignored.

    GET  /api/kiosk/me                     who am I (kiosk -> store -> retailer)
    GET  /api/kiosk/receipts/<number>      receipt with return eligibility
    GET  /api/kiosk/products/<barcode>     product in this retailer's catalog
    POST /api/kiosk/returns                submit a return (multipart: metadata + image)
    GET  /api/kiosk/returns/by-key/<key>   status of a return this kiosk submitted
"""
import json

from flask import current_app, g, jsonify, request

from app.api import api_bp
from app.api.serializers import product_to_dict, return_result_to_dict
from app.catalog import repository as catalog
from app.errors import DomainError
from app.receipts import service as receipts
from app.returns import repository as returns_repository
from app.returns import service as returns
from app.returns.policy import policy_for
from app.tenancy import repository as tenancy
from app.tenancy.device_auth import require_kiosk_device


@api_bp.get("/kiosk/me")
@require_kiosk_device
def kiosk_me():
    return jsonify({"success": True, "kiosk": tenancy.kiosk_identity(g.kiosk_context)})


@api_bp.get("/kiosk/receipts/<receipt_number>")
@require_kiosk_device
def kiosk_receipt(receipt_number):
    kiosk = g.kiosk_context
    policy = policy_for(current_app.config, kiosk.retailer_id)
    return jsonify({"success": True,
                    "transaction": receipts.lookup_receipt(kiosk, receipt_number, policy)})


@api_bp.get("/kiosk/products/<barcode>")
@require_kiosk_device
def kiosk_product(barcode):
    product = catalog.find_by_barcode(g.kiosk_context.retailer_id, barcode)
    if not product:
        return jsonify({"success": False, "code": "PRODUCT_NOT_FOUND",
                        "message": "Product not found"}), 404
    return jsonify({"success": True, "product": product_to_dict(product)})


def _metadata():
    raw = request.form.get("metadata")
    try:
        data = json.loads(raw) if raw else None
    except ValueError:
        data = None
    if not isinstance(data, dict):
        raise DomainError("INVALID_REQUEST", "Invalid request. Please try again.", 400)
    return data


@api_bp.post("/kiosk/returns")
@require_kiosk_device
def kiosk_submit_return():
    cfg = current_app.config
    kiosk = g.kiosk_context
    data = _metadata()
    scale = data.get("scale") if isinstance(data.get("scale"), dict) else {}
    camera = data.get("camera") if isinstance(data.get("camera"), dict) else {}
    image = request.files.get("image")

    req = returns.ReturnRequest(
        receipt_number=data.get("receipt_number"),
        transaction_id=data.get("transaction_id"),
        item_id=data.get("item_id"),
        product_id=data.get("product_id"),
        barcode=data.get("barcode"),
        quantity=data.get("quantity", 1),
        idempotency_key=request.headers.get("Idempotency-Key", ""),
    )

    def read_scale():
        return returns.ScaleMeasurement(
            weight_grams=scale.get("weight_grams"), stable=scale.get("stable") is True,
            device=str(scale.get("device") or "unknown")[:50], mock=scale.get("mock") is True)

    def obtain_photo():
        if not image:
            return None
        path, digest = current_app.evidence_storage.store_jpeg(
            image.read(cfg["MAX_EVIDENCE_BYTES"] + 1), cfg["MAX_EVIDENCE_BYTES"])
        return returns.Photo(path, digest)

    result = returns.submit_return(
        req, kiosk=kiosk, policy=policy_for(cfg, kiosk.retailer_id),
        read_scale=read_scale, obtain_photo=obtain_photo,
        discard_photo=lambda photo: current_app.evidence_storage.delete_stored(photo.relative_path),
        camera_mock=camera.get("mock") is True, require_idempotency_key=True)
    status = 200 if result.replay else 201
    return jsonify({"success": True, "refund": return_result_to_dict(result)}), status


@api_bp.get("/kiosk/returns/by-key/<key>")
@require_kiosk_device
def kiosk_return_by_key(key):
    """Lets the agent find out whether a submission it could not confirm
    (network failure) was actually received. Only this kiosk's returns."""
    refund = returns_repository.find_by_idempotency_key(key)
    if not refund or refund.kiosk_id != g.kiosk_context.kiosk_id:
        return jsonify({"success": False, "code": "NOT_FOUND", "message": "Not found"}), 404
    return jsonify({"success": True, "refund": {
        "refund_id": str(refund.refund_id),
        "decision_status": refund.decision_status,
        "refund_amount": float(refund.refund_amount),
    }})
