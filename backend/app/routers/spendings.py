from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..auth import get_current_user
from ..periods import parse_month, in_month
from .. import models, owned, schemas

router = APIRouter(prefix="/spendings", tags=["spendings"], dependencies=[Depends(get_current_user)])


def _get_owned_spending(db: Session, spending_id: str, user_id: str) -> models.Spending:
    sp = (
        db.query(models.Spending)
        .filter(models.Spending.id == spending_id, models.Spending.user_id == user_id)
        .first()
    )
    if not sp:
        raise HTTPException(status_code=404, detail="Gasto não encontrado")
    return sp


def _to_out(sp: models.Spending) -> schemas.SpendingOut:
    cat = sp.category
    return schemas.SpendingOut(
        id=sp.id, amount=sp.amount, category_id=sp.category_id, categoria=cat.name if cat else None,
        icone=cat.icon if cat else None, description=sp.description, place=sp.place, date=sp.date,
    )


@router.get("", response_model=List[schemas.SpendingOut])
def list_spendings(month: Optional[str] = None, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Gastos com data no mês pedido (por defeito o atual), mais recentes primeiro."""
    m = parse_month(month)
    spendings = (
        db.query(models.Spending)
        .options(joinedload(models.Spending.category))
        .filter(models.Spending.user_id == current_user.id, in_month(models.Spending.date, m))
        .order_by(models.Spending.date.desc(), models.Spending.created_at.desc())
        .all()
    )
    return [_to_out(sp) for sp in spendings]


@router.get("/places", response_model=List[str])
def list_places(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Locais já usados (para sugestões), dos mais frequentes para os menos."""
    uses = func.count(models.Spending.id)
    rows = (
        db.query(models.Spending.place)
        .filter(models.Spending.user_id == current_user.id, models.Spending.place.isnot(None))
        .group_by(models.Spending.place)
        .order_by(uses.desc(), func.max(models.Spending.date).desc(), models.Spending.place)
        .limit(50)
        .all()
    )
    return [place for (place,) in rows]


@router.post("", response_model=schemas.SpendingOut)
def create_spending(data: schemas.SpendingIn, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    owned.get_category(db, data.category_id, current_user.id)
    sp = models.Spending(
        user_id=current_user.id, category_id=data.category_id, amount=data.amount,
        description=data.description or None, place=data.place, date=data.date or date.today(),
    )
    db.add(sp)
    db.commit()
    db.refresh(sp)
    return _to_out(sp)


@router.put("/{spending_id}", response_model=schemas.SpendingOut)
def update_spending(spending_id: str, data: schemas.SpendingUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    sp = _get_owned_spending(db, spending_id, current_user.id)
    fields = data.model_dump(exclude_unset=True)
    for required in ("amount", "category_id", "date"):
        if required in fields and fields[required] is None:
            raise HTTPException(status_code=422, detail="Valor, categoria e data não podem ficar vazios")
    if "category_id" in fields:
        owned.get_category(db, fields["category_id"], current_user.id)
    if "description" in fields:
        fields["description"] = fields["description"] or None
    for field, value in fields.items():
        setattr(sp, field, value)
    db.commit()
    db.refresh(sp)
    return _to_out(sp)


@router.delete("/{spending_id}")
def delete_spending(spending_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    sp = _get_owned_spending(db, spending_id, current_user.id)
    db.delete(sp)
    db.commit()
    return {"ok": True}
