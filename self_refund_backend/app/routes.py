from decimal import Decimal
from datetime import datetime
import os
import cv2

from flask import Blueprint, jsonify, request, Response, send_from_directory
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
from hardware.scale_service import get_weight_grams, get_live_weight_grams
from app.usb_camera_service import USBCameraService, CAPTURE_DIR

api_bp = Blueprint("api", __name__)

camera_service = USBCameraService("/dev/video0")


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
    image_path = normalize_capture_path(data.get("image_path", "mock_images/test.jpg"))
    kiosk_id = data.get("kiosk_id", "KIOSK-001")

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
        return jsonify({
            "success": False,
            "message": "This item has already been submitted for refund.",
            "existing_refund_status": existing_refund.decision_status
        }), 400

    measured = Decimal(str(measured_weight_grams))
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
            "timestamp": datetime.utcnow().isoformat()
        }
    )

    db.session.add(audit)
    db.session.commit()

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
        weight = get_weight_grams()
        return jsonify({
            "success": True,
            "weight_grams": weight
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@api_bp.get("/scale/live")
def get_live_scale():
    try:
        weight = get_live_weight_grams()
        safe_weight = 0 if weight is None else float(weight)
        stable = safe_weight > 0

        return jsonify({
            "success": True,
            "weight_grams": safe_weight,
            "stable": stable,
            "message": "Live weight fetched"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e),
            "weight_grams": 0,
            "stable": False
        }), 500


@api_bp.get("/camera/health")
def camera_health():
    try:
        if not camera_service.ensure_camera():
            return jsonify({
                "success": False,
                "message": "USB camera could not be opened"
            }), 500

        return jsonify({
            "success": True,
            "message": "USB camera is working",
            "source": str(camera_service.current_source)
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@api_bp.get("/camera/preview")
def camera_preview():
    try:
        frame = camera_service.get_frame()
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
        if not camera_service.ensure_camera():
            return jsonify({
                "success": False,
                "message": "Could not open USB camera"
            }), 500

        return Response(
            camera_service.generate_mjpeg_frames(),
            mimetype="multipart/x-mixed-replace; boundary=frame"
        )
    except Exception as e:
        print(f"/camera/stream failed: {e}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@api_bp.post("/camera/capture")
def camera_capture():
    try:
        result = camera_service.capture_image()
        filename = result["filename"]
        image_path = result["relative_path"]
        image_url = f"/api/captures/{filename}"

        return jsonify({
            "success": True,
            "filename": filename,
            "file_name": filename,
            "image_path": image_path,
            "image_url": image_url
        })
    except Exception as e:
        print(f"/camera/capture failed: {e}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@api_bp.get("/receipt/scan")
def scan_receipt():
    try:
        result = camera_service.scan_barcode()

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


@api_bp.get("/captures/<path:filename>")
def get_capture_file(filename):
    return send_from_directory(CAPTURE_DIR, filename)


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

    staff = Staff.query.filter_by(username=username).first()
    if not staff:
        return jsonify({
            "success": False,
            "message": "Invalid credentials"
        }), 401

    if not check_password_hash(staff.password_hash, password):
        return jsonify({
            "success": False,
            "message": "Invalid credentials"
        }), 401

    return jsonify({
        "success": True,
        "staff": {
            "staff_id": str(staff.staff_id),
            "username": staff.username,
            "full_name": staff.full_name,
            "role": staff.role,
            "email": staff.email
        }
    })


@api_bp.get("/refunds/logs")
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

    data = []
    for refund in refunds:
        product = Product.query.filter_by(product_id=refund.product_id).first()
        image_path = normalize_capture_path(refund.image_path)

        data.append({
            "refund_id": str(refund.refund_id),
            "item_name": product.name if product else "Unknown Item",
            "decision_status": refund.decision_status,
            "refund_date": refund.refund_date.isoformat() if refund.refund_date else None,
            "measured_weight_grams": float(refund.measured_weight_grams),
            "expected_weight_grams": float(product.expected_weight_grams) if product else None,
            "refund_amount": float(refund.refund_amount),
            "decision_reason": refund.decision_reason,
            "image_path": image_path,
            "image_url": f"/api/captures/{os.path.basename(image_path)}" if image_path else None
        })

    return jsonify({
        "success": True,
        "refunds": data
    })


@api_bp.get("/refunds/pending")
def pending_refunds():
    refunds = (
        Refund.query
        .filter_by(decision_status="pending_review")
        .order_by(Refund.refund_date.desc())
        .all()
    )

    data = []
    for refund in refunds:
        product = Product.query.filter_by(product_id=refund.product_id).first()
        image_path = normalize_capture_path(refund.image_path)

        data.append({
            "refund_id": str(refund.refund_id),
            "item_name": product.name if product else "Unknown Item",
            "decision_status": refund.decision_status,
            "refund_date": refund.refund_date.isoformat() if refund.refund_date else None,
            "measured_weight_grams": float(refund.measured_weight_grams),
            "expected_weight_grams": float(product.expected_weight_grams) if product else None,
            "refund_amount": float(refund.refund_amount),
            "decision_reason": refund.decision_reason,
            "image_path": image_path,
            "image_url": f"/api/captures/{os.path.basename(image_path)}" if image_path else None
        })

    return jsonify({
        "success": True,
        "refunds": data
    })


@api_bp.post("/refunds/<refund_id>/approve")
def approve_refund(refund_id):
    refund = Refund.query.filter_by(refund_id=refund_id).first()

    if not refund:
        return jsonify({
            "success": False,
            "message": "Refund not found"
        }), 404

    refund.decision_status = "approved"
    refund.decision_reason = "Approved by staff review"
    refund.staff_override = True

    audit = AuditLog(
        event_type="refund_approved_by_staff",
        refund_id=refund.refund_id,
        staff_id=None,
        details={
            "refund_id": str(refund.refund_id),
            "decision_status": "approved",
            "timestamp": datetime.utcnow().isoformat()
        }
    )

    db.session.add(audit)
    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Refund approved successfully"
    })


@api_bp.post("/refunds/<refund_id>/reject")
def reject_refund(refund_id):
    refund = Refund.query.filter_by(refund_id=refund_id).first()

    if not refund:
        return jsonify({
            "success": False,
            "message": "Refund not found"
        }), 404

    refund.decision_status = "rejected"
    refund.decision_reason = "Rejected by staff review"
    refund.staff_override = True

    audit = AuditLog(
        event_type="refund_rejected_by_staff",
        refund_id=refund.refund_id,
        staff_id=None,
        details={
            "refund_id": str(refund.refund_id),
            "decision_status": "rejected",
            "timestamp": datetime.utcnow().isoformat()
        }
    )

    db.session.add(audit)
    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Refund rejected successfully"
    })