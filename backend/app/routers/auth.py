import secrets

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..auth import verify_password, hash_password, create_access_token, get_current_user
from .. import models, schemas

router = APIRouter(tags=["auth"])


@router.post("/auth/register", response_model=schemas.TokenOut)
def register(data: schemas.RegisterIn, db: Session = Depends(get_db)):
    # o convite é válido se for o código mestre definido no .env,
    # ou um InviteCode ainda não usado gerado por outro utilizador
    invite = None
    if data.invite_code != settings.admin_invite_code:
        invite = (
            db.query(models.InviteCode)
            .filter(models.InviteCode.code == data.invite_code, models.InviteCode.used_by.is_(None))
            .first()
        )
        if not invite:
            raise HTTPException(status_code=400, detail="Código de convite inválido ou já usado")

    if db.query(models.User).filter(models.User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Já existe uma conta com este email")
    if db.query(models.User).filter(models.User.username == data.username).first():
        raise HTTPException(status_code=400, detail="Esse nome de utilizador já está em uso")

    user = models.User(
        email=data.email,
        username=data.username,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    db.flush()

    if invite:
        invite.used_by = user.id
        from datetime import datetime
        invite.used_at = datetime.utcnow()

    db.commit()

    token = create_access_token(subject=user.id)
    return schemas.TokenOut(access_token=token)


@router.post("/auth/login", response_model=schemas.TokenOut)
def login(data: schemas.LoginIn, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == data.username).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    token = create_access_token(subject=user.id)
    return schemas.TokenOut(access_token=token)


@router.get("/auth/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.post("/auth/invites", response_model=schemas.InviteOut)
def create_invite(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Qualquer utilizador autenticado pode gerar um código para convidar outra pessoa."""
    code = secrets.token_urlsafe(6)
    invite = models.InviteCode(code=code, created_by=current_user.id)
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return schemas.InviteOut(code=invite.code, created_at=invite.created_at, used_by=invite.used_by)


@router.get("/auth/invites", response_model=list[schemas.InviteOut])
def list_my_invites(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    invites = db.query(models.InviteCode).filter(models.InviteCode.created_by == current_user.id).all()
    return [schemas.InviteOut(code=i.code, created_at=i.created_at, used_by=i.used_by) for i in invites]
