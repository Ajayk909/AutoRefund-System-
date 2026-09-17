r"""
Load the demo retailer, store, kiosk, products, receipts and admin user.

WARNING: this DELETES all existing returns, receipts, products, staff, kiosks,
stores and retailers first. Run with --yes to skip the confirmation prompt.

The demo kiosk is KIOSK-001 (or the KIOSK_ID environment variable). Afterwards
give the kiosk agent its development key:
    python manage_tenancy.py issue-dev-key KIOSK-001 --write-env ..\kiosk_agent\.env

Outside local (ENVIRONMENT != local), the admin password is NOT admin123: a
random password is generated and stored in the Secrets Manager secret named
by SEED_ADMIN_SECRET_NAME (required in that case). It is never printed.
"""
import os
import secrets
import sys

from app import create_app, db
from app.models import (AuditLog, Kiosk, KioskCredential, Product, ProductIdentifier, Refund,
                        Retailer, Staff, StaffSession, Store, StoreGroup, Transaction,
                        TransactionItem)
from app.tenancy import setup
from cloud_secrets import store_secret

if "--yes" not in sys.argv:
    answer = input(
        "This will DELETE all returns, receipts, products, staff, kiosks, kiosk agent keys, "
        "stores and retailers in the configured database.\nType YES to continue: ")
    if answer.strip() != "YES":
        print("Cancelled. Nothing was changed.")
        sys.exit(1)

app = create_app()

with app.app_context():
    print("Clearing old demo/test data...")
    for model in (AuditLog, Refund, TransactionItem, Transaction, ProductIdentifier, Product,
                  StaffSession, Staff, KioskCredential, Kiosk, Store, StoreGroup, Retailer):
        model.query.delete()
    db.session.commit()

    # The kiosk agent's KIOSK_ID (kiosk_agent\.env). Override: set KIOSK_ID=...
    kiosk_code = os.getenv("KIOSK_ID", "KIOSK-001")
    print(f"Adding retailer DEMO -> Ontario -> STORE-001 -> kiosk {kiosk_code}...")
    retailer = setup.create_retailer("DEMO", "Demo Retailer")
    ontario = setup.create_group(retailer, "CA-ON", "Ontario", group_type="province")
    store = setup.create_store(retailer, "STORE-001", "Demo Store", group=ontario,
                               timezone="America/Toronto", country_code="CA",
                               region_code="ON")
    setup.create_kiosk(store, kiosk_code)

    print("Adding products...")
    coke = setup.create_product(retailer, "111111", "Coca Cola Can", 250, "2.99",
                                category="Beverage")
    chips = setup.create_product(retailer, "222222", "Potato Chips", 150, "3.49",
                                 category="Snacks")
    chocolate = setup.create_product(retailer, "333333", "Chocolate Bar", 50, "1.99",
                                     category="Candy")
    yogurt = setup.create_product(retailer, "444444", "Yogurt Cup", 100, "1.25",
                                  category="Dairy")

    print("Adding receipts...")
    setup.create_receipt(store, "RCP-1001", [(coke, 1), (chips, 1), (chocolate, 1)],
                         customer_email="customer@test.com")
    # RCP-1002: quantity 3 of one product (quantity-aware returns)
    setup.create_receipt(store, "RCP-1002", [(yogurt, 3)])
    # RCP-0900: bought 45 days ago, outside the default 30-day return window
    setup.create_receipt(store, "RCP-0900", [(coke, 1)], days_ago=45, payment_method="Cash")

    print("Adding admin user...")
    environment = app.config.get("ENVIRONMENT", "local")
    if environment == "local":
        admin_password = "admin123"
    else:
        secret_name = os.getenv("SEED_ADMIN_SECRET_NAME")
        if not secret_name:
            print("SEED_ADMIN_SECRET_NAME must be set outside local so the generated "
                 "admin password can be stored in Secrets Manager.")
            sys.exit(1)
        admin_password = secrets.token_urlsafe(18)
    setup.create_staff(retailer, "admin1", admin_password, "Demo Admin", role="admin",
                       email="admin@test.com")
    db.session.commit()

    print("\nSEED COMPLETE")
    print("Receipts: RCP-1001 (3 items), RCP-1002 (Yogurt Cup x3), RCP-0900 (outside return window)")
    if environment == "local":
        print("admin1 / admin123  (demo only - change before any real use)")
    else:
        store_secret(secret_name, admin_password)
        print(f"admin1 password stored in Secrets Manager secret {secret_name!r} (not printed).")
    print("\nOld kiosk agent keys were deleted. Give the agent a new one:")
    if environment == "local":
        print(f"python manage_tenancy.py issue-dev-key {kiosk_code} "
              "--write-env ..\\kiosk_agent\\.env")
    else:
        print(f"python manage_tenancy.py issue-staging-key {kiosk_code} "
              "--secret-name <Secrets Manager secret name>")
