from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import get_current_user
from ..periods import parse_month, active_in_month, check_recurrence, split_recurring, end_recurring
from .. import models, schemas

router = APIRouter(prefix="/income-entries", tags=["income"], dependencies=[Depends(get_current_user)])


def _get_owned_entry(db: Session, entry_id: str, user_id: str) -> models.IncomeEntry:
    entry = (
        db.query(models.IncomeEntry)
        .filter(models.IncomeEntry.id == entry_id, models.IncomeEntry.user_id == user_id)
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Receita não encontrada")
    return entry


@router.get("", response_model=List[schemas.IncomeEntryOut])
def list_entries(month: Optional[str] = None, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Receitas ativas no mês pedido (por defeito o atual), mais recentes primeiro."""
    m = parse_month(month)
    return (
        db.query(models.IncomeEntry)
        .filter(models.IncomeEntry.user_id == current_user.id, active_in_month(models.IncomeEntry, m))
        .order_by(models.IncomeEntry.date.desc(), models.IncomeEntry.created_at.desc())
        .all()
    )


@router.post("", response_model=schemas.IncomeEntryOut)
def create_entry(data: schemas.IncomeEntryCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    entry = models.IncomeEntry(user_id=current_user.id, **data.model_dump())
    check_recurrence(entry)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.put("/{entry_id}", response_model=schemas.IncomeEntryOut)
def update_entry(entry_id: str, data: schemas.IncomeEntryUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    entry = _get_owned_entry(db, entry_id, current_user.id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    check_recurrence(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}")
def delete_entry(entry_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    entry = _get_owned_entry(db, entry_id, current_user.id)
    db.delete(entry)
    db.commit()
    return {"ok": True}


@router.post("/{entry_id}/change", response_model=schemas.IncomeEntryOut)
def change_entry(entry_id: str, data: schemas.ChangeRecurringIn, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Muda o valor de um recorrente a partir de um mês, preservando o histórico."""
    entry = _get_owned_entry(db, entry_id, current_user.id)
    split = split_recurring(entry, data.start_month)
    if split is None:
        entry.amount = data.amount
        result = entry
    else:
        start, end = split
        result = models.IncomeEntry(
            user_id=entry.user_id, amount=data.amount, source=entry.source, description=entry.description,
            date=start, is_recurring=True, end_date=end,
        )
        db.add(result)
    db.commit()
    db.refresh(result)
    return result


@router.post("/{entry_id}/end", response_model=schemas.IncomeEntryOut)
def end_entry(entry_id: str, data: schemas.EndRecurringIn, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    entry = _get_owned_entry(db, entry_id, current_user.id)
    end_recurring(entry, data.end_month)
    db.commit()
    db.refresh(entry)
    return entry
