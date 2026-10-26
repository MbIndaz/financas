from datetime import date, datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import get_current_user
from .. import envelopes, models, owned, schemas

router = APIRouter(prefix="/buckets", tags=["buckets"], dependencies=[Depends(get_current_user)])
movements_router = APIRouter(prefix="/bucket-movements", tags=["buckets"], dependencies=[Depends(get_current_user)])


def _bucket_out(b: models.SavingsBucket, balance) -> schemas.BucketOut:
    return schemas.BucketOut(
        id=b.id, name=b.name, icon=b.icon, kind=b.kind, opening_amount=b.opening_amount,
        target_amount=b.target_amount, monthly_contribution=b.monthly_contribution,
        is_mandatory=bool(b.is_mandatory), position=b.position or 0,
        current_amount=balance, archived=b.archived_at is not None,
    )


def _movement_out(mv: models.BucketMovement) -> schemas.BucketMovementOut:
    return schemas.BucketMovementOut(
        id=mv.id, bucket_id=mv.bucket_id, kind="deposito" if mv.amount > 0 else "levantamento",
        amount=abs(mv.amount), date=mv.date, note=mv.note,
    )


def _get_owned_movement(db: Session, movement_id: str, user_id: str) -> models.BucketMovement:
    mv = (
        db.query(models.BucketMovement)
        .join(models.SavingsBucket)
        .filter(models.BucketMovement.id == movement_id, models.SavingsBucket.user_id == user_id)
        .first()
    )
    if not mv:
        raise HTTPException(status_code=404, detail="Movimento não encontrado")
    return mv


def _require_active(bucket: models.SavingsBucket) -> None:
    if bucket.archived_at is not None:
        raise HTTPException(status_code=400, detail="Este objetivo foi apagado")


@router.get("", response_model=List[schemas.BucketOut])
def list_buckets(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Objetivos com o saldo de hoje; os apagados só aparecem se ainda tiverem saldo."""
    balances = envelopes.compute(db, current_user.id).buckets
    buckets = (
        db.query(models.SavingsBucket)
        .filter(models.SavingsBucket.user_id == current_user.id)
        .order_by(models.SavingsBucket.position)
        .all()
    )
    return [
        _bucket_out(b, balances.get(b.id, envelopes.ZERO))
        for b in buckets
        if b.archived_at is None or balances.get(b.id, envelopes.ZERO) != 0
    ]


@router.post("", response_model=schemas.BucketOut)
def create_bucket(data: schemas.BucketCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    count = db.query(models.SavingsBucket).filter(models.SavingsBucket.user_id == current_user.id).count()
    bucket = models.SavingsBucket(user_id=current_user.id, position=count, **data.model_dump())
    db.add(bucket)
    db.commit()
    db.refresh(bucket)
    return _bucket_out(bucket, envelopes.compute(db, current_user.id).buckets.get(bucket.id, envelopes.ZERO))


@router.put("/{bucket_id}", response_model=schemas.BucketOut)
def update_bucket(bucket_id: str, data: schemas.BucketUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    bucket = owned.get_bucket(db, bucket_id, current_user.id)
    _require_active(bucket)
    fields = data.model_dump(exclude_unset=True)
    for required in ("name", "opening_amount", "monthly_contribution"):
        if required in fields and fields[required] is None:
            raise HTTPException(status_code=422, detail="Nome, já guardado e contribuição não podem ficar vazios")
    for field, value in fields.items():
        setattr(bucket, field, value)
    db.commit()
    db.refresh(bucket)
    return _bucket_out(bucket, envelopes.compute(db, current_user.id).buckets.get(bucket.id, envelopes.ZERO))


@router.delete("/{bucket_id}")
def delete_bucket(bucket_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Sem histórico, apaga mesmo. Com histórico, devolve o saldo ao Para gastar com um levantamento
    (dinheiro nunca aparece nem desaparece) e arquiva o objetivo, mantendo os movimentos. Num objetivo
    já apagado que voltou a ter saldo, volta a devolvê-lo."""
    bucket = owned.get_bucket(db, bucket_id, current_user.id)
    today = date.today()
    movements = bucket.movements
    allocations = (
        db.query(models.IncomeAllocation, models.IncomeEntry.date)
        .join(models.IncomeEntry, models.IncomeEntry.id == models.IncomeAllocation.income_entry_id)
        .filter(models.IncomeAllocation.bucket_id == bucket.id)
        .all()
    )
    if bucket.archived_at is None and not movements and not allocations and not bucket.opening_amount:
        db.delete(bucket)
        db.commit()
        return {"ok": True, "archived": False, "devolvido": 0.0}
    if any(m.date > today for m in movements) or any(d > today for _, d in allocations):
        raise HTTPException(status_code=400, detail="Este objetivo tem movimentos com data futura; apaga-os ou muda-lhes a data primeiro")
    balance = envelopes.compute(db, current_user.id, today).buckets.get(bucket.id, envelopes.ZERO)
    if balance != 0:
        db.add(models.BucketMovement(bucket_id=bucket.id, amount=-balance, date=today,
                                     note="Objetivo apagado: saldo devolvido ao Para gastar"))
    if bucket.archived_at is None:
        bucket.archived_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "archived": True, "devolvido": float(balance)}


# ---------- Depósitos e levantamentos ----------
@router.get("/{bucket_id}/movements", response_model=List[schemas.BucketMovementOut])
def list_movements(bucket_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Histórico do objetivo: depósitos, levantamentos e partes de rendimentos, mais recentes primeiro."""
    bucket = owned.get_bucket(db, bucket_id, current_user.id)
    items = [_movement_out(mv) for mv in bucket.movements]
    allocations = (
        db.query(models.IncomeAllocation, models.IncomeEntry)
        .join(models.IncomeEntry, models.IncomeEntry.id == models.IncomeAllocation.income_entry_id)
        .filter(models.IncomeAllocation.bucket_id == bucket.id)
        .all()
    )
    items += [
        schemas.BucketMovementOut(bucket_id=bucket.id, kind="rendimento", amount=a.amount, date=inc.date,
                                  note=inc.source, income_entry_id=inc.id)
        for a, inc in allocations
    ]
    return sorted(items, key=lambda i: i.date, reverse=True)


@router.post("/{bucket_id}/movements", response_model=schemas.BucketMovementOut)
def create_movement(bucket_id: str, data: schemas.BucketMovementIn, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Depositar tira do Para gastar; levantar devolve ao Para gastar."""
    bucket = owned.get_bucket(db, bucket_id, current_user.id)
    _require_active(bucket)
    mv = models.BucketMovement(
        bucket_id=bucket.id, amount=data.amount if data.kind == "deposito" else -data.amount,
        date=data.date or date.today(), note=data.note or None,
    )
    db.add(mv)
    db.commit()
    db.refresh(mv)
    return _movement_out(mv)


@movements_router.put("/{movement_id}", response_model=schemas.BucketMovementOut)
def update_movement(movement_id: str, data: schemas.BucketMovementUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    mv = _get_owned_movement(db, movement_id, current_user.id)
    _require_active(mv.bucket)
    fields = data.model_dump(exclude_unset=True)
    if any(fields.get(f, True) is None for f in ("kind", "amount", "date")):
        raise HTTPException(status_code=422, detail="Tipo, valor e data não podem ficar vazios")
    kind = fields.get("kind", "deposito" if mv.amount > 0 else "levantamento")
    amount = fields.get("amount", abs(mv.amount))
    mv.amount = amount if kind == "deposito" else -amount
    if "date" in fields:
        mv.date = fields["date"]
    if "note" in fields:
        mv.note = fields["note"] or None
    db.commit()
    db.refresh(mv)
    return _movement_out(mv)


@movements_router.delete("/{movement_id}")
def delete_movement(movement_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    mv = _get_owned_movement(db, movement_id, current_user.id)
    _require_active(mv.bucket)
    db.delete(mv)
    db.commit()
    return {"ok": True}
