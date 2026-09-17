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


def find_kiosk_with_tenant_by_id(kiosk_id):
    return (
        db.session.query(Kiosk, Store, Retailer)
        .join(Store, (Store.store_id == Kiosk.store_id) & (Store.retailer_id == Kiosk.retailer_id))
        .join(Retailer, Retailer.retailer_id == Kiosk.retailer_id)
        .filter(Kiosk.kiosk_id == kiosk_id)
        .first()
    )


def get_kiosk_by_code(code):
    return Kiosk.query.filter_by(code=code).first()


def kiosk_identity(kiosk_context):
    """Kiosk -> store -> retailer codes for the agent's status screen."""
    kiosk, store, retailer = find_kiosk_with_tenant_by_id(kiosk_context.kiosk_id)
    return {
        "kiosk_code": kiosk.code,
        "kiosk_name": kiosk.name,
        "store_code": store.code,
        "store_name": store.name,
        "retailer_code": retailer.code,
        "retailer_name": retailer.name,
        "active": bool(kiosk.is_active and store.is_active and retailer.is_active),
    }
