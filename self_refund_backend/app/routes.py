from decimal import Decimal
from datetime import datetime
import base64
import logging
import os
import secrets
import cv2
from sqlalchemy.exc import IntegrityError

from flask import Blueprint, current_app, g, jsonify, request, Response, send_from_directory
from werkzeug.security import check_password_hash

from app import db
from app.models import (
    Product,
    Transaction,
    TransactionItem,
    Refund,
    AuditLog,
    Staff,
)
from app.auth import (
    REVIEW_ROLES,
    create_session,
    current_session,
    login_limiter,
    parse_uuid,
    require_staff,
)
from app import returns
from app.refund_states import (
    APPROVED,
    PENDING_REVIEW,
    QUANTITY_CONSUMING,
    REFUNDED,
    REJECTED,
    InvalidTransition,
    ensure_transition,
)
from app.timeutil import utcnow
from hardware import HardwareError, get_camera, get_scale
from hardware.barcode import backend_name as barcode_backend_name

api_bp = Blueprint("api", __name__)
log = logging.getLogger("autorefund.api")


def capture_dir():
    return str(current_app.config["CAPTURE_DIR"])


def product_to_dict(product):
    return {
        "product_id": str(product.product_id),
        "barcode": product.barcode,
        "name": product.name,
        "category": product.category,
        "expected_weight_grams": float(product.expected_weight_grams),
        "weight_tolerance_percent": float(product.weight_tolerance_percent),
        "price": float(product.price),
    }


def normalize_capture_path(image_path):
    if not image_path:
        return None

    normalized = str(image_path).replace("\\", "/").strip()

    if normalized.startswith("captures/"):
        return normalized

    filename = os.path.basename(normalized)
    return f"captures/{filename}"


@api_bp.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "message": "Backend is running"
    })


@api_bp.get("/products/lookup/<barcode>")
def lookup_product(barcode):
    product = Product.query.filter_by(barcode=barcode).first()

    if not product:
        return jsonify({
            "success": False,
            "message": "Product not found"
        }), 404

    return jsonify({
        "success": True,
        "product": product_to_dict(product)
    })


@api_bp.get("/transactions/<receipt_number>")
def get_transaction(receipt_number):
    """Receipt lookup for the kiosk screen.

    Deliberately excludes customer email and payment method: the kiosk only
    needs to show which items can be returned.
    """
    transaction = Transaction.query.filter_by(receipt_number=receipt_number).first()

    if not transaction:
        return jsonify({
            "success": False,
            "message": "Transaction not found"
        }), 404

    items = (
        db.session.query(TransactionItem, Product)
        .join(Product, TransactionItem.product_id == Product.product_id)
        .filter(TransactionItem.transaction_id == transaction.transaction_id)
        .all()
    )

    cfg = current_app.config
    item_list = []
    for item, product in items:
        eligibility = returns.line_eligibility(transaction, item, cfg)
        item_list.append({
            "item_id": str(item.item_id),
            "product_id": str(product.product_id),
            "barcode": product.barcode,
            "name": product.name,
            "quantity": item.quantity,
            "price_at_purchase": float(item.price_at_purchase),
            "expected_weight_grams": float(product.expected_weight_grams),
            "weight_tolerance_percent": float(product.weight_tolerance_percent),
            "returned_quantity": eligibility["returned_quantity"],
            "returnable_quantity": eligibility["returnable_quantity"],
            "is_refundable": eligibility["is_refundable"],
            "ineligible_reason": eligibility["ineligible_reason"],
            "refund_status": eligibility["latest_status"],
        })

    deadline = returns.return_deadline(transaction, cfg["RETURN_WINDOW_DAYS"])
    return jsonify({
        "success": True,
        "transaction": {
            "transaction_id": str(transaction.transaction_id),
            "receipt_number": transaction.receipt_number,
            "purchase_date": transaction.purchase_date.isoformat(),
            "total_amount": float(transaction.total_amount),
            "return_deadline": deadline.isoformat(),
            "within_return_window": returns.within_return_window(
                transaction, cfg["RETURN_WINDOW_DAYS"]),
            "items": item_list
        }
    })


_IGNORED_CLIENT_FIELDS = ("measured_weight_grams", "kiosk_id", "image_path")


def _audit_blocked(event_type, transaction, product, kiosk_id, **details):
    db.session.add(AuditLog(event_type=event_type, refund_id=details.pop("refund_id", None),
                            details={
                                "receipt_number": transaction.receipt_number,
                                "barcode": product.barcode,
                                "kiosk_id": kiosk_id,
                                "timestamp": utcnow().isoformat(),
                                **details,
                            }))
    db.session.commit()


def _refund_result(refund, product, weight, image_captured, replay=False):
    return {
        "refund_id": str(refund.refund_id),
        "decision_status": refund.decision_status,
        "decision_reason": refund.decision_reason,
        "weight_match": refund.weight_match,
        "quantity": refund.quantity,
        "expected_weight_grams": float(weight["expected"]) if weight else
        float(product.expected_weight_grams) * refund.quantity,
        "measured_weight_grams": float(refund.measured_weight_grams),
        "refund_amount": float(refund.refund_amount),
        "image_captured": image_captured,
        "idempotent_replay": replay,
    }


@api_bp.post("/refunds/start")
def start_refund():
    """Create a return for one receipt line.

    Security model (Phase 0, single kiosk PC):
    * weight is read from the scale HERE, never taken from the request
    * kiosk id comes from configuration, never from the request
    * the photo must be one this backend captured recently (capture_id);
      otherwise the backend takes the photo itself
    * the receipt line is locked while quantity is checked, so parallel
      submissions cannot return the same unit twice
    * an Idempotency-Key makes a retried submission return the same refund
    """
    data = request.get_json(silent=True) or {}
    cfg = current_app.config
    kiosk_id = cfg["KIOSK_ID"]

    for field in _IGNORED_CLIENT_FIELDS:
        if field in data:
            log.warning("Ignoring client-supplied %s on /refunds/start", field)

    try:
        return _start_refund(data, cfg, kiosk_id)
    except returns.ReturnError as err:
        db.session.rollback()
        return jsonify(err.body()), err.status


def _start_refund(data, cfg, kiosk_id):
    ReturnError = returns.ReturnError

    # --- idempotency key -----------------------------------------------------
    key = (request.headers.get("Idempotency-Key") or data.get("idempotency_key") or "").strip()
    if key and not returns.IDEMPOTENCY_KEY_RE.match(key):
        raise ReturnError("INVALID_IDEMPOTENCY_KEY", "Invalid request. Please try again.")

    # --- resolve receipt and line -------------------------------------------
    transaction = None
    if data.get("receipt_number"):
        transaction = Transaction.query.filter_by(receipt_number=data["receipt_number"]).first()
    elif parse_uuid(data.get("transaction_id")):
        transaction = db.session.get(Transaction, parse_uuid(data["transaction_id"]))
    if not transaction:
        raise ReturnError("RECEIPT_NOT_FOUND", "Transaction not found", 404)

    product = None
    if data.get("barcode"):
        product = Product.query.filter_by(barcode=data["barcode"]).first()
    elif parse_uuid(data.get("product_id")):
        product = db.session.get(Product, parse_uuid(data["product_id"]))

    transaction_item = None
    if parse_uuid(data.get("item_id")):
        transaction_item = TransactionItem.query.filter_by(
            item_id=parse_uuid(data["item_id"]),
            transaction_id=transaction.transaction_id).first()
        if transaction_item and product and transaction_item.product_id != product.product_id:
            transaction_item = None
        if transaction_item and not product:
            product = db.session.get(Product, transaction_item.product_id)
    if not product:
        raise ReturnError("PRODUCT_NOT_FOUND", "Product not found", 404)
    if not transaction_item:
        transaction_item = TransactionItem.query.filter_by(
            transaction_id=transaction.transaction_id, product_id=product.product_id).first()
    if not transaction_item:
        raise ReturnError("NOT_ON_RECEIPT", "This product is not part of the provided transaction")

    # --- replayed request? ---------------------------------------------------
    if key:
        existing = Refund.query.filter_by(idempotency_key=key).first()
        if existing:
            return _idempotent_replay(existing, transaction_item, product)

    # --- quantity -------------------------------------------------------------
    raw_quantity = data.get("quantity", 1)
    try:
        quantity = int(raw_quantity)
        if isinstance(raw_quantity, bool) or str(raw_quantity).strip() != str(quantity):
            raise ValueError
    except (TypeError, ValueError):
        raise ReturnError("INVALID_QUANTITY", "Please choose how many items you are returning.")
    if quantity < 1:
        raise ReturnError("INVALID_QUANTITY", "Please choose how many items you are returning.")

    # --- return window --------------------------------------------------------
    if not returns.within_return_window(transaction, cfg["RETURN_WINDOW_DAYS"]):
        log.info("Return outside window: receipt=%s", transaction.receipt_number)
        raise ReturnError(
            "OUTSIDE_RETURN_WINDOW",
            f"This item is outside the {cfg['RETURN_WINDOW_DAYS']}-day return window. "
            "Please visit customer service.")

    # Cheap check first so blocked returns don't weigh or photograph anything.
    # It is repeated under the row lock below, which is what makes it safe.
    _check_line_available(transaction, transaction_item, product, quantity, kiosk_id, cfg)

    # --- hardware (before taking any database lock) --------------------------
    scale = get_scale()
    try:
        reading = scale.read_live()
    except HardwareError as exc:
        log.warning("Scale unavailable during refund submission: %s", exc)
        raise ReturnError("SCALE_UNAVAILABLE",
                          "The scale isn't responding. Please ask an employee for help.", 503)
    measured = Decimal(str(reading.weight_grams))
    if not reading.stable or measured <= 0:
        raise ReturnError("SCALE_NOT_READY",
                          "Place your item on the scale and keep it still, then try again.", 409,
                          measured_weight_grams=float(measured), stable=bool(reading.stable))

    image_path = returns.resolve_capture(data.get("capture_id"), capture_dir(),
                                         cfg["CAPTURE_MAX_AGE_SECONDS"])
    if data.get("capture_id") and not image_path:
        log.warning("Capture id not usable (unknown, expired or already used); recapturing")
    camera = get_camera()
    if not image_path:
        try:
            image_path = camera.capture_image()["relative_path"]
        except Exception as exc:  # camera errors must not crash the return
            log.warning("Camera capture failed during refund submission: %s", exc)
            image_path = None

    # --- lock the receipt line and apply the rules ---------------------------
    TransactionItem.query.filter_by(item_id=transaction_item.item_id).with_for_update().one()

    if key:  # a parallel request with the same key may have just finished
        existing = Refund.query.filter_by(idempotency_key=key).first()
        if existing:
            db.session.rollback()
            return _idempotent_replay(existing, transaction_item, product)

    rejected = _check_line_available(transaction, transaction_item, product, quantity,
                                     kiosk_id, cfg)

    weight = returns.weight_check(product, quantity, measured)
    if not weight["match"]:
        decision_status, decision_reason = "pending_review", "Weight outside allowed tolerance"
    elif image_path is None and cfg["REQUIRE_PHOTO_FOR_AUTO_APPROVAL"]:
        decision_status, decision_reason = "pending_review", "No item photo could be captured"
    else:
        decision_status, decision_reason = "approved", "Weight matched expected product tolerance"

    now = utcnow()
    refund = Refund(
        transaction_id=transaction.transaction_id,
        product_id=product.product_id,
        transaction_item_id=transaction_item.item_id,
        quantity=quantity,
        kiosk_id=kiosk_id,
        measured_weight_grams=measured,
        weight_match=weight["match"],
        refund_amount=transaction_item.price_at_purchase * quantity,
        refund_date=now,
        decision_status=decision_status,
        decision_reason=decision_reason,
        image_path=image_path,
        staff_override=False,
        idempotency_key=key or None,
    )
    db.session.add(refund)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        raise ReturnError("IDEMPOTENCY_KEY_REUSED", "Invalid request. Please start again.", 422)

    db.session.add(AuditLog(
        event_type="refund_started",
        refund_id=refund.refund_id,
        staff_id=None,
        details={
            "receipt_number": transaction.receipt_number,
            "barcode": product.barcode,
            "kiosk_id": kiosk_id,
            "quantity": quantity,
            "expected_weight_grams": float(weight["expected"]),
            "measured_weight_grams": float(measured),
            "weight_source": scale.name,
            "hardware_mock": bool(scale.is_mock or camera.is_mock),
            "weight_match": weight["match"],
            "decision_status": decision_status,
            "decision_reason": decision_reason,
            "image_captured": image_path is not None,
            "previous_rejections": rejected,
            "timestamp": now.isoformat()
        }
    ))
    db.session.commit()
    log.info("Refund %s created: receipt=%s product=%s qty=%s weight=%s expected=%s status=%s",
             refund.refund_id, transaction.receipt_number, product.barcode, quantity,
             measured, weight["expected"], decision_status)

    return jsonify({"success": True,
                    "refund": _refund_result(refund, product, weight, image_path is not None)}), 201


def _check_line_available(transaction, transaction_item, product, quantity, kiosk_id, cfg):
    """Quantity / duplicate / retry-limit rules. Returns rejected attempts."""
    ReturnError = returns.ReturnError
    used, rejected, refunds = returns.count_line_usage(transaction_item)
    remaining = transaction_item.quantity - used

    if remaining <= 0 or quantity > remaining:
        latest = next((r for r in refunds if r.decision_status in QUANTITY_CONSUMING), None)
        if remaining <= 0 and latest:
            log.warning("Duplicate refund attempt blocked: receipt=%s product=%s existing=%s",
                        transaction.receipt_number, product.barcode, latest.refund_id)
            _audit_blocked("duplicate_refund_blocked", transaction, product, kiosk_id,
                           refund_id=latest.refund_id,
                           existing_refund_status=latest.decision_status,
                           requested_quantity=quantity)
            message = ("This item is already waiting for an employee to review it."
                       if latest.decision_status == PENDING_REVIEW
                       else "This item has already been submitted for refund.")
            raise ReturnError("DUPLICATE_RETURN", message,
                              existing_refund_status=latest.decision_status)
        raise ReturnError("QUANTITY_EXCEEDS_REMAINING",
                          f"Only {max(remaining, 0)} of this item can still be returned.",
                          returnable_quantity=max(remaining, 0))

    retry_limit = cfg["RETURN_RETRY_LIMIT_AFTER_REJECTION"]
    if rejected > retry_limit:
        _audit_blocked("return_attempt_limit_reached", transaction, product, kiosk_id,
                       rejected_attempts=rejected, retry_limit=retry_limit)
        raise ReturnError("TOO_MANY_ATTEMPTS",
                          "We can't accept this return at the kiosk. "
                          "Please visit customer service for help.")
    return rejected


def _idempotent_replay(existing, transaction_item, product):
    same_line = (existing.transaction_item_id == transaction_item.item_id)
    if not same_line:
        raise returns.ReturnError("IDEMPOTENCY_KEY_REUSED",
                                  "Invalid request. Please start again.", 422)
    log.info("Idempotent replay for refund %s", existing.refund_id)
    return jsonify({"success": True, "refund": _refund_result(
        existing, product, None, existing.image_path is not None, replay=True)}), 200


@api_bp.get("/scale/read")
def read_scale():
    try:
        reading = get_scale().read()
        return jsonify({
            "success": True,
            "connected": True,
            "weight_grams": reading.weight_grams,
            "stable": reading.stable,
        })
    except HardwareError as e:
        log.warning("Scale read failed: %s", e)
        return jsonify({
            "success": False,
            "connected": False,
            "weight_grams": 0,
            "stable": False,
            "message": "Scale unavailable"
        }), 503


@api_bp.get("/scale/live")
def get_live_scale():
    try:
        reading = get_scale().read_live()
        return jsonify({
            "success": True,
            "connected": True,
            "weight_grams": float(reading.weight_grams or 0),
            "stable": bool(reading.stable),
            "message": "Live weight fetched"
        })
    except HardwareError as e:
        log.warning("Live scale read failed: %s", e)
        return jsonify({
            "success": False,
            "connected": False,
            "message": "Scale unavailable",
            "weight_grams": 0,
            "stable": False
        }), 503


@api_bp.get("/hardware/status")
def hardware_status():
    """Diagnostics for setup/testing (which devices are real or mocked)."""
    camera = get_camera()
    scale = get_scale()
    return jsonify({
        "success": True,
        "camera": camera.status(),
        "scale": scale.status(),
        "barcode_decoder": barcode_backend_name(),
        "keyboard_scanner": "handled by the kiosk UI (USB HID keyboard mode)",
    })


@api_bp.get("/camera/health")
def camera_health():
    try:
        if not get_camera().ensure_camera():
            return jsonify({
                "success": False,
                "message": "USB camera could not be opened"
            }), 500

        return jsonify({
            "success": True,
            "message": "USB camera is working",
            "source": str(get_camera().current_source)
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@api_bp.get("/camera/preview")
def camera_preview():
    try:
        frame = get_camera().get_frame()
        if frame is None:
            return jsonify({
                "success": False,
                "message": "Could not read frame from camera"
            }), 500

        ok, buffer = cv2.imencode(".jpg", frame)
        if not ok:
            return jsonify({
                "success": False,
                "message": "Could not encode frame"
            }), 500

        return Response(buffer.tobytes(), mimetype="image/jpeg")
    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@api_bp.get("/camera/stream")
def camera_stream():
    try:
        if not get_camera().ensure_camera():
            return jsonify({
                "success": False,
                "message": "Could not open USB camera"
            }), 500

        return Response(
            get_camera().generate_mjpeg_frames(),
            mimetype="multipart/x-mixed-replace; boundary=frame"
        )
    except Exception as e:
        log.exception("/camera/stream failed: %s", e)
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@api_bp.post("/camera/capture")
def camera_capture():
    """Take the item photo.

    Returns an unguessable capture_id (the kiosk sends it with the return)
    and an inline preview, so evidence files are never served publicly.
    """
    try:
        result = get_camera().capture_image()
        capture_id = secrets.token_hex(16)
        stem, _ = os.path.splitext(result["filename"])
        filename = f"{stem}_{capture_id}.jpg"
        src = os.path.join(capture_dir(), result["filename"])
        dst = os.path.join(capture_dir(), filename)
        os.replace(src, dst)
        with open(dst, "rb") as fh:
            preview = base64.b64encode(fh.read()).decode("ascii")
        log.info("Image captured: %s", filename)

        return jsonify({
            "success": True,
            "capture_id": capture_id,
            "file_name": filename,
            "preview_data_url": f"data:image/jpeg;base64,{preview}",
        })
    except Exception as e:
        log.error("/camera/capture failed: %s", e)
        return jsonify({
            "success": False,
            "message": "Camera unavailable. Please try again."
        }), 503


@api_bp.get("/receipt/scan")
def scan_receipt():
    try:
        result = get_camera().scan_barcode()

        if result:
            return jsonify({
                "success": True,
                "found": True,
                "barcode": result["barcode"],
                "barcode_type": result["type"]
            })

        return jsonify({
            "success": True,
            "found": False,
            "message": "No barcode detected"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


def _refund_image_file(refund):
    """Absolute path of a refund's evidence image, or None."""
    normalized = normalize_capture_path(refund.image_path)
    if not normalized:
        return None
    filename = os.path.basename(normalized)
    path = os.path.join(capture_dir(), filename)
    return path if os.path.isfile(path) else None


def refund_to_staff_dict(refund):
    product = db.session.get(Product, refund.product_id)
    reviewer = db.session.get(Staff, refund.staff_id) if refund.staff_id else None
    quantity = refund.quantity or 1
    has_image = _refund_image_file(refund) is not None
    return {
        "refund_id": str(refund.refund_id),
        "item_name": product.name if product else "Unknown Item",
        "barcode": product.barcode if product else None,
        "decision_status": refund.decision_status,
        "refund_date": refund.refund_date.isoformat() if refund.refund_date else None,
        "quantity": quantity,
        "measured_weight_grams": float(refund.measured_weight_grams),
        "expected_weight_grams": (float(product.expected_weight_grams) * quantity
                                  if product else None),
        "weight_match": refund.weight_match,
        "refund_amount": float(refund.refund_amount),
        "decision_reason": refund.decision_reason,
        "kiosk_id": refund.kiosk_id,
        "reviewed_by": reviewer.full_name if reviewer else None,
        "decided_at": refund.decided_at.isoformat() if refund.decided_at else None,
        "payment_reference": refund.payment_reference,
        "refunded_at": refund.refunded_at.isoformat() if refund.refunded_at else None,
        "has_image": has_image,
        # Authenticated URL: the browser must send the staff bearer token.
        "image_url": f"/api/refunds/{refund.refund_id}/image" if has_image else None,
    }


@api_bp.get("/captures/<path:filename>")
@require_staff()
def get_capture_file(filename):
    return send_from_directory(capture_dir(), os.path.basename(filename))


@api_bp.get("/refunds/<refund_id>/image")
@require_staff()
def get_refund_image(refund_id):
    uid = parse_uuid(refund_id)
    refund = db.session.get(Refund, uid) if uid else None
    path = _refund_image_file(refund) if refund else None
    if not path:
        return jsonify({"success": False, "message": "Image not found"}), 404
    db.session.add(AuditLog(event_type="evidence_viewed", refund_id=refund.refund_id,
                            staff_id=g.staff.staff_id,
                            details={"timestamp": utcnow().isoformat()}))
    db.session.commit()
    response = send_from_directory(capture_dir(), os.path.basename(path))
    response.headers["Cache-Control"] = "no-store"
    return response


@api_bp.post("/staff/login")
def staff_login():
    data = request.get_json() or {}
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({
            "success": False,
            "message": "username and password are required"
        }), 400

    if login_limiter.is_blocked(username):
        log.warning("Staff login temporarily locked for username=%s", username)
        return jsonify({
            "success": False,
            "code": "TOO_MANY_ATTEMPTS",
            "message": "Too many failed attempts. Please wait a few minutes and try again."
        }), 429

    staff = Staff.query.filter_by(username=username).first()
    if not staff or not check_password_hash(staff.password_hash, password):
        login_limiter.record_failure(username)
        log.warning("Failed staff login for username=%s", username)
        db.session.add(AuditLog(event_type="staff_login_failed", details={
            "username": str(username)[:100], "timestamp": utcnow().isoformat()}))
        db.session.commit()
        return jsonify({
            "success": False,
            "message": "Invalid credentials"
        }), 401

    login_limiter.reset(username)
    token, session = create_session(staff)
    db.session.add(AuditLog(event_type="staff_login", staff_id=staff.staff_id,
                            details={"timestamp": utcnow().isoformat()}))
    db.session.commit()
    log.info("Staff login: %s", staff.username)

    return jsonify({
        "success": True,
        "token": token,
        "expires_at": session.expires_at.isoformat(),
        "staff": {
            "staff_id": str(staff.staff_id),
            "username": staff.username,
            "full_name": staff.full_name,
            "role": staff.role,
            "email": staff.email
        }
    })


@api_bp.post("/staff/logout")
def staff_logout():
    session = current_session()
    if session:
        session.revoked_at = utcnow()
        db.session.add(AuditLog(event_type="staff_logout", staff_id=session.staff_id,
                                details={"timestamp": utcnow().isoformat()}))
        db.session.commit()
    return jsonify({"success": True})


@api_bp.get("/staff/me")
@require_staff()
def staff_me():
    staff = g.staff
    return jsonify({"success": True, "staff": {
        "staff_id": str(staff.staff_id), "username": staff.username,
        "full_name": staff.full_name, "role": staff.role, "email": staff.email,
    }})


@api_bp.get("/refunds/logs")
@require_staff()
def refund_logs():
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    query = Refund.query

    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.filter(Refund.refund_date >= start_dt)
        except ValueError:
            return jsonify({
                "success": False,
                "message": "Invalid start_date format. Use YYYY-MM-DD"
            }), 400

    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            end_dt = end_dt.replace(hour=23, minute=59, second=59)
            query = query.filter(Refund.refund_date <= end_dt)
        except ValueError:
            return jsonify({
                "success": False,
                "message": "Invalid end_date format. Use YYYY-MM-DD"
            }), 400

    refunds = query.order_by(Refund.refund_date.desc()).all()
    return jsonify({
        "success": True,
        "refunds": [refund_to_staff_dict(r) for r in refunds]
    })


@api_bp.get("/refunds/pending")
@require_staff()
def pending_refunds():
    refunds = (
        Refund.query
        .filter_by(decision_status="pending_review")
        .order_by(Refund.refund_date.desc())
        .all()
    )
    return jsonify({
        "success": True,
        "refunds": [refund_to_staff_dict(r) for r in refunds]
    })


_TRANSITION_EVENTS = {
    APPROVED: "refund_approved_by_staff",
    REJECTED: "refund_rejected_by_staff",
    REFUNDED: "refund_marked_refunded",
}
_DEFAULT_REASONS = {
    APPROVED: "Approved by staff review",
    REJECTED: "Rejected by staff review",
}


def _staff_transition(refund_id, target):
    """Apply a staff state change with a row lock and a full audit record."""
    data = request.get_json(silent=True) or {}
    uid = parse_uuid(refund_id)
    refund = (Refund.query.filter_by(refund_id=uid).with_for_update().first()
              if uid else None)
    if not refund:
        db.session.rollback()
        return jsonify({"success": False, "message": "Refund not found"}), 404

    previous = refund.decision_status
    try:
        ensure_transition(previous, target)
    except InvalidTransition:
        db.session.rollback()
        log.warning("Illegal transition %s -> %s for refund %s by %s",
                    previous, target, refund_id, g.staff.username)
        return jsonify({
            "success": False,
            "code": "INVALID_STATE",
            "message": f"This return is already {previous.replace('_', ' ')}.",
            "decision_status": previous,
        }), 409

    reason = str(data.get("reason") or "").strip()[:500]
    now = utcnow()
    details = {"previous_status": previous, "new_status": target,
               "timestamp": now.isoformat()}

    if target == REFUNDED:
        reference = str(data.get("payment_reference") or "").strip()[:255]
        if not reference:
            db.session.rollback()
            return jsonify({"success": False, "code": "PAYMENT_REFERENCE_REQUIRED",
                            "message": "Enter the POS refund reference."}), 400
        refund.payment_reference = reference
        refund.refunded_at = now
        refund.refunded_by_staff_id = g.staff.staff_id
        details["payment_reference"] = reference
    else:
        refund.decision_reason = reason or _DEFAULT_REASONS[target]
        refund.staff_override = True
        refund.staff_id = g.staff.staff_id
        refund.decided_at = now
        details["reason"] = refund.decision_reason

    refund.decision_status = target
    db.session.add(AuditLog(event_type=_TRANSITION_EVENTS[target], refund_id=refund.refund_id,
                            staff_id=g.staff.staff_id, details=details))
    db.session.commit()
    log.info("Refund %s %s -> %s by %s", refund.refund_id, previous, target, g.staff.username)
    return jsonify({"success": True, "message": f"Return {target.replace('_', ' ')}",
                    "refund": refund_to_staff_dict(refund)})


@api_bp.post("/refunds/<refund_id>/approve")
@require_staff(*REVIEW_ROLES)
def approve_refund(refund_id):
    return _staff_transition(refund_id, APPROVED)


@api_bp.post("/refunds/<refund_id>/reject")
@require_staff(*REVIEW_ROLES)
def reject_refund(refund_id):
    return _staff_transition(refund_id, REJECTED)


@api_bp.post("/refunds/<refund_id>/mark-refunded")
@require_staff(*REVIEW_ROLES)
def mark_refunded(refund_id):
    """Record that the money was returned (e.g. refund issued at the POS)."""
    return _staff_transition(refund_id, REFUNDED)
