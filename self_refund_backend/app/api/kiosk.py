"""Customer kiosk endpoints."""
import logging

from flask import current_app, jsonify, request

from app.api import api_bp
from app.api.serializers import product_to_dict, return_result_to_dict
from app.catalog import repository as catalog
from app.receipts import service as receipts
from app.returns import service as returns
from app.returns.policy import policy_for
from app.tenancy.context import current_kiosk
from app.evidence import captures, storage
from app.returns.rules import ReturnError
from hardware import HardwareError, get_camera, get_scale

log = logging.getLogger("autorefund.api")

# Fields a browser might send that the server must never trust.
_IGNORED_CLIENT_FIELDS = ("measured_weight_grams", "kiosk_id", "image_path")


@api_bp.get("/health")
def health():
    return jsonify({"status": "ok", "message": "Backend is running"})


@api_bp.get("/products/lookup/<barcode>")
def lookup_product(barcode):
    product = catalog.find_by_barcode(current_kiosk().retailer_id, barcode)
    if not product:
        return jsonify({"success": False, "message": "Product not found"}), 404
    return jsonify({"success": True, "product": product_to_dict(product)})


@api_bp.get("/transactions/<receipt_number>")
def get_transaction(receipt_number):
    kiosk = current_kiosk()
    policy = policy_for(current_app.config, kiosk.retailer_id)
    return jsonify({"success": True,
                    "transaction": receipts.lookup_receipt(kiosk, receipt_number, policy)})


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
    kiosk = current_kiosk()
    policy = policy_for(cfg, kiosk.retailer_id)
    scale, camera = get_scale(), get_camera()

    def read_scale():
        try:
            r = scale.read_live()
        except HardwareError as exc:
            log.warning("Scale unavailable during refund submission: %s", exc)
            raise ReturnError("SCALE_UNAVAILABLE",
                              "The scale isn't responding. Please ask an employee for help.", 503)
        return returns.ScaleMeasurement(r.weight_grams, r.stable, scale.name, scale.is_mock)

    def obtain_photo():
        path = captures.resolve_capture(req.capture_id, cfg["CAPTURE_DIR"],
                                        cfg["CAPTURE_MAX_AGE_SECONDS"])
        if not path:
            try:
                path = captures.take_photo(camera, cfg["CAPTURE_DIR"])["relative_path"]
            except Exception as exc:  # camera errors must not crash the return
                log.warning("Camera capture failed during refund submission: %s", exc)
                return None
        return returns.Photo(path)

    result = returns.submit_return(
        req, kiosk=kiosk, policy=policy, read_scale=read_scale, obtain_photo=obtain_photo,
        discard_photo=lambda photo: None, camera_mock=camera.is_mock)
    status = 200 if result.replay else 201
    return jsonify({"success": True, "refund": return_result_to_dict(result)}), status
