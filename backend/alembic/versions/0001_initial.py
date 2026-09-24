"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-19

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "invite_codes",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("used_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_invite_codes_code", "invite_codes", ["code"], unique=True)

    op.create_table(
        "income",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("label", sa.String(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("user_id", name="uq_income_user_id"),
    )

    op.create_table(
        "expense_categories",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("icon", sa.String(), nullable=True, server_default="📦"),
        sa.Column("position", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_expense_categories_user_id", "expense_categories", ["user_id"])

    op.create_table(
        "expenses",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("category_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("expense_categories.id"), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_expenses_category_id", "expenses", ["category_id"])

    op.create_table(
        "savings_buckets",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("icon", sa.String(), nullable=True, server_default="🎯"),
        sa.Column("kind", sa.String(), nullable=True, server_default="objetivo"),
        sa.Column("current_amount", sa.Float(), nullable=True, server_default="0"),
        sa.Column("target_amount", sa.Float(), nullable=True),
        sa.Column("monthly_contribution", sa.Float(), nullable=True, server_default="0"),
        sa.Column("is_mandatory", sa.Boolean(), nullable=True, server_default="false"),
        sa.Column("position", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_savings_buckets_user_id", "savings_buckets", ["user_id"])


def downgrade() -> None:
    op.drop_table("savings_buckets")
    op.drop_table("expenses")
    op.drop_table("expense_categories")
    op.drop_table("income")
    op.drop_index("ix_invite_codes_code", table_name="invite_codes")
    op.drop_table("invite_codes")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
