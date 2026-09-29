"""
Verification signals: one row per check made on a return (barcode, weight,
photo, AI), with its result, confidence and reason. Staff use them to see
why a return was approved or sent to review.
"""
import uuid

from sqlalchemy.dialects.postgresql import UUID

from app import db


class VerificationSignal(db.Model):
    __tablename__ = "verification_signals"

    signal_id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    refund_id = db.Column(UUID(as_uuid=True), nullable=False)
    retailer_id = db.Column(UUID(as_uuid=True), nullable=False)
    signal_type = db.Column(db.String(20), nullable=False)
    result = db.Column(db.String(20), nullable=False)
    # NULL for rule checks (weight, barcode, photo): they don't produce a
    # confidence, and we don't invent one.
    confidence = db.Column(db.Numeric(4, 3), nullable=True)
    reason = db.Column(db.String(500), nullable=False)
    # What made the check, e.g. "weight-rule", or "none" when no AI is set up.
    source = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False)

    __table_args__ = (
        # One row per check per return. Also serves "all signals of a return"
        # lookups, because refund_id comes first.
        db.UniqueConstraint("refund_id", "signal_type",
                            name="uq_verification_signals_refund_type"),
        # Same-retailer link, like the other tables: PostgreSQL refuses a
        # signal that points at another retailer's return.
        db.ForeignKeyConstraint(["retailer_id", "refund_id"],
                                ["refunds.retailer_id", "refunds.refund_id"],
                                name="fk_verification_signals_refund_same_retailer"),
        # Plain text + CHECK instead of a PostgreSQL ENUM: adding a value
        # later is a simple migration.
        db.CheckConstraint("signal_type IN ('barcode', 'weight', 'photo', 'ai')",
                           name="ck_verification_signals_type"),
        db.CheckConstraint("result IN ('match', 'mismatch', 'uncertain')",
                           name="ck_verification_signals_result"),
        db.CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
                           name="ck_verification_signals_confidence"),
    )
