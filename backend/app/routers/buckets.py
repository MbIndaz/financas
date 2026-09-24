from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import get_current_user
from .. import models, schemas

router = APIRouter(prefix="/buckets", tags=["buckets"], dependencies=[Depends(get_current_user)])


def _get_owned_bucket(db: Session, bucket_id: str, user_id: str) -> models.SavingsBucket:
    b = (
        db.query(models.SavingsBucket)
        .filter(models.SavingsBucket.id == bucket_id, models.SavingsBucket.user_id == user_id)
        .first()
    )
    if not b:
        raise HTTPException(status_code=404, detail="Objetivo não encontrado")
    return b


@router.get("", response_model=List[schemas.BucketOut])
def list_buckets(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return (
        db.query(models.SavingsBucket)
        .filter(models.SavingsBucket.user_id == current_user.id)
        .order_by(models.SavingsBucket.position)
        .all()
    )


@router.post("", response_model=schemas.BucketOut)
def create_bucket(data: schemas.BucketCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    count = db.query(models.SavingsBucket).filter(models.SavingsBucket.user_id == current_user.id).count()
    bucket = models.SavingsBucket(user_id=current_user.id, position=count, **data.model_dump())
    db.add(bucket)
    db.commit()
    db.refresh(bucket)
    return bucket


@router.put("/{bucket_id}", response_model=schemas.BucketOut)
def update_bucket(bucket_id: str, data: schemas.BucketUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    bucket = _get_owned_bucket(db, bucket_id, current_user.id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(bucket, field, value)
    db.commit()
    db.refresh(bucket)
    return bucket


@router.delete("/{bucket_id}")
def delete_bucket(bucket_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    bucket = _get_owned_bucket(db, bucket_id, current_user.id)
    db.delete(bucket)
    db.commit()
    return {"ok": True}
