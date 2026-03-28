"""Tests for startup health registry and /health endpoint."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.health import (
    init_health_registry,
    register_module_ok,
    register_module_failed,
    router,
)


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


class TestHealthRegistry:
    def setup_method(self):
        init_health_registry()

    def test_all_healthy(self):
        register_module_ok("mod_a")
        register_module_ok("mod_b")
        client = TestClient(_make_app())
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "mod_a" in data["modules_loaded"]
        assert "mod_b" in data["modules_loaded"]
        assert data["modules_failed"] == []

    def test_degraded(self):
        register_module_ok("mod_a")
        register_module_failed("mod_b", "ImportError: no module")
        client = TestClient(_make_app())
        resp = client.get("/health")
        data = resp.json()
        assert data["status"] == "degraded"
        assert len(data["modules_failed"]) == 1
        assert data["modules_failed"][0]["name"] == "mod_b"
        assert "ImportError" in data["modules_failed"][0]["error"]

    def test_uptime_present(self):
        client = TestClient(_make_app())
        resp = client.get("/health")
        data = resp.json()
        assert "uptime_seconds" in data
        assert isinstance(data["uptime_seconds"], (int, float))

    def test_empty_registry(self):
        """Freshly initialized registry with no modules is healthy."""
        client = TestClient(_make_app())
        resp = client.get("/health")
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["modules_loaded"] == []
        assert data["modules_failed"] == []

    def test_multiple_failures(self):
        """Multiple failed modules all reported in response."""
        register_module_failed("mod_x", "err_x")
        register_module_failed("mod_y", "err_y")
        client = TestClient(_make_app())
        resp = client.get("/health")
        data = resp.json()
        assert data["status"] == "degraded"
        assert len(data["modules_failed"]) == 2
        failed_names = [m["name"] for m in data["modules_failed"]]
        assert "mod_x" in failed_names
        assert "mod_y" in failed_names
