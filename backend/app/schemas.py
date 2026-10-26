from datetime import date as Date, datetime
from typing import Annotated, Optional, List

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# os campos chamam-se "date", por isso o tipo usa o alias Date para não ser sombreado
Money = Annotated[float, Field(gt=0)]


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


# ---------- Recorrência (receitas e despesas) ----------
class ChangeRecurringIn(BaseModel):
    amount: Money
    start_month: str  # "AAAA-MM": primeiro mês em que vale o novo valor


class EndRecurringIn(BaseModel):
    end_month: str  # "AAAA-MM": último mês em que ainda vale


# ---------- Income entries ----------
class IncomeEntryBase(BaseModel):
    amount: Money
    source: str = Field(min_length=1, max_length=60)
    description: Optional[str] = None
    date: Optional[Date] = None  # por defeito hoje; nas recorrentes é a data de início
    is_recurring: bool = False
    end_date: Optional[Date] = None


class IncomeEntryCreate(IncomeEntryBase):
    pass


class IncomeEntryUpdate(BaseModel):
    amount: Optional[float] = Field(default=None, gt=0)
    source: Optional[str] = Field(default=None, min_length=1, max_length=60)
    description: Optional[str] = None
    date: Optional[Date] = None
    is_recurring: Optional[bool] = None
    end_date: Optional[Date] = None


class IncomeEntryOut(IncomeEntryBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    amount: float
    date: Date


# ---------- Expenses ----------
class ExpenseBase(BaseModel):
    title: str
    amount: Money
    date: Optional[Date] = None  # por defeito hoje; nas recorrentes é a data de início
    is_recurring: bool = False
    end_date: Optional[Date] = None


class ExpenseCreate(ExpenseBase):
    pass


class ExpenseUpdate(BaseModel):
    title: Optional[str] = None
    amount: Optional[float] = Field(default=None, gt=0)
    date: Optional[Date] = None
    is_recurring: Optional[bool] = None
    end_date: Optional[Date] = None


class ExpenseOut(ExpenseBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    category_id: str
    amount: float
    date: Date


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


# ---------- Savings buckets ----------
class BucketBase(BaseModel):
    name: str
    icon: Optional[str] = "🎯"
    kind: Optional[str] = "objetivo"
    current_amount: float = 0
    target_amount: Optional[float] = None
    monthly_contribution: float = 0
    is_mandatory: bool = False


class BucketCreate(BucketBase):
    pass


class BucketUpdate(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    kind: Optional[str] = None
    current_amount: Optional[float] = None
    target_amount: Optional[float] = None
    monthly_contribution: Optional[float] = None
    is_mandatory: Optional[bool] = None
    position: Optional[int] = None


class BucketOut(BucketBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    position: int


# ---------- Summary ----------
class CategoryTotal(BaseModel):
    id: str
    nome: str
    icone: Optional[str] = None
    total: float


class MonthHistory(BaseModel):
    mes: str  # "AAAA-MM"
    recebido: float
    gasto: float


class SummaryOut(BaseModel):
    month: str  # "AAAA-MM"
    recebido: float
    gasto: float
    contribuicoes_mensais: float
    pronto_a_gastar: float
    saldo_total: float
    total_poupado: float
    disponivel: float
    por_categoria: List[CategoryTotal]
    historico: List[MonthHistory]
    # campos antigos (versão anterior da PWA ainda em cache), calculados para o mês pedido
    income: float
    total_expenses: float
    left_after_expenses: float
    total_monthly_contributions: float
    left_to_spend: float
    total_saved: float
