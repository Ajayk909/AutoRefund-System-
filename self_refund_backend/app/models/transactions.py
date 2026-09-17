"""Receipts: purchase transactions and their lines."""
import uuid

from sqlalchemy.dialects.postgresql import UUID

from app import db


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
