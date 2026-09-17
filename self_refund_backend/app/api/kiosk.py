"""Public Core API endpoints (no kiosk or staff data).

Kiosk endpoints live in kiosk_device.py and require device authentication.
Before Phase 2 the browser called /api/transactions, /api/products/lookup,
/api/refunds/start and the hardware endpoints here directly; those now go
through the kiosk agent.
"""
from flask import jsonify

from app.api import api_bp


@api_bp.get("/health")
def health():
    return jsonify({"status": "ok", "message": "Backend is running"})
