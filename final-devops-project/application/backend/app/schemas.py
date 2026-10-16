from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import CATEGORIES


class ExpenseBase(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    # gt=0: a zero or negative expense is a data entry mistake, so reject it at
    # the edge instead of letting it corrupt the monthly totals.
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    category: str
    spent_on: date
    note: str = Field(default="", max_length=500)

    @field_validator("category")
    @classmethod
    def category_must_be_known(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in CATEGORIES:
            raise ValueError(f"category must be one of: {', '.join(CATEGORIES)}")
        return value

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title must not be blank")
        return value.strip()


class ExpenseCreate(ExpenseBase):
    pass


class ExpenseUpdate(ExpenseBase):
    pass


class ExpenseOut(ExpenseBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime | None = None


class CategoryTotal(BaseModel):
    category: str
    total: Decimal
    count: int


class SummaryOut(BaseModel):
    month: str
    currency: str
    total: Decimal
    count: int
    budget: Decimal
    budget_used_pct: float
    remaining: Decimal
    by_category: list[CategoryTotal]
