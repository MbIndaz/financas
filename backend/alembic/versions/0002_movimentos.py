"""receitas com data e recorrência, despesas com data e recorrência

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-26

Dados: o valor único de cada utilizador em income (só se > 0) passa a uma receita
recorrente "Salário" a começar no primeiro dia do mês atual; as despesas existentes
eram mensais fixas e ficam recorrentes a partir do mesmo dia. A tabela income fica
intacta (deixa de ser usada pela app).

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "income_entries",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("date", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")),
        sa.Column("is_recurring", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("amount > 0", name="ck_income_entries_amount_positive"),
    )
    op.create_index("ix_income_entries_user_id", "income_entries", ["user_id"])

    op.add_column("expenses", sa.Column("date", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")))
    op.add_column("expenses", sa.Column("is_recurring", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("expenses", sa.Column("end_date", sa.Date(), nullable=True))

    op.execute(
        """
        INSERT INTO income_entries (id, user_id, amount, source, description, date, is_recurring, created_at)
        SELECT gen_random_uuid(), user_id, round(amount::numeric, 2), 'Salário',
               NULLIF(label, 'Rendimento mensal'), date_trunc('month', CURRENT_DATE)::date, true, now()
        FROM income
        WHERE amount > 0
        """
    )
    op.execute(
        """
        UPDATE expenses
        SET is_recurring = true, date = date_trunc('month', CURRENT_DATE)::date
        """
    )


def downgrade() -> None:
    # As receitas e as datas/recorrência das despesas perdem-se; a tabela income nunca foi alterada.
    op.drop_column("expenses", "end_date")
    op.drop_column("expenses", "is_recurring")
    op.drop_column("expenses", "date")
    op.drop_index("ix_income_entries_user_id", table_name="income_entries")
    op.drop_table("income_entries")
