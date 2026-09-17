"""Staff decisions on returns: approve, reject, mark refunded."""
import logging

from app import db
from app.audit import service as audit
from app.errors import DomainError
from app.ids import parse_uuid
from app.returns import repository
from app.returns.states import APPROVED, REFUNDED, REJECTED, InvalidTransition, ensure_transition
from app.timeutil import utcnow

log = logging.getLogger("autorefund.review")

_EVENTS = {
    APPROVED: "refund_approved_by_staff",
    REJECTED: "refund_rejected_by_staff",
    REFUNDED: "refund_marked_refunded",
}
_DEFAULT_REASONS = {
    APPROVED: "Approved by staff review",
    REJECTED: "Rejected by staff review",
}


def apply_staff_decision(staff, refund_id, target, reason=None, payment_reference=None):
    """Change a return's status with a row lock and a full audit record."""
    uid = parse_uuid(refund_id)
    refund = repository.get(uid, lock=True) if uid else None
    if not refund:
        db.session.rollback()
        raise DomainError("NOT_FOUND", "Refund not found", 404)

    previous = refund.decision_status
    try:
        ensure_transition(previous, target)
    except InvalidTransition:
        db.session.rollback()
        log.warning("Illegal transition %s -> %s for refund %s by %s",
                    previous, target, refund_id, staff.username)
        raise DomainError("INVALID_STATE",
                          f"This return is already {previous.replace('_', ' ')}.", 409,
                          decision_status=previous)

    now = utcnow()
    details = {"previous_status": previous, "new_status": target, "timestamp": now.isoformat()}

    if target == REFUNDED:
        reference = str(payment_reference or "").strip()[:255]
        if not reference:
            db.session.rollback()
            raise DomainError("PAYMENT_REFERENCE_REQUIRED", "Enter the POS refund reference.")
        refund.payment_reference = reference
        refund.refunded_at = now
        refund.refunded_by_staff_id = staff.staff_id
        details["payment_reference"] = reference
    else:
        refund.decision_reason = str(reason or "").strip()[:500] or _DEFAULT_REASONS[target]
        refund.staff_override = True
        refund.staff_id = staff.staff_id
        refund.decided_at = now
        details["reason"] = refund.decision_reason

    refund.decision_status = target
    audit.record(_EVENTS[target], refund_id=refund.refund_id, staff_id=staff.staff_id, **details)
    db.session.commit()
    log.info("Refund %s %s -> %s by %s", refund.refund_id, previous, target, staff.username)
    return refund
