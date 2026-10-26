from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import get_current_user
from ..periods import (
    parse_month, month_start, month_key, active_in_month, is_active, check_recurrence, split_recurring, end_recurring,
)
from .. import models, owned, schemas

router = APIRouter(tags=["expenses"], dependencies=[Depends(get_current_user)])


def _payment_out(p: models.ExpensePayment) -> schemas.PaymentOut:
    return schemas.PaymentOut(expense_id=p.expense_id, month=month_key(p.month), amount=p.amount, paid_date=p.paid_date)


def _expense_out(e: models.Expense, payment: Optional[models.ExpensePayment] = None) -> schemas.ExpenseOut:
    out = schemas.ExpenseOut.model_validate(e)
    out.payment = _payment_out(payment) if payment else None
    return out


def _check_payments_active(exp: models.Expense) -> None:
    """Cada pagamento tem de cair num mês em que a conta existe (ao editar datas ou recorrência)."""
    if any(not is_active(exp, p.month) for p in exp.payments):
        raise HTTPException(
            status_code=400,
            detail="Há pagamentos registados em meses em que esta conta deixaria de existir; desmarca-os primeiro",
        )


# ---------- Categories ----------
@router.get("/categories", response_model=List[schemas.CategoryOut])
def list_categories(month: Optional[str] = None, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Categorias com as contas ativas no mês pedido (por defeito o atual) e o pagamento desse mês."""
    m = parse_month(month)
    cats = (
        db.query(models.ExpenseCategory)
        .filter(models.ExpenseCategory.user_id == current_user.id)
        .order_by(models.ExpenseCategory.position)
        .all()
    )
    active = (
        db.query(models.Expense)
        .join(models.ExpenseCategory)
        .filter(models.ExpenseCategory.user_id == current_user.id, active_in_month(models.Expense, m))
        .order_by(models.Expense.date.desc(), models.Expense.created_at.desc())
        .all()
    )
    payments = {
        p.expense_id: p
        for p in db.query(models.ExpensePayment).filter(
            models.ExpensePayment.expense_id.in_([e.id for e in active]), models.ExpensePayment.month == m
        )
    } if active else {}
    by_cat = {}
    for e in active:
        by_cat.setdefault(e.category_id, []).append(_expense_out(e, payments.get(e.id)))
    return [
        schemas.CategoryOut(id=c.id, name=c.name, icon=c.icon, position=c.position, expenses=by_cat.get(c.id, []))
        for c in cats
    ]


@router.post("/categories", response_model=schemas.CategoryOut)
def create_category(data: schemas.CategoryCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    count = db.query(models.ExpenseCategory).filter(models.ExpenseCategory.user_id == current_user.id).count()
    cat = models.ExpenseCategory(user_id=current_user.id, name=data.name, icon=data.icon, position=count)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return schemas.CategoryOut(id=cat.id, name=cat.name, icon=cat.icon, position=cat.position)


@router.put("/categories/{category_id}", response_model=schemas.CategoryOut)
def update_category(category_id: str, data: schemas.CategoryUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    cat = owned.get_category(db, category_id, current_user.id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(cat, field, value)
    db.commit()
    db.refresh(cat)
    return schemas.CategoryOut(id=cat.id, name=cat.name, icon=cat.icon, position=cat.position)


@router.delete("/categories/{category_id}")
def delete_category(category_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Apaga a categoria com as suas contas e respetivos pagamentos; os gastos ficam sem categoria."""
    cat = owned.get_category(db, category_id, current_user.id)
    db.delete(cat)
    db.commit()
    return {"ok": True}


# ---------- Contas (despesas planeadas, dentro de uma categoria) ----------
@router.post("/categories/{category_id}/expenses", response_model=schemas.ExpenseOut)
def create_expense(category_id: str, data: schemas.ExpenseCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    owned.get_category(db, category_id, current_user.id)
    fields = data.model_dump(exclude={"paid_date"})
    exp = models.Expense(category_id=category_id, **fields)
    check_recurrence(exp)
    payment = None
    if data.paid_date is not None:
        # "já paga": o pagamento do primeiro mês da conta, pelo valor da conta
        payment = models.ExpensePayment(month=month_start(exp.date), amount=exp.amount, paid_date=data.paid_date)
        exp.payments.append(payment)
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return _expense_out(exp, payment)


@router.put("/expenses/{expense_id}", response_model=schemas.ExpenseOut)
def update_expense(expense_id: str, data: schemas.ExpenseUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    exp = owned.get_expense(db, expense_id, current_user.id)
    fields = data.model_dump(exclude_unset=True)
    for required in ("title", "amount"):
        if required in fields and fields[required] is None:
            raise HTTPException(status_code=422, detail="O título e o valor não podem ficar vazios")
    for field, value in fields.items():
        setattr(exp, field, value)
    check_recurrence(exp)
    _check_payments_active(exp)
    db.commit()
    db.refresh(exp)
    return _expense_out(exp)


@router.delete("/expenses/{expense_id}")
def delete_expense(expense_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Apaga a conta e os seus pagamentos (o dinheiro pago volta ao envelope Despesas)."""
    exp = owned.get_expense(db, expense_id, current_user.id)
    db.delete(exp)
    db.commit()
    return {"ok": True}


@router.post("/expenses/{expense_id}/change", response_model=schemas.ExpenseOut)
def change_expense(expense_id: str, data: schemas.ChangeRecurringIn, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Muda o valor de uma conta recorrente a partir de um mês, preservando o histórico."""
    exp = owned.get_expense(db, expense_id, current_user.id)
    split = split_recurring(exp, data.start_month)
    if split is None:
        exp.amount = data.amount
        result = exp
    else:
        start, end = split
        result = models.Expense(
            category_id=exp.category_id, title=exp.title, amount=data.amount,
            date=start, is_recurring=True, end_date=end,
        )
        db.add(result)
        # os pagamentos dos meses que passam para a conta nova acompanham-na
        for p in [p for p in exp.payments if p.month >= start]:
            exp.payments.remove(p)
            result.payments.append(p)
    db.commit()
    db.refresh(result)
    return _expense_out(result)


@router.post("/expenses/{expense_id}/end", response_model=schemas.ExpenseOut)
def end_expense(expense_id: str, data: schemas.EndRecurringIn, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    exp = owned.get_expense(db, expense_id, current_user.id)
    end_recurring(exp, data.end_month)
    _check_payments_active(exp)
    db.commit()
    db.refresh(exp)
    return _expense_out(exp)


# ---------- Pagamentos (estado por mês) ----------
@router.put("/expenses/{expense_id}/payments/{month}", response_model=schemas.PaymentOut)
def pay_expense(expense_id: str, month: str, data: schemas.PaymentIn, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Marca a conta como paga nesse mês (ou corrige o pagamento): sai do envelope Despesas."""
    exp = owned.get_expense(db, expense_id, current_user.id)
    m = parse_month(month)
    if not is_active(exp, m):
        raise HTTPException(status_code=400, detail="Esta conta não existe nesse mês")
    payment = next((p for p in exp.payments if p.month == m), None)
    if payment is None:
        payment = models.ExpensePayment(month=m, amount=data.amount or exp.amount, paid_date=data.paid_date or date.today())
        exp.payments.append(payment)
    else:
        if data.amount is not None:
            payment.amount = data.amount
        if data.paid_date is not None:
            payment.paid_date = data.paid_date
    db.commit()
    db.refresh(payment)
    return _payment_out(payment)


@router.delete("/expenses/{expense_id}/payments/{month}")
def unpay_expense(expense_id: str, month: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Desmarca: a conta volta a estar por pagar e o dinheiro volta ao envelope Despesas."""
    exp = owned.get_expense(db, expense_id, current_user.id)
    m = parse_month(month)
    payment = next((p for p in exp.payments if p.month == m), None)
    if payment is None:
        raise HTTPException(status_code=404, detail="Esta conta não está paga nesse mês")
    exp.payments.remove(payment)
    db.commit()
    return {"ok": True}
