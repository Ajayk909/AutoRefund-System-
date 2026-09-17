"""Catalog: products sold by a retailer and their external identifiers."""
import uuid

from sqlalchemy.dialects.postgresql import UUID

from app import db


class Product(db.Model):
    """A retailer's product. ``product_id`` is AutoRefund's own identity;
    barcodes, SKUs etc. live in ``product_identifiers``."""
    __tablename__ = "products"

    product_id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    retailer_id = db.Column(UUID(as_uuid=True), db.ForeignKey("retailers.retailer_id"),
                            nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(100))
    expected_weight_grams = db.Column(db.Numeric(10, 2), nullable=False)
    weight_tolerance_percent = db.Column(db.Numeric(5, 2), default=5.0)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    __table_args__ = (
        db.UniqueConstraint("retailer_id", "product_id", name="uq_products_retailer_product"),
    )


class ProductIdentifier(db.Model):
    """An external identifier (barcode, SKU, PLU...) for a product.

    Unique per retailer: the same barcode may belong to different products at
    different retailers, but never to two products of the same retailer.
    """
    __tablename__ = "product_identifiers"

    identifier_id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    retailer_id = db.Column(UUID(as_uuid=True), nullable=False)
    product_id = db.Column(UUID(as_uuid=True), nullable=False, index=True)
    identifier_type = db.Column(db.String(20), nullable=False, default="barcode",
                                server_default="barcode")
    value = db.Column(db.String(100), nullable=False)
    is_primary = db.Column(db.Boolean, nullable=False, default=False, server_default="false")
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    __table_args__ = (
        db.UniqueConstraint("retailer_id", "value", name="uq_product_identifiers_retailer_value"),
        db.ForeignKeyConstraint(["retailer_id", "product_id"],
                                ["products.retailer_id", "products.product_id"],
                                name="fk_product_identifiers_product_same_retailer",
                                ondelete="CASCADE"),
        db.Index("uq_product_identifiers_one_primary", "product_id", unique=True,
                 postgresql_where=db.text("is_primary")),
    )
