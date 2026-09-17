"""
Test fixtures.

The tests use a REAL PostgreSQL database (the models use Postgres UUID/JSONB
types) and MOCK hardware. Point TEST_DATABASE_URL at an empty, disposable
database - all tables in it are dropped and recreated.

    set TEST_DATABASE_URL=postgresql://refund_user:pass@localhost:5432/refund_kiosk_test
    python -m pytest
"""
import os
import sys

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
# Database workflow tests only run when a disposable test database is given.
collect_ignore = [] if TEST_DATABASE_URL else ["test_workflows.py"]

import hardware  # noqa: E402
from hardware.mock import MockCamera, MockScale  # noqa: E402
from app import create_app, db  # noqa: E402
from app.models import Retailer, Store  # noqa: E402
from app.tenancy import setup  # noqa: E402


@pytest.fixture()
def app(tmp_path):
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not set")
    # create_app() refuses to start without a URL; make sure one is present.
    os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)
    app = create_app({
        "SQLALCHEMY_DATABASE_URI": TEST_DATABASE_URL,
        "CAPTURE_DIR": tmp_path / "captures",
        "TESTING": True,
    })
    os.makedirs(app.config["CAPTURE_DIR"], exist_ok=True)

    camera = MockCamera(app.config["CAPTURE_DIR"])
    scale = MockScale(250)
    hardware.reset_devices()
    hardware.set_devices(camera=camera, scale=scale)
    app.mock_camera = camera
    app.mock_scale = scale

    with app.app_context():
        db.drop_all()
        db.create_all()
        _seed(app.config["KIOSK_ID"])
        yield app
        db.session.remove()
        db.drop_all()
    hardware.reset_devices()


def _seed(kiosk_code):
    """Phase 0 demo data (same products, receipts and weights), now owned by
    retailer DEMO -> store STORE-001 -> the configured kiosk."""
    retailer = setup.create_retailer("DEMO", "Demo Retailer")
    store = setup.create_store(retailer, "STORE-001", "Demo Store")
    setup.create_kiosk(store, kiosk_code)
    p1 = setup.create_product(retailer, "111111", "Coca Cola Can", "250.00", "2.99",
                              category="Beverage")
    p2 = setup.create_product(retailer, "222222", "Potato Chips", "150.00", "3.49",
                              category="Snacks")
    setup.create_product(retailer, "999999", "Not On Receipt", "100.00", "5.00",
                         category="Other")
    setup.create_receipt(store, "RCP-1001", [(p1, 1), (p2, 1)], customer_email="c@test.com")
    # Receipt with quantity 3 of one product (quantity-aware returns).
    p4 = setup.create_product(retailer, "444444", "Yogurt Cup", "100.00", "1.25",
                              category="Dairy")
    setup.create_receipt(store, "RCP-2002", [(p4, 3)])
    setup.create_receipt(store, "RCP-OLD", [(p1, 1)], days_ago=45, payment_method="Cash")
    setup.create_staff(retailer, "admin1", "admin123", "Demo Admin", role="admin",
                       email="admin@test.com")
    db.session.commit()


@pytest.fixture()
def tenants(app):
    """A second retailer that deliberately re-uses DEMO's barcode 111111 and
    receipt number RCP-1001, plus a second DEMO store with its own kiosk and a
    store-limited employee. Used by the tenant-isolation tests."""
    demo = Retailer.query.filter_by(code="DEMO").one()
    demo_store = Store.query.filter_by(retailer_id=demo.retailer_id, code="STORE-001").one()

    other = setup.create_retailer("OTHER", "Other Retailer")
    other_store = setup.create_store(other, "O-001", "Other Store")
    other_kiosk = setup.create_kiosk(other_store, "KIOSK-OTHER-1")
    other_product = setup.create_product(other, "111111", "Other Retailer Soda", "400.00",
                                         "9.99")
    other_receipt = setup.create_receipt(other_store, "RCP-1001", [(other_product, 1)])
    setup.create_staff(other, "other_admin", "other123", "Other Admin")

    demo_store2 = setup.create_store(demo, "STORE-002", "Demo Store 2")
    setup.create_kiosk(demo_store2, "KIOSK-002")
    setup.create_staff(demo, "store2_clerk", "clerk123", "Store Two Clerk",
                       role="customer_service", store=demo_store2)
    db.session.commit()
    return {
        "demo": demo, "demo_store": demo_store, "demo_store2": demo_store2,
        "other": other, "other_store": other_store, "other_kiosk": other_kiosk,
        "other_product": other_product, "other_receipt": other_receipt,
    }


@pytest.fixture()
def client(app):
    from app.identity.auth import login_limiter
    login_limiter.reset()
    return app.test_client()


def login(client, username="admin1", password="admin123"):
    r = client.post("/api/staff/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.get_json()
    return {"Authorization": f"Bearer {r.get_json()['token']}"}


@pytest.fixture()
def staff_headers(client):
    return login(client)
