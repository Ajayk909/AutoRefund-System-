"""Audit trail."""
import uuid

from sqlalchemy.dialects.postgresql import JSONB, UUID

from app import db


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    log_id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp = db.Column(db.DateTime, server_default=db.func.now())
    event_type = db.Column(db.String(100), nullable=False)
    refund_id = db.Column(UUID(as_uuid=True), db.ForeignKey("refunds.refund_id"), nullable=True)
    staff_id = db.Column(UUID(as_uuid=True), db.ForeignKey("staff.staff_id"), nullable=True)
    details = db.Column(JSONB, nullable=True)
