"""
Load the demo products / receipt / admin user.

WARNING: this DELETES all existing products, receipts, refunds, staff and
audit logs first. Run with --yes to skip the confirmation prompt.
"""
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models import (AuditLog, Product, Refund, Staff, StaffSession, Transaction,
                        TransactionItem)


if "--yes" not in sys.argv:
    answer = input(
        "This will DELETE all refunds, receipts, products, staff and audit "
        "logs in the configured database.\nType YES to continue: ")
    if answer.strip() != "YES":
        print("Cancelled. Nothing was changed.")
        sys.exit(1)

app = create_app()

with app.app_context():
    print("Clearing old demo/test data...")

    AuditLog.query.delete()
    Refund.query.delete()
    TransactionItem.query.delete()
    Transaction.query.delete()
    Product.query.delete()
    StaffSession.query.delete()
    Staff.query.delete()

    db.session.commit()

    print("Adding store products...")

    product1 = Product(
        barcode="111111",
        name="Coca Cola Can",
        category="Beverage",
        expected_weight_grams=Decimal("250.00"),
        weight_tolerance_percent=Decimal("10.00"),
        price=Decimal("2.99"),
    )

    product2 = Product(
        barcode="222222",
        name="Potato Chips",
        category="Snacks",
        expected_weight_grams=Decimal("150.00"),
        weight_tolerance_percent=Decimal("10.00"),
        price=Decimal("3.49"),
    )

    product3 = Product(
        barcode="333333",
        name="Chocolate Bar",
        category="Candy",
        expected_weight_grams=Decimal("50.00"),
        weight_tolerance_percent=Decimal("10.00"),
        price=Decimal("1.99"),
    )

    db.session.add_all([product1, product2, product3])
    db.session.flush()

    print("Adding receipts...")

    transaction = Transaction(
        receipt_number="RCP-1001",
        customer_email="customer@test.com",
        purchase_date=datetime.utcnow(),
        payment_method="Card",
        total_amount=Decimal("8.47"),
    )

    db.session.add(transaction)
    db.session.flush()

    item1 = TransactionItem(
        transaction_id=transaction.transaction_id,
        product_id=product1.product_id,
        quantity=1,
        price_at_purchase=Decimal("2.99"),
    )

    item2 = TransactionItem(
        transaction_id=transaction.transaction_id,
        product_id=product2.product_id,
        quantity=1,
        price_at_purchase=Decimal("3.49"),
    )

    item3 = TransactionItem(
        transaction_id=transaction.transaction_id,
        product_id=product3.product_id,
        quantity=1,
        price_at_purchase=Decimal("1.99"),
    )

    db.session.add_all([item1, item2, item3])

    # RCP-1002: quantity 3 of one product (quantity-aware returns)
    product4 = Product(
        barcode="444444",
        name="Yogurt Cup",
        category="Dairy",
        expected_weight_grams=Decimal("100.00"),
        weight_tolerance_percent=Decimal("10.00"),
        price=Decimal("1.25"),
    )
    db.session.add(product4)
    db.session.flush()
    multi = Transaction(
        receipt_number="RCP-1002",
        purchase_date=datetime.utcnow(),
        payment_method="Card",
        total_amount=Decimal("3.75"),
    )
    # RCP-0900: bought 45 days ago, outside the default 30-day return window
    old = Transaction(
        receipt_number="RCP-0900",
        purchase_date=datetime.utcnow() - timedelta(days=45),
        payment_method="Cash",
        total_amount=Decimal("2.99"),
    )
    db.session.add_all([multi, old])
    db.session.flush()
    db.session.add_all([
        TransactionItem(transaction_id=multi.transaction_id, product_id=product4.product_id,
                        quantity=3, price_at_purchase=Decimal("1.25")),
        TransactionItem(transaction_id=old.transaction_id, product_id=product1.product_id,
                        quantity=1, price_at_purchase=Decimal("2.99")),
    ])

    print("Adding admin user...")

    admin = Staff(
        username="admin1",
        password_hash=generate_password_hash("admin123"),
        full_name="Demo Admin",
        role="admin",
        email="admin@test.com",
    )

    db.session.add(admin)
    db.session.commit()

    print("\nSEED COMPLETE")
    print("Receipts: RCP-1001 (3 items), RCP-1002 (Yogurt Cup x3), RCP-0900 (outside return window)")
    print("admin1 / admin123  (demo only - change before any real use)")