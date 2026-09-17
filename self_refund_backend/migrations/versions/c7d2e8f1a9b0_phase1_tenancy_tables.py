"""phase 1: tenancy tables (retailers, store groups, stores, kiosks)

Revision ID: c7d2e8f1a9b0
Revises: b3f1c2d4e5a6
Create Date: 2026-09-17

Creates the tenant hierarchy and a DEFAULT retailer + DEFAULT-STORE that the
next migration assigns all existing Phase 0 data to. One kiosk row is created
for every kiosk code already used by a refund, plus KIOSK-001 (the default
KIOSK_ID), so an existing kiosk keeps working without extra setup.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c7d2e8f1a9b0"
down_revision: Union[str, Sequence[str], None] = "b3f1c2d4e5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_RETAILER = "DEFAULT"
DEFAULT_STORE = "DEFAULT-STORE"
DEFAULT_KIOSK = "KIOSK-001"


def upgrade() -> None:
    op.create_table(
        "retailers",
        sa.Column("retailer_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("retailer_id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "store_groups",
        sa.Column("group_id", sa.UUID(), nullable=False),
        sa.Column("retailer_id", sa.UUID(), nullable=False),
        sa.Column("parent_group_id", sa.UUID(), nullable=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("group_type", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("group_id"),
        sa.ForeignKeyConstraint(["retailer_id"], ["retailers.retailer_id"]),
        sa.UniqueConstraint("retailer_id", "code", name="uq_store_groups_retailer_code"),
        sa.UniqueConstraint("retailer_id", "group_id", name="uq_store_groups_retailer_group"),
        sa.ForeignKeyConstraint(["retailer_id", "parent_group_id"],
                                ["store_groups.retailer_id", "store_groups.group_id"],
                                name="fk_store_groups_parent_same_retailer"),
    )
    op.create_table(
        "stores",
        sa.Column("store_id", sa.UUID(), nullable=False),
        sa.Column("retailer_id", sa.UUID(), nullable=False),
        sa.Column("group_id", sa.UUID(), nullable=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("region_code", sa.String(length=10), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("store_id"),
        sa.ForeignKeyConstraint(["retailer_id"], ["retailers.retailer_id"]),
        sa.UniqueConstraint("retailer_id", "code", name="uq_stores_retailer_code"),
        sa.UniqueConstraint("retailer_id", "store_id", name="uq_stores_retailer_store"),
        sa.ForeignKeyConstraint(["retailer_id", "group_id"],
                                ["store_groups.retailer_id", "store_groups.group_id"],
                                name="fk_stores_group_same_retailer"),
    )
    op.create_table(
        "kiosks",
        sa.Column("kiosk_id", sa.UUID(), nullable=False),
        sa.Column("retailer_id", sa.UUID(), nullable=False),
        sa.Column("store_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("kiosk_id"),
        sa.UniqueConstraint("code"),
        sa.UniqueConstraint("retailer_id", "store_id", "kiosk_id",
                            name="uq_kiosks_retailer_store_kiosk"),
        sa.ForeignKeyConstraint(["retailer_id", "store_id"],
                                ["stores.retailer_id", "stores.store_id"],
                                name="fk_kiosks_store_same_retailer"),
    )

    # --- default tenant for existing Phase 0 data ------------------------------
    op.execute(f"""
        INSERT INTO retailers (retailer_id, code, name)
        VALUES (gen_random_uuid(), '{DEFAULT_RETAILER}', 'Default Retailer')
    """)
    op.execute(f"""
        INSERT INTO stores (store_id, retailer_id, code, name)
        SELECT gen_random_uuid(), retailer_id, '{DEFAULT_STORE}', 'Default Store'
        FROM retailers WHERE code = '{DEFAULT_RETAILER}'
    """)
    op.execute(f"""
        INSERT INTO kiosks (kiosk_id, retailer_id, store_id, code, name)
        SELECT gen_random_uuid(), s.retailer_id, s.store_id, codes.code, codes.code
        FROM stores s
        JOIN retailers r ON r.retailer_id = s.retailer_id AND r.code = '{DEFAULT_RETAILER}'
        CROSS JOIN (
            SELECT DISTINCT kiosk_id AS code FROM refunds
            UNION SELECT '{DEFAULT_KIOSK}'
        ) AS codes
        WHERE s.code = '{DEFAULT_STORE}'
    """)


def downgrade() -> None:
    op.drop_table("kiosks")
    op.drop_table("stores")
    op.drop_table("store_groups")
    op.drop_table("retailers")
