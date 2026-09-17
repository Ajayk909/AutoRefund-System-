"""
Return eligibility rules.

These functions decide *whether* something is allowed. They do not read
requests, talk to hardware or commit to the database, so they are easy to
test and to reuse when the kiosk agent / cloud API split happens.
"""
import re
from datetime import timedelta
from decimal import Decimal

from app.errors import DomainError
from app.returns import repository
from app.returns.states import PENDING_REVIEW, QUANTITY_CONSUMING, REJECTED
from app.timeutil import utcnow

IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{8,100}$")


class ReturnError(DomainError):
    """A return rule stopped the return. ``message`` is customer-safe."""


# --- Return window ---------------------------------------------------------
def return_deadline(transaction, window_days):
    return transaction.purchase_date + timedelta(days=window_days)


def within_return_window(transaction, window_days, now=None):
    return (now or utcnow()) <= return_deadline(transaction, window_days)


# --- Quantity accounting ---------------------------------------------------
def count_line_usage(transaction_item):
    """Return (used_quantity, rejected_attempts, refunds_newest_first)."""
    refunds = repository.refunds_for_line(transaction_item)
    used = sum((r.quantity or 1) for r in refunds if r.decision_status in QUANTITY_CONSUMING)
    rejected = sum(1 for r in refunds if r.decision_status == REJECTED)
    return used, rejected, refunds


def line_eligibility(transaction, transaction_item, policy):
    """Customer-facing eligibility for one receipt line."""
    used, rejected, refunds = count_line_usage(transaction_item)
    remaining = max(transaction_item.quantity - used, 0)
    reason = None
    if not within_return_window(transaction, policy.window_days):
        reason = "OUTSIDE_RETURN_WINDOW"
    elif remaining == 0:
        pending = any(r.decision_status == PENDING_REVIEW for r in refunds)
        reason = "PENDING_REVIEW" if pending else "ALREADY_RETURNED"
    elif rejected > policy.retry_limit_after_rejection:
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


# --- Decision ----------------------------------------------------------------
def decide(weight_match, photo_captured, policy):
    """Automatic outcome from the verification signals available today."""
    if not weight_match:
        return "pending_review", "Weight outside allowed tolerance"
    if not photo_captured and policy.require_photo_for_auto_approval:
        return "pending_review", "No item photo could be captured"
    return "approved", "Weight matched expected product tolerance"
