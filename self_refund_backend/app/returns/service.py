"""
Submit a customer return.

Security model:
* the weight comes from the trusted kiosk boundary (the kiosk agent, which
  owns the scale), never from the customer's browser
* the kiosk identity comes from configuration, never from the request, and
  every lookup is limited to that kiosk's retailer
* the photo comes from the kiosk boundary; its bytes are validated and stored
  under a name generated here
* the receipt line is locked while quantity is checked, so parallel
  submissions cannot return the same unit twice
* an idempotency key makes a retried submission return the same return
"""
import logging
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.exc import IntegrityError

from app import db
from app.audit import service as audit
from app.catalog import repository as catalog
from app.ids import parse_uuid
from app.models import Refund
from app.receipts import repository as receipts
from app.returns import repository, rules
from app.returns.rules import ReturnError
from app.returns.states import PENDING_REVIEW, QUANTITY_CONSUMING
from app.timeutil import utcnow

log = logging.getLogger("autorefund.returns")


@dataclass
class ReturnRequest:
    receipt_number: str = None
    transaction_id: str = None
    item_id: str = None
    product_id: str = None
    barcode: str = None
    quantity: object = 1
    capture_id: str = None
    idempotency_key: str = ""


@dataclass
class ScaleMeasurement:
    """A scale reading supplied by the trusted kiosk boundary."""
    weight_grams: object
    stable: bool
    device: str = "unknown"
    mock: bool = False


@dataclass
class Photo:
    relative_path: str
    sha256: str = None


@dataclass
class ReturnResult:
    refund: Refund
    product: object
    expected_weight: Decimal
    image_captured: bool
    replay: bool = False


def submit_return(req, *, kiosk, policy, read_scale, obtain_photo, discard_photo,
                  camera_mock=False, require_idempotency_key=False):
    """Create a return.

    ``read_scale()`` -> ScaleMeasurement (may raise ReturnError)
    ``obtain_photo()`` -> Photo or None; ``discard_photo(photo)`` undoes it
    Both are called only after the cheap eligibility checks pass, so a blocked
    return never stores evidence.
    """
    key = (req.idempotency_key or "").strip()
    if require_idempotency_key and not key:
        raise ReturnError("IDEMPOTENCY_KEY_REQUIRED", "Invalid request. Please try again.")
    if key and not rules.IDEMPOTENCY_KEY_RE.match(key):
        raise ReturnError("INVALID_IDEMPOTENCY_KEY", "Invalid request. Please try again.")

    transaction, product, line = _resolve_line(kiosk, req)

    if key:
        existing = repository.find_by_idempotency_key(key)
        if existing:
            return _replay(existing, line, product)

    quantity = _parse_quantity(req.quantity)

    if not rules.within_return_window(transaction, policy.window_days):
        log.info("Return outside window: receipt=%s", transaction.receipt_number)
        raise ReturnError(
            "OUTSIDE_RETURN_WINDOW",
            f"This item is outside the {policy.window_days}-day return window. "
            "Please visit customer service.")

    # Cheap check first so blocked returns don't weigh or photograph anything.
    # It is repeated under the row lock below, which is what makes it safe.
    _check_line_available(transaction, line, product, quantity, kiosk, policy)

    # --- measurements from the kiosk boundary (before any database lock) ------
    reading = read_scale()
    try:
        measured = Decimal(str(reading.weight_grams))
        valid = measured.is_finite()
    except (ArithmeticError, ValueError, TypeError):
        valid = False
    if not valid or not reading.stable or measured <= 0:
        raise ReturnError("SCALE_NOT_READY",
                          "Place your item on the scale and keep it still, then try again.", 409,
                          measured_weight_grams=float(measured) if valid else None,
                          stable=bool(reading.stable))

    photo = obtain_photo()
    try:
        result = _create(req, kiosk, policy, transaction, product, line, quantity, key,
                         reading, measured, photo, camera_mock)
    except Exception:
        if photo:
            discard_photo(photo)
        raise
    if result.replay and photo:  # a parallel request with the same key won
        discard_photo(photo)
    return result


def _create(req, kiosk, policy, transaction, product, line, quantity, key, reading, measured,
            photo, camera_mock):
    image_path = photo.relative_path if photo else None

    # --- lock the receipt line and apply the rules ---------------------------
    receipts.lock_line(line)

    if key:  # a parallel request with the same key may have just finished
        existing = repository.find_by_idempotency_key(key)
        if existing:
            db.session.rollback()
            return _replay(existing, line, product)

    rejected = _check_line_available(transaction, line, product, quantity, kiosk, policy)

    weight = rules.weight_check(product, quantity, measured)
    decision_status, decision_reason = rules.decide(weight["match"], image_path is not None, policy)

    now = utcnow()
    refund = Refund(
        transaction_id=transaction.transaction_id,
        product_id=product.product_id,
        transaction_item_id=line.item_id,
        quantity=quantity,
        retailer_id=kiosk.retailer_id,
        store_id=kiosk.store_id,
        kiosk_id=kiosk.kiosk_id,
        kiosk_code=kiosk.kiosk_code,
        measured_weight_grams=measured,
        weight_match=weight["match"],
        refund_amount=line.price_at_purchase * quantity,
        refund_date=now,
        decision_status=decision_status,
        decision_reason=decision_reason,
        image_path=image_path,
        image_sha256=photo.sha256 if photo else None,
        staff_override=False,
        idempotency_key=key or None,
    )
    db.session.add(refund)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        raise ReturnError("IDEMPOTENCY_KEY_REUSED", "Invalid request. Please start again.", 422)

    audit.record(
        "refund_started",
        refund_id=refund.refund_id,
        receipt_number=transaction.receipt_number,
        retailer_id=kiosk.retailer_id,
        store_id=kiosk.store_id,
        barcode=catalog.primary_barcode(product),
        kiosk_id=kiosk.kiosk_code,
        quantity=quantity,
        expected_weight_grams=float(weight["expected"]),
        measured_weight_grams=float(measured),
        weight_source=reading.device,
        hardware_mock=bool(reading.mock or camera_mock),
        weight_match=weight["match"],
        decision_status=decision_status,
        decision_reason=decision_reason,
        image_captured=image_path is not None,
        previous_rejections=rejected,
        timestamp=now.isoformat(),
    )
    db.session.commit()
    log.info("Refund %s created: receipt=%s product=%s qty=%s weight=%s expected=%s status=%s",
             refund.refund_id, transaction.receipt_number, catalog.primary_barcode(product),
             quantity, measured, weight["expected"], decision_status)
    return ReturnResult(refund, product, weight["expected"], image_path is not None)


def _resolve_line(kiosk, req):
    """Receipt, product and line - all from the kiosk's own retailer. IDs of
    another retailer's data are simply "not found"."""
    retailer_id = kiosk.retailer_id
    transaction = None
    if req.receipt_number:
        transaction = receipts.find_by_receipt_number(retailer_id, req.receipt_number)
    elif parse_uuid(req.transaction_id):
        transaction = receipts.get(retailer_id, parse_uuid(req.transaction_id))
    if not transaction:
        raise ReturnError("RECEIPT_NOT_FOUND", "Transaction not found", 404)

    product = None
    if req.barcode:
        product = catalog.find_by_barcode(retailer_id, req.barcode)
    elif parse_uuid(req.product_id):
        product = catalog.get(retailer_id, parse_uuid(req.product_id))

    line = None
    if parse_uuid(req.item_id):
        line = receipts.find_line(transaction, item_id=parse_uuid(req.item_id))
        if line and product and line.product_id != product.product_id:
            line = None
        if line and not product:
            product = catalog.get(retailer_id, line.product_id)
    if not product:
        raise ReturnError("PRODUCT_NOT_FOUND", "Product not found", 404)
    if not line:
        line = receipts.find_line(transaction, product_id=product.product_id)
    if not line:
        raise ReturnError("NOT_ON_RECEIPT", "This product is not part of the provided transaction")
    return transaction, product, line


def _parse_quantity(raw):
    try:
        quantity = int(raw)
        if isinstance(raw, bool) or str(raw).strip() != str(quantity):
            raise ValueError
    except (TypeError, ValueError):
        quantity = 0
    if quantity < 1:
        raise ReturnError("INVALID_QUANTITY", "Please choose how many items you are returning.")
    return quantity


def _check_line_available(transaction, line, product, quantity, kiosk, policy):
    """Quantity / duplicate / retry-limit rules. Returns rejected attempts."""
    used, rejected, refunds = rules.count_line_usage(line)
    remaining = line.quantity - used

    if remaining <= 0 or quantity > remaining:
        latest = next((r for r in refunds if r.decision_status in QUANTITY_CONSUMING), None)
        if remaining <= 0 and latest:
            log.warning("Duplicate refund attempt blocked: receipt=%s product=%s existing=%s",
                        transaction.receipt_number, catalog.primary_barcode(product),
                        latest.refund_id)
            _audit_blocked("duplicate_refund_blocked", transaction, product, kiosk,
                           refund_id=latest.refund_id,
                           existing_refund_status=latest.decision_status,
                           requested_quantity=quantity)
            message = ("This item is already waiting for an employee to review it."
                       if latest.decision_status == PENDING_REVIEW
                       else "This item has already been submitted for refund.")
            raise ReturnError("DUPLICATE_RETURN", message,
                              existing_refund_status=latest.decision_status)
        raise ReturnError("QUANTITY_EXCEEDS_REMAINING",
                          f"Only {max(remaining, 0)} of this item can still be returned.",
                          returnable_quantity=max(remaining, 0))

    if rejected > policy.retry_limit_after_rejection:
        _audit_blocked("return_attempt_limit_reached", transaction, product, kiosk,
                       rejected_attempts=rejected,
                       retry_limit=policy.retry_limit_after_rejection)
        raise ReturnError("TOO_MANY_ATTEMPTS",
                          "We can't accept this return at the kiosk. "
                          "Please visit customer service for help.")
    return rejected


def _audit_blocked(event_type, transaction, product, kiosk, refund_id=None, **details):
    audit.record(event_type, refund_id=refund_id,
                 retailer_id=kiosk.retailer_id, store_id=kiosk.store_id,
                 receipt_number=transaction.receipt_number,
                 barcode=catalog.primary_barcode(product), kiosk_id=kiosk.kiosk_code, **details)
    db.session.commit()


def _replay(existing, line, product):
    if existing.transaction_item_id != line.item_id:
        raise ReturnError("IDEMPOTENCY_KEY_REUSED", "Invalid request. Please start again.", 422)
    log.info("Idempotent replay for refund %s", existing.refund_id)
    expected = Decimal(str(product.expected_weight_grams)) * existing.quantity
    return ReturnResult(existing, product, expected, existing.image_path is not None, replay=True)
