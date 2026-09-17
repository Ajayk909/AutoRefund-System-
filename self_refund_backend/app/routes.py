from decimal import Decimal
from datetime import datetime
import logging
import os
import cv2

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
from app.refund_states import APPROVED, REFUNDED, REJECTED, InvalidTransition, ensure_transition
from app.timeutil import utcnow
from hardware import HardwareError, get_camera, get_scale
from hardware.barcode import backend_name as barcode_backend_name

api_bp = Blueprint("api", __name__)
log = logging.getLogger("autorefund.api")


def capture_dir():
    return str(current_app.config["CAPTURE_DIR"])


def existing_capture_path(image_path):
    """Return the normalized captures/<file> path only if the file exists."""
    normalized = normalize_capture_path(image_path)
    if not normalized:
        return None
    filename = os.path.basename(normalized)
    if os.path.isfile(os.path.join(capture_dir(), filename)):
        return normalized
    return None


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

    item_list = []
    for item, product in items:
        existing_refund = Refund.query.filter_by(
            transaction_id=transaction.transaction_id,
            product_id=product.product_id
        ).first()

        item_list.append({
            "item_id": str(item.item_id),
            "product_id": str(product.product_id),
            "barcode": product.barcode,
            "name": product.name,
            "quantity": item.quantity,
            "price_at_purchase": float(item.price_at_purchase),
            "expected_weight_grams": float(product.expected_weight_grams),
            "weight_tolerance_percent": float(product.weight_tolerance_percent),
            "is_refundable": existing_refund is None,
            "refund_status": existing_refund.decision_status if existing_refund else None,
        })

    return jsonify({
        "success": True,
        "transaction": {
            "transaction_id": str(transaction.transaction_id),
            "receipt_number": transaction.receipt_number,
            "purchase_date": transaction.purchase_date.isoformat(),
            "payment_method": transaction.payment_method,
            "customer_email": transaction.customer_email,
            "total_amount": float(transaction.total_amount),
            "items": item_list
        }
    })


@api_bp.post("/refunds/start")
def start_refund():
    data = request.get_json() or {}

    receipt_number = data.get("receipt_number")
    barcode = data.get("barcode")
    transaction_id = data.get("transaction_id")
    product_id = data.get("product_id")
    item_id = data.get("item_id")
    measured_weight_grams = data.get("measured_weight_grams")
    requested_image_path = data.get("image_path")
    image_path = existing_capture_path(requested_image_path)
    if requested_image_path and not image_path:
        log.warning("Refund submitted with missing image file: %s", requested_image_path)
    kiosk_id = data.get("kiosk_id") or current_app.config["KIOSK_ID"]

    if measured_weight_grams is None:
        return jsonify({
            "success": False,
            "message": "measured_weight_grams is required"
        }), 400

    transaction = None
    product = None

    if receipt_number:
        transaction = Transaction.query.filter_by(receipt_number=receipt_number).first()
    elif transaction_id:
        transaction = Transaction.query.filter_by(transaction_id=transaction_id).first()

    if not transaction:
        return jsonify({
            "success": False,
            "message": "Transaction not found"
        }), 404

    if barcode:
        product = Product.query.filter_by(barcode=barcode).first()
    elif product_id:
        product = Product.query.filter_by(product_id=product_id).first()

    if not product:
        return jsonify({
            "success": False,
            "message": "Product not found"
        }), 404

    transaction_item = None

    if item_id:
        transaction_item = TransactionItem.query.filter_by(
            item_id=item_id,
            transaction_id=transaction.transaction_id
        ).first()

    if not transaction_item:
        transaction_item = TransactionItem.query.filter_by(
            transaction_id=transaction.transaction_id,
            product_id=product.product_id
        ).first()

    if not transaction_item:
        return jsonify({
            "success": False,
            "message": "This product is not part of the provided transaction"
        }), 400

    existing_refund = Refund.query.filter_by(
        transaction_id=transaction.transaction_id,
        product_id=product.product_id
    ).first()

    if existing_refund:
        log.warning(
            "Duplicate refund attempt blocked: receipt=%s product=%s existing=%s",
            transaction.receipt_number, product.barcode, existing_refund.refund_id)
        db.session.add(AuditLog(
            event_type="duplicate_refund_blocked",
            refund_id=existing_refund.refund_id,
            staff_id=None,
            details={
                "receipt_number": transaction.receipt_number,
                "barcode": product.barcode,
                "kiosk_id": kiosk_id,
                "existing_refund_status": existing_refund.decision_status,
                "timestamp": datetime.utcnow().isoformat(),
            },
        ))
        db.session.commit()
        return jsonify({
            "success": False,
            "message": "This item has already been submitted for refund.",
            "existing_refund_status": existing_refund.decision_status
        }), 400

    try:
        measured = Decimal(str(measured_weight_grams))
    except Exception:
        return jsonify({
            "success": False,
            "message": "measured_weight_grams must be a number"
        }), 400
    if not measured.is_finite() or measured < 0:
        return jsonify({
            "success": False,
            "message": "measured_weight_grams must be a non-negative number"
        }), 400
    expected = Decimal(str(product.expected_weight_grams))
    tolerance_percent = Decimal(str(product.weight_tolerance_percent))

    allowed_diff = expected * (tolerance_percent / Decimal("100"))
    min_weight = expected - allowed_diff
    max_weight = expected + allowed_diff

    weight_match = min_weight <= measured <= max_weight

    if weight_match:
        decision_status = "approved"
        decision_reason = "Weight matched expected product tolerance"
    else:
        decision_status = "pending_review"
        decision_reason = "Weight outside allowed tolerance"

    refund = Refund(
        transaction_id=transaction.transaction_id,
        product_id=product.product_id,
        kiosk_id=kiosk_id,
        measured_weight_grams=measured,
        weight_match=weight_match,
        refund_amount=transaction_item.price_at_purchase,
        refund_date=datetime.utcnow(),
        decision_status=decision_status,
        decision_reason=decision_reason,
        image_path=image_path,
        staff_override=False
    )

    db.session.add(refund)
    db.session.flush()

    audit = AuditLog(
        event_type="refund_started",
        refund_id=refund.refund_id,
        staff_id=None,
        details={
            "receipt_number": transaction.receipt_number,
            "barcode": product.barcode,
            "kiosk_id": kiosk_id,
            "expected_weight_grams": float(expected),
            "measured_weight_grams": float(measured),
            "weight_match": weight_match,
            "decision_status": decision_status,
            "image_captured": image_path is not None,
            "timestamp": datetime.utcnow().isoformat()
        }
    )

    db.session.add(audit)
    db.session.commit()
    log.info("Refund %s created: receipt=%s product=%s weight=%s expected=%s status=%s",
             refund.refund_id, transaction.receipt_number, product.barcode,
             measured, expected, decision_status)

    return jsonify({
        "success": True,
        "refund": {
            "refund_id": str(refund.refund_id),
            "decision_status": decision_status,
            "decision_reason": decision_reason,
            "weight_match": weight_match,
            "expected_weight_grams": float(expected),
            "measured_weight_grams": float(measured),
            "refund_amount": float(transaction_item.price_at_purchase),
            "image_path": image_path
        }
    }), 201


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
    try:
        result = get_camera().capture_image()
        filename = result["filename"]
        image_path = result["relative_path"]
        image_url = f"/api/captures/{filename}"
        log.info("Image captured: %s", image_path)

        return jsonify({
            "success": True,
            "filename": filename,
            "file_name": filename,
            "image_path": image_path,
            "image_url": image_url
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
