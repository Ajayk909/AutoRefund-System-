"""Catalog: products sold by a retailer."""
import uuid

from sqlalchemy.dialects.postgresql import UUID

from app import db


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
