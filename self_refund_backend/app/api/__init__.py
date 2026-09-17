"""
HTTP API (all routes under /api).

    kiosk.py         public health check
    kiosk_device.py  kiosk agent endpoints (device authentication required)
    staff.py         staff login, review queue, decisions, evidence images

Hardware endpoints are not here: the kiosk agent owns the hardware.

Routes only translate HTTP <-> domain services. Business rules live in the
domain packages (returns, receipts, catalog, identity, evidence, audit).
"""
from flask import Blueprint, jsonify

from app.errors import DomainError

api_bp = Blueprint("api", __name__)


@api_bp.errorhandler(DomainError)
def _domain_error(err):
    from app import db

    db.session.rollback()
    return jsonify(err.body()), err.status


from app.api import kiosk, kiosk_device, staff  # noqa: E402,F401  (register routes)
