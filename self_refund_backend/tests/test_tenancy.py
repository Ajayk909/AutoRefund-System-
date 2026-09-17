"""Phase 1: retailer -> group -> store -> kiosk model and database-level
tenant integrity (composite foreign keys, per-retailer uniqueness)."""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Kiosk, ProductIdentifier, Refund, Store, TransactionItem
from app.tenancy import setup
from app.tenancy.context import kiosk_context_for
from app.timeutil import utcnow


def _integrity_error(action):
    with pytest.raises(IntegrityError):
        action()
        db.session.flush()
    db.session.rollback()


# --- hierarchy ------------------------------------------------------------------
def test_hierarchy_links_retailer_store_kiosk(app, tenants):
    retailer = setup.create_retailer("NEST", "Nested Retailer")
    country = setup.create_group(retailer, "CA", "Canada", group_type="country")
    province = setup.create_group(retailer, "CA-ON", "Ontario", group_type="province",
                                  parent=country)
    store = setup.create_store(retailer, "S-1", "Brampton", group=province,
                               country_code="CA", region_code="ON")
    kiosk = setup.create_kiosk(store, "KIOSK-NEST-1")
    db.session.commit()

    ctx = kiosk_context_for("KIOSK-NEST-1")
    assert (ctx.retailer_id, ctx.store_id, ctx.kiosk_id) == (
        retailer.retailer_id, store.store_id, kiosk.kiosk_id)
    assert province.parent_group_id == country.group_id
    assert store.group_id == province.group_id


def test_configured_kiosk_resolves_to_demo_tenant(app, client):
    ctx = kiosk_context_for(app.config["KIOSK_ID"])
    store = db.session.get(Store, ctx.store_id)
    assert store.code == "STORE-001"


def test_unknown_kiosk_is_refused(client, app):
    app.config["KIOSK_ID"] = "KIOSK-NOT-REGISTERED"
    r = client.get("/api/transactions/RCP-1001")
    assert r.status_code == 503 and r.get_json()["code"] == "KIOSK_NOT_CONFIGURED"
    r = client.post("/api/refunds/start", json={"receipt_number": "RCP-1001", "barcode": "111111"})
    assert r.status_code == 503
    assert Refund.query.count() == 0


@pytest.mark.parametrize("disable", ["kiosk", "store", "retailer"])
def test_disabled_kiosk_store_or_retailer_is_refused(client, app, tenants, disable):
    ctx = kiosk_context_for(app.config["KIOSK_ID"])
    target = {"kiosk": db.session.get(Kiosk, ctx.kiosk_id),
              "store": db.session.get(Store, ctx.store_id),
              "retailer": tenants["demo"]}[disable]
    target.is_active = False
    db.session.commit()
    r = client.get("/api/transactions/RCP-1001")
    assert r.status_code == 503 and r.get_json()["code"] == "KIOSK_DISABLED"


# --- database-level tenant integrity ---------------------------------------------------
def test_kiosk_cannot_reference_another_retailers_store(app, tenants):
    _integrity_error(lambda: db.session.add(Kiosk(
        retailer_id=tenants["demo"].retailer_id, store_id=tenants["other_store"].store_id,
        code="BAD-KIOSK")))


def test_store_cannot_use_another_retailers_group(app, tenants):
    other_group = setup.create_group(tenants["other"], "G", "Other group")
    db.session.commit()
    _integrity_error(lambda: db.session.add(Store(
        retailer_id=tenants["demo"].retailer_id, group_id=other_group.group_id,
        code="BAD", name="Bad")))


def test_receipt_line_cannot_use_another_retailers_product(app, tenants):
    demo_receipt = setup.create_receipt(tenants["demo_store"], "RCP-MIX", [])
    db.session.commit()
    _integrity_error(lambda: db.session.add(TransactionItem(
        retailer_id=tenants["demo"].retailer_id, transaction_id=demo_receipt.transaction_id,
        product_id=tenants["other_product"].product_id, quantity=1,
        price_at_purchase=Decimal("1.00"))))


def test_return_cannot_mix_retailers(app, tenants):
    other_line = TransactionItem.query.filter_by(
        transaction_id=tenants["other_receipt"].transaction_id).one()
    demo_kiosk = kiosk_context_for(app.config["KIOSK_ID"])
    # DEMO kiosk/store but OTHER retailer's receipt line
    _integrity_error(lambda: db.session.add(Refund(
        retailer_id=tenants["demo"].retailer_id, store_id=demo_kiosk.store_id,
        kiosk_id=demo_kiosk.kiosk_id, kiosk_code=demo_kiosk.kiosk_code,
        transaction_id=other_line.transaction_id, product_id=other_line.product_id,
        transaction_item_id=other_line.item_id, quantity=1, measured_weight_grams=1,
        weight_match=True, decision_status="approved", refund_amount=1, refund_date=utcnow())))


def test_return_kiosk_must_belong_to_return_store(app, tenants):
    line = TransactionItem.query.filter_by(retailer_id=tenants["demo"].retailer_id).first()
    kiosk2 = Kiosk.query.filter_by(code="KIOSK-002").one()
    _integrity_error(lambda: db.session.add(Refund(
        retailer_id=tenants["demo"].retailer_id, store_id=tenants["demo_store"].store_id,
        kiosk_id=kiosk2.kiosk_id, kiosk_code="KIOSK-002",
        transaction_id=line.transaction_id, product_id=line.product_id,
        transaction_item_id=line.item_id, quantity=1, measured_weight_grams=1,
        weight_match=True, decision_status="approved", refund_amount=1, refund_date=utcnow())))


# --- identifiers and receipt numbers ----------------------------------------------
def test_same_barcode_allowed_at_different_retailers(app, tenants):
    values = ProductIdentifier.query.filter_by(value="111111").all()
    assert {v.retailer_id for v in values} == {tenants["demo"].retailer_id,
                                               tenants["other"].retailer_id}


def test_barcode_unique_within_a_retailer(app, tenants):
    with pytest.raises(IntegrityError):
        setup.create_product(tenants["demo"], "111111", "Duplicate barcode", 1, 1)
    db.session.rollback()


def test_only_one_primary_identifier_per_product(app, tenants):
    product = tenants["other_product"]
    db.session.add(ProductIdentifier(retailer_id=product.retailer_id,
                                     product_id=product.product_id, identifier_type="sku",
                                     value="SKU-1", is_primary=False))
    db.session.commit()  # a second, non-primary identifier is fine
    _integrity_error(lambda: db.session.add(ProductIdentifier(
        retailer_id=product.retailer_id, product_id=product.product_id,
        identifier_type="sku", value="SKU-2", is_primary=True)))


def test_identifier_cannot_point_to_another_retailers_product(app, tenants):
    _integrity_error(lambda: db.session.add(ProductIdentifier(
        retailer_id=tenants["demo"].retailer_id,
        product_id=tenants["other_product"].product_id, value="X-1")))


def test_receipt_number_unique_per_retailer(app, tenants):
    # RCP-1001 already exists at both DEMO and OTHER (fixture) - allowed.
    with pytest.raises(IntegrityError):
        setup.create_receipt(tenants["demo_store"], "RCP-1001", [])
    db.session.rollback()


def test_kiosk_code_is_globally_unique(app, tenants):
    with pytest.raises(IntegrityError):
        setup.create_kiosk(tenants["other_store"], "KIOSK-002")
    db.session.rollback()


def test_store_code_unique_per_retailer_only(app, tenants):
    setup.create_store(tenants["other"], "STORE-001", "Same code, other retailer")
    db.session.commit()
    with pytest.raises(IntegrityError):
        setup.create_store(tenants["demo"], "STORE-001", "Duplicate")
    db.session.rollback()


def test_manage_tenancy_script_creates_kiosk(app, tenants, capsys, monkeypatch):
    import manage_tenancy

    monkeypatch.setattr(manage_tenancy, "create_app", lambda: app)
    assert manage_tenancy.main(["add-kiosk", "OTHER", "O-001", f"K-{uuid.uuid4().hex[:6]}"]) == 0
    assert manage_tenancy.main(["add-kiosk", "NOPE", "O-001", "K-X"]) == 1
    assert manage_tenancy.main(["list"]) == 0
    assert "O-001" in capsys.readouterr().out
