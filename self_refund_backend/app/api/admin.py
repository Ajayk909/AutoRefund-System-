"""Admin-only endpoints: managing the retailer's product catalog."""
from flask import current_app, g, jsonify, request

from app.api import api_bp
from app.catalog import reference_images
from app.identity.auth import require_staff
from app.ids import parse_uuid


@api_bp.post("/admin/products/<product_id>/reference-images")
@require_staff("admin")
def add_reference_image(product_id):
    """Upload a reference photo (multipart form field "image", JPG or PNG)."""
    max_bytes = current_app.config["MAX_EVIDENCE_BYTES"]
    upload = request.files.get("image")
    # Read one byte past the limit, so an oversized file is detected
    # without reading all of it.
    data = upload.read(max_bytes + 1) if upload else b""
    image = reference_images.add_reference_image(
        g.staff, parse_uuid(product_id), data, current_app.evidence_storage, max_bytes)
    return jsonify({"success": True, "image_id": str(image.image_id),
                    "s3_key": image.s3_key}), 201
