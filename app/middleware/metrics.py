"""Prometheus metrics middleware for HTTP request tracking."""

import re
import time

from prometheus_client import Counter, Gauge, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# HTTP metrics
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration",
    ["method", "endpoint"],
)
ACTIVE_REQUESTS = Gauge(
    "http_active_requests",
    "Active HTTP requests",
)

# Application metrics (exported for use elsewhere)
DOCUMENT_PROCESSING_DURATION = Histogram(
    "document_processing_duration_seconds",
    "Document processing duration",
)
CELERY_TASKS_TOTAL = Counter(
    "celery_tasks_total",
    "Total Celery tasks",
    ["task_name", "status"],
)
DOCUMENTS_TOTAL = Gauge(
    "documents_total",
    "Total documents in system",
)
USERS_TOTAL = Gauge(
    "users_total",
    "Total users in system",
)
STORAGE_BYTES_USED = Gauge(
    "storage_bytes_used",
    "Storage bytes used",
)

# Pattern to normalize path parameters (UUIDs, integers)
_UUID_PATTERN = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_INT_PATTERN = re.compile(r"/\d+(?=/|$)")

# Paths to skip metrics tracking
_SKIP_PATHS = {"/health", "/health/ready", "/metrics"}


def _normalize_path(path: str) -> str:
    """Normalize path parameters to keep metric cardinality low."""
    path = _UUID_PATTERN.sub("{id}", path)
    path = _INT_PATTERN.sub("/{id}", path)
    return path


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Middleware that tracks HTTP request metrics for Prometheus."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip health and metrics endpoints
        if path in _SKIP_PATHS:
            return await call_next(request)

        method = request.method
        normalized_path = _normalize_path(path)

        ACTIVE_REQUESTS.inc()
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            ACTIVE_REQUESTS.dec()
            raise

        duration = time.perf_counter() - start_time
        ACTIVE_REQUESTS.dec()

        REQUEST_DURATION.labels(method=method, endpoint=normalized_path).observe(
            duration
        )
        REQUEST_COUNT.labels(
            method=method, endpoint=normalized_path, status=response.status_code
        ).inc()

        return response
