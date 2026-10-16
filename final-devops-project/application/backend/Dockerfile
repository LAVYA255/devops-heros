# ---------------------------------------------------------------------------
# Stage 1: build wheels. Anything that needs a compiler happens here and stays
# here, so the runtime image ships no build tooling.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt


# ---------------------------------------------------------------------------
# Stage 2: runtime.
# ---------------------------------------------------------------------------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_VERSION=dev \
    RUN_MIGRATIONS=false

# Non-root user with a fixed UID, so Kubernetes `runAsNonRoot` / `runAsUser`
# can match it exactly.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin kharcha

WORKDIR /app
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels \
    # pip is not needed at runtime and is a frequent source of image CVEs.
    && pip uninstall -y pip

COPY --chown=kharcha:kharcha alembic.ini ./
COPY --chown=kharcha:kharcha alembic ./alembic
COPY --chown=kharcha:kharcha app ./app
COPY --chown=kharcha:kharcha entrypoint.sh ./entrypoint.sh
# A plain RUN rather than COPY --chmod, which needs BuildKit. Also strips any
# Windows line endings, which would make the shebang line fail with a confusing
# "no such file or directory".
RUN sed -i 's/\r$//' entrypoint.sh && chmod 0755 entrypoint.sh

USER 10001
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

ENTRYPOINT ["./entrypoint.sh"]
