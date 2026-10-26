from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import get_current_user
from .. import models, schemas

router = APIRouter(prefix="/account", tags=["account"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=schemas.AccountOut)
def get_account(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    settings = db.query(models.AccountSettings).filter(models.AccountSettings.user_id == current_user.id).first()
    if not settings:
        return schemas.AccountOut()
    return schemas.AccountOut(opening_balance=float(settings.opening_balance), opening_date=settings.opening_date)


@router.put("", response_model=schemas.AccountOut)
def update_account(data: schemas.AccountIn, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if data.opening_date > date.today():
        raise HTTPException(status_code=400, detail="A data do saldo inicial não pode ser no futuro")
    settings = db.query(models.AccountSettings).filter(models.AccountSettings.user_id == current_user.id).first()
    if not settings:
        settings = models.AccountSettings(user_id=current_user.id)
        db.add(settings)
    settings.opening_balance = data.opening_balance
    settings.opening_date = data.opening_date
    db.commit()
    db.refresh(settings)
    return schemas.AccountOut(opening_balance=float(settings.opening_balance), opening_date=settings.opening_date)
