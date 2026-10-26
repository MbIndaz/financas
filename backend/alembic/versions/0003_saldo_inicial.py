"""saldo inicial com data (account_settings)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-26

Não insere linhas: cada utilizador define o seu saldo inicial na app.

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_settings",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("opening_balance", sa.Numeric(12, 2), nullable=False),
        sa.Column("opening_date", sa.Date(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("user_id", name="uq_account_settings_user_id"),
    )


def downgrade() -> None:
    op.drop_table("account_settings")
