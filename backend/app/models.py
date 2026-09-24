import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Float, DateTime, ForeignKey, Boolean, Integer
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
    categories = relationship("ExpenseCategory", back_populates="user", cascade="all, delete-orphan")
    buckets = relationship("SavingsBucket", back_populates="user", cascade="all, delete-orphan")


class InviteCode(Base):
    __tablename__ = "invite_codes"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    code = Column(String, unique=True, nullable=False, index=True)
    created_by = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    used_by = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Income(Base):
    __tablename__ = "income"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), unique=True, nullable=False)
    amount = Column(Float, nullable=False, default=0)
    label = Column(String, nullable=True, default="Rendimento mensal")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="income")


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


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    category_id = Column(UUID(as_uuid=False), ForeignKey("expense_categories.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    category = relationship("ExpenseCategory", back_populates="expenses")


class SavingsBucket(Base):
    __tablename__ = "savings_buckets"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    icon = Column(String, default="🎯")
    kind = Column(String, default="objetivo")  # "emergencia" | "obrigatoria" | "objetivo" | "livre"
    current_amount = Column(Float, default=0)
    target_amount = Column(Float, nullable=True)
    monthly_contribution = Column(Float, default=0)
    is_mandatory = Column(Boolean, default=False)
    position = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="buckets")
