"""phase 4: verification signals

Adds the verification_signals table: one row per check made on a return
(barcode, weight, photo, AI) with its result, confidence and reason.

Revision ID: f1a7c3d9b2e4
Revises: e5b9c0d7f3a1
Create Date: 2026-09-24

Additive. refunds gets a unique (retailer_id, refund_id) so signals can use
a same-retailer foreign key, like the other tenant-owned tables. Existing
returns get no signal rows: their checks were stored on the return row only.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f1a7c3d9b2e4"
down_revision: Union[str, Sequence[str], None] = "e5b9c0d7f3a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint("uq_refunds_retailer_refund", "refunds",
                                ["retailer_id", "refund_id"])
    op.create_table(
        "verification_signals",
        sa.Column("signal_id", sa.UUID(), nullable=False),
        sa.Column("refund_id", sa.UUID(), nullable=False),
        sa.Column("retailer_id", sa.UUID(), nullable=False),
        sa.Column("signal_type", sa.String(length=20), nullable=False),
        sa.Column("result", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("signal_id"),
        sa.UniqueConstraint("refund_id", "signal_type",
                            name="uq_verification_signals_refund_type"),
        sa.ForeignKeyConstraint(["retailer_id", "refund_id"],
                                ["refunds.retailer_id", "refunds.refund_id"],
                                name="fk_verification_signals_refund_same_retailer"),
        sa.CheckConstraint("signal_type IN ('barcode', 'weight', 'photo', 'ai')",
                           name="ck_verification_signals_type"),
        sa.CheckConstraint("result IN ('match', 'mismatch', 'uncertain')",
                           name="ck_verification_signals_result"),
        sa.CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
                           name="ck_verification_signals_confidence"),
    )


def downgrade() -> None:
    op.drop_table("verification_signals")
    op.drop_constraint("uq_refunds_retailer_refund", "refunds", type_="unique")
