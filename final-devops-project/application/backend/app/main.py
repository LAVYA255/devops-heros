from datetime import date
from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.metrics import AMOUNT_SPENT, EXPENSES_CREATED, MetricsMiddleware
from app.models import CATEGORIES, Expense
from app.schemas import (
    CategoryTotal,
    ExpenseCreate,
    ExpenseOut,
    ExpenseUpdate,
    SummaryOut,
)

app = FastAPI(
    title="Kharcha API",
    description="Personal expense tracker. Record what you spend, see where it goes.",
    version=settings.app_version,
)

app.add_middleware(MetricsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _month_bounds(month: str) -> tuple[date, date]:
    """'2026-10' -> (2026-10-01, 2026-11-01). Half-open range, works on any DB."""
    try:
        year, mon = (int(part) for part in month.split("-"))
        start = date(year, mon, 1)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="month must look like YYYY-MM")
    end = date(year + 1, 1, 1) if mon == 12 else date(year, mon + 1, 1)
    return start, end


def _get_or_404(db: Session, expense_id: int) -> Expense:
    expense = db.get(Expense, expense_id)
    if expense is None:
        raise HTTPException(status_code=404, detail=f"expense {expense_id} not found")
    return expense


# ---------------------------------------------------------------- platform


@app.get("/", tags=["platform"])
def root():
    return {"service": "kharcha-api", "version": settings.app_version, "docs": "/docs"}


@app.get("/health", tags=["platform"])
def health():
    """Liveness. Answers as long as the process is alive. Deliberately does NOT
    touch the database: if Postgres blips, restarting every API pod would make
    things worse, not better."""
    return {"status": "UP", "version": settings.app_version}


@app.get("/ready", tags=["platform"])
def ready(response: Response, db: Session = Depends(get_db)):
    """Readiness. Only says yes when the database is reachable, so Kubernetes
    stops routing traffic to a pod that cannot actually serve it."""
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - any DB failure means not ready
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "NOT_READY", "reason": type(exc).__name__}
    return {"status": "READY"}


@app.get("/metrics", tags=["platform"])
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ---------------------------------------------------------------- expenses


@app.get("/api/categories", response_model=list[str], tags=["expenses"])
def list_categories():
    return CATEGORIES


@app.get("/api/expenses", response_model=list[ExpenseOut], tags=["expenses"])
def list_expenses(
    category: str | None = None,
    month: str | None = Query(default=None, description="YYYY-MM"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    stmt = select(Expense)
    if category:
        stmt = stmt.where(Expense.category == category.lower())
    if month:
        start, end = _month_bounds(month)
        stmt = stmt.where(Expense.spent_on >= start, Expense.spent_on < end)
    stmt = stmt.order_by(Expense.spent_on.desc(), Expense.id.desc()).limit(limit)
    return db.scalars(stmt).all()


@app.post(
    "/api/expenses",
    response_model=ExpenseOut,
    status_code=status.HTTP_201_CREATED,
    tags=["expenses"],
)
def create_expense(payload: ExpenseCreate, db: Session = Depends(get_db)):
    expense = Expense(**payload.model_dump())
    db.add(expense)
    db.commit()
    db.refresh(expense)
    EXPENSES_CREATED.labels(expense.category).inc()
    AMOUNT_SPENT.labels(expense.category).inc(float(expense.amount))
    return expense


# Declared before /{expense_id} so "summary" is not parsed as an ID.
@app.get("/api/expenses/summary", response_model=SummaryOut, tags=["expenses"])
def summary(
    month: str | None = Query(default=None, description="YYYY-MM, defaults to this month"),
    db: Session = Depends(get_db),
):
    month = month or date.today().strftime("%Y-%m")
    start, end = _month_bounds(month)

    rows = db.execute(
        select(
            Expense.category,
            func.coalesce(func.sum(Expense.amount), 0),
            func.count(Expense.id),
        )
        .where(Expense.spent_on >= start, Expense.spent_on < end)
        .group_by(Expense.category)
        .order_by(func.sum(Expense.amount).desc())
    ).all()

    cents = Decimal("0.01")
    by_category = [
        CategoryTotal(category=c, total=Decimal(t).quantize(cents), count=n) for c, t, n in rows
    ]
    total = sum((c.total for c in by_category), start=Decimal("0")).quantize(cents)
    count = sum(c.count for c in by_category)
    # Through str() so 20000 becomes Decimal("20000") rather than the float's
    # binary approximation, then fixed to two places like every other amount.
    budget = Decimal(str(settings.monthly_budget)).quantize(cents)
    used = round(float(total / budget * 100), 1) if budget else 0.0

    return SummaryOut(
        month=month,
        currency=settings.currency,
        total=total,
        count=count,
        budget=budget,
        budget_used_pct=used,
        remaining=(budget - total).quantize(cents),
        by_category=by_category,
    )


@app.get("/api/expenses/{expense_id}", response_model=ExpenseOut, tags=["expenses"])
def get_expense(expense_id: int, db: Session = Depends(get_db)):
    return _get_or_404(db, expense_id)


@app.put("/api/expenses/{expense_id}", response_model=ExpenseOut, tags=["expenses"])
def update_expense(expense_id: int, payload: ExpenseUpdate, db: Session = Depends(get_db)):
    expense = _get_or_404(db, expense_id)
    for field, value in payload.model_dump().items():
        setattr(expense, field, value)
    db.commit()
    db.refresh(expense)
    return expense


@app.delete(
    "/api/expenses/{expense_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["expenses"],
)
def delete_expense(expense_id: int, db: Session = Depends(get_db)):
    expense = _get_or_404(db, expense_id)
    db.delete(expense)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
