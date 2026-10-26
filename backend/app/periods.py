"""Regras de meses e recorrência partilhadas por receitas (IncomeEntry) e despesas (Expense).

Um registo não recorrente conta só no mês da sua data. Um recorrente conta em todos os
meses desde o mês da sua data até ao mês do end_date (inclusive), ou sem fim se for nulo.

Data de ocorrência (usada no saldo real): a própria date nos não recorrentes; nos
recorrentes, em cada mês ativo, o dia do mês da date de início (ou o último dia do mês,
se o mês for mais curto).
"""
import calendar
import re
from datetime import date, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import and_, or_

_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")


def month_start(d: date) -> date:
    return d.replace(day=1)


def month_end(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def add_months(m: date, n: int) -> date:
    idx = m.year * 12 + (m.month - 1) + n
    return date(idx // 12, idx % 12 + 1, 1)


def parse_month(value: Optional[str]) -> date:
    """'YYYY-MM' -> primeiro dia desse mês; None -> mês atual."""
    if not value:
        return month_start(date.today())
    match = _MONTH_RE.match(value)
    if not match or not 1 <= int(match.group(2)) <= 12:
        raise HTTPException(status_code=422, detail="Mês inválido, usa o formato AAAA-MM")
    return date(int(match.group(1)), int(match.group(2)), 1)


def _month_index(d: date) -> int:
    return d.year * 12 + (d.month - 1)


def occurrence_in_month(entry, m: date) -> date:
    """Data de ocorrência de um recorrente no mês m (dia da data de início, limitado ao fim do mês)."""
    return m.replace(day=min(entry.date.day, calendar.monthrange(m.year, m.month)[1]))


def count_occurrences(entry, start: date, end: date) -> int:
    """Quantas ocorrências do registo caem em [start, end] (inclusive). O(1) por registo."""
    if start > end:
        return 0
    if not entry.is_recurring:
        return 1 if start <= entry.date <= end else 0
    lo = max(_month_index(entry.date), _month_index(start))
    hi = _month_index(end)
    if entry.end_date is not None:
        hi = min(hi, _month_index(entry.end_date))
    if lo > hi:
        return 0
    # só o primeiro e o último mês do intervalo podem ter a ocorrência fora de [start, end]
    first_ok = occurrence_in_month(entry, date(lo // 12, lo % 12 + 1, 1)) >= start
    last_ok = occurrence_in_month(entry, date(hi // 12, hi % 12 + 1, 1)) <= end
    if lo == hi:
        return 1 if first_ok and last_ok else 0
    return (hi - lo + 1) - (not first_ok) - (not last_ok)


def month_key(m: date) -> str:
    return f"{m.year:04d}-{m.month:02d}"


def active_in_month(model, m: date):
    """Filtro SQL equivalente a is_active() para um modelo com date/is_recurring/end_date."""
    nxt = add_months(m, 1)
    return or_(
        and_(model.is_recurring.is_(False), model.date >= m, model.date < nxt),
        and_(
            model.is_recurring.is_(True),
            model.date < nxt,
            or_(model.end_date.is_(None), model.end_date >= m),
        ),
    )


def is_active(entry, m: date) -> bool:
    start = month_start(entry.date)
    if not entry.is_recurring:
        return start == m
    return start <= m and (entry.end_date is None or month_start(entry.end_date) >= m)


def check_recurrence(entry) -> None:
    """Normaliza e valida date/is_recurring/end_date depois de criar ou editar."""
    if entry.date is None:
        entry.date = date.today()
    if not entry.is_recurring:
        entry.end_date = None
    elif entry.end_date is not None and month_start(entry.end_date) < month_start(entry.date):
        raise HTTPException(status_code=400, detail="O fim não pode ser anterior ao mês de início")


def require_recurring(entry) -> None:
    if not entry.is_recurring:
        raise HTTPException(status_code=400, detail="Só é possível em registos recorrentes")


def split_recurring(entry, start_month: str) -> Optional[tuple[date, Optional[date]]]:
    """Prepara a alteração de um recorrente a partir de start_month.

    Devolve (início, fim) do novo registo, em que o fim é o end_date original, ou None
    quando o mês é o próprio mês de início (não há histórico a preservar e basta alterar
    o valor no registo existente). Quando devolve o par, fecha o registo antigo no mês anterior.
    """
    require_recurring(entry)
    new_start = parse_month(start_month)
    old_start = month_start(entry.date)
    if new_start < old_start:
        raise HTTPException(status_code=400, detail="O novo valor não pode começar antes do registo original")
    if entry.end_date is not None and new_start > month_start(entry.end_date):
        raise HTTPException(status_code=400, detail="Este registo já terminou antes desse mês")
    if new_start == old_start:
        return None
    old_end = entry.end_date
    entry.end_date = new_start - timedelta(days=1)
    return new_start, old_end


def end_recurring(entry, end_month: str) -> None:
    require_recurring(entry)
    last = parse_month(end_month)
    if last < month_start(entry.date):
        raise HTTPException(status_code=400, detail="O fim não pode ser anterior ao mês de início")
    entry.end_date = month_end(last)
