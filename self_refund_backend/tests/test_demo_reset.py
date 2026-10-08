"""
manage_tenancy.py reset-demo-returns: delete one retailer's returns so the
demo receipts can be returned again (local/dev only). Needs TEST_DATABASE_URL.
"""
import pytest

import manage_tenancy
from app.models import (AuditLog, KioskCredential, Product, ProductImage, Refund, Staff,
                        Transaction, TransactionItem, VerificationSignal)
from tests.test_reference_images import _product, _upload
from tests.test_tenant_isolation import _receipt, _return, _use_kiosk
from tests.test_workflows import _item

JPEG = b"\xff\xd8\xff reference photo"


def _make_returns(client, app, staff_headers):
    _upload(client, staff_headers, _product("Coca Cola Can").product_id, JPEG)
    _, demo_tx = _receipt(client)
    assert _return(client, app, demo_tx, _item(demo_tx, "111111"), 250).status_code == 201
    assert _return(client, app, demo_tx, _item(demo_tx, "222222"), 180).status_code == 201
    # Returning the same line again is blocked and audited without a return.
    assert _return(client, app, demo_tx, _item(demo_tx, "111111"), 250).status_code == 400
    _use_kiosk(app, "KIOSK-OTHER-1")
    _, other_tx = _receipt(client)
    assert _return(client, app, other_tx, other_tx["items"][0], 400).status_code == 201
    _use_kiosk(app, "KIOSK-001")


def _counts(retailer_id):
    return {
        "returns": Refund.query.filter_by(retailer_id=retailer_id).count(),
        "signals": VerificationSignal.query.filter_by(retailer_id=retailer_id).count(),
        "return_audit": AuditLog.query.filter(
            AuditLog.retailer_id == retailer_id,
            AuditLog.event_type.in_(("refund_started", *manage_tenancy.BLOCKED_RETURN_EVENTS)),
        ).count(),
    }


def _kept():
    """Everything the reset must not touch."""
    return {model.__name__: model.query.count()
            for model in (Product, ProductImage, Transaction, TransactionItem, Staff,
                          KioskCredential)} | {
        "staff_login": AuditLog.query.filter_by(event_type="staff_login").count()}


def test_deletes_only_that_retailers_returns(client, app, tenants, staff_headers, monkeypatch):
    monkeypatch.setattr(manage_tenancy, "create_app", lambda: app)
    _make_returns(client, app, staff_headers)
    demo, other = tenants["demo"].retailer_id, tenants["other"].retailer_id
    assert all(_counts(demo).values())
    other_before = _counts(other)
    kept_before = _kept()

    assert manage_tenancy.main(["reset-demo-returns", "DEMO"]) == 0

    assert _counts(demo) == {"returns": 0, "signals": 0, "return_audit": 0}
    assert _counts(other) == other_before
    assert _kept() == kept_before
    # The receipt line can be returned again.
    _, demo_tx = _receipt(client)
    assert _item(demo_tx, "111111")["is_refundable"] is True


def test_prints_what_it_deleted(client, app, tenants, staff_headers, monkeypatch, capsys):
    monkeypatch.setattr(manage_tenancy, "create_app", lambda: app)
    _make_returns(client, app, staff_headers)
    assert manage_tenancy.main(["reset-demo-returns", "DEMO"]) == 0
    assert "Deleted 2 returns" in capsys.readouterr().out


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_refuses_outside_local_and_dev(client, app, tenants, staff_headers, monkeypatch,
                                       environment):
    monkeypatch.setattr(manage_tenancy, "create_app", lambda: app)
    _make_returns(client, app, staff_headers)
    app.config["ENVIRONMENT"] = environment
    before = _counts(tenants["demo"].retailer_id)

    assert manage_tenancy.main(["reset-demo-returns", "DEMO"]) == 1
    assert _counts(tenants["demo"].retailer_id) == before


def test_unknown_retailer(app, monkeypatch):
    monkeypatch.setattr(manage_tenancy, "create_app", lambda: app)
    assert manage_tenancy.main(["reset-demo-returns", "NOPE"]) == 1
