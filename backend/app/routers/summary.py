from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import get_current_user
from ..periods import parse_month, month_start, add_months, month_key, is_active
from .. import models, schemas

router = APIRouter(prefix="/summary", tags=["summary"], dependencies=[Depends(get_current_user)])

HISTORY_MONTHS = 6


def _money(n) -> float:
    return round(float(n), 2)


@router.get("", response_model=schemas.SummaryOut)
def get_summary(month: Optional[str] = None, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    m = parse_month(month)

    # volumes pequenos por utilizador: carrega tudo e aplica a regra de atividade em Python
    incomes = db.query(models.IncomeEntry).filter(models.IncomeEntry.user_id == current_user.id).all()
    expenses = (
        db.query(models.Expense)
        .join(models.ExpenseCategory)
        .filter(models.ExpenseCategory.user_id == current_user.id)
        .all()
    )
    categories = (
        db.query(models.ExpenseCategory)
        .filter(models.ExpenseCategory.user_id == current_user.id)
        .order_by(models.ExpenseCategory.position)
        .all()
    )
    buckets = db.query(models.SavingsBucket).filter(models.SavingsBucket.user_id == current_user.id).all()

    def received(month_: date) -> float:
        return sum(float(i.amount) for i in incomes if is_active(i, month_))

    def spent(month_: date) -> float:
        return sum(e.amount for e in expenses if is_active(e, month_))

    recebido = received(m)
    gasto = spent(m)
    contribuicoes = sum(b.monthly_contribution or 0 for b in buckets)
    total_poupado = sum(b.current_amount or 0 for b in buckets)

    # saldo total: (recebido - gasto) de cada mês desde o primeiro registo até ao mês atual
    saldo_total = 0.0
    starts = [month_start(r.date) for r in (*incomes, *expenses)]
    if starts:
        current = month_start(date.today())
        cursor = min(starts)
        while cursor <= current:
            saldo_total += received(cursor) - spent(cursor)
            cursor = add_months(cursor, 1)

    por_categoria = []
    for c in categories:
        total = sum(e.amount for e in expenses if e.category_id == c.id and is_active(e, m))
        if total > 0:
            por_categoria.append(schemas.CategoryTotal(id=c.id, nome=c.name, icone=c.icon, total=_money(total)))

    historico = []
    for offset in range(HISTORY_MONTHS - 1, -1, -1):
        h = add_months(m, -offset)
        historico.append(schemas.MonthHistory(mes=month_key(h), recebido=_money(received(h)), gasto=_money(spent(h))))

    pronto_a_gastar = recebido - gasto - contribuicoes

    return schemas.SummaryOut(
        month=month_key(m),
        recebido=_money(recebido),
        gasto=_money(gasto),
        contribuicoes_mensais=_money(contribuicoes),
        pronto_a_gastar=_money(pronto_a_gastar),
        saldo_total=_money(saldo_total),
        total_poupado=_money(total_poupado),
        disponivel=_money(saldo_total - total_poupado),
        por_categoria=por_categoria,
        historico=historico,
        income=_money(recebido),
        total_expenses=_money(gasto),
        left_after_expenses=_money(recebido - gasto),
        total_monthly_contributions=_money(contribuicoes),
        left_to_spend=_money(pronto_a_gastar),
        total_saved=_money(total_poupado),
    )
