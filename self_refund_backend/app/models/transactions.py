"""Receipts: purchase transactions and their lines."""
import uuid

from sqlalchemy.dialects.postgresql import UUID

from app import db


class Transaction(db.Model):
    __tablename__ = "transactions"

    transaction_id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    retailer_id = db.Column(UUID(as_uuid=True), nullable=False)
    # Store where the purchase was made.
    store_id = db.Column(UUID(as_uuid=True), nullable=False)
    receipt_number = db.Column(db.String(100), nullable=False)
    customer_email = db.Column(db.String(255), nullable=True)
    purchase_date = db.Column(db.DateTime, nullable=False)
    payment_method = db.Column(db.String(100), nullable=False)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("retailer_id", "receipt_number",
                            name="uq_transactions_retailer_receipt"),
        db.UniqueConstraint("retailer_id", "transaction_id",
                            name="uq_transactions_retailer_transaction"),
        db.ForeignKeyConstraint(["retailer_id", "store_id"],
                                ["stores.retailer_id", "stores.store_id"],
                                name="fk_transactions_store_same_retailer"),
    )


class TransactionItem(db.Model):
    __tablename__ = "transaction_items"

    item_id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    retailer_id = db.Column(UUID(as_uuid=True), nullable=False)
    transaction_id = db.Column(UUID(as_uuid=True), db.ForeignKey("transactions.transaction_id"), nullable=False)
    product_id = db.Column(UUID(as_uuid=True), db.ForeignKey("products.product_id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price_at_purchase = db.Column(db.Numeric(10, 2), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("retailer_id", "item_id", name="uq_transaction_items_retailer_item"),
        db.ForeignKeyConstraint(["retailer_id", "transaction_id"],
                                ["transactions.retailer_id", "transactions.transaction_id"],
                                name="fk_transaction_items_transaction_same_retailer"),
        db.ForeignKeyConstraint(["retailer_id", "product_id"],
                                ["products.retailer_id", "products.product_id"],
                                name="fk_transaction_items_product_same_retailer"),
    )
