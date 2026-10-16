from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


# pool_pre_ping checks a pooled connection is still alive before handing it out.
# Without it, the first request after Postgres restarts fails with a stale
# connection error, which in Kubernetes shows up as a burst of 500s every time
# the database pod is rescheduled.
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
