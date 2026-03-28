"""Tests for API key authentication middleware."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.middleware import ApiKeyAuthMiddleware


def _make_app(api_key: str = "test-key", enabled: bool = True) -> FastAPI:
    """Create a minimal FastAPI app with auth middleware."""
    app = FastAPI()
    app.add_middleware(
        ApiKeyAuthMiddleware, api_key=api_key, enabled=enabled
    )

    @app.get("/read")
    def read_endpoint():
        return {"ok": True}

    @app.post("/write")
    def write_endpoint():
        return {"ok": True}

    return app


class TestAuthMiddleware:
    def test_valid_key_accepted(self):
        client = TestClient(_make_app())
        resp = client.post(
            "/write", headers={"X-API-Key": "test-key"}
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_missing_key_rejected(self):
        client = TestClient(_make_app())
        resp = client.post("/write")
        assert resp.status_code == 401
        assert resp.json()["error"] == "Missing API key"

    def test_invalid_key_rejected(self):
        client = TestClient(_make_app())
        resp = client.post(
            "/write", headers={"X-API-Key": "wrong"}
        )
        assert resp.status_code == 401
        assert resp.json()["error"] == "Invalid API key"

    def test_auth_disabled_passes_all(self):
        client = TestClient(_make_app(enabled=False))
        resp = client.post("/write")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_read_only_bypass(self):
        """GET (read-only) requests bypass auth even when enabled."""
        client = TestClient(_make_app())
        resp = client.get("/read")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_auth_enabled_no_key_configured(self):
        """Auth enabled with empty api_key returns 500 for writes."""
        client = TestClient(_make_app(api_key="", enabled=True))
        resp = client.post("/write")
        assert resp.status_code == 500
        assert "no API key configured" in resp.json()["error"]
