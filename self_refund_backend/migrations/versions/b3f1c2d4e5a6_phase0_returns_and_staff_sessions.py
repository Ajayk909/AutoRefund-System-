"""phase 0: quantity-aware returns, idempotency, refunded state, staff sessions

Revision ID: b3f1c2d4e5a6
Revises: 8c6babcc8841
Create Date: 2026-09-17

Additive only: existing refunds keep working. Old rows are back-filled with
quantity=1 and the matching transaction_items row where one exists.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b3f1c2d4e5a6"
down_revision: Union[str, Sequence[str], None] = "8c6babcc8841"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New enum value. ADD VALUE cannot be used inside the same transaction
    # that later uses the value, so run it in an autocommit block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE decision_status_enum ADD VALUE IF NOT EXISTS 'refunded'")

    op.add_column("refunds", sa.Column("transaction_item_id", sa.UUID(), nullable=True))
    op.add_column("refunds", sa.Column("quantity", sa.Integer(), nullable=False,
                                       server_default="1"))
    op.add_column("refunds", sa.Column("idempotency_key", sa.String(length=100), nullable=True))
    op.add_column("refunds", sa.Column("decided_at", sa.DateTime(), nullable=True))
    op.add_column("refunds", sa.Column("refunded_at", sa.DateTime(), nullable=True))
    op.add_column("refunds", sa.Column("refunded_by_staff_id", sa.UUID(), nullable=True))

    op.create_foreign_key("fk_refunds_transaction_item", "refunds", "transaction_items",
                          ["transaction_item_id"], ["item_id"])
    op.create_foreign_key("fk_refunds_refunded_by_staff", "refunds", "staff",
                          ["refunded_by_staff_id"], ["staff_id"])
    op.create_unique_constraint("uq_refunds_idempotency_key", "refunds", ["idempotency_key"])
    op.create_index("ix_refunds_transaction_item_id", "refunds", ["transaction_item_id"])
    op.create_check_constraint("ck_refunds_quantity_positive", "refunds", "quantity > 0")

    # Back-fill the receipt line for existing refunds.
    op.execute("""
        UPDATE refunds r SET transaction_item_id = ti.item_id
        FROM transaction_items ti
        WHERE r.transaction_item_id IS NULL
          AND ti.transaction_id = r.transaction_id
          AND ti.product_id = r.product_id
    """)

    op.create_table(
        "staff_sessions",
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("staff_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["staff_id"], ["staff.staff_id"]),
        sa.PrimaryKeyConstraint("session_id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_staff_sessions_staff_id", "staff_sessions", ["staff_id"])


def downgrade() -> None:
    op.drop_index("ix_staff_sessions_staff_id", table_name="staff_sessions")
    op.drop_table("staff_sessions")
    op.drop_constraint("ck_refunds_quantity_positive", "refunds", type_="check")
    op.drop_index("ix_refunds_transaction_item_id", table_name="refunds")
    op.drop_constraint("uq_refunds_idempotency_key", "refunds", type_="unique")
    op.drop_constraint("fk_refunds_refunded_by_staff", "refunds", type_="foreignkey")
    op.drop_constraint("fk_refunds_transaction_item", "refunds", type_="foreignkey")
    for col in ("refunded_by_staff_id", "refunded_at", "decided_at",
                "idempotency_key", "quantity", "transaction_item_id"):
        op.drop_column("refunds", col)
    # PostgreSQL cannot drop a single enum value. Rows must not use it.
    op.execute("UPDATE refunds SET decision_status = 'approved' WHERE decision_status = 'refunded'")
