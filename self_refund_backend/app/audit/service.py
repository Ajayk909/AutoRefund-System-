"""Write audit events. Callers decide when to commit."""
from app import db
from app.models import AuditLog
from app.timeutil import utcnow


def record(event_type, *, refund_id=None, staff_id=None, retailer_id=None, store_id=None,
           **details):
    """Add an audit event to the current database session."""
    details.setdefault("timestamp", utcnow().isoformat())
    event = AuditLog(event_type=event_type, refund_id=refund_id, staff_id=staff_id,
                     retailer_id=retailer_id, store_id=store_id, details=details)
    db.session.add(event)
    return event
