import uuid
from datetime import date, datetime

from sqlalchemy import (
    Column, String, Float, DateTime, ForeignKey, Boolean, Integer, Numeric, Date, CheckConstraint, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .database import Base


def gen_uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    income = relationship("Income", back_populates="user", uselist=False, cascade="all, delete-orphan")
    income_entries = relationship("IncomeEntry", back_populates="user", cascade="all, delete-orphan")
    account_settings = relationship("AccountSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    categories = relationship("ExpenseCategory", back_populates="user", cascade="all, delete-orphan")
    buckets = relationship("SavingsBucket", back_populates="user", cascade="all, delete-orphan")
    spendings = relationship("Spending", back_populates="user", cascade="all, delete-orphan")


class InviteCode(Base):
    __tablename__ = "invite_codes"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    code = Column(String, unique=True, nullable=False, index=True)
    created_by = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    used_by = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Income(Base):
    """Valor único antigo; desde a 0002 a app usa IncomeEntry. Mantida só para não perder dados."""
    __tablename__ = "income"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), unique=True, nullable=False)
    amount = Column(Float, nullable=False, default=0)
    label = Column(String, nullable=True, default="Rendimento mensal")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="income")


class IncomeEntry(Base):
    """Dinheiro recebido, repartido por Despesas, objetivos e (o resto) Para gastar."""
    __tablename__ = "income_entries"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_income_entries_amount_positive"),
        CheckConstraint("alloc_despesas >= 0 AND alloc_despesas <= amount", name="ck_income_entries_alloc_despesas"),
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    source = Column(String, nullable=False)  # origem: "Salário", "Venda", "Extra"...
    description = Column(String, nullable=True)
    date = Column(Date, nullable=False, default=date.today)
    alloc_despesas = Column(Numeric(12, 2), nullable=False, default=0)  # parte reservada para pagar contas
    # legado da 0002: desde a 0004 todos os rendimentos são pontuais e estas colunas são ignoradas
    is_recurring = Column(Boolean, nullable=False, default=False)
    end_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="income_entries")
    allocations = relationship("IncomeAllocation", back_populates="income_entry", cascade="all, delete-orphan")


class IncomeAllocation(Base):
    """Parte de um rendimento depositada num objetivo (conta na data do rendimento)."""
    __tablename__ = "income_allocations"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_income_allocations_amount_positive"),)

    income_entry_id = Column(UUID(as_uuid=False), ForeignKey("income_entries.id", ondelete="CASCADE"), primary_key=True)
    bucket_id = Column(UUID(as_uuid=False), ForeignKey("savings_buckets.id"), primary_key=True, index=True)
    amount = Column(Numeric(12, 2), nullable=False)

    income_entry = relationship("IncomeEntry", back_populates="allocations")
    bucket = relationship("SavingsBucket")


class AccountSettings(Base):
    """Saldo inicial: o dinheiro na conta no início de opening_date (movimentos anteriores não contam)."""
    __tablename__ = "account_settings"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), unique=True, nullable=False)
    opening_balance = Column(Numeric(12, 2), nullable=False)  # pode ser negativo
    opening_date = Column(Date, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="account_settings")


class ExpenseCategory(Base):
    __tablename__ = "expense_categories"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    icon = Column(String, default="📦")
    position = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="categories")
    expenses = relationship("Expense", back_populates="category", cascade="all, delete-orphan")
    # ao apagar a categoria, os gastos ficam sem categoria (ON DELETE SET NULL na base de dados)
    spendings = relationship("Spending", back_populates="category", passive_deletes=True)


class Expense(Base):
    """Conta (despesa planeada) de uma categoria; o estado pago/por pagar é por mês (ExpensePayment)."""
    __tablename__ = "expenses"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    category_id = Column(UUID(as_uuid=False), ForeignKey("expense_categories.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    date = Column(Date, nullable=False, default=date.today)  # nas recorrentes é a data de início
    is_recurring = Column(Boolean, nullable=False, default=False)
    end_date = Column(Date, nullable=True)  # só recorrentes: último mês em que ainda vale
    created_at = Column(DateTime, default=datetime.utcnow)

    category = relationship("ExpenseCategory", back_populates="expenses")
    payments = relationship("ExpensePayment", back_populates="expense", cascade="all, delete-orphan", passive_deletes=True)


class ExpensePayment(Base):
    """Pagamento de uma conta num mês: sai do envelope Despesas na data de pagamento."""
    __tablename__ = "expense_payments"
    __table_args__ = (
        UniqueConstraint("expense_id", "month", name="uq_expense_payments_expense_month"),
        CheckConstraint("amount > 0", name="ck_expense_payments_amount_positive"),
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    expense_id = Column(UUID(as_uuid=False), ForeignKey("expenses.id", ondelete="CASCADE"), nullable=False, index=True)
    month = Column(Date, nullable=False)  # primeiro dia do mês a que o pagamento diz respeito
    amount = Column(Numeric(12, 2), nullable=False)
    paid_date = Column(Date, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    expense = relationship("Expense", back_populates="payments")


class Spending(Base):
    """Gasto do dia a dia: sai do envelope Para gastar."""
    __tablename__ = "spendings"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_spendings_amount_positive"),)

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True)
    category_id = Column(UUID(as_uuid=False), ForeignKey("expense_categories.id", ondelete="SET NULL"), nullable=True, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    description = Column(String, nullable=True)
    date = Column(Date, nullable=False, default=date.today)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="spendings")
    category = relationship("ExpenseCategory", back_populates="spendings")


class SavingsBucket(Base):
    __tablename__ = "savings_buckets"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    icon = Column(String, default="🎯")
    kind = Column(String, default="objetivo")  # "emergencia" | "obrigatoria" | "objetivo" | "livre"
    # o saldo do objetivo é derivado: opening_amount + repartições de rendimentos + depósitos − levantamentos
    opening_amount = Column(Numeric(12, 2), nullable=False, default=0)  # já guardado no dia do saldo inicial
    target_amount = Column(Numeric(12, 2), nullable=True)
    monthly_contribution = Column(Numeric(12, 2), nullable=False, default=0)  # sugestão ao repartir um rendimento
    is_mandatory = Column(Boolean, default=False)
    position = Column(Integer, default=0)
    archived_at = Column(DateTime, nullable=True)  # apagado mas com histórico: escondido e com saldo devolvido
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="buckets")
    movements = relationship("BucketMovement", back_populates="bucket")


class BucketMovement(Base):
    """Depósito (valor positivo) ou levantamento (negativo) de um objetivo, contra o Para gastar."""
    __tablename__ = "bucket_movements"
    __table_args__ = (CheckConstraint("amount <> 0", name="ck_bucket_movements_amount_nonzero"),)

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    bucket_id = Column(UUID(as_uuid=False), ForeignKey("savings_buckets.id"), nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    date = Column(Date, nullable=False, default=date.today)
    note = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    bucket = relationship("SavingsBucket", back_populates="movements")
