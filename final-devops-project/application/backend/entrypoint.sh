#!/bin/sh
# Container entrypoint for the Kharcha API.
#
# RUN_MIGRATIONS=true  -> run `alembic upgrade head` first. Used by docker compose,
#                         where there is exactly one backend container.
# RUN_MIGRATIONS=false -> just start the server. Used in Kubernetes, where several
#                         replicas start at once and would race each other on the
#                         same migration. There a Helm hook Job runs it once.
set -e

if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
  echo "[entrypoint] running database migrations"
  alembic upgrade head
fi

echo "[entrypoint] starting kharcha-api ${APP_VERSION:-dev} on :8000"
# One worker per container on purpose. Scaling is done with replicas, and a single
# process keeps the prometheus_client counters correct without multiprocess mode.
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --no-access-log
