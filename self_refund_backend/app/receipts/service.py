"""Receipt lookup for the kiosk screen."""
from app.catalog import repository as catalog
from app.errors import DomainError
from app.receipts import repository
from app.returns import rules


def lookup_receipt(kiosk, receipt_number, policy):
    """Receipt with per-line return eligibility.

    Deliberately excludes customer email and payment method: the kiosk only
    needs to show which items can be returned.
    """
    transaction = repository.find_by_receipt_number(kiosk.retailer_id, receipt_number)
    if not transaction:
        raise DomainError("RECEIPT_NOT_FOUND", "Transaction not found", 404)

    items = []
    for item, product in repository.lines_with_products(transaction):
        eligibility = rules.line_eligibility(transaction, item, policy)
        items.append({
            "item_id": str(item.item_id),
            "product_id": str(product.product_id),
            "barcode": catalog.primary_barcode(product),
            "name": product.name,
            "quantity": item.quantity,
            "price_at_purchase": float(item.price_at_purchase),
            "expected_weight_grams": float(product.expected_weight_grams),
            "weight_tolerance_percent": float(product.weight_tolerance_percent),
            "returned_quantity": eligibility["returned_quantity"],
            "returnable_quantity": eligibility["returnable_quantity"],
            "is_refundable": eligibility["is_refundable"],
            "ineligible_reason": eligibility["ineligible_reason"],
            "refund_status": eligibility["latest_status"],
        })

    return {
        "transaction_id": str(transaction.transaction_id),
        "receipt_number": transaction.receipt_number,
        "purchase_date": transaction.purchase_date.isoformat(),
        "total_amount": float(transaction.total_amount),
        "return_deadline": rules.return_deadline(transaction, policy.window_days).isoformat(),
        "within_return_window": rules.within_return_window(transaction, policy.window_days),
        "items": items,
    }
