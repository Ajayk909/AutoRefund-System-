"""Database access for products. Every lookup is scoped to one retailer."""
from app import db
from app.models import Product, ProductIdentifier


def find_by_barcode(retailer_id, value):
    """The retailer's product with this barcode/identifier, or None."""
    return (
        Product.query.join(ProductIdentifier,
                           (ProductIdentifier.product_id == Product.product_id)
                           & (ProductIdentifier.retailer_id == Product.retailer_id))
        .filter(Product.retailer_id == retailer_id, ProductIdentifier.value == value)
        .first()
    )


def get(retailer_id, product_id):
    if not product_id:
        return None
    return Product.query.filter_by(retailer_id=retailer_id, product_id=product_id).first()


def primary_barcode(product):
    """The identifier shown as "barcode" (primary one, else the oldest)."""
    identifier = (
        db.session.query(ProductIdentifier.value)
        .filter(ProductIdentifier.product_id == product.product_id)
        .order_by(ProductIdentifier.is_primary.desc(), ProductIdentifier.created_at)
        .first()
    )
    return identifier[0] if identifier else None


def add_identifier(product, value, identifier_type="barcode", is_primary=True):
    identifier = ProductIdentifier(retailer_id=product.retailer_id,
                                   product_id=product.product_id,
                                   identifier_type=identifier_type, value=value,
                                   is_primary=is_primary)
    db.session.add(identifier)
    return identifier
