import uuid
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import Enum
from app import db

decision_status_enum = Enum(
    "approved", "rejected", "pending_review",
    name="decision_status_enum"
)

staff_role_enum = Enum(
    "admin", "customer_service", "manager",
    name="staff_role_enum"
)

class Product(db.Model):
    __tablename__ = "products"

    product_id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    barcode = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(100))
    expected_weight_grams = db.Column(db.Numeric(10, 2), nullable=False)
    weight_tolerance_percent = db.Column(db.Numeric(5, 2), default=5.0)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())


class Transaction(db.Model):
    __tablename__ = "transactions"

    transaction_id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    receipt_number = db.Column(db.String(100), nullable=False, unique=True)
    customer_email = db.Column(db.String(255), nullable=True)
    purchase_date = db.Column(db.DateTime, nullable=False)
    payment_method = db.Column(db.String(100), nullable=False)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)


class TransactionItem(db.Model):
    __tablename__ = "transaction_items"

    item_id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = db.Column(UUID(as_uuid=True), db.ForeignKey("transactions.transaction_id"), nullable=False)
    product_id = db.Column(UUID(as_uuid=True), db.ForeignKey("products.product_id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price_at_purchase = db.Column(db.Numeric(10, 2), nullable=False)


class Staff(db.Model):
    __tablename__ = "staff"

    staff_id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(255), nullable=False)
    role = db.Column(staff_role_enum, nullable=False)
    email = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())


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


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    log_id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp = db.Column(db.DateTime, server_default=db.func.now())
    event_type = db.Column(db.String(100), nullable=False)
    refund_id = db.Column(UUID(as_uuid=True), db.ForeignKey("refunds.refund_id"), nullable=True)
    staff_id = db.Column(UUID(as_uuid=True), db.ForeignKey("staff.staff_id"), nullable=True)
    details = db.Column(JSONB, nullable=True)