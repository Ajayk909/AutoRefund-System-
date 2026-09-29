"""Phase 4: product reference photos (admin upload + lookup for the AI check)."""
import io
import os
import uuid

import pytest

from app.catalog.reference_images import get_reference_images
from app.models import AuditLog, Product, ProductImage
from tests.conftest import login

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 200
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 200


def _product(name):
    return Product.query.filter_by(name=name).one()


def _upload(client, headers, product_id, data, filename="photo.jpg"):
    return client.post(f"/api/admin/products/{product_id}/reference-images", headers=headers,
                       data={"image": (io.BytesIO(data), filename)},
                       content_type="multipart/form-data")


def test_admin_can_upload_a_reference_image(client, app, staff_headers):
    coke = _product("Coca Cola Can")
    r = _upload(client, staff_headers, coke.product_id, JPEG)
    assert r.status_code == 201, r.get_json()
    key = r.get_json()["s3_key"]
    assert key.startswith("reference/") and key.endswith(".jpg")

    row = ProductImage.query.one()
    assert (row.product_id, row.retailer_id) == (coke.product_id, coke.retailer_id)
    assert row.s3_key == key
    assert row.source == "retailer_catalog"
    # Local-dev backend: saved under CAPTURE_DIR/reference/, not with the evidence photos.
    saved = os.path.join(app.config["CAPTURE_DIR"], "reference", os.path.basename(key))
    with open(saved, "rb") as fh:
        assert fh.read() == JPEG
    assert AuditLog.query.filter_by(event_type="reference_image_added").count() == 1


def test_non_admin_is_rejected(client, tenants):
    clerk = login(client, "store2_clerk", "clerk123")
    r = _upload(client, clerk, _product("Coca Cola Can").product_id, JPEG)
    assert r.status_code == 403
    assert ProductImage.query.count() == 0


def test_other_retailers_admin_cannot_see_the_product(client, tenants):
    other_admin = login(client, "other_admin", "other123")
    r = _upload(client, other_admin, _product("Coca Cola Can").product_id, JPEG)
    assert r.status_code == 404
    assert ProductImage.query.count() == 0


def test_not_signed_in_is_rejected(client):
    r = _upload(client, {}, _product("Coca Cola Can").product_id, JPEG)
    assert r.status_code == 401


@pytest.mark.parametrize("data, status", [
    (b"GIF89a" + b"0" * 200, 400),  # named photo.jpg, but the bytes are a GIF
    (b"", 400),
    (JPEG + b"0" * 1000, 413),
])
def test_bad_or_too_large_file_is_rejected(client, app, staff_headers, data, status):
    app.config["MAX_EVIDENCE_BYTES"] = 1000
    r = _upload(client, staff_headers, _product("Coca Cola Can").product_id, data)
    assert r.status_code == status
    assert ProductImage.query.count() == 0
    assert not os.path.exists(os.path.join(app.config["CAPTURE_DIR"], "reference"))


def test_get_reference_images_returns_only_that_products_images(client, staff_headers):
    coke, chips = _product("Coca Cola Can"), _product("Potato Chips")
    first = _upload(client, staff_headers, coke.product_id, JPEG).get_json()["s3_key"]
    second = _upload(client, staff_headers, coke.product_id, PNG, "photo.png").get_json()["s3_key"]
    _upload(client, staff_headers, chips.product_id, JPEG)

    assert second.endswith(".png")
    assert get_reference_images(coke.retailer_id, coke.product_id) == [first, second]
    # Another retailer asking for DEMO's product gets nothing.
    assert get_reference_images(uuid.uuid4(), coke.product_id) == []
