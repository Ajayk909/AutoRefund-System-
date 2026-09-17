"""
Helpers to create tenants and their data.

Used by seed.py, manage_tenancy.py and the automated tests, so everyone
creates retailers, stores, kiosks, products and receipts the same way.
Callers commit.
"""
from datetime import timedelta
from decimal import Decimal

from werkzeug.security import generate_password_hash

from app import db
from app.catalog.repository import add_identifier
from app.models import (Kiosk, Product, Retailer, Staff, Store, StoreGroup, Transaction,
                        TransactionItem)
from app.timeutil import utcnow


def create_retailer(code, name):
    retailer = Retailer(code=code, name=name)
    db.session.add(retailer)
    db.session.flush()
    return retailer


def create_group(retailer, code, name, group_type=None, parent=None):
    group = StoreGroup(retailer_id=retailer.retailer_id, code=code, name=name,
                       group_type=group_type,
                       parent_group_id=parent.group_id if parent else None)
    db.session.add(group)
    db.session.flush()
    return group


def create_store(retailer, code, name, group=None, **fields):
    store = Store(retailer_id=retailer.retailer_id, code=code, name=name,
                  group_id=group.group_id if group else None, **fields)
    db.session.add(store)
    db.session.flush()
    return store


def create_kiosk(store, code, name=None):
    kiosk = Kiosk(retailer_id=store.retailer_id, store_id=store.store_id, code=code,
                  name=name or code)
    db.session.add(kiosk)
    db.session.flush()
    return kiosk


def create_product(retailer, barcode, name, weight_grams, price, tolerance_percent="10.00",
                   category=None):
    product = Product(retailer_id=retailer.retailer_id, name=name, category=category,
                      expected_weight_grams=Decimal(str(weight_grams)),
                      weight_tolerance_percent=Decimal(str(tolerance_percent)),
                      price=Decimal(str(price)))
    db.session.add(product)
    db.session.flush()
    add_identifier(product, barcode)
    db.session.flush()
    return product


def create_receipt(store, receipt_number, lines, days_ago=0, payment_method="Card",
                   customer_email=None):
    """lines: [(product, quantity), ...] - priced at the product price."""
    total = sum(Decimal(str(p.price)) * q for p, q in lines)
    transaction = Transaction(retailer_id=store.retailer_id, store_id=store.store_id,
                              receipt_number=receipt_number, customer_email=customer_email,
                              purchase_date=utcnow() - timedelta(days=days_ago),
                              payment_method=payment_method, total_amount=total)
    db.session.add(transaction)
    db.session.flush()
    for product, quantity in lines:
        db.session.add(TransactionItem(retailer_id=store.retailer_id,
                                       transaction_id=transaction.transaction_id,
                                       product_id=product.product_id, quantity=quantity,
                                       price_at_purchase=product.price))
    db.session.flush()
    return transaction


def create_staff(retailer, username, password, full_name, role="admin", email=None, store=None):
    staff = Staff(retailer_id=retailer.retailer_id,
                  store_id=store.store_id if store else None,
                  username=username, password_hash=generate_password_hash(password),
                  full_name=full_name, role=role, email=email or f"{username}@example.com")
    db.session.add(staff)
    db.session.flush()
    return staff
