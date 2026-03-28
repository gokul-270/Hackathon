"""
Middleware — Auth and rate-limiting middleware for the dashboard backend.

Provides API key authentication for mutating endpoints and
sliding-window rate limiting per client IP.
"""

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Methods that require API key authentication
_MUTATING_METHODS = {"POST", "PUT", "DELETE", "PATCH"}

# How often (in requests) to purge stale IPs from the rate-limit store
_CLEANUP_EVERY = 200


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    """Validate X-API-Key header on mutating requests."""

    def __init__(self, app, api_key: str, enabled: bool = True):
        super().__init__(app)
        self.api_key = api_key
        self.enabled = enabled
        if enabled and not api_key:
            logger.warning(
                "Auth is enabled but no API key configured — "
                "mutating requests will be rejected"
            )

    async def dispatch(self, request: Request, call_next):
        if not self.enabled:
            return await call_next(request)

        # Read-only methods always pass through
        if request.method not in _MUTATING_METHODS:
            return await call_next(request)

        # Auth enabled but no key configured — server misconfiguration
        if not self.api_key:
            return JSONResponse(
                status_code=500,
                content={"error": "Auth enabled but no API key configured"},
            )

        provided = request.headers.get("X-API-Key")
        if not provided:
            return JSONResponse(
                status_code=401,
                content={"error": "Missing API key"},
            )

        if provided != self.api_key:
            return JSONResponse(
                status_code=401,
                content={"error": "Invalid API key"},
            )

        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter keyed by client IP."""

    def __init__(self, app, requests_per_minute: int = 1000):
        super().__init__(app)
        self.rpm = requests_per_minute
        # {ip: [timestamp, ...]}
        self._hits: dict[str, list[float]] = {}
        self._request_count = 0

    async def dispatch(self, request: Request, call_next):
        now = time.monotonic()
        window_start = now - 60.0
        ip = request.client.host if request.client else "unknown"

        # Get or create the timestamp list for this IP
        timestamps = self._hits.get(ip)
        if timestamps is None:
            timestamps = []
            self._hits[ip] = timestamps

        # Prune entries older than the 60-second window
        while timestamps and timestamps[0] <= window_start:
            timestamps.pop(0)

        if len(timestamps) >= self.rpm:
            # Estimate when the oldest entry in the window will expire
            retry_after = max(1, int(60.0 - (now - timestamps[0])) + 1)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        timestamps.append(now)

        # Periodic cleanup of stale IPs
        self._request_count += 1
        if self._request_count >= _CLEANUP_EVERY:
            self._request_count = 0
            stale = [
                k for k, v in self._hits.items()
                if not v or v[-1] <= window_start
            ]
            for k in stale:
                del self._hits[k]

        return await call_next(request)
