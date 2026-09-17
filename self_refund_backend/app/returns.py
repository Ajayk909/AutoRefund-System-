"""
Return eligibility rules used by the kiosk endpoints.

Kept free of Flask request handling so the rules can be unit tested and,
in Phase 1, moved into the returns service unchanged.
"""
import glob
import os
import re
import time
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import and_, or_

from app.models import Refund
from app.refund_states import PENDING_REVIEW, QUANTITY_CONSUMING, REJECTED
from app.timeutil import utcnow

IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{8,100}$")
CAPTURE_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class ReturnError(Exception):
    """A business rule stopped the return. ``message`` is customer-safe."""

    def __init__(self, code, message, status=400, **extra):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.extra = extra

    def body(self):
        return {"success": False, "code": self.code, "message": self.message, **self.extra}


# --- Return window ---------------------------------------------------------
def return_deadline(transaction, window_days):
    return transaction.purchase_date + timedelta(days=window_days)


def within_return_window(transaction, window_days, now=None):
    return (now or utcnow()) <= return_deadline(transaction, window_days)


# --- Quantity accounting ---------------------------------------------------
def refunds_for_line(transaction_item):
    """All refunds for a receipt line (includes pre-Phase-0 rows that were
    recorded by transaction + product only)."""
    return Refund.query.filter(or_(
        Refund.transaction_item_id == transaction_item.item_id,
        and_(Refund.transaction_item_id.is_(None),
             Refund.transaction_id == transaction_item.transaction_id,
             Refund.product_id == transaction_item.product_id),
    )).order_by(Refund.refund_date.desc()).populate_existing().all()


def count_line_usage(transaction_item):
    """Return (used_quantity, rejected_attempts, refunds_newest_first)."""
    refunds = refunds_for_line(transaction_item)
    used = sum((r.quantity or 1) for r in refunds if r.decision_status in QUANTITY_CONSUMING)
    rejected = sum(1 for r in refunds if r.decision_status == REJECTED)
    return used, rejected, refunds


def line_eligibility(transaction, transaction_item, config):
    """Customer-facing eligibility for one receipt line."""
    used, rejected, refunds = count_line_usage(transaction_item)
    remaining = max(transaction_item.quantity - used, 0)
    reason = None
    if not within_return_window(transaction, config["RETURN_WINDOW_DAYS"]):
        reason = "OUTSIDE_RETURN_WINDOW"
    elif remaining == 0:
        pending = any(r.decision_status == PENDING_REVIEW for r in refunds)
        reason = "PENDING_REVIEW" if pending else "ALREADY_RETURNED"
    elif rejected > config["RETURN_RETRY_LIMIT_AFTER_REJECTION"]:
        reason = "TOO_MANY_ATTEMPTS"
    return {
        "returned_quantity": used,
        "returnable_quantity": remaining,
        "rejected_attempts": rejected,
        "is_refundable": reason is None,
        "ineligible_reason": reason,
        "latest_status": refunds[0].decision_status if refunds else None,
    }


# --- Weight ------------------------------------------------------------------
def weight_check(product, quantity, measured):
    expected = Decimal(str(product.expected_weight_grams)) * quantity
    tolerance = Decimal(str(product.weight_tolerance_percent or 0))
    allowed = expected * tolerance / Decimal("100")
    return {
        "expected": expected,
        "min": expected - allowed,
        "max": expected + allowed,
        "match": expected - allowed <= measured <= expected + allowed,
    }


# --- Captured evidence -------------------------------------------------------
def capture_filename_for(capture_id, capture_dir):
    matches = glob.glob(os.path.join(str(capture_dir), f"*_{capture_id}.jpg"))
    return os.path.basename(matches[0]) if len(matches) == 1 else None


def resolve_capture(capture_id, capture_dir, max_age_seconds):
    """Map a kiosk capture id to its image, only if it was taken by this
    backend recently and has not already been used as evidence."""
    if not capture_id or not CAPTURE_ID_RE.match(str(capture_id)):
        return None
    filename = capture_filename_for(capture_id, capture_dir)
    if not filename:
        return None
    path = os.path.join(str(capture_dir), filename)
    if time.time() - os.path.getmtime(path) > max_age_seconds:
        return None
    relative = f"captures/{filename}"
    if Refund.query.filter_by(image_path=relative).first():
        return None
    return relative
