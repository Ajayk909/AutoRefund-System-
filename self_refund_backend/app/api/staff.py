"""Staff endpoints: login, review queue, decisions and evidence images."""
import os
from datetime import datetime

from flask import current_app, g, jsonify, request, send_from_directory

from app import db
from app.api import api_bp
from app.api.serializers import refund_to_staff_dict
from app.audit import service as audit
from app.errors import DomainError
from app.evidence import captures
from app.identity import service as identity
from app.identity.auth import REVIEW_ROLES, require_staff
from app.ids import parse_uuid
from app.returns import repository as returns_repository
from app.returns import review
from app.tenancy import repository as tenancy
from app.tenancy.context import scope_for
from app.returns.states import APPROVED, PENDING_REVIEW, REFUNDED, REJECTED


def _capture_dir():
    return str(current_app.config["CAPTURE_DIR"])


def _staff_dict(staff):
    return {"staff_id": str(staff.staff_id), "username": staff.username,
            "full_name": staff.full_name, "role": staff.role, "email": staff.email,
            "store_code": tenancy.store_code(staff.store_id)}


@api_bp.post("/staff/login")
def staff_login():
    data = request.get_json() or {}
    staff, token, session = identity.login(data.get("username"), data.get("password"))
    return jsonify({
        "success": True,
        "token": token,
        "expires_at": session.expires_at.isoformat(),
        "staff": _staff_dict(staff),
    })


@api_bp.post("/staff/logout")
def staff_logout():
    identity.logout()
    return jsonify({"success": True})


@api_bp.get("/staff/me")
@require_staff()
def staff_me():
    return jsonify({"success": True, "staff": _staff_dict(g.staff)})


def _parse_day(value, field, end_of_day=False):
    if not value:
        return None
    try:
        day = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise DomainError("INVALID_DATE", f"Invalid {field} format. Use YYYY-MM-DD")
    return day.replace(hour=23, minute=59, second=59) if end_of_day else day


@api_bp.get("/refunds/logs")
@require_staff()
def refund_logs():
    start = _parse_day(request.args.get("start_date"), "start_date")
    end = _parse_day(request.args.get("end_date"), "end_date", end_of_day=True)
    refunds = returns_repository.list_for_staff(scope_for(g.staff), start=start, end=end)
    return jsonify({"success": True,
                    "refunds": [refund_to_staff_dict(r, _capture_dir()) for r in refunds]})


@api_bp.get("/refunds/pending")
@require_staff()
def pending_refunds():
    refunds = returns_repository.list_for_staff(scope_for(g.staff), status=PENDING_REVIEW)
    return jsonify({"success": True,
                    "refunds": [refund_to_staff_dict(r, _capture_dir()) for r in refunds]})


def _decision_response(target):
    def handler(refund_id):
        data = request.get_json(silent=True) or {}
        refund = review.apply_staff_decision(
            g.staff, refund_id, target,
            reason=data.get("reason"), payment_reference=data.get("payment_reference"))
        return jsonify({"success": True, "message": f"Return {target.replace('_', ' ')}",
                        "refund": refund_to_staff_dict(refund, _capture_dir())})
    return handler


@api_bp.post("/refunds/<refund_id>/approve")
@require_staff(*REVIEW_ROLES)
def approve_refund(refund_id):
    return _decision_response(APPROVED)(refund_id)


@api_bp.post("/refunds/<refund_id>/reject")
@require_staff(*REVIEW_ROLES)
def reject_refund(refund_id):
    return _decision_response(REJECTED)(refund_id)


@api_bp.post("/refunds/<refund_id>/mark-refunded")
@require_staff(*REVIEW_ROLES)
def mark_refunded(refund_id):
    """Record that the money was returned (e.g. refund issued at the POS)."""
    return _decision_response(REFUNDED)(refund_id)


@api_bp.get("/refunds/<refund_id>/image")
@require_staff()
def get_refund_image(refund_id):
    uid = parse_uuid(refund_id)
    refund = returns_repository.get_for_staff(scope_for(g.staff), uid) if uid else None
    path = captures.evidence_file(refund.image_path, _capture_dir()) if refund else None
    if not path:
        return jsonify({"success": False, "message": "Image not found"}), 404
    audit.record("evidence_viewed", refund_id=refund.refund_id, staff_id=g.staff.staff_id,
                 retailer_id=refund.retailer_id, store_id=refund.store_id)
    db.session.commit()
    response = send_from_directory(_capture_dir(), os.path.basename(path))
    response.headers["Cache-Control"] = "no-store"
    return response


@api_bp.get("/captures/<path:filename>")
@require_staff()
def get_capture_file(filename):
    """Evidence by file name - only if it belongs to a return this staff member
    may see (orphan photos and other retailers' photos are not served)."""
    name = os.path.basename(filename)
    refund = returns_repository.find_for_staff_by_image(scope_for(g.staff), f"captures/{name}")
    if not refund or not captures.evidence_file(refund.image_path, _capture_dir()):
        return jsonify({"success": False, "message": "Image not found"}), 404
    response = send_from_directory(_capture_dir(), name)
    response.headers["Cache-Control"] = "no-store"
    return response
