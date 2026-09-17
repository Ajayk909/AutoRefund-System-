"""Database access for products."""
from app import db
from app.models import Product


def find_by_barcode(barcode):
    return Product.query.filter_by(barcode=barcode).first()


def get(product_id):
    return db.session.get(Product, product_id) if product_id else None


def primary_barcode(product):
    return product.barcode
