"""
Legal return/refund state transitions.

    pending_review --staff--> approved | rejected
    approved       --staff--> refunded      (money actually returned)

"approved" means the return passed verification or staff review. It does
NOT mean money has moved: there is no payment integration yet, so an
employee issues the refund at the POS and records it with "mark refunded".
A future payment/retailer adapter will perform approved -> refunded.
"""

PENDING_REVIEW = "pending_review"
APPROVED = "approved"
REJECTED = "rejected"
REFUNDED = "refunded"

ALLOWED_TRANSITIONS = {
    PENDING_REVIEW: {APPROVED, REJECTED},
    APPROVED: {REFUNDED},
    REJECTED: set(),
    REFUNDED: set(),
}

# Statuses whose quantity is "used up" on a receipt line. A rejected return
# releases its quantity so the customer may try again (subject to limits).
QUANTITY_CONSUMING = {PENDING_REVIEW, APPROVED, REFUNDED}


class InvalidTransition(Exception):
    def __init__(self, current, target):
        super().__init__(f"Cannot change a {current} return to {target}")
        self.current = current
        self.target = target


def ensure_transition(current, target):
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise InvalidTransition(current, target)
