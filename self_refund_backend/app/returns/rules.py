"""
Return eligibility rules.

These functions decide *whether* something is allowed. They do not read
requests, talk to hardware or commit to the database, so they are easy to
test and to reuse when the kiosk agent / cloud API split happens.
"""
import re
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from app.errors import DomainError
from app.returns import repository
from app.returns.policy import ReturnPolicy
from app.returns.states import APPROVED, PENDING_REVIEW, QUANTITY_CONSUMING, REJECTED
from app.timeutil import utcnow
from app.verification.image_verifier import (MATCH, MISMATCH, UNCERTAIN, ImageVerifier,
                                             VerificationResult)

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
def weight_check(product, quantity, measured, decline_percent):
    expected = Decimal(str(product.expected_weight_grams)) * quantity
    tolerance = Decimal(str(product.weight_tolerance_percent or 0))
    allowed = expected * tolerance / Decimal("100")
    far = expected * Decimal(decline_percent) / Decimal("100")
    return {
        "expected": expected,
        "min": expected - allowed,
        "max": expected + allowed,
        "match": expected - allowed <= measured <= expected + allowed,
        # So far off that it can't be the right item (e.g. an empty can).
        "far_off": abs(measured - expected) > far,
    }


# --- Verification signals ------------------------------------------------------
BARCODE = "barcode"
WEIGHT = "weight"
PHOTO = "photo"
AI = "ai"
# decide() looks at signals in this order, so the reason a return goes to
# review is always the same for the same checks.
SIGNAL_ORDER = (BARCODE, WEIGHT, PHOTO, AI)
# The customer sees the decision reason. The AI's own words ("the pump is
# missing") are for staff only, and are saved with the AI signal.
AI_REVIEW_REASON = "We need an employee to review this return"
# Polite on purpose: a declined customer is sent to a person, never accused.
WEIGHT_DECLINE_MESSAGE = ("This item doesn't match your receipt. "
                          "Please visit the customer service desk.")


@dataclass(frozen=True)
class Signal:
    """One check on a return, as saved in verification_signals."""
    signal_type: str          # barcode | weight | photo | ai
    result: str               # match | mismatch | uncertain
    reason: str
    source: str
    confidence: float | None = None
    # False only for the "no AI configured" placeholder. It is saved so staff
    # can see that no AI looked at the photo, but it must not change the decision.
    is_real_check: bool = True
    # Set only when this check alone is sure enough for the kiosk to decline
    # the return. The text is what the customer sees. Not saved: the decline
    # itself is saved as the return's status and reason.
    decline_message: str | None = None


def barcode_signal(barcode: str | None) -> Signal | None:
    """Only saved when the kiosk sent a barcode (today's screens let the
    customer pick the item from the receipt instead). A barcode that isn't on
    the receipt never gets here: the return is refused earlier (NOT_ON_RECEIPT)."""
    if not barcode:
        return None
    return Signal(BARCODE, MATCH, "Barcode matches a line on the receipt", "receipt-lookup")


def weight_signal(weight: dict) -> Signal:
    if weight["match"]:
        return Signal(WEIGHT, MATCH, "Weight matched expected product tolerance", "weight-rule")
    if weight["far_off"]:
        return Signal(WEIGHT, MISMATCH, "Weight far outside the allowed range (declined)",
                      "weight-rule", decline_message=WEIGHT_DECLINE_MESSAGE)
    return Signal(WEIGHT, MISMATCH, "Weight outside allowed tolerance", "weight-rule")


def photo_signal(photo_captured: bool) -> Signal:
    """Only says whether a photo exists. What the photo shows is the AI signal's job."""
    if photo_captured:
        return Signal(PHOTO, MATCH, "Item photo captured", "kiosk-camera")
    return Signal(PHOTO, UNCERTAIN, "No item photo could be captured", "kiosk-camera")


def ai_signal(answer: VerificationResult, verifier: ImageVerifier) -> Signal:
    return Signal(AI, answer.result, answer.reason, verifier.name,
                  confidence=answer.confidence, is_real_check=verifier.is_real_check)


# --- Decision ----------------------------------------------------------------
def decide(signals: list[Signal], policy: ReturnPolicy) -> tuple[str, str]:
    """Automatic outcome from the verification signals.

    A check with a decline_message declines the return straight away
    (rejected, by the system). Any other check that isn't a clear "match"
    sends the return to an employee. Only a matching weight can approve: a
    photo or an AI "match" on its own never does, because the weight is the
    one check we fully trust.
    """
    ordered = sorted(signals, key=lambda s: SIGNAL_ORDER.index(s.signal_type))
    for signal in ordered:
        if signal.decline_message and _counts(signal, policy):
            return REJECTED, signal.decline_message
    for signal in ordered:
        if _counts(signal, policy) and signal.result != MATCH:
            return PENDING_REVIEW, AI_REVIEW_REASON if signal.signal_type == AI else signal.reason
    if not any(s.signal_type == WEIGHT and s.result == MATCH for s in signals):
        return PENDING_REVIEW, "Weight was not checked"
    return APPROVED, "Weight matched expected product tolerance"


def _counts(signal: Signal, policy: ReturnPolicy) -> bool:
    """Whether a signal may change the decision."""
    if not signal.is_real_check:
        return False  # "no AI configured" is a note for staff, not a check
    if signal.signal_type == PHOTO and not policy.require_photo_for_auto_approval:
        return False  # this policy accepts returns without a photo
    return True
