from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

CATEGORIES = [
    "food",
    "transport",
    "rent",
    "utilities",
    "shopping",
    "health",
    "entertainment",
    "education",
    "other",
]


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    # Numeric, never Float, for money. Float would turn 0.1 + 0.2 into
    # 0.30000000000000004 and the monthly totals would drift.
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    category: Mapped[str] = mapped_column(String(30), index=True)
    spent_on: Mapped[date] = mapped_column(Date, index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
