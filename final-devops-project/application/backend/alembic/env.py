from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from app.config import settings
from app.db import Base
from app import models  # noqa: F401 - registers the models on Base.metadata

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Arbitrary but fixed key for pg_advisory_lock. In Kubernetes every backend
# replica runs migrations from an init container, so two pods starting together
# would race on the same CREATE TABLE. The advisory lock makes them queue: the
# first one migrates, the rest wait, then find nothing left to do.
MIGRATION_LOCK_KEY = 72624201


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        is_postgres = connection.dialect.name == "postgresql"
        if is_postgres:
            connection.execute(text("SELECT pg_advisory_lock(:k)"), {"k": MIGRATION_LOCK_KEY})
            connection.commit()
        try:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
        finally:
            if is_postgres:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:k)"), {"k": MIGRATION_LOCK_KEY}
                )
                connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
