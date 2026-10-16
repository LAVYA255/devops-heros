from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


# pool_pre_ping checks a pooled connection is still alive before handing it out.
# Without it, the first request after Postgres restarts fails with a stale
# connection error, which in Kubernetes shows up as a burst of 500s every time
# the database pod is rescheduled.
#
# Pool size is set on purpose rather than left at SQLAlchemy's 5 + 10 overflow.
# The HPA can run 6 backend pods; 6 x 15 = 90 connections against Postgres's
# max_connections of 100 leaves almost nothing for migrations or a psql
# session. 5 + 5 per pod caps the fleet at 60. pool_timeout makes a request
# that cannot get a connection fail after 10s instead of hanging for 30.
_pool_args = (
    {"pool_size": 5, "max_overflow": 5, "pool_timeout": 10}
    if settings.database_url.startswith("postgresql")
    else {}
)
engine = create_engine(settings.database_url, pool_pre_ping=True, **_pool_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def wait_for_database(timeout_seconds: int = 120, interval: float = 2.0) -> None:
    """Block until the database answers SELECT 1, or raise after the timeout.

    Used before migrations. In Kubernetes the backend and Postgres start at the
    same time, and a migration that runs before Postgres is up just fails and
    sends the pod into a crash loop. Waiting here turns that into a short pause.
    """
    import time

    from sqlalchemy import text

    deadline = time.monotonic() + timeout_seconds
    attempt = 0
    while True:
        attempt += 1
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print(f"[db] reachable after {attempt} attempt(s)", flush=True)
            return
        except Exception as exc:  # noqa: BLE001 - any failure means "not yet"
            if time.monotonic() > deadline:
                raise RuntimeError(f"database not reachable after {timeout_seconds}s") from exc
            print(f"[db] not ready yet ({type(exc).__name__}), retrying", flush=True)
            time.sleep(interval)
