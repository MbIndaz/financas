from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..auth import get_current_user
from ..periods import parse_month, in_month
from .. import models, owned, schemas
from ..textnorm import group_spellings, text_key

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


def _place_groups(db: Session, user_id: str) -> dict:
    """Locais do utilizador agrupados pela chave normalizada (ver textnorm.group_spellings)."""
    rows = (
        db.query(models.Spending.place, func.count(models.Spending.id), func.max(models.Spending.date))
        .filter(models.Spending.user_id == user_id, models.Spending.place.isnot(None))
        .group_by(models.Spending.place)
        .all()
    )
    return group_spellings(rows)


def _canonical_place(db: Session, user_id: str, place: Optional[str]) -> Optional[str]:
    """Se já existe um local com a mesma chave, usa a grafia mais usada dele; senão fica como foi escrito."""
    key = text_key(place)
    return _place_groups(db, user_id).get(key, [place])[0] if key else place


@router.get("/places", response_model=List[str])
def list_places(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Locais já usados (para sugestões), dos mais frequentes para os menos, sem duplicados."""
    groups = _place_groups(db, current_user.id).values()
    ranked = sorted(groups, key=lambda g: (-g[1], -g[2].toordinal(), g[0]))
    return [name for name, _, _ in ranked[:50]]


@router.post("", response_model=schemas.SpendingOut)
def create_spending(data: schemas.SpendingIn, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    owned.get_category(db, data.category_id, current_user.id)
    sp = models.Spending(
        user_id=current_user.id, category_id=data.category_id, amount=data.amount,
        description=data.description or None,
        place=_canonical_place(db, current_user.id, data.place), date=data.date or date.today(),
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
    if fields.get("place") and fields["place"] != sp.place:
        fields["place"] = _canonical_place(db, current_user.id, fields["place"])
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
