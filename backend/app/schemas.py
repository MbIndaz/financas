from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator


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


# ---------- Income ----------
class IncomeIn(BaseModel):
    amount: float
    label: Optional[str] = "Rendimento mensal"


class IncomeOut(IncomeIn):
    model_config = ConfigDict(from_attributes=True)


# ---------- Expenses ----------
class ExpenseBase(BaseModel):
    title: str
    amount: float


class ExpenseCreate(ExpenseBase):
    pass


class ExpenseUpdate(BaseModel):
    title: Optional[str] = None
    amount: Optional[float] = None


class ExpenseOut(ExpenseBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    category_id: str


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
class SummaryOut(BaseModel):
    income: float
    total_expenses: float
    left_after_expenses: float
    total_monthly_contributions: float
    left_to_spend: float
    total_saved: float
