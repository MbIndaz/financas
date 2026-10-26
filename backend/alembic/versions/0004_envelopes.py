"""modelo de envelopes: repartição dos rendimentos, gastos, pagamentos de contas, movimentos dos objetivos

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-26

Os saldos dos envelopes (Despesas, Objetivos, Para gastar) não são guardados: derivam destes
registos. Valores de dinheiro passam a Numeric(12, 2). O current_amount dos objetivos passa a
opening_amount (o que já estava guardado antes de haver movimentos). Os rendimentos existentes
ficam com a repartição toda em Para gastar.

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("expenses", "amount", type_=sa.Numeric(12, 2), existing_type=sa.Float(),
                    existing_nullable=False, postgresql_using="round(amount::numeric, 2)")

    op.execute("UPDATE savings_buckets SET current_amount = 0 WHERE current_amount IS NULL")
    op.execute("UPDATE savings_buckets SET monthly_contribution = 0 WHERE monthly_contribution IS NULL")
    op.alter_column("savings_buckets", "current_amount", type_=sa.Numeric(12, 2), existing_type=sa.Float(),
                    nullable=False, existing_nullable=True, postgresql_using="round(current_amount::numeric, 2)")
    op.alter_column("savings_buckets", "current_amount", new_column_name="opening_amount")
    op.alter_column("savings_buckets", "target_amount", type_=sa.Numeric(12, 2), existing_type=sa.Float(),
                    existing_nullable=True, postgresql_using="round(target_amount::numeric, 2)")
    op.alter_column("savings_buckets", "monthly_contribution", type_=sa.Numeric(12, 2), existing_type=sa.Float(),
                    nullable=False, existing_nullable=True, postgresql_using="round(monthly_contribution::numeric, 2)")
    op.add_column("savings_buckets", sa.Column("archived_at", sa.DateTime(), nullable=True))

    op.add_column("income_entries", sa.Column("alloc_despesas", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.create_check_constraint("ck_income_entries_alloc_despesas", "income_entries",
                               "alloc_despesas >= 0 AND alloc_despesas <= amount")

    op.create_table(
        "income_allocations",
        sa.Column("income_entry_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("income_entries.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("bucket_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("savings_buckets.id"), primary_key=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_income_allocations_amount_positive"),
    )
    op.create_index("ix_income_allocations_bucket_id", "income_allocations", ["bucket_id"])

    op.create_table(
        "bucket_movements",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("bucket_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("savings_buckets.id"), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("date", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("amount <> 0", name="ck_bucket_movements_amount_nonzero"),
    )
    op.create_index("ix_bucket_movements_bucket_id", "bucket_movements", ["bucket_id"])

    op.create_table(
        "spendings",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("expense_categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("date", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("amount > 0", name="ck_spendings_amount_positive"),
    )
    op.create_index("ix_spendings_user_id", "spendings", ["user_id"])
    op.create_index("ix_spendings_category_id", "spendings", ["category_id"])

    op.create_table(
        "expense_payments",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("expense_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("expenses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("paid_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("expense_id", "month", name="uq_expense_payments_expense_month"),
        sa.CheckConstraint("amount > 0", name="ck_expense_payments_amount_positive"),
        sa.CheckConstraint("date_part('day', month) = 1", name="ck_expense_payments_month_first_day"),
    )
    op.create_index("ix_expense_payments_expense_id", "expense_payments", ["expense_id"])


def downgrade() -> None:
    # O objetivo volta a ter um único valor guardado: o que já tinha mais todas as repartições e
    # movimentos (sem filtro de datas). Gastos, pagamentos e repartições perdem-se; para um regresso
    # exato usa o backup.
    op.execute(
        """
        UPDATE savings_buckets b SET opening_amount = b.opening_amount
            + COALESCE((SELECT sum(a.amount) FROM income_allocations a WHERE a.bucket_id = b.id), 0)
            + COALESCE((SELECT sum(m.amount) FROM bucket_movements m WHERE m.bucket_id = b.id), 0)
        """
    )
    op.drop_index("ix_expense_payments_expense_id", table_name="expense_payments")
    op.drop_table("expense_payments")
    op.drop_index("ix_spendings_category_id", table_name="spendings")
    op.drop_index("ix_spendings_user_id", table_name="spendings")
    op.drop_table("spendings")
    op.drop_index("ix_bucket_movements_bucket_id", table_name="bucket_movements")
    op.drop_table("bucket_movements")
    op.drop_index("ix_income_allocations_bucket_id", table_name="income_allocations")
    op.drop_table("income_allocations")

    op.drop_constraint("ck_income_entries_alloc_despesas", "income_entries", type_="check")
    op.drop_column("income_entries", "alloc_despesas")

    # objetivos apagados já tinham o saldo devolvido ao Para gastar: no esquema antigo deixam de existir
    op.execute("DELETE FROM savings_buckets WHERE archived_at IS NOT NULL")
    op.drop_column("savings_buckets", "archived_at")
    op.alter_column("savings_buckets", "monthly_contribution", type_=sa.Float(), existing_type=sa.Numeric(12, 2),
                    nullable=True, existing_nullable=False)
    op.alter_column("savings_buckets", "target_amount", type_=sa.Float(), existing_type=sa.Numeric(12, 2),
                    existing_nullable=True)
    op.alter_column("savings_buckets", "opening_amount", new_column_name="current_amount")
    op.alter_column("savings_buckets", "current_amount", type_=sa.Float(), existing_type=sa.Numeric(12, 2),
                    nullable=True, existing_nullable=False)

    op.alter_column("expenses", "amount", type_=sa.Float(), existing_type=sa.Numeric(12, 2), existing_nullable=False)
