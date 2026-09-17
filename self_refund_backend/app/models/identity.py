"""Identity: staff accounts and login sessions."""
import uuid

from sqlalchemy import Enum
from sqlalchemy.dialects.postgresql import UUID

from app import db


staff_role_enum = Enum(
    "admin", "customer_service", "manager",
    name="staff_role_enum"
)


class Staff(db.Model):
    __tablename__ = "staff"

    staff_id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(255), nullable=False)
    role = db.Column(staff_role_enum, nullable=False)
    email = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())


class StaffSession(db.Model):
    """Server-side staff login session. Only a SHA-256 hash of the token is
    stored, so a database leak does not reveal usable tokens."""
    __tablename__ = "staff_sessions"

    session_id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    staff_id = db.Column(UUID(as_uuid=True), db.ForeignKey("staff.staff_id"),
                         nullable=False, index=True)
    token_hash = db.Column(db.String(64), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    last_used_at = db.Column(db.DateTime, nullable=True)
    revoked_at = db.Column(db.DateTime, nullable=True)
