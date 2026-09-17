"""Database access for retailers, stores and kiosks."""
from app import db
from app.models import Kiosk, Retailer, Store


def find_kiosk_with_tenant(code):
    """(kiosk, store, retailer) for a kiosk code, or None."""
    return (
        db.session.query(Kiosk, Store, Retailer)
        .join(Store, (Store.store_id == Kiosk.store_id) & (Store.retailer_id == Kiosk.retailer_id))
        .join(Retailer, Retailer.retailer_id == Kiosk.retailer_id)
        .filter(Kiosk.code == code)
        .first()
    )


def get_retailer_by_code(code):
    return Retailer.query.filter_by(code=code).first()


def get_store_by_code(retailer_id, code):
    return Store.query.filter_by(retailer_id=retailer_id, code=code).first()


def store_code(store_id):
    store = db.session.get(Store, store_id) if store_id else None
    return store.code if store else None
