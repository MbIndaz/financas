"""Saldos dos envelopes (Despesas, Objetivos, Para gastar), sempre derivados dos movimentos.

Nenhum saldo é guardado: cada euro que entra ou sai está registado uma única vez (rendimento
com a sua repartição, gasto do dia a dia, pagamento de conta, depósito/levantamento de um
objetivo) e os saldos são somas desses registos. Editar ou apagar um movimento, mudar o saldo
inicial ou a passagem do tempo (movimentos com data futura) refletem-se sozinhos, sem nada
para manter sincronizado.

Só contam movimentos com data entre opening_date e hoje; os anteriores são histórico.

    Para gastar = saldo inicial + (rendimentos − parte para Despesas − partes para objetivos)
                  − gastos − depósitos + levantamentos
    Despesas    = partes para Despesas − pagamentos de contas (pela data de pagamento)
    Objetivo    = já guardado no saldo inicial + partes de rendimentos + depósitos − levantamentos
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from . import models

ZERO = Decimal("0.00")


@dataclass
class Envelopes:
    despesas: Decimal
    objetivos: Decimal
    para_gastar: Decimal
    buckets: dict  # bucket_id -> saldo do objetivo (inclui os arquivados)
    opening_balance: Optional[Decimal]
    opening_date: Optional[date]

    @property
    def saldo_total(self) -> Decimal:
        return self.despesas + self.objetivos + self.para_gastar


def counted(column, start: Optional[date], today: date):
    """Filtro SQL dos movimentos que mexem nos envelopes: data entre o saldo inicial (se houver) e hoje."""
    return and_(column >= start, column <= today) if start else column <= today


def compute(db: Session, user_id: str, today: Optional[date] = None) -> Envelopes:
    today = today or date.today()
    settings = db.query(models.AccountSettings).filter(models.AccountSettings.user_id == user_id).first()
    start = settings.opening_date if settings else None
    opening = settings.opening_balance if settings else ZERO

    Inc, Alloc = models.IncomeEntry, models.IncomeAllocation
    Bucket, Mov = models.SavingsBucket, models.BucketMovement
    Pay, Exp, Cat = models.ExpensePayment, models.Expense, models.ExpenseCategory
    Spend = models.Spending

    received, for_bills = (
        db.query(func.coalesce(func.sum(Inc.amount), ZERO), func.coalesce(func.sum(Inc.alloc_despesas), ZERO))
        .filter(Inc.user_id == user_id, counted(Inc.date, start, today))
        .one()
    )
    allocated = dict(
        db.query(Alloc.bucket_id, func.sum(Alloc.amount))
        .join(Inc, Inc.id == Alloc.income_entry_id)
        .filter(Inc.user_id == user_id, counted(Inc.date, start, today))
        .group_by(Alloc.bucket_id)
        .all()
    )
    moved = dict(
        db.query(Mov.bucket_id, func.sum(Mov.amount))
        .join(Bucket, Bucket.id == Mov.bucket_id)
        .filter(Bucket.user_id == user_id, counted(Mov.date, start, today))
        .group_by(Mov.bucket_id)
        .all()
    )
    spent = (
        db.query(func.coalesce(func.sum(Spend.amount), ZERO))
        .filter(Spend.user_id == user_id, counted(Spend.date, start, today))
        .scalar()
    )
    paid = (
        db.query(func.coalesce(func.sum(Pay.amount), ZERO))
        .join(Exp, Exp.id == Pay.expense_id)
        .join(Cat, Cat.id == Exp.category_id)
        .filter(Cat.user_id == user_id, counted(Pay.paid_date, start, today))
        .scalar()
    )
    openings = db.query(Bucket.id, Bucket.opening_amount).filter(Bucket.user_id == user_id).all()

    buckets = {bid: (op or ZERO) + allocated.get(bid, ZERO) + moved.get(bid, ZERO) for bid, op in openings}
    para_gastar = (
        opening + received - for_bills - sum(allocated.values(), ZERO) - spent - sum(moved.values(), ZERO)
    )
    return Envelopes(
        despesas=for_bills - paid,
        objetivos=sum(buckets.values(), ZERO),
        para_gastar=para_gastar,
        buckets=buckets,
        opening_balance=settings.opening_balance if settings else None,
        opening_date=start,
    )
