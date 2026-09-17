"""JSON shapes returned by the API."""
from app import db
from app.catalog import repository as catalog
from app.evidence import captures
from app.models import Staff
from app.tenancy import repository as tenancy


def product_to_dict(product):
    return {
        "product_id": str(product.product_id),
        "barcode": catalog.primary_barcode(product),
        "name": product.name,
        "category": product.category,
        "expected_weight_grams": float(product.expected_weight_grams),
        "weight_tolerance_percent": float(product.weight_tolerance_percent),
        "price": float(product.price),
    }


def return_result_to_dict(result):
    refund = result.refund
    return {
        "refund_id": str(refund.refund_id),
        "decision_status": refund.decision_status,
        "decision_reason": refund.decision_reason,
        "weight_match": refund.weight_match,
        "quantity": refund.quantity,
        "expected_weight_grams": float(result.expected_weight),
        "measured_weight_grams": float(refund.measured_weight_grams),
        "refund_amount": float(refund.refund_amount),
        "image_captured": result.image_captured,
        "idempotent_replay": result.replay,
    }


def refund_to_staff_dict(refund, capture_dir):
    product = catalog.get(refund.retailer_id, refund.product_id)
    reviewer = db.session.get(Staff, refund.staff_id) if refund.staff_id else None
    quantity = refund.quantity or 1
    has_image = captures.evidence_file(refund.image_path, capture_dir) is not None
    return {
        "refund_id": str(refund.refund_id),
        "item_name": product.name if product else "Unknown Item",
        "barcode": catalog.primary_barcode(product) if product else None,
        "decision_status": refund.decision_status,
        "refund_date": refund.refund_date.isoformat() if refund.refund_date else None,
        "quantity": quantity,
        "measured_weight_grams": float(refund.measured_weight_grams),
        "expected_weight_grams": (float(product.expected_weight_grams) * quantity
                                  if product else None),
        "weight_match": refund.weight_match,
        "refund_amount": float(refund.refund_amount),
        "decision_reason": refund.decision_reason,
        "kiosk_id": str(refund.kiosk_id),
        "kiosk_code": refund.kiosk_code,
        "store_code": tenancy.store_code(refund.store_id),
        "reviewed_by": reviewer.full_name if reviewer else None,
        "decided_at": refund.decided_at.isoformat() if refund.decided_at else None,
        "payment_reference": refund.payment_reference,
        "refunded_at": refund.refunded_at.isoformat() if refund.refunded_at else None,
        "has_image": has_image,
        # Authenticated URL: the browser must send the staff bearer token.
        "image_url": f"/api/refunds/{refund.refund_id}/image" if has_image else None,
    }
