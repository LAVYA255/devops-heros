"""Prometheus metrics for the Kharcha API.

Two kinds of metric live here. The HTTP ones (request count, latency) are the
"golden signals" that tell you whether the service is healthy. The business ones
(expenses created, money spent) are what makes the dashboard actually say
something about the application rather than just about a web server.
"""
import time

from prometheus_client import Counter, Gauge, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.config import settings

HTTP_REQUESTS = Counter(
    "kharcha_http_requests_total",
    "HTTP requests handled, by method, route template and status code.",
    ["method", "route", "status"],
)

HTTP_LATENCY = Histogram(
    "kharcha_http_request_duration_seconds",
    "HTTP request latency in seconds, by method and route template.",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

EXPENSES_CREATED = Counter(
    "kharcha_expenses_created_total",
    "Expenses created, by category.",
    ["category"],
)

AMOUNT_SPENT = Counter(
    "kharcha_amount_spent_total",
    "Total money recorded as spent, by category.",
    ["category"],
)

APP_INFO = Gauge(
    "kharcha_app_info",
    "Constant 1, labelled with the running version. Useful to see rollouts on a graph.",
    ["version"],
)
APP_INFO.labels(version=settings.app_version).set(1)

# Paths that would only add noise to the request metrics.
_SKIP = {"/metrics"}


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in _SKIP:
            return await call_next(request)

        start = time.perf_counter()
        status = "500"
        try:
            response = await call_next(request)
            status = str(response.status_code)
            return response
        finally:
            # Label by the route TEMPLATE (/api/expenses/{expense_id}), never by
            # the raw path (/api/expenses/1, /api/expenses/2, ...). Raw paths give
            # one time series per ID, which is unbounded label cardinality and is
            # the classic way to take down a Prometheus server.
            route = request.scope.get("route")
            template = getattr(route, "path", None) or "unmatched"
            HTTP_REQUESTS.labels(request.method, template, status).inc()
            HTTP_LATENCY.labels(request.method, template).observe(
                time.perf_counter() - start
            )
