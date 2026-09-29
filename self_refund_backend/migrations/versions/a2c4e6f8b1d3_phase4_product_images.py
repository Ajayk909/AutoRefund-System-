"""phase 4: product reference images

Adds the product_images table: reference photos of a product for the AI
photo check. Only the storage key is stored; the image is in S3.

Revision ID: a2c4e6f8b1d3
Revises: f1a7c3d9b2e4
Create Date: 2026-09-29

Additive. products already has a unique (retailer_id, product_id), so images
use a same-retailer foreign key like product_identifiers does.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a2c4e6f8b1d3"
down_revision: Union[str, Sequence[str], None] = "f1a7c3d9b2e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "product_images",
        sa.Column("image_id", sa.UUID(), nullable=False),
        sa.Column("retailer_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("s3_key", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("image_id"),
        sa.ForeignKeyConstraint(["retailer_id", "product_id"],
                                ["products.retailer_id", "products.product_id"],
                                name="fk_product_images_product_same_retailer"),
        sa.CheckConstraint("source IN ('retailer_catalog', 'kiosk_capture')",
                           name="ck_product_images_source"),
    )
    op.create_index("ix_product_images_product_id", "product_images", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_product_images_product_id", table_name="product_images")
    op.drop_table("product_images")
