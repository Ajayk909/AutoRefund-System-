"""
Migration test: a real Phase 0 database is upgraded to Phase 1, used by the
application, then downgraded again.

Needs its OWN empty, disposable database (every table in it is dropped):

    set MIGRATION_TEST_DATABASE_URL=postgresql://refund_user:pass@localhost:5432/refund_migration_test
    python -m pytest tests/test_migrations.py

Skipped when MIGRATION_TEST_DATABASE_URL is not set.
"""
import os
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, text
from werkzeug.security import generate_password_hash

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = os.getenv("MIGRATION_TEST_DATABASE_URL")
PHASE0_HEAD = "b3f1c2d4e5a6"

pytestmark = pytest.mark.skipif(not URL, reason="MIGRATION_TEST_DATABASE_URL is not set")


def alembic(*args):
    env = dict(os.environ, DATABASE_URL=URL, HARDWARE_MODE="mock")
    result = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND_DIR, env=env,
                            capture_output=True, text=True)
    return result


def run_ok(*args):
    result = alembic(*args)
    assert result.returncode == 0, result.stdout + result.stderr
    return result


PHASE0_DATA = """
INSERT INTO products VALUES
 ('11111111-1111-1111-1111-111111111111','111111','Coca Cola Can','Beverage',250,10,2.99,now()),
 ('22222222-2222-2222-2222-222222222222','222222','Potato Chips','Snacks',150,10,3.49,now());
INSERT INTO transactions VALUES
 ('aaaaaaaa-0000-0000-0000-000000000001','RCP-1001','c@x.com',now(),'Card',13.46);
INSERT INTO transaction_items VALUES
 ('bbbbbbbb-0000-0000-0000-000000000001','aaaaaaaa-0000-0000-0000-000000000001','11111111-1111-1111-1111-111111111111',1,2.99),
 ('bbbbbbbb-0000-0000-0000-000000000002','aaaaaaaa-0000-0000-0000-000000000001','22222222-2222-2222-2222-222222222222',3,3.49);
INSERT INTO staff VALUES
 ('cccccccc-0000-0000-0000-000000000001','admin1',:pw,'Demo Admin','admin','a@x.com',now());
INSERT INTO refunds (refund_id,transaction_id,product_id,kiosk_id,measured_weight_grams,weight_match,
                     decision_status,refund_amount,transaction_item_id,quantity,staff_id,decided_at,
                     payment_reference,refunded_at)
 VALUES ('dddddddd-0000-0000-0000-000000000001','aaaaaaaa-0000-0000-0000-000000000001',
         '11111111-1111-1111-1111-111111111111','KIOSK-001',250,true,'refunded',2.99,
         'bbbbbbbb-0000-0000-0000-000000000001',1,'cccccccc-0000-0000-0000-000000000001',now(),
         'POS-1',now());
INSERT INTO refunds (refund_id,transaction_id,product_id,kiosk_id,measured_weight_grams,weight_match,
                     decision_status,refund_amount,transaction_item_id,quantity,idempotency_key)
 VALUES ('dddddddd-0000-0000-0000-000000000002','aaaaaaaa-0000-0000-0000-000000000001',
         '22222222-2222-2222-2222-222222222222','KIOSK-LOBBY',999,false,'pending_review',3.49,
         'bbbbbbbb-0000-0000-0000-000000000002',1,'legacy-key-0001');
INSERT INTO audit_logs VALUES
 (gen_random_uuid(),now(),'refund_started','dddddddd-0000-0000-0000-000000000002',null,'{}'),
 (gen_random_uuid(),now(),'staff_login',null,'cccccccc-0000-0000-0000-000000000001','{}');
"""


@pytest.fixture()
def engine():
    eng = create_engine(URL)
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    yield eng
    eng.dispose()


def scalar(engine, sql):
    with engine.connect() as conn:
        return conn.execute(text(sql)).scalar()


def test_phase0_database_upgrades_keeps_data_and_works(engine, tmp_path):
    run_ok("upgrade", PHASE0_HEAD)
    with engine.begin() as conn:
        conn.execute(text(PHASE0_DATA), {"pw": generate_password_hash("admin123")})

    run_ok("upgrade", "head")

    # data kept and assigned to the default tenant
    assert scalar(engine, "SELECT count(*) FROM products WHERE retailer_id IS NULL") == 0
    assert scalar(engine, "SELECT count(*) FROM refunds") == 2
    assert scalar(engine, "SELECT count(*) FROM audit_logs") == 2
    assert scalar(engine, "SELECT string_agg(value, ',' ORDER BY value) FROM product_identifiers "
                          "WHERE is_primary") == "111111,222222"
    assert scalar(engine, "SELECT string_agg(code, ',' ORDER BY code) FROM kiosks") == \
        "KIOSK-001,KIOSK-LOBBY"
    assert scalar(engine, "SELECT count(*) FROM refunds r JOIN kiosks k "
                          "ON k.kiosk_id = r.kiosk_id AND k.code = r.kiosk_code") == 2
    assert scalar(engine, "SELECT count(*) FROM audit_logs WHERE retailer_id IS NOT NULL") == 2
    assert scalar(engine, "SELECT decision_status FROM refunds WHERE payment_reference='POS-1'") == \
        "refunded"

    # models match the migrated schema
    check = alembic("check")
    assert check.returncode == 0 and "No new upgrade operations" in check.stdout + check.stderr

    # the application works on the migrated data (kiosk agent in front, as deployed)
    import hardware
    from app import create_app, db
    from hardware.mock import MockCamera, MockScale
    from tests.kiosk_harness import attach_kiosk_system

    app = create_app({"SQLALCHEMY_DATABASE_URI": URL, "KIOSK_ID": "KIOSK-001",
                      "CAPTURE_DIR": tmp_path, "TESTING": True})
    attach_kiosk_system(app, tmp_path, MockCamera(tmp_path), MockScale(150))
    try:
        with app.app_context():
            client = app.test_client()
            tx = client.get("/api/transactions/RCP-1001").get_json()["transaction"]
            items = {i["barcode"]: i for i in tx["items"]}
            assert items["111111"]["ineligible_reason"] == "ALREADY_RETURNED"
            assert items["222222"]["returned_quantity"] == 1
            assert items["222222"]["returnable_quantity"] == 2

            token = client.post("/api/staff/login", json={
                "username": "admin1", "password": "admin123"}).get_json()["token"]
            h = {"Authorization": f"Bearer {token}"}
            pending = client.get("/api/refunds/pending", headers=h).get_json()["refunds"]
            assert [p["kiosk_code"] for p in pending] == ["KIOSK-LOBBY"]

            # legacy idempotency key still replays
            r = client.post("/api/refunds/start", headers={"Idempotency-Key": "legacy-key-0001"},
                            json={"transaction_id": tx["transaction_id"],
                                  "item_id": items["222222"]["item_id"]})
            assert r.status_code == 200 and r.get_json()["refund"]["idempotent_replay"] is True

            # a new return works and approval of the legacy pending one works
            r = client.post("/api/refunds/start", json={"transaction_id": tx["transaction_id"],
                                                        "item_id": items["222222"]["item_id"]})
            assert r.status_code == 201 and r.get_json()["refund"]["decision_status"] == "approved"
            assert client.post(f"/api/refunds/{pending[0]['refund_id']}/approve",
                               headers=h).status_code == 200
            db.session.remove()
            db.engine.dispose()
    finally:
        hardware.reset_devices()

    # downgrade restores the Phase 0 shape with the data
    run_ok("downgrade", PHASE0_HEAD)
    assert scalar(engine, "SELECT barcode FROM products WHERE name='Coca Cola Can'") == "111111"
    assert scalar(engine, "SELECT count(*) FROM refunds WHERE kiosk_id='KIOSK-LOBBY'") == 1
    assert scalar(engine, "SELECT count(*) FROM refunds") == 3
    run_ok("upgrade", "head")


def test_downgrade_refuses_when_data_needs_tenants(engine):
    run_ok("upgrade", "head")
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO retailers (retailer_id, code, name) VALUES (gen_random_uuid(), 'A', 'A'),
                                                                    (gen_random_uuid(), 'B', 'B');
            INSERT INTO stores (store_id, retailer_id, code, name)
                SELECT gen_random_uuid(), retailer_id, 'S', 'S' FROM retailers WHERE code IN ('A','B');
            INSERT INTO transactions (transaction_id, retailer_id, store_id, receipt_number,
                                      purchase_date, payment_method, total_amount)
                SELECT gen_random_uuid(), s.retailer_id, s.store_id, 'RCP-SAME', now(), 'Card', 1
                FROM stores s JOIN retailers r USING (retailer_id) WHERE r.code IN ('A','B');
        """))
    result = alembic("downgrade", PHASE0_HEAD)
    assert result.returncode != 0
    assert "same receipt number exists at more than one retailer" in result.stderr
    assert "(head)" in alembic("current").stdout  # nothing was changed (still at head)
