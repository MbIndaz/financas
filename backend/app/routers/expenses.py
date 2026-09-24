from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..auth import get_current_user
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
def list_categories(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return (
        db.query(models.ExpenseCategory)
        .options(joinedload(models.ExpenseCategory.expenses))
        .filter(models.ExpenseCategory.user_id == current_user.id)
        .order_by(models.ExpenseCategory.position)
        .all()
    )


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
    exp = models.Expense(category_id=category_id, title=data.title, amount=data.amount)
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
    db.commit()
    db.refresh(exp)
    return exp


@router.delete("/expenses/{expense_id}")
def delete_expense(expense_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    exp = _get_owned_expense(db, expense_id, current_user.id)
    db.delete(exp)
    db.commit()
    return {"ok": True}
