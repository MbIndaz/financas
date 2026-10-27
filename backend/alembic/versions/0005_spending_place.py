"""local dos gastos do dia a dia

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-27

Só acrescenta a coluna opcional spendings.place (onde foi o gasto, ex.: "Pingo Doce"),
separada da descrição. Os gastos existentes ficam sem local. Não mexe em nenhum saldo.

"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("spendings", sa.Column("place", sa.String(), nullable=True))


def downgrade() -> None:
    # o local dos gastos perde-se; o resto do gasto mantém-se
    op.drop_column("spendings", "place")
