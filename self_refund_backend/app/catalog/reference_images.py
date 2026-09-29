"""
Product reference photos: the retailer's own picture of each product. The AI
photo check (later) will compare the kiosk's photo against these.
"""
from app import db
from app.audit import service as audit
from app.catalog import repository as catalog
from app.errors import DomainError
from app.models import ProductImage

RETAILER_CATALOG = "retailer_catalog"


def add_reference_image(staff, product_id, data, storage, max_bytes):
    """Save a reference photo for a product of the staff member's retailer."""
    product = catalog.get(staff.retailer_id, product_id)
    if not product:
        # Same answer for another retailer's product, so we don't reveal it exists.
        raise DomainError("PRODUCT_NOT_FOUND", "Product not found.", 404)
    key = storage.store_reference_image(data, max_bytes)
    image = ProductImage(retailer_id=product.retailer_id, product_id=product.product_id,
                         s3_key=key, source=RETAILER_CATALOG)
    db.session.add(image)
    audit.record("reference_image_added", staff_id=staff.staff_id,
                 retailer_id=product.retailer_id, product_id=str(product.product_id),
                 s3_key=key)
    db.session.commit()
    return image


def get_reference_images(retailer_id, product_id):
    """Storage keys of a product's reference photos, oldest first."""
    # A real retailer catalog connector will plug in here later.
    images = (ProductImage.query.filter_by(retailer_id=retailer_id, product_id=product_id)
              .order_by(ProductImage.created_at).all())
    return [image.s3_key for image in images]
