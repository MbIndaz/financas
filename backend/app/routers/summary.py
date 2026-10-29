from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import Date, cast, func
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import get_current_user
from ..periods import parse_month, add_months, month_key, month_end, active_in_month, in_month
from .. import envelopes, models, schemas
from ..textnorm import group_spellings, text_key

router = APIRouter(prefix="/summary", tags=["summary"], dependencies=[Depends(get_current_user)])

HISTORY_MONTHS = 6
TOP_PLACES = 5
ZERO = envelopes.ZERO


def _by_month(db: Session, date_col, amount_col, *filters, joins=()) -> dict:
    """Soma por mês (primeiro dia do mês -> total) para os filtros dados."""
    month_col = cast(func.date_trunc("month", date_col), Date)
    q = db.query(month_col, func.sum(amount_col))
    for target, on in joins:
        q = q.join(target, on)
    return dict(q.filter(*filters).group_by(month_col).all())


@router.get("", response_model=schemas.SummaryOut)
def get_summary(month: Optional[str] = None, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    m = parse_month(month)
    uid = current_user.id
    Inc, Spend = models.IncomeEntry, models.Spending
    Pay, Exp, Cat = models.ExpensePayment, models.Expense, models.ExpenseCategory

    # estatísticas do mês e dos 6 meses até ele: contam todos os movimentos (também os anteriores ao saldo inicial)
    first = add_months(m, -(HISTORY_MONTHS - 1))
    window = lambda col: [col >= first, col < add_months(m, 1)]
    received = _by_month(db, Inc.date, Inc.amount, Inc.user_id == uid, *window(Inc.date))
    spent = _by_month(db, Spend.date, Spend.amount, Spend.user_id == uid, *window(Spend.date))
    paid = _by_month(
        db, Pay.paid_date, Pay.amount, Cat.user_id == uid, *window(Pay.paid_date),
        joins=((Exp, Exp.id == Pay.expense_id), (Cat, Cat.id == Exp.category_id)),
    )

    # por categoria no mês: contas pagas (pela data de pagamento) + gastos do dia a dia
    totals: dict = {}
    paid_by_cat = (
        db.query(Exp.category_id, func.sum(Pay.amount))
        .join(Exp, Exp.id == Pay.expense_id)
        .join(Cat, Cat.id == Exp.category_id)
        .filter(Cat.user_id == uid, in_month(Pay.paid_date, m))
        .group_by(Exp.category_id)
    )
    spent_by_cat = (
        db.query(Spend.category_id, func.sum(Spend.amount))
        .filter(Spend.user_id == uid, in_month(Spend.date, m))
        .group_by(Spend.category_id)
    )
    for cat_id, total in [*paid_by_cat, *spent_by_cat]:
        totals[cat_id] = totals.get(cat_id, ZERO) + total
    categories = db.query(Cat).filter(Cat.user_id == uid).order_by(Cat.position).all()
    por_categoria = [
        schemas.CategoryTotal(id=c.id, nome=c.name, icone=c.icon, total=totals[c.id])
        for c in categories if totals.get(c.id, ZERO) > 0
    ]
    if totals.get(None, ZERO) > 0:
        por_categoria.append(schemas.CategoryTotal(id=None, nome="Sem categoria", icone="🏷️", total=totals[None]))

    # contas planeadas no mês e as que ainda não têm pagamento desse mês
    bills = db.query(Exp).join(Cat).filter(Cat.user_id == uid, active_in_month(Exp, m)).all()
    paid_bills = {
        expense_id for (expense_id,) in
        db.query(Pay.expense_id).filter(Pay.expense_id.in_([b.id for b in bills]), Pay.month == m)
    } if bills else set()
    planeado = sum((b.amount for b in bills), ZERO)
    por_pagar = sum((b.amount for b in bills if b.id not in paid_bills), ZERO)

    historico = []
    for offset in range(HISTORY_MONTHS - 1, -1, -1):
        h = add_months(m, -offset)
        historico.append(schemas.MonthHistory(
            mes=month_key(h), recebido=received.get(h, ZERO), saidas=paid.get(h, ZERO) + spent.get(h, ZERO),
        ))

    # Para gastar no fim de cada dia do mês, até hoje (meses futuros ficam vazios)
    today = date.today()
    last = min(month_end(m), today)
    evolucao = [
        schemas.DayBalance(dia=d, saldo=v)
        for d, v in (envelopes.para_gastar_by_day(db, uid, m, last) if m <= last else [])
    ]

    # onde se gastou mais: gastos do dia a dia por local; os sem local juntam-se pela categoria
    places: dict = {}  # (por categoria?, chave do local ou id da categoria) -> [nome, ícone, total]
    spellings = []  # (grafia, usos, data mais recente) dos gastos com local
    for place, cat_id, cat_name, cat_icon, total, uses, last in (
        db.query(Spend.place, Cat.id, Cat.name, Cat.icon, func.sum(Spend.amount), func.count(Spend.id), func.max(Spend.date))
        .outerjoin(Cat, Cat.id == Spend.category_id)
        .filter(Spend.user_id == uid, in_month(Spend.date, m))
        .group_by(Spend.place, Cat.id, Cat.name, Cat.icon)
    ):
        if text_key(place):
            spellings.append((place, uses, last))
            entry = places.setdefault((False, text_key(place)), [None, None, ZERO])
        else:
            entry = places.setdefault((True, cat_id), [cat_name or "Sem categoria", cat_icon if cat_id else "🏷️", ZERO])
        entry[2] += total
    names = group_spellings(spellings)
    for (by_cat, key), entry in places.items():
        if not by_cat:
            entry[0] = names[key][0]
    top = sorted(places.items(), key=lambda kv: (-kv[1][2], kv[1][0]))[:TOP_PLACES]
    top_locais = [
        schemas.PlaceTotal(nome=name, total=total, por_categoria=by_cat, icone=icon)
        for (by_cat, _), (name, icon, total) in top
    ]

    env = envelopes.compute(db, uid)
    return schemas.SummaryOut(
        month=month_key(m),
        recebido=received.get(m, ZERO),
        pago_contas=paid.get(m, ZERO),
        gasto_dia_a_dia=spent.get(m, ZERO),
        planeado=planeado,
        por_pagar=por_pagar,
        por_categoria=por_categoria,
        historico=historico,
        saldo_total=env.saldo_total,
        envelopes=schemas.EnvelopesOut(despesas=env.despesas, objetivos=env.objetivos, para_gastar=env.para_gastar),
        opening_balance=env.opening_balance,
        opening_date=env.opening_date,
        opening_defined=env.opening_date is not None,
        evolucao_para_gastar=evolucao,
        top_locais=top_locais,
    )
