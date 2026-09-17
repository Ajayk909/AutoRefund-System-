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
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from werkzeug.security import generate_password_hash

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
# Database workflow tests only run when a disposable test database is given.
collect_ignore = [] if TEST_DATABASE_URL else ["test_workflows.py"]

import hardware  # noqa: E402
from hardware.mock import MockCamera, MockScale  # noqa: E402
from app import create_app, db  # noqa: E402
from app.models import Product, Staff, Transaction, TransactionItem  # noqa: E402


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
        _seed()
        yield app
        db.session.remove()
        db.drop_all()
    hardware.reset_devices()


def _seed():
    p1 = Product(barcode="111111", name="Coca Cola Can", category="Beverage",
                 expected_weight_grams=Decimal("250.00"),
                 weight_tolerance_percent=Decimal("10.00"), price=Decimal("2.99"))
    p2 = Product(barcode="222222", name="Potato Chips", category="Snacks",
                 expected_weight_grams=Decimal("150.00"),
                 weight_tolerance_percent=Decimal("10.00"), price=Decimal("3.49"))
    p3 = Product(barcode="999999", name="Not On Receipt", category="Other",
                 expected_weight_grams=Decimal("100.00"),
                 weight_tolerance_percent=Decimal("10.00"), price=Decimal("5.00"))
    db.session.add_all([p1, p2, p3])
    db.session.flush()
    t = Transaction(receipt_number="RCP-1001", customer_email="c@test.com",
                    purchase_date=datetime.utcnow(), payment_method="Card",
                    total_amount=Decimal("6.48"))
    db.session.add(t)
    db.session.flush()
    db.session.add_all([
        TransactionItem(transaction_id=t.transaction_id, product_id=p1.product_id,
                        quantity=1, price_at_purchase=Decimal("2.99")),
        TransactionItem(transaction_id=t.transaction_id, product_id=p2.product_id,
                        quantity=1, price_at_purchase=Decimal("3.49")),
    ])
    # Receipt with quantity 3 of one product (quantity-aware returns).
    p4 = Product(barcode="444444", name="Yogurt Cup", category="Dairy",
                 expected_weight_grams=Decimal("100.00"),
                 weight_tolerance_percent=Decimal("10.00"), price=Decimal("1.25"))
    db.session.add(p4)
    db.session.flush()
    multi = Transaction(receipt_number="RCP-2002", purchase_date=datetime.utcnow(),
                        payment_method="Card", total_amount=Decimal("3.75"))
    old = Transaction(receipt_number="RCP-OLD", purchase_date=datetime.utcnow() - timedelta(days=45),
                      payment_method="Cash", total_amount=Decimal("2.99"))
    db.session.add_all([multi, old])
    db.session.flush()
    db.session.add_all([
        TransactionItem(transaction_id=multi.transaction_id, product_id=p4.product_id,
                        quantity=3, price_at_purchase=Decimal("1.25")),
        TransactionItem(transaction_id=old.transaction_id, product_id=p1.product_id,
                        quantity=1, price_at_purchase=Decimal("2.99")),
    ])
    db.session.add(Staff(username="admin1",
                         password_hash=generate_password_hash("admin123"),
                         full_name="Demo Admin", role="admin",
                         email="admin@test.com"))
    db.session.commit()


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
