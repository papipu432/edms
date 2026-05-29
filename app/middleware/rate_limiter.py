"""Simple in-memory sliding window rate limiter middleware.

NOTE: This rate limiter uses per-process in-memory state. In multi-worker
deployments (e.g., gunicorn with multiple workers, uvicorn --workers N),
each worker maintains independent state. Rate limits are NOT enforced across
workers. For production multi-worker deployments, replace with a shared-state
backend such as Redis.
"""

import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """Sliding window rate limiter per client IP address.

    Configurable via constructor params:
    - requests_per_minute: maximum requests allowed per 60-second window
    - burst: additional burst capacity above the per-minute rate
    """

    def __init__(self, app, requests_per_minute: int = 60, burst: int = 10):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.burst = burst
        self.max_requests = requests_per_minute + burst
        self.window_seconds = 60.0
        # Dict of IP -> list of request timestamps
        self._requests: dict[str, list[float]] = defaultdict(list)

    def reset(self) -> None:
        """Clear all rate limit state. Useful for testing."""
        self._requests.clear()

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request."""
        # Check X-Forwarded-For header first
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"

    def _clean_old_requests(self, ip: str, now: float) -> None:
        """Remove timestamps outside the current window."""
        cutoff = now - self.window_seconds
        self._requests[ip] = [
            ts for ts in self._requests[ip] if ts > cutoff
        ]

    async def dispatch(self, request: Request, call_next):
        ip = self._get_client_ip(request)
        now = time.time()

        self._clean_old_requests(ip, now)

        if len(self._requests[ip]) >= self.max_requests:
            # Calculate retry-after based on oldest request in window
            oldest = self._requests[ip][0]
            retry_after = int(self.window_seconds - (now - oldest)) + 1
            retry_after = max(1, retry_after)

            return JSONResponse(
                status_code=429,
                content={
                    "error_code": "RATE_LIMIT_EXCEEDED",
                    "message": "Too many requests. Please try again later.",
                },
                headers={"Retry-After": str(retry_after)},
            )

        self._requests[ip].append(now)
        response = await call_next(request)
        return response
