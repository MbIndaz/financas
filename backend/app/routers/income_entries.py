from datetime import date
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..auth import get_current_user
from ..periods import parse_month, in_month
from .. import models, owned, schemas

router = APIRouter(prefix="/income-entries", tags=["income"], dependencies=[Depends(get_current_user)])


def _get_owned_entry(db: Session, entry_id: str, user_id: str) -> models.IncomeEntry:
    entry = (
        db.query(models.IncomeEntry)
        .filter(models.IncomeEntry.id == entry_id, models.IncomeEntry.user_id == user_id)
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Rendimento não encontrado")
    return entry


def _to_out(entry: models.IncomeEntry) -> schemas.IncomeEntryOut:
    allocations = sorted(entry.allocations, key=lambda a: (a.bucket.position or 0, a.bucket.name))
    return schemas.IncomeEntryOut(
        id=entry.id, amount=entry.amount, source=entry.source, description=entry.description, date=entry.date,
        despesas=entry.alloc_despesas,
        objetivos=[
            schemas.AllocationOut(bucket_id=a.bucket_id, nome=a.bucket.name, icone=a.bucket.icon, amount=a.amount,
                                  archived=a.bucket.archived_at is not None)
            for a in allocations
        ],
        para_gastar=entry.amount - entry.alloc_despesas - sum((a.amount for a in entry.allocations), Decimal(0)),
    )


def _apply(db: Session, entry: models.IncomeEntry, data: schemas.IncomeEntryIn, user_id: str) -> None:
    """Aplica valores e repartição. Os saldos são derivados, por isso substituir a repartição
    reverte a anterior e aplica a nova de uma vez (na mesma transação)."""
    wanted = {}
    for line in data.objetivos:
        bucket = owned.get_bucket(db, line.bucket_id, user_id)
        if bucket.archived_at is not None:
            raise HTTPException(status_code=400, detail=f"O objetivo «{bucket.name}» foi apagado")
        if line.bucket_id in wanted:
            raise HTTPException(status_code=400, detail="Há um objetivo repetido na repartição")
        wanted[line.bucket_id] = line.amount
    # repartições para objetivos entretanto apagados mantêm-se tal como estão
    kept = [a for a in entry.allocations if a.bucket is not None and a.bucket.archived_at is not None]
    total = data.despesas + sum(wanted.values(), Decimal(0)) + sum((a.amount for a in kept), Decimal(0))
    if total > data.amount:
        raise HTTPException(status_code=400, detail="A repartição (despesas + objetivos) ultrapassa o valor recebido")

    entry.amount = data.amount
    entry.source = data.source
    entry.description = data.description or None
    entry.date = data.date or date.today()
    entry.alloc_despesas = data.despesas
    current = {a.bucket_id: a for a in entry.allocations if a not in kept}
    for bucket_id, alloc in current.items():
        if wanted.get(bucket_id, 0) > 0:
            alloc.amount = wanted[bucket_id]
        else:
            entry.allocations.remove(alloc)
    for bucket_id, amount in wanted.items():
        if amount > 0 and bucket_id not in current:
            entry.allocations.append(models.IncomeAllocation(bucket_id=bucket_id, amount=amount))


@router.get("", response_model=List[schemas.IncomeEntryOut])
def list_entries(month: Optional[str] = None, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Rendimentos com data no mês pedido (por defeito o atual), mais recentes primeiro."""
    m = parse_month(month)
    entries = (
        db.query(models.IncomeEntry)
        .options(selectinload(models.IncomeEntry.allocations).selectinload(models.IncomeAllocation.bucket))
        .filter(models.IncomeEntry.user_id == current_user.id, in_month(models.IncomeEntry.date, m))
        .order_by(models.IncomeEntry.date.desc(), models.IncomeEntry.created_at.desc())
        .all()
    )
    return [_to_out(e) for e in entries]


@router.post("", response_model=schemas.IncomeEntryOut)
def create_entry(data: schemas.IncomeEntryIn, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    entry = models.IncomeEntry(user_id=current_user.id)
    _apply(db, entry, data, current_user.id)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return _to_out(entry)


@router.put("/{entry_id}", response_model=schemas.IncomeEntryOut)
def update_entry(entry_id: str, data: schemas.IncomeEntryIn, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    entry = _get_owned_entry(db, entry_id, current_user.id)
    _apply(db, entry, data, current_user.id)
    db.commit()
    db.refresh(entry)
    return _to_out(entry)


@router.delete("/{entry_id}")
def delete_entry(entry_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Apagar o rendimento apaga também a sua repartição (os envelopes revertem sozinhos)."""
    entry = _get_owned_entry(db, entry_id, current_user.id)
    db.delete(entry)
    db.commit()
    return {"ok": True}
