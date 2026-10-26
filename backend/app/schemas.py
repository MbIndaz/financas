from datetime import date as Date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Optional, List

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# os campos chamam-se "date", por isso o tipo usa o alias Date para não ser sombreado
# Dinheiro à entrada: Decimal com 2 casas e no máximo 10 dígitos inteiros (Numeric(12, 2)); à saída: float.
Money = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
MoneyOrZero = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
SignedMoney = Annotated[Decimal, Field(max_digits=12, decimal_places=2)]


# ---------- Auth ----------
class RegisterIn(BaseModel):
    email: EmailStr
    username: str
    password: str
    invite_code: str

    @field_validator("password")
    @classmethod
    def password_min_len(cls, v):
        if len(v) < 8:
            raise ValueError("A password deve ter pelo menos 8 caracteres.")
        return v


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    username: str


class InviteOut(BaseModel):
    code: str
    created_at: datetime
    used_by: Optional[str] = None


# ---------- Recorrência das contas ----------
class ChangeRecurringIn(BaseModel):
    amount: Money
    start_month: str  # "AAAA-MM": primeiro mês em que vale o novo valor


class EndRecurringIn(BaseModel):
    end_month: str  # "AAAA-MM": último mês em que ainda vale


# ---------- Conta (saldo inicial) ----------
class AccountIn(BaseModel):
    opening_balance: SignedMoney  # dinheiro livre (Para gastar) no início de opening_date
    opening_date: Date


class AccountOut(BaseModel):
    opening_balance: Optional[float] = None
    opening_date: Optional[Date] = None


# ---------- Rendimentos (com repartição) ----------
class AllocationIn(BaseModel):
    bucket_id: str
    amount: MoneyOrZero  # 0 = não deposita nada nesse objetivo


class AllocationOut(BaseModel):
    bucket_id: str
    nome: str
    icone: Optional[str] = None
    amount: float
    archived: bool = False  # objetivo apagado: a linha mantém-se mas já não se altera


class IncomeEntryIn(BaseModel):
    amount: Money
    source: str = Field(min_length=1, max_length=60)
    description: Optional[str] = None
    date: Optional[Date] = None  # por defeito hoje
    despesas: MoneyOrZero = Decimal("0")
    objetivos: List[AllocationIn] = []
    # o resto (amount − despesas − objetivos) vai para Para gastar


class IncomeEntryOut(BaseModel):
    id: str
    amount: float
    source: str
    description: Optional[str] = None
    date: Date
    despesas: float
    objetivos: List[AllocationOut]
    para_gastar: float


# ---------- Gastos do dia a dia ----------
class SpendingIn(BaseModel):
    amount: Money
    category_id: str
    description: Optional[str] = None
    date: Optional[Date] = None  # por defeito hoje


class SpendingUpdate(BaseModel):
    amount: Optional[Money] = None
    category_id: Optional[str] = None
    description: Optional[str] = None
    date: Optional[Date] = None


class SpendingOut(BaseModel):
    id: str
    amount: float
    category_id: Optional[str] = None  # None: a categoria foi apagada
    categoria: Optional[str] = None
    icone: Optional[str] = None
    description: Optional[str] = None
    date: Date


# ---------- Contas (despesas planeadas) e pagamentos ----------
class PaymentIn(BaseModel):
    amount: Optional[Money] = None  # por defeito o valor da conta
    paid_date: Optional[Date] = None  # por defeito hoje


class PaymentOut(BaseModel):
    expense_id: str
    month: str  # "AAAA-MM"
    amount: float
    paid_date: Date


class ExpenseBase(BaseModel):
    title: str = Field(min_length=1)
    amount: Money
    date: Optional[Date] = None  # por defeito hoje; nas recorrentes é a data de início
    is_recurring: bool = False
    end_date: Optional[Date] = None


class ExpenseCreate(ExpenseBase):
    paid_date: Optional[Date] = None  # "já paga": regista o pagamento do primeiro mês com esta data


class ExpenseUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1)
    amount: Optional[Money] = None
    date: Optional[Date] = None
    is_recurring: Optional[bool] = None
    end_date: Optional[Date] = None


class ExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    category_id: str
    title: str
    amount: float
    date: Date
    is_recurring: bool
    end_date: Optional[Date] = None
    payment: Optional[PaymentOut] = None  # pagamento do mês pedido, se a conta já está paga


class CategoryBase(BaseModel):
    name: str
    icon: Optional[str] = "📦"


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    position: Optional[int] = None


class CategoryOut(CategoryBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    position: int
    expenses: List[ExpenseOut] = []


# ---------- Objetivos ----------
class BucketBase(BaseModel):
    name: str
    icon: Optional[str] = "🎯"
    kind: Optional[str] = "objetivo"
    opening_amount: MoneyOrZero = Decimal("0")  # já guardado no dia do saldo inicial
    target_amount: Optional[MoneyOrZero] = None
    monthly_contribution: MoneyOrZero = Decimal("0")  # sugestão ao repartir um rendimento
    is_mandatory: bool = False


class BucketCreate(BucketBase):
    pass


class BucketUpdate(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    kind: Optional[str] = None
    opening_amount: Optional[MoneyOrZero] = None
    target_amount: Optional[MoneyOrZero] = None
    monthly_contribution: Optional[MoneyOrZero] = None
    is_mandatory: Optional[bool] = None
    position: Optional[int] = None


class BucketOut(BaseModel):
    id: str
    name: str
    icon: Optional[str] = None
    kind: Optional[str] = None
    opening_amount: float
    target_amount: Optional[float] = None
    monthly_contribution: float
    is_mandatory: bool = False
    position: int
    current_amount: float  # saldo atual (derivado dos movimentos)
    archived: bool = False


class BucketMovementIn(BaseModel):
    kind: Literal["deposito", "levantamento"]
    amount: Money
    date: Optional[Date] = None  # por defeito hoje
    note: Optional[str] = None


class BucketMovementUpdate(BaseModel):
    kind: Optional[Literal["deposito", "levantamento"]] = None
    amount: Optional[Money] = None
    date: Optional[Date] = None
    note: Optional[str] = None


class BucketMovementOut(BaseModel):
    id: Optional[str] = None  # None nas repartições de rendimentos (editam-se no rendimento)
    bucket_id: str
    kind: Literal["deposito", "levantamento", "rendimento"]
    amount: float  # sempre positivo; o tipo diz o sentido
    date: Date
    note: Optional[str] = None
    income_entry_id: Optional[str] = None


# ---------- Resumo ----------
class EnvelopesOut(BaseModel):
    despesas: float
    objetivos: float
    para_gastar: float


class CategoryTotal(BaseModel):
    id: Optional[str] = None  # None: gastos sem categoria
    nome: str
    icone: Optional[str] = None
    total: float


class MonthHistory(BaseModel):
    mes: str  # "AAAA-MM"
    recebido: float
    saidas: float  # contas pagas + gastos do dia a dia


class SummaryOut(BaseModel):
    month: str  # "AAAA-MM"
    # estatísticas do mês (incluem movimentos anteriores ao saldo inicial)
    recebido: float
    pago_contas: float  # pagamentos de contas com data de pagamento no mês
    gasto_dia_a_dia: float
    planeado: float  # contas ativas no mês
    por_pagar: float  # contas ativas no mês ainda sem pagamento
    por_categoria: List[CategoryTotal]
    historico: List[MonthHistory]
    # saldos de hoje
    saldo_total: float
    envelopes: EnvelopesOut
    opening_balance: Optional[float] = None
    opening_date: Optional[Date] = None
    opening_defined: bool
