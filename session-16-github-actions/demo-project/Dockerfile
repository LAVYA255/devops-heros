# Multi-stage build: wheels are built in the first stage so the runtime image
# does not carry a compiler or pip's build cache.
FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt


FROM python:3.12-slim

# Run as a non-root user. Scanners flag root containers, and so does the
# security gate in the Session 17 pipeline.
RUN useradd --create-home --uid 10001 appuser

WORKDIR /app
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

COPY app/ ./app/

ENV PORT=5000 \
    APP_VERSION=dev \
    PYTHONUNBUFFERED=1

USER appuser
EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5000/healthz').status==200 else 1)"

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "app.server:app"]
