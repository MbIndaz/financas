from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import get_current_user
from ..periods import parse_month, month_key, in_month
from .. import envelopes, models, schemas

router = APIRouter(prefix="/history", tags=["history"], dependencies=[Depends(get_current_user)])

ZERO = envelopes.ZERO
ENVELOPE_NAMES = ("Despesas", "Objetivos", "Para gastar")


def _income_envelopes(entry: models.IncomeEntry) -> str:
    """Envelopes para onde foi o rendimento, pela ordem da repartição."""
    to_goals = sum((a.amount for a in entry.allocations), ZERO)
    parts = (entry.alloc_despesas, to_goals, entry.amount - entry.alloc_despesas - to_goals)
    return " · ".join(name for name, v in zip(ENVELOPE_NAMES, parts) if v > 0) or "Para gastar"


def _bucket_label(b: models.SavingsBucket) -> str:
    return f"{b.icon} {b.name}" if b.icon else b.name


@router.get("", response_model=schemas.HistoryOut)
def get_history(
    month: Optional[str] = None,
    type: schemas.HistoryType = "tudo",
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Todos os movimentos do mês (por defeito o atual) numa só lista, mais recentes primeiro.

    Os valores têm o sinal do envelope afetado (+ entra, − sai). Movimentos com data anterior ao
    saldo inicial vêm marcados como histórico (não afetam o saldo). q filtra por descrição, local
    ou categoria.
    """
    m = parse_month(month)
    uid = current_user.id
    settings = db.query(models.AccountSettings).filter(models.AccountSettings.user_id == uid).first()
    start = settings.opening_date if settings else None
    Inc, Alloc, Spend = models.IncomeEntry, models.IncomeAllocation, models.Spending
    Bucket, Mov = models.SavingsBucket, models.BucketMovement
    Pay, Exp, Cat = models.ExpensePayment, models.Expense, models.ExpenseCategory

    rows = []  # (created_at para desempatar, item)

    def add(created_at, **fields):
        rows.append((created_at, schemas.HistoryItem(historico=bool(start and fields["date"] < start), **fields)))

    if type in ("tudo", "receitas"):
        for e in db.query(Inc).filter(Inc.user_id == uid, in_month(Inc.date, m)):
            add(e.created_at, tipo="receitas", subtipo="rendimento", id=e.id,
                descricao=f"{e.source} · {e.description}" if e.description else e.source,
                date=e.date, amount=e.amount, envelope=_income_envelopes(e))

    if type in ("tudo", "despesas"):
        for p, exp, cat in (
            db.query(Pay, Exp, Cat).join(Exp, Exp.id == Pay.expense_id).join(Cat, Cat.id == Exp.category_id)
            .filter(Cat.user_id == uid, in_month(Pay.paid_date, m))
        ):
            add(p.created_at, tipo="despesas", subtipo="pagamento", id=p.id, descricao=exp.title,
                categoria=cat.name, icone=cat.icon, date=p.paid_date, amount=-p.amount, envelope="Despesas")

    if type in ("tudo", "gastos"):
        for sp, cat in (
            db.query(Spend, Cat).outerjoin(Cat, Cat.id == Spend.category_id)
            .filter(Spend.user_id == uid, in_month(Spend.date, m))
        ):
            add(sp.created_at, tipo="gastos", subtipo="gasto", id=sp.id,
                descricao=sp.description or sp.place or (cat.name if cat else "Gasto"), local=sp.place,
                categoria=cat.name if cat else "Sem categoria", icone=cat.icon if cat else "🏷️",
                date=sp.date, amount=-sp.amount, envelope="Para gastar")

    if type in ("tudo", "objetivos"):
        for mv, b in (
            db.query(Mov, Bucket).join(Bucket, Bucket.id == Mov.bucket_id)
            .filter(Bucket.user_id == uid, in_month(Mov.date, m))
        ):
            deposit = mv.amount > 0
            label = "Depósito" if deposit else "Levantamento"
            add(mv.created_at, tipo="objetivos", subtipo="deposito" if deposit else "levantamento", id=mv.id,
                descricao=f"{label} · {mv.note}" if mv.note else label, categoria=b.name, icone=b.icon,
                date=mv.date, amount=mv.amount, interno=True,
                envelope=f"Para gastar → {_bucket_label(b)}" if deposit else f"{_bucket_label(b)} → Para gastar")
        for a, e, b in (
            db.query(Alloc, Inc, Bucket).join(Inc, Inc.id == Alloc.income_entry_id).join(Bucket, Bucket.id == Alloc.bucket_id)
            .filter(Inc.user_id == uid, in_month(Inc.date, m))
        ):
            add(e.created_at, tipo="objetivos", subtipo="reparticao", id=e.id, descricao=f"Do rendimento «{e.source}»",
                categoria=b.name, icone=b.icon, date=e.date, amount=a.amount, interno=True,
                envelope=f"Rendimento → {_bucket_label(b)}")

    items = [item for _, item in sorted(rows, key=lambda r: (r[1].date, r[0] or datetime.min), reverse=True)]
    if q and q.strip():
        needle = q.strip().casefold()
        items = [
            i for i in items
            if any(needle in (v or "").casefold() for v in (i.descricao, i.local, i.categoria))
        ]
    # em "tudo" as passagens entre envelopes não são entradas nem saídas da conta
    counted = [i for i in items if not (type == "tudo" and i.interno)]
    return schemas.HistoryOut(
        month=month_key(m),
        type=type,
        items=items,
        entradas=round(sum(i.amount for i in counted if i.amount > 0), 2),
        saidas=round(-sum(i.amount for i in counted if i.amount < 0), 2),
    )
