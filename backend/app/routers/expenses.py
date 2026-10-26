from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import get_current_user
from ..periods import parse_month, active_in_month, check_recurrence, split_recurring, end_recurring
from .. import models, schemas

router = APIRouter(tags=["expenses"], dependencies=[Depends(get_current_user)])


def _get_owned_category(db: Session, category_id: str, user_id: str) -> models.ExpenseCategory:
    cat = (
        db.query(models.ExpenseCategory)
        .filter(models.ExpenseCategory.id == category_id, models.ExpenseCategory.user_id == user_id)
        .first()
    )
    if not cat:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")
    return cat


# ---------- Categories ----------
@router.get("/categories", response_model=List[schemas.CategoryOut])
def list_categories(month: Optional[str] = None, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Categorias com as despesas ativas no mês pedido (por defeito o atual)."""
    m = parse_month(month)
    cats = (
        db.query(models.ExpenseCategory)
        .filter(models.ExpenseCategory.user_id == current_user.id)
        .order_by(models.ExpenseCategory.position)
        .all()
    )
    active = (
        db.query(models.Expense)
        .join(models.ExpenseCategory)
        .filter(models.ExpenseCategory.user_id == current_user.id, active_in_month(models.Expense, m))
        .order_by(models.Expense.date.desc(), models.Expense.created_at.desc())
        .all()
    )
    by_cat = {}
    for e in active:
        by_cat.setdefault(e.category_id, []).append(e)
    return [
        schemas.CategoryOut(id=c.id, name=c.name, icon=c.icon, position=c.position, expenses=by_cat.get(c.id, []))
        for c in cats
    ]


@router.post("/categories", response_model=schemas.CategoryOut)
def create_category(data: schemas.CategoryCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    count = db.query(models.ExpenseCategory).filter(models.ExpenseCategory.user_id == current_user.id).count()
    cat = models.ExpenseCategory(user_id=current_user.id, name=data.name, icon=data.icon, position=count)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


@router.put("/categories/{category_id}", response_model=schemas.CategoryOut)
def update_category(category_id: str, data: schemas.CategoryUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    cat = _get_owned_category(db, category_id, current_user.id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(cat, field, value)
    db.commit()
    db.refresh(cat)
    return cat


@router.delete("/categories/{category_id}")
def delete_category(category_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    cat = _get_owned_category(db, category_id, current_user.id)
    db.delete(cat)
    db.commit()
    return {"ok": True}


# ---------- Expenses (dentro de uma categoria) ----------
@router.post("/categories/{category_id}/expenses", response_model=schemas.ExpenseOut)
def create_expense(category_id: str, data: schemas.ExpenseCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    _get_owned_category(db, category_id, current_user.id)
    exp = models.Expense(category_id=category_id, **data.model_dump())
    check_recurrence(exp)
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return exp


def _get_owned_expense(db: Session, expense_id: str, user_id: str) -> models.Expense:
    exp = (
        db.query(models.Expense)
        .join(models.ExpenseCategory)
        .filter(models.Expense.id == expense_id, models.ExpenseCategory.user_id == user_id)
        .first()
    )
    if not exp:
        raise HTTPException(status_code=404, detail="Despesa não encontrada")
    return exp


@router.put("/expenses/{expense_id}", response_model=schemas.ExpenseOut)
def update_expense(expense_id: str, data: schemas.ExpenseUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    exp = _get_owned_expense(db, expense_id, current_user.id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(exp, field, value)
    check_recurrence(exp)
    db.commit()
    db.refresh(exp)
    return exp


@router.delete("/expenses/{expense_id}")
def delete_expense(expense_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    exp = _get_owned_expense(db, expense_id, current_user.id)
    db.delete(exp)
    db.commit()
    return {"ok": True}


@router.post("/expenses/{expense_id}/change", response_model=schemas.ExpenseOut)
def change_expense(expense_id: str, data: schemas.ChangeRecurringIn, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Muda o valor de uma despesa recorrente a partir de um mês, preservando o histórico."""
    exp = _get_owned_expense(db, expense_id, current_user.id)
    split = split_recurring(exp, data.start_month)
    if split is None:
        exp.amount = data.amount
        result = exp
    else:
        start, end = split
        result = models.Expense(
            category_id=exp.category_id, title=exp.title, amount=data.amount,
            date=start, is_recurring=True, end_date=end,
        )
        db.add(result)
    db.commit()
    db.refresh(result)
    return result


@router.post("/expenses/{expense_id}/end", response_model=schemas.ExpenseOut)
def end_expense(expense_id: str, data: schemas.EndRecurringIn, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    exp = _get_owned_expense(db, expense_id, current_user.id)
    end_recurring(exp, data.end_month)
    db.commit()
    db.refresh(exp)
    return exp
