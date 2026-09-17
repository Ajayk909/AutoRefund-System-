"""
Tenancy and fleet: Retailer -> (optional groups) -> Store -> Kiosk.

Shared-schema multi-tenancy: every retailer lives in the same tables and each
tenant-owned row carries ``retailer_id``. Composite foreign keys such as
(retailer_id, store_id) make PostgreSQL itself refuse rows that would link
data from two different retailers.
"""
import uuid

from sqlalchemy.dialects.postgresql import UUID

from app import db


class Retailer(db.Model):
    __tablename__ = "retailers"

    retailer_id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = db.Column(db.String(50), nullable=False, unique=True)
    name = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default="true")
    created_at = db.Column(db.DateTime, server_default=db.func.now())


class StoreGroup(db.Model):
    """Optional grouping of stores inside one retailer (country, province,
    district...). Groups may nest through ``parent_group_id``."""
    __tablename__ = "store_groups"

    group_id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    retailer_id = db.Column(UUID(as_uuid=True), db.ForeignKey("retailers.retailer_id"),
                            nullable=False)
    parent_group_id = db.Column(UUID(as_uuid=True), nullable=True)
    code = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    group_type = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    __table_args__ = (
        db.UniqueConstraint("retailer_id", "code", name="uq_store_groups_retailer_code"),
        db.UniqueConstraint("retailer_id", "group_id", name="uq_store_groups_retailer_group"),
        db.ForeignKeyConstraint(["retailer_id", "parent_group_id"],
                                ["store_groups.retailer_id", "store_groups.group_id"],
                                name="fk_store_groups_parent_same_retailer"),
    )


class Store(db.Model):
    __tablename__ = "stores"

    store_id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    retailer_id = db.Column(UUID(as_uuid=True), db.ForeignKey("retailers.retailer_id"),
                            nullable=False)
    group_id = db.Column(UUID(as_uuid=True), nullable=True)
    code = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    timezone = db.Column(db.String(64), nullable=True)
    country_code = db.Column(db.String(2), nullable=True)
    region_code = db.Column(db.String(10), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default="true")
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    __table_args__ = (
        db.UniqueConstraint("retailer_id", "code", name="uq_stores_retailer_code"),
        db.UniqueConstraint("retailer_id", "store_id", name="uq_stores_retailer_store"),
        db.ForeignKeyConstraint(["retailer_id", "group_id"],
                                ["store_groups.retailer_id", "store_groups.group_id"],
                                name="fk_stores_group_same_retailer"),
    )


class Kiosk(db.Model):
    """A physical kiosk. ``code`` is the value of KIOSK_ID in the kiosk's .env
    (Phase 2 replaces this with device enrollment)."""
    __tablename__ = "kiosks"

    kiosk_id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    retailer_id = db.Column(UUID(as_uuid=True), nullable=False)
    store_id = db.Column(UUID(as_uuid=True), nullable=False)
    code = db.Column(db.String(100), nullable=False, unique=True)
    name = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default="true")
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    __table_args__ = (
        db.UniqueConstraint("retailer_id", "store_id", "kiosk_id",
                            name="uq_kiosks_retailer_store_kiosk"),
        db.ForeignKeyConstraint(["retailer_id", "store_id"],
                                ["stores.retailer_id", "stores.store_id"],
                                name="fk_kiosks_store_same_retailer"),
    )
