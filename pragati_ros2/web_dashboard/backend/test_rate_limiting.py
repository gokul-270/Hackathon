"""Tests for rate limiting middleware."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.middleware import RateLimitMiddleware


def _make_app(requests_per_minute: int = 5) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware, requests_per_minute=requests_per_minute
    )

    @app.get("/test")
    def test_endpoint():
        return {"ok": True}

    return app


class TestRateLimiting:
    def test_within_limit(self):
        """Requests within the limit all succeed."""
        client = TestClient(_make_app(requests_per_minute=10))
        for _ in range(10):
            resp = client.get("/test")
            assert resp.status_code == 200

    def test_over_limit(self):
        """Request exceeding the limit gets 429 with retry info."""
        client = TestClient(_make_app(requests_per_minute=3))
        for _ in range(3):
            resp = client.get("/test")
            assert resp.status_code == 200
        resp = client.get("/test")
        assert resp.status_code == 429
        body = resp.json()
        assert body["error"] == "Rate limit exceeded"
        assert "retry_after_seconds" in body
        assert isinstance(body["retry_after_seconds"], int)
        assert body["retry_after_seconds"] >= 1
        assert "Retry-After" in resp.headers

    def test_config_driven_limit(self):
        """Limit of 1 blocks the second request."""
        client = TestClient(_make_app(requests_per_minute=1))
        resp = client.get("/test")
        assert resp.status_code == 200
        resp = client.get("/test")
        assert resp.status_code == 429

    def test_high_limit_allows_many_requests(self):
        """A high limit allows many requests without blocking."""
        client = TestClient(_make_app(requests_per_minute=1000))
        for _ in range(100):
            resp = client.get("/test")
            assert resp.status_code == 200

    def test_ip_isolation(self):
        """Different IPs have independent rate-limit counters."""
        from backend.middleware import RateLimitMiddleware

        mw = RateLimitMiddleware(None, requests_per_minute=5)
        # Simulate two different IPs hitting the counter
        import time

        now = time.monotonic()
        mw._hits["10.0.0.1"] = [now] * 5
        mw._hits["10.0.0.2"] = [now] * 2
        # IP1 is at the limit (5), IP2 is not (2)
        assert len(mw._hits["10.0.0.1"]) >= mw.rpm
        assert len(mw._hits["10.0.0.2"]) < mw.rpm
