"""Returns: one customer return of a receipt line (table name kept as
``refunds`` for compatibility)."""
import uuid

from sqlalchemy import Enum
from sqlalchemy.dialects.postgresql import UUID

from app import db


# Return lifecycle (see app/returns/states.py for the legal transitions):
#   pending_review -> approved | rejected
#   approved       -> refunded   (money actually returned, recorded separately)
decision_status_enum = Enum(
    "approved", "rejected", "pending_review", "refunded",
    name="decision_status_enum"
)


class Refund(db.Model):
    __tablename__ = "refunds"

    refund_id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = db.Column(UUID(as_uuid=True), db.ForeignKey("transactions.transaction_id"), nullable=False)
    product_id = db.Column(UUID(as_uuid=True), db.ForeignKey("products.product_id"), nullable=False)
    kiosk_id = db.Column(db.String(100), nullable=False)
    refund_date = db.Column(db.DateTime, server_default=db.func.now())
    measured_weight_grams = db.Column(db.Numeric(10, 2), nullable=False)
    weight_match = db.Column(db.Boolean, nullable=False)
    image_path = db.Column(db.String(500), nullable=True)
    decision_status = db.Column(decision_status_enum, nullable=False)
    decision_reason = db.Column(db.Text, nullable=True)
    staff_override = db.Column(db.Boolean, default=False)
    staff_id = db.Column(UUID(as_uuid=True), db.ForeignKey("staff.staff_id"), nullable=True)
    refund_amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_reference = db.Column(db.String(255), nullable=True)

    # --- Phase 0 additions (all nullable/defaulted so old rows stay valid) ---
    # Exact receipt line being returned; enables quantity accounting.
    transaction_item_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("transaction_items.item_id"),
        nullable=True, index=True)
    quantity = db.Column(db.Integer, nullable=False, default=1,
                         server_default="1")
    # Client-generated key; a retried submission returns the same refund.
    idempotency_key = db.Column(db.String(100), nullable=True, unique=True)
    decided_at = db.Column(db.DateTime, nullable=True)
    refunded_at = db.Column(db.DateTime, nullable=True)
    refunded_by_staff_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("staff.staff_id"), nullable=True)

    __table_args__ = (
        db.CheckConstraint("quantity > 0", name="ck_refunds_quantity_positive"),
    )
