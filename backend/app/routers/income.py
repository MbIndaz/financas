from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import get_current_user
from .. import models, schemas

router = APIRouter(prefix="/income", tags=["income"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=schemas.IncomeOut)
def get_income(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    income = db.query(models.Income).filter(models.Income.user_id == current_user.id).first()
    if not income:
        income = models.Income(user_id=current_user.id, amount=0)
        db.add(income)
        db.commit()
        db.refresh(income)
    return income


@router.put("", response_model=schemas.IncomeOut)
def update_income(data: schemas.IncomeIn, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    income = db.query(models.Income).filter(models.Income.user_id == current_user.id).first()
    if not income:
        income = models.Income(user_id=current_user.id)
        db.add(income)
    income.amount = data.amount
    income.label = data.label
    db.commit()
    db.refresh(income)
    return income
