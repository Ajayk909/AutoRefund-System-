"""Database access for returns (the ``refunds`` table).

Staff-facing queries take a StaffScope so employees only ever see returns of
their own retailer (and store, when they are limited to one).
"""
from sqlalchemy import and_, or_

from app import db
from app.models import Refund


def _scoped(scope):
    query = Refund.query.filter(Refund.retailer_id == scope.retailer_id)
    if scope.store_id is not None:
        query = query.filter(Refund.store_id == scope.store_id)
    return query


def refunds_for_line(transaction_item):
    """All returns for a receipt line, newest first (includes pre-Phase-0
    rows that were recorded by transaction + product only)."""
    return Refund.query.filter(
        Refund.retailer_id == transaction_item.retailer_id,
        or_(
            Refund.transaction_item_id == transaction_item.item_id,
            and_(Refund.transaction_item_id.is_(None),
                 Refund.transaction_id == transaction_item.transaction_id,
                 Refund.product_id == transaction_item.product_id),
        ),
    ).order_by(Refund.refund_date.desc()).populate_existing().all()


def find_by_idempotency_key(key):
    return Refund.query.filter_by(idempotency_key=key).first()


def get_for_staff(scope, refund_id, lock=False):
    query = _scoped(scope).filter(Refund.refund_id == refund_id)
    if lock:
        query = query.with_for_update()
    return query.first()


def list_for_staff(scope, status=None, start=None, end=None):
    query = _scoped(scope)
    if status:
        query = query.filter(Refund.decision_status == status)
    if start:
        query = query.filter(Refund.refund_date >= start)
    if end:
        query = query.filter(Refund.refund_date <= end)
    return query.order_by(Refund.refund_date.desc()).all()


def find_for_staff_by_image(scope, relative_path):
    return _scoped(scope).filter(Refund.image_path == relative_path).first()


def image_in_use(relative_path):
    return db.session.query(Refund.refund_id).filter_by(image_path=relative_path).first() is not None
