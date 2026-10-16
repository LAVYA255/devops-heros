#!/bin/sh
# Container entrypoint for the Kharcha API.
#
#   ./entrypoint.sh            start the API server (default)
#   ./entrypoint.sh migrate    wait for the database, run migrations, exit
#
# docker compose : one backend container, so RUN_MIGRATIONS=true lets it
#                  migrate itself before serving.
# Kubernetes     : an init container runs "migrate" before each pod starts.
#                  Several pods may do that at once; alembic/env.py takes a
#                  Postgres advisory lock so they queue instead of racing.
set -e

migrate() {
  echo "[entrypoint] waiting for the database"
  python -c "from app.db import wait_for_database; wait_for_database()"
  echo "[entrypoint] running database migrations"
  alembic upgrade head
}

if [ "${1:-serve}" = "migrate" ]; then
  migrate
  echo "[entrypoint] migrations done"
  exit 0
fi

if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
  migrate
fi

echo "[entrypoint] starting kharcha-api ${APP_VERSION:-dev} on :8000"
# One worker per container on purpose. Scaling is done with replicas, and a single
# process keeps the prometheus_client counters correct without multiprocess mode.
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --no-access-log
