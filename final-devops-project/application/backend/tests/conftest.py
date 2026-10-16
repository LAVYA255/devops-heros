"""Test fixtures.

Tests run against an in-memory SQLite database, never the real Postgres. The
DATABASE_URL is set BEFORE the app is imported, because app.db builds its engine
at import time; setting it afterwards would be too late and the tests would try
to reach a Postgres server that does not exist in CI.
"""
import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["MONTHLY_BUDGET"] = "10000"
os.environ["APP_VERSION"] = "test"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

# StaticPool keeps ONE connection for the whole engine. An in-memory SQLite
# database lives only as long as its connection, so without this every new
# session would see a brand new, empty database with no tables.
engine = create_engine(
    "sqlite+pysqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def fresh_schema():
    """Every test starts from empty tables, so tests cannot depend on each other."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def make_expense(client):
    def _make(**overrides):
        payload = {
            "title": "Lunch",
            "amount": "250.00",
            "category": "food",
            "spent_on": "2026-10-05",
            "note": "",
        }
        payload.update(overrides)
        resp = client.post("/api/expenses", json=payload)
        assert resp.status_code == 201, resp.text
        return resp.json()

    return _make
