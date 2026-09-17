"""Customer kiosk endpoints."""
import logging

from flask import current_app, jsonify, request

from app.api import api_bp
from app.api.serializers import product_to_dict, return_result_to_dict
from app.catalog import repository as catalog
from app.receipts import service as receipts
from app.returns import service as returns
from app.returns.policy import policy_for
from hardware import get_camera, get_scale

log = logging.getLogger("autorefund.api")

# Fields a browser might send that the server must never trust.
_IGNORED_CLIENT_FIELDS = ("measured_weight_grams", "kiosk_id", "image_path")


@api_bp.get("/health")
def health():
    return jsonify({"status": "ok", "message": "Backend is running"})


@api_bp.get("/products/lookup/<barcode>")
def lookup_product(barcode):
    product = catalog.find_by_barcode(barcode)
    if not product:
        return jsonify({"success": False, "message": "Product not found"}), 404
    return jsonify({"success": True, "product": product_to_dict(product)})


@api_bp.get("/transactions/<receipt_number>")
def get_transaction(receipt_number):
    policy = policy_for(current_app.config)
    return jsonify({"success": True,
                    "transaction": receipts.lookup_receipt(receipt_number, policy)})


@api_bp.post("/refunds/start")
def start_refund():
    data = request.get_json(silent=True) or {}
    cfg = current_app.config

    for field in _IGNORED_CLIENT_FIELDS:
        if field in data:
            log.warning("Ignoring client-supplied %s on /refunds/start", field)

    req = returns.ReturnRequest(
        receipt_number=data.get("receipt_number"),
        transaction_id=data.get("transaction_id"),
        item_id=data.get("item_id"),
        product_id=data.get("product_id"),
        barcode=data.get("barcode"),
        quantity=data.get("quantity", 1),
        capture_id=data.get("capture_id"),
        idempotency_key=request.headers.get("Idempotency-Key") or data.get("idempotency_key") or "",
    )
    result = returns.submit_return(
        req,
        kiosk_code=cfg["KIOSK_ID"],
        policy=policy_for(cfg),
        scale=get_scale(),
        camera=get_camera(),
        capture_dir=cfg["CAPTURE_DIR"],
    )
    status = 200 if result.replay else 201
    return jsonify({"success": True, "refund": return_result_to_dict(result)}), status
