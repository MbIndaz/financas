from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import get_current_user
from .. import models, schemas

router = APIRouter(prefix="/summary", tags=["summary"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=schemas.SummaryOut)
def get_summary(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    income_row = db.query(models.Income).filter(models.Income.user_id == current_user.id).first()
    income = income_row.amount if income_row else 0

    expenses = (
        db.query(models.Expense)
        .join(models.ExpenseCategory)
        .filter(models.ExpenseCategory.user_id == current_user.id)
        .all()
    )
    total_expenses = sum(e.amount for e in expenses)
    left_after_expenses = income - total_expenses

    buckets = db.query(models.SavingsBucket).filter(models.SavingsBucket.user_id == current_user.id).all()
    total_monthly_contributions = sum(b.monthly_contribution for b in buckets)
    total_saved = sum(b.current_amount for b in buckets)

    left_to_spend = left_after_expenses - total_monthly_contributions

    return schemas.SummaryOut(
        income=income,
        total_expenses=total_expenses,
        left_after_expenses=left_after_expenses,
        total_monthly_contributions=total_monthly_contributions,
        left_to_spend=left_to_spend,
        total_saved=total_saved,
    )
