"""The database plumbing: the startup wait loop and the readiness failure path.

Both only matter when Postgres is NOT fine, which never happens against the
in-memory test database, so they are exercised here with stand-ins that fail
on purpose.
"""
import itertools

import pytest
from sqlalchemy.exc import OperationalError

import app.db as db
from app.db import get_db
from app.main import app


class FlakyEngine:
    """Refuses the first `failures` connections, then works."""

    def __init__(self, failures):
        self.failures = failures
        self.calls = 0

    def connect(self):
        self.calls += 1
        if self.calls <= self.failures:
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))
        return _Conn()


class _Conn:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, stmt):
        return None


@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)


def test_wait_for_database_returns_on_first_success(monkeypatch, capsys, no_sleep):
    engine = FlakyEngine(failures=0)
    monkeypatch.setattr(db, "engine", engine)
    db.wait_for_database(timeout_seconds=5)
    assert engine.calls == 1
    assert "reachable after 1 attempt(s)" in capsys.readouterr().out


def test_wait_for_database_retries_until_postgres_is_up(monkeypatch, capsys, no_sleep):
    # This is the Kubernetes start-up race: backend pod first, Postgres a few
    # seconds later. Two refusals, then success, and no crash.
    engine = FlakyEngine(failures=2)
    monkeypatch.setattr(db, "engine", engine)
    db.wait_for_database(timeout_seconds=60)
    out = capsys.readouterr().out
    assert engine.calls == 3
    assert out.count("not ready yet (OperationalError)") == 2
    assert "reachable after 3 attempt(s)" in out


def test_wait_for_database_gives_up_after_timeout(monkeypatch, no_sleep):
    monkeypatch.setattr(db, "engine", FlakyEngine(failures=10**6))
    # Fake clock: every call is 10s later, so the 5s budget is gone on the
    # first failure.
    clock = itertools.count(start=0, step=10)
    monkeypatch.setattr("time.monotonic", lambda: next(clock))
    with pytest.raises(RuntimeError, match="not reachable after 5s"):
        db.wait_for_database(timeout_seconds=5)


def test_get_db_always_closes_the_session(monkeypatch):
    closed = []

    class Session:
        def close(self):
            closed.append(True)

    monkeypatch.setattr(db, "SessionLocal", Session)
    gen = get_db()
    session = next(gen)
    assert isinstance(session, Session)
    with pytest.raises(StopIteration):
        next(gen)
    assert closed == [True]


def test_ready_is_503_when_database_is_down(client):
    class DeadSession:
        def execute(self, stmt):
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    def broken_db():
        yield DeadSession()

    previous = app.dependency_overrides[get_db]
    app.dependency_overrides[get_db] = broken_db
    try:
        resp = client.get("/ready")
    finally:
        app.dependency_overrides[get_db] = previous

    # 503 is what takes the pod out of the Service's endpoints.
    assert resp.status_code == 503
    assert resp.json() == {"status": "NOT_READY", "reason": "OperationalError"}
    # Liveness must stay green at the same time, or Kubernetes would restart
    # healthy API pods because of a database problem.
    assert client.get("/health").status_code == 200
