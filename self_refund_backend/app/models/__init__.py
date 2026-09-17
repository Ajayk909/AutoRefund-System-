"""
Database models, grouped by business domain.

Import from ``app.models`` everywhere; the sub-modules only organise the code.
"""
from app.models.audit import AuditLog
from app.models.catalog import Product
from app.models.identity import Staff, StaffSession, staff_role_enum
from app.models.returns import Refund, decision_status_enum
from app.models.transactions import Transaction, TransactionItem

__all__ = [
    "AuditLog",
    "Product",
    "Refund",
    "Staff",
    "StaffSession",
    "Transaction",
    "TransactionItem",
    "decision_status_enum",
    "staff_role_enum",
]
