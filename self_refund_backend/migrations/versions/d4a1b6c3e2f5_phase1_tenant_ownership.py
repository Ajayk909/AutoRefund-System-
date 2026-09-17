"""phase 1: tenant ownership, retailer-scoped product identifiers and receipts

Revision ID: d4a1b6c3e2f5
Revises: c7d2e8f1a9b0
Create Date: 2026-09-17

Data migration (explicit, reversible):
* every existing product, transaction, line, staff member and return is
  assigned to the DEFAULT retailer / DEFAULT-STORE created by c7d2e8f1a9b0
* products.barcode moves to product_identifiers (is_primary = true)
* receipt numbers become unique per retailer instead of globally
* refunds.kiosk_id (text) is renamed to kiosk_code and a real kiosk_id
  foreign key is filled in from the kiosks table
* composite foreign keys make cross-retailer links impossible

Downgrade restores the Phase 0 columns. It refuses to run if data now exists
that Phase 0 cannot represent (the same barcode or receipt number at two
retailers).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d4a1b6c3e2f5"
down_revision: Union[str, Sequence[str], None] = "c7d2e8f1a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_RETAILER_ID = "(SELECT retailer_id FROM retailers WHERE code = 'DEFAULT')"
DEFAULT_STORE_ID = ("(SELECT s.store_id FROM stores s JOIN retailers r USING (retailer_id) "
                    "WHERE r.code = 'DEFAULT' AND s.code = 'DEFAULT-STORE')")


def upgrade() -> None:
    # --- products + identifiers ------------------------------------------------
    op.add_column("products", sa.Column("retailer_id", sa.UUID(), nullable=True))
    op.execute(f"UPDATE products SET retailer_id = {DEFAULT_RETAILER_ID}")
    op.alter_column("products", "retailer_id", nullable=False)
    op.create_foreign_key("products_retailer_id_fkey", "products", "retailers",
                          ["retailer_id"], ["retailer_id"])
    op.create_index("ix_products_retailer_id", "products", ["retailer_id"])
    op.create_unique_constraint("uq_products_retailer_product", "products",
                                ["retailer_id", "product_id"])

    op.create_table(
        "product_identifiers",
        sa.Column("identifier_id", sa.UUID(), nullable=False),
        sa.Column("retailer_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("identifier_type", sa.String(length=20), server_default="barcode",
                  nullable=False),
        sa.Column("value", sa.String(length=100), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("identifier_id"),
        sa.UniqueConstraint("retailer_id", "value", name="uq_product_identifiers_retailer_value"),
        sa.ForeignKeyConstraint(["retailer_id", "product_id"],
                                ["products.retailer_id", "products.product_id"],
                                name="fk_product_identifiers_product_same_retailer",
                                ondelete="CASCADE"),
    )
    op.create_index("ix_product_identifiers_product_id", "product_identifiers", ["product_id"])
    op.create_index("uq_product_identifiers_one_primary", "product_identifiers", ["product_id"],
                    unique=True, postgresql_where=sa.text("is_primary"))
    op.execute("""
        INSERT INTO product_identifiers
            (identifier_id, retailer_id, product_id, identifier_type, value, is_primary)
        SELECT gen_random_uuid(), retailer_id, product_id, 'barcode', barcode, true
        FROM products
    """)
    op.drop_constraint("products_barcode_key", "products", type_="unique")
    op.drop_column("products", "barcode")

    # --- transactions --------------------------------------------------------------
    op.add_column("transactions", sa.Column("retailer_id", sa.UUID(), nullable=True))
    op.add_column("transactions", sa.Column("store_id", sa.UUID(), nullable=True))
    op.execute(f"UPDATE transactions SET retailer_id = {DEFAULT_RETAILER_ID}, "
               f"store_id = {DEFAULT_STORE_ID}")
    op.alter_column("transactions", "retailer_id", nullable=False)
    op.alter_column("transactions", "store_id", nullable=False)
    op.drop_constraint("transactions_receipt_number_key", "transactions", type_="unique")
    op.create_unique_constraint("uq_transactions_retailer_receipt", "transactions",
                                ["retailer_id", "receipt_number"])
    op.create_unique_constraint("uq_transactions_retailer_transaction", "transactions",
                                ["retailer_id", "transaction_id"])
    op.create_foreign_key("fk_transactions_store_same_retailer", "transactions", "stores",
                          ["retailer_id", "store_id"], ["retailer_id", "store_id"])

    # --- transaction lines -----------------------------------------------------------
    op.add_column("transaction_items", sa.Column("retailer_id", sa.UUID(), nullable=True))
    op.execute("""
        UPDATE transaction_items ti SET retailer_id = t.retailer_id
        FROM transactions t WHERE t.transaction_id = ti.transaction_id
    """)
    op.alter_column("transaction_items", "retailer_id", nullable=False)
    op.create_unique_constraint("uq_transaction_items_retailer_item", "transaction_items",
                                ["retailer_id", "item_id"])
    op.create_foreign_key("fk_transaction_items_transaction_same_retailer", "transaction_items",
                          "transactions", ["retailer_id", "transaction_id"],
                          ["retailer_id", "transaction_id"])
    op.create_foreign_key("fk_transaction_items_product_same_retailer", "transaction_items",
                          "products", ["retailer_id", "product_id"], ["retailer_id", "product_id"])

    # --- staff ---------------------------------------------------------------------
    op.add_column("staff", sa.Column("retailer_id", sa.UUID(), nullable=True))
    op.add_column("staff", sa.Column("store_id", sa.UUID(), nullable=True))
    op.execute(f"UPDATE staff SET retailer_id = {DEFAULT_RETAILER_ID}")
    op.alter_column("staff", "retailer_id", nullable=False)
    op.create_foreign_key("staff_retailer_id_fkey", "staff", "retailers",
                          ["retailer_id"], ["retailer_id"])
    op.create_foreign_key("fk_staff_store_same_retailer", "staff", "stores",
                          ["retailer_id", "store_id"], ["retailer_id", "store_id"])

    # --- returns (refunds) ---------------------------------------------------------------
    op.alter_column("refunds", "kiosk_id", new_column_name="kiosk_code")
    op.add_column("refunds", sa.Column("retailer_id", sa.UUID(), nullable=True))
    op.add_column("refunds", sa.Column("store_id", sa.UUID(), nullable=True))
    op.add_column("refunds", sa.Column("kiosk_id", sa.UUID(), nullable=True))
    op.execute("""
        UPDATE refunds r SET retailer_id = k.retailer_id, store_id = k.store_id,
                             kiosk_id = k.kiosk_id
        FROM kiosks k WHERE k.code = r.kiosk_code
    """)
    for column in ("retailer_id", "store_id", "kiosk_id"):
        op.alter_column("refunds", column, nullable=False)
    op.create_foreign_key("fk_refunds_transaction_same_retailer", "refunds", "transactions",
                          ["retailer_id", "transaction_id"], ["retailer_id", "transaction_id"])
    op.create_foreign_key("fk_refunds_product_same_retailer", "refunds", "products",
                          ["retailer_id", "product_id"], ["retailer_id", "product_id"])
    op.create_foreign_key("fk_refunds_line_same_retailer", "refunds", "transaction_items",
                          ["retailer_id", "transaction_item_id"], ["retailer_id", "item_id"])
    op.create_foreign_key("fk_refunds_kiosk_same_store", "refunds", "kiosks",
                          ["retailer_id", "store_id", "kiosk_id"],
                          ["retailer_id", "store_id", "kiosk_id"])
    op.create_index("ix_refunds_retailer_status_date", "refunds",
                    ["retailer_id", "decision_status", "refund_date"])

    # --- audit ---------------------------------------------------------------------
    op.add_column("audit_logs", sa.Column("retailer_id", sa.UUID(), nullable=True))
    op.add_column("audit_logs", sa.Column("store_id", sa.UUID(), nullable=True))
    op.create_foreign_key("audit_logs_retailer_id_fkey", "audit_logs", "retailers",
                          ["retailer_id"], ["retailer_id"])
    op.create_foreign_key("audit_logs_store_id_fkey", "audit_logs", "stores",
                          ["store_id"], ["store_id"])
    op.execute("""
        UPDATE audit_logs a SET retailer_id = r.retailer_id, store_id = r.store_id
        FROM refunds r WHERE a.refund_id = r.refund_id
    """)
    op.execute("""
        UPDATE audit_logs a SET retailer_id = s.retailer_id
        FROM staff s WHERE a.retailer_id IS NULL AND a.staff_id = s.staff_id
    """)
    op.create_index("ix_audit_logs_retailer_timestamp", "audit_logs",
                    ["retailer_id", "timestamp"])


def _refuse_if(sql, message):
    if op.get_bind().execute(sa.text(sql)).first():
        raise RuntimeError(message)


def downgrade() -> None:
    _refuse_if("SELECT receipt_number FROM transactions GROUP BY receipt_number "
               "HAVING count(*) > 1",
               "Cannot downgrade: the same receipt number exists at more than one retailer.")
    _refuse_if("SELECT value FROM product_identifiers WHERE is_primary "
               "GROUP BY value HAVING count(*) > 1",
               "Cannot downgrade: the same barcode exists at more than one retailer.")

    # audit
    op.drop_index("ix_audit_logs_retailer_timestamp", table_name="audit_logs")
    op.drop_constraint("audit_logs_store_id_fkey", "audit_logs", type_="foreignkey")
    op.drop_constraint("audit_logs_retailer_id_fkey", "audit_logs", type_="foreignkey")
    op.drop_column("audit_logs", "store_id")
    op.drop_column("audit_logs", "retailer_id")

    # returns
    op.drop_index("ix_refunds_retailer_status_date", table_name="refunds")
    for name in ("fk_refunds_kiosk_same_store", "fk_refunds_line_same_retailer",
                 "fk_refunds_product_same_retailer", "fk_refunds_transaction_same_retailer"):
        op.drop_constraint(name, "refunds", type_="foreignkey")
    for column in ("kiosk_id", "store_id", "retailer_id"):
        op.drop_column("refunds", column)
    op.alter_column("refunds", "kiosk_code", new_column_name="kiosk_id")

    # staff
    op.drop_constraint("fk_staff_store_same_retailer", "staff", type_="foreignkey")
    op.drop_constraint("staff_retailer_id_fkey", "staff", type_="foreignkey")
    op.drop_column("staff", "store_id")
    op.drop_column("staff", "retailer_id")

    # transaction lines
    op.drop_constraint("fk_transaction_items_product_same_retailer", "transaction_items",
                       type_="foreignkey")
    op.drop_constraint("fk_transaction_items_transaction_same_retailer", "transaction_items",
                       type_="foreignkey")
    op.drop_constraint("uq_transaction_items_retailer_item", "transaction_items", type_="unique")
    op.drop_column("transaction_items", "retailer_id")

    # transactions
    op.drop_constraint("fk_transactions_store_same_retailer", "transactions", type_="foreignkey")
    op.drop_constraint("uq_transactions_retailer_transaction", "transactions", type_="unique")
    op.drop_constraint("uq_transactions_retailer_receipt", "transactions", type_="unique")
    op.create_unique_constraint("transactions_receipt_number_key", "transactions",
                                ["receipt_number"])
    op.drop_column("transactions", "store_id")
    op.drop_column("transactions", "retailer_id")

    # products: bring barcode back from the primary identifier
    op.add_column("products", sa.Column("barcode", sa.String(length=100), nullable=True))
    op.execute("""
        UPDATE products p SET barcode = pi.value
        FROM product_identifiers pi
        WHERE pi.product_id = p.product_id AND pi.is_primary
    """)
    op.execute("UPDATE products SET barcode = product_id::text WHERE barcode IS NULL")
    op.alter_column("products", "barcode", nullable=False)
    op.create_unique_constraint("products_barcode_key", "products", ["barcode"])
    op.drop_index("uq_product_identifiers_one_primary", table_name="product_identifiers")
    op.drop_index("ix_product_identifiers_product_id", table_name="product_identifiers")
    op.drop_table("product_identifiers")
    op.drop_constraint("uq_products_retailer_product", "products", type_="unique")
    op.drop_index("ix_products_retailer_id", table_name="products")
    op.drop_constraint("products_retailer_id_fkey", "products", type_="foreignkey")
    op.drop_column("products", "retailer_id")
