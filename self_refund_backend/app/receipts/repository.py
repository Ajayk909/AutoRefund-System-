"""Database access for receipts. Every lookup is scoped to one retailer."""
from app import db
from app.models import Product, Transaction, TransactionItem


def find_by_receipt_number(retailer_id, receipt_number):
    return Transaction.query.filter_by(retailer_id=retailer_id,
                                       receipt_number=receipt_number).first()


def get(retailer_id, transaction_id):
    if not transaction_id:
        return None
    return Transaction.query.filter_by(retailer_id=retailer_id,
                                       transaction_id=transaction_id).first()


def lines_with_products(transaction):
    return (
        db.session.query(TransactionItem, Product)
        .join(Product, (TransactionItem.product_id == Product.product_id)
              & (TransactionItem.retailer_id == Product.retailer_id))
        .filter(TransactionItem.transaction_id == transaction.transaction_id,
                TransactionItem.retailer_id == transaction.retailer_id)
        .all()
    )


def find_line(transaction, item_id=None, product_id=None):
    query = TransactionItem.query.filter_by(transaction_id=transaction.transaction_id,
                                            retailer_id=transaction.retailer_id)
    if item_id:
        return query.filter_by(item_id=item_id).first()
    if product_id:
        return query.filter_by(product_id=product_id).first()
    return None


def lock_line(transaction_item):
    """SELECT ... FOR UPDATE on the receipt line until commit/rollback."""
    return TransactionItem.query.filter_by(item_id=transaction_item.item_id).with_for_update().one()
