"""Procura registos do utilizador atual; registos de outra conta dão 404, como se não existissem."""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from . import models


def get_category(db: Session, category_id: str, user_id: str) -> models.ExpenseCategory:
    cat = (
        db.query(models.ExpenseCategory)
        .filter(models.ExpenseCategory.id == category_id, models.ExpenseCategory.user_id == user_id)
        .first()
    )
    if not cat:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")
    return cat


def get_expense(db: Session, expense_id: str, user_id: str) -> models.Expense:
    exp = (
        db.query(models.Expense)
        .join(models.ExpenseCategory)
        .filter(models.Expense.id == expense_id, models.ExpenseCategory.user_id == user_id)
        .first()
    )
    if not exp:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    return exp


def get_bucket(db: Session, bucket_id: str, user_id: str) -> models.SavingsBucket:
    b = (
        db.query(models.SavingsBucket)
        .filter(models.SavingsBucket.id == bucket_id, models.SavingsBucket.user_id == user_id)
        .first()
    )
    if not b:
        raise HTTPException(status_code=404, detail="Objetivo não encontrado")
    return b
