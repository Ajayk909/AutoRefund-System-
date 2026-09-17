"""phase 2: kiosk credentials and evidence hash

Revision ID: e5b9c0d7f3a1
Revises: d4a1b6c3e2f5
Create Date: 2026-09-17

Additive. kiosk_credentials holds hashed kiosk-agent credentials (Phase 2:
development keys only). refunds.image_sha256 records the hash of evidence
uploaded by the kiosk agent. Existing rows are unchanged.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e5b9c0d7f3a1"
down_revision: Union[str, Sequence[str], None] = "d4a1b6c3e2f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kiosk_credentials",
        sa.Column("credential_id", sa.UUID(), nullable=False),
        sa.Column("kiosk_id", sa.UUID(), nullable=False),
        sa.Column("credential_type", sa.String(length=30), nullable=False),
        sa.Column("secret_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["kiosk_id"], ["kiosks.kiosk_id"]),
        sa.PrimaryKeyConstraint("credential_id"),
        sa.UniqueConstraint("secret_hash"),
    )
    op.create_index("ix_kiosk_credentials_kiosk_id", "kiosk_credentials", ["kiosk_id"])
    op.add_column("refunds", sa.Column("image_sha256", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("refunds", "image_sha256")
    op.drop_index("ix_kiosk_credentials_kiosk_id", table_name="kiosk_credentials")
    op.drop_table("kiosk_credentials")
