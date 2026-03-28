"""DEPRECATED: Tests for role-based tab filtering (roleConfig). The entity-centric
sidebar (Phase 6) replaces role-based filtering. These tests remain until
roleConfig.mjs and the /api/config/role endpoint are removed in a follow-up change.
See openspec/changes/dashboard-entity-core/design.md D7."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


def _make_app(role_config=None):
    """Create isolated FastAPI app with fleet_api router.

    Args:
        role_config: Value for the 'role' key in dashboard.yaml config.
            If None, simulates missing role key entirely.
    """
    # Reset module-level state before each test
    import backend.fleet_api as mod

    mod._dashboard_role = None

    # Build config dict
    config = {}
    if role_config is not None:
        config["role"] = role_config

    app = FastAPI()
    app.include_router(mod.role_config_router)
    return app, mod, config


class TestRoleConfigParsing:
    """Test role config parsing logic."""

    def test_valid_role_dev(self):
        """Valid role 'dev' is accepted."""
        from backend.fleet_api import parse_role_config

        role = parse_role_config({"role": "dev"})
        assert role == "dev"

    def test_valid_role_vehicle(self):
        """Valid role 'vehicle' is accepted."""
        from backend.fleet_api import parse_role_config

        role = parse_role_config({"role": "vehicle"})
        assert role == "vehicle"

    def test_valid_role_arm(self):
        """Valid role 'arm' is accepted."""
        from backend.fleet_api import parse_role_config

        role = parse_role_config({"role": "arm"})
        assert role == "arm"

    def test_missing_role_defaults_to_dev(self):
        """Missing role key defaults to 'dev' with warning."""
        from backend.fleet_api import parse_role_config

        role = parse_role_config({})
        assert role == "dev"

    def test_empty_role_defaults_to_dev(self):
        """Empty string role defaults to 'dev'."""
        from backend.fleet_api import parse_role_config

        role = parse_role_config({"role": ""})
        assert role == "dev"

    def test_none_role_defaults_to_dev(self):
        """None role defaults to 'dev'."""
        from backend.fleet_api import parse_role_config

        role = parse_role_config({"role": None})
        assert role == "dev"

    def test_invalid_role_raises_error(self):
        """Invalid role raises ValueError with valid roles listed."""
        from backend.fleet_api import parse_role_config

        with pytest.raises(ValueError, match="Invalid role"):
            parse_role_config({"role": "invalid"})

    def test_invalid_role_error_lists_valid_roles(self):
        """Error message includes valid role options."""
        from backend.fleet_api import parse_role_config

        with pytest.raises(ValueError, match="dev.*vehicle.*arm"):
            parse_role_config({"role": "operator"})


class TestRoleConfigEndpoint:
    """Test /api/config/role endpoint."""

    def test_role_endpoint_returns_dev(self):
        """GET /api/config/role returns dev role."""
        app, mod, _ = _make_app("dev")
        mod._dashboard_role = "dev"
        client = TestClient(app)
        resp = client.get("/api/config/role")
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "dev"

    def test_role_endpoint_returns_vehicle(self):
        """GET /api/config/role returns vehicle role."""
        app, mod, _ = _make_app("vehicle")
        mod._dashboard_role = "vehicle"
        client = TestClient(app)
        resp = client.get("/api/config/role")
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "vehicle"

    def test_role_endpoint_returns_arm(self):
        """GET /api/config/role returns arm role."""
        app, mod, _ = _make_app("arm")
        mod._dashboard_role = "arm"
        client = TestClient(app)
        resp = client.get("/api/config/role")
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "arm"

    def test_role_endpoint_default_when_uninitialized(self):
        """GET /api/config/role returns dev when role not yet initialized."""
        app, mod, _ = _make_app()
        mod._dashboard_role = None
        client = TestClient(app)
        resp = client.get("/api/config/role")
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "dev"
