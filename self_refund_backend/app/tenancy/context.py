"""Tenant context for kiosk and staff requests."""
from dataclasses import dataclass

from flask import current_app, g

from app.errors import DomainError
from app.tenancy import repository


@dataclass(frozen=True)
class KioskContext:
    retailer_id: object
    store_id: object
    kiosk_id: object
    kiosk_code: str


@dataclass(frozen=True)
class StaffScope:
    """What a staff member may see. store_id None = all stores of the retailer."""
    retailer_id: object
    store_id: object = None


def kiosk_context_for(code):
    row = repository.find_kiosk_with_tenant(code)
    if not row:
        raise DomainError("KIOSK_NOT_CONFIGURED",
                          "This kiosk is not set up yet. Please ask an employee for help.", 503)
    kiosk, store, retailer = row
    if not (kiosk.is_active and store.is_active and retailer.is_active):
        raise DomainError("KIOSK_DISABLED",
                          "This kiosk is not accepting returns right now. "
                          "Please visit customer service.", 503)
    return KioskContext(retailer.retailer_id, store.store_id, kiosk.kiosk_id, kiosk.code)


def current_kiosk():
    """Kiosk context for this request, from the KIOSK_ID configuration."""
    code = current_app.config["KIOSK_ID"]
    cached = g.get("kiosk_context")
    if cached is None or cached.kiosk_code != code:
        g.kiosk_context = kiosk_context_for(code)
    return g.kiosk_context


def scope_for(staff):
    return StaffScope(retailer_id=staff.retailer_id, store_id=staff.store_id)
