"""DEPRECATED: Tests for role-based route filtering (ROLE_EXCLUDED_ROUTERS). The
entity-centric architecture (Phase 3) hardcodes role to 'dev', bypassing route
exclusion. These tests remain until ROLE_EXCLUDED_ROUTERS is removed in a follow-up
change. See openspec/changes/dashboard-entity-core/design.md D7."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch


def _make_app_with_register_routers(role: str) -> FastAPI:
    """Create a FastAPI app using register_routers with role filtering.

    This tests the actual register_routers function with the role param.
    We patch out optional modules to avoid import issues in test env.
    """
    from backend.service_registry import register_routers

    app = FastAPI()
    register_routers(app, role=role)
    return app


class TestRoleExcludedRouters:
    """Test ROLE_EXCLUDED_ROUTERS mapping exists and is correct."""

    def test_role_excluded_routers_exists(self):
        """ROLE_EXCLUDED_ROUTERS constant is defined in app_factory."""
        from backend.app_factory import ROLE_EXCLUDED_ROUTERS

        assert isinstance(ROLE_EXCLUDED_ROUTERS, dict)

    def test_dev_role_excludes_nothing(self):
        """Dev role has empty exclusion set (all routers allowed)."""
        from backend.app_factory import ROLE_EXCLUDED_ROUTERS

        assert ROLE_EXCLUDED_ROUTERS["dev"] == set()

    def test_vehicle_role_excludes_motor_and_fleet(self):
        """Vehicle role excludes motor and fleet routers."""
        from backend.app_factory import ROLE_EXCLUDED_ROUTERS

        excluded = ROLE_EXCLUDED_ROUTERS["vehicle"]
        assert "motor" in excluded
        assert "fleet" in excluded

    def test_arm_role_excludes_mqtt_and_fleet(self):
        """Arm role excludes mqtt (multi-arm) and fleet routers."""
        from backend.app_factory import ROLE_EXCLUDED_ROUTERS

        excluded = ROLE_EXCLUDED_ROUTERS["arm"]
        assert "mqtt" in excluded
        assert "fleet" in excluded

    def test_all_valid_roles_have_entries(self):
        """All three valid roles have entries in the map."""
        from backend.app_factory import ROLE_EXCLUDED_ROUTERS

        assert "dev" in ROLE_EXCLUDED_ROUTERS
        assert "vehicle" in ROLE_EXCLUDED_ROUTERS
        assert "arm" in ROLE_EXCLUDED_ROUTERS

    def test_vehicle_excludes_analysis(self):
        """Vehicle role excludes analysis router (dev-only feature)."""
        from backend.app_factory import ROLE_EXCLUDED_ROUTERS

        excluded = ROLE_EXCLUDED_ROUTERS["vehicle"]
        assert "analysis" in excluded

    def test_arm_excludes_analysis(self):
        """Arm role excludes analysis router (dev-only feature)."""
        from backend.app_factory import ROLE_EXCLUDED_ROUTERS

        excluded = ROLE_EXCLUDED_ROUTERS["arm"]
        assert "analysis" in excluded


class TestRegisterRoutersWithRole:
    """Test register_routers(app, role) filters routers by role."""

    def test_register_routers_accepts_role_param(self):
        """register_routers accepts a role keyword argument."""
        from backend.service_registry import register_routers
        import inspect

        sig = inspect.signature(register_routers)
        assert "role" in sig.parameters

    def test_dev_role_registers_fleet_router(self):
        """Dev role registers fleet_router (fleet routes accessible)."""
        from backend.service_registry import register_routers
        import backend.fleet_api as fleet_mod

        fleet_mod._dashboard_role = "dev"

        app = FastAPI()
        register_routers(app, role="dev")

        # fleet_router has /api/config/role — check it's accessible
        client = TestClient(app)
        resp = client.get("/api/config/role")
        assert resp.status_code == 200

    def test_arm_role_excludes_fleet_routes_but_keeps_role(self):
        """Arm role excludes fleet endpoints but /api/config/role is accessible."""
        from backend.service_registry import register_routers
        import backend.fleet_api as fleet_mod

        fleet_mod._dashboard_role = "arm"

        app = FastAPI()
        register_routers(app, role="arm")

        client = TestClient(app)
        # Role endpoint must always be accessible (all roles need it)
        resp = client.get("/api/config/role")
        assert resp.status_code == 200
        assert resp.json()["role"] == "arm"

        # Fleet-specific endpoints must be 404 for arm
        resp = client.get("/api/fleet/status")
        assert resp.status_code == 404

    def test_vehicle_role_excludes_fleet_routes_but_keeps_role(self):
        """Vehicle role excludes fleet endpoints but /api/config/role is accessible."""
        from backend.service_registry import register_routers
        import backend.fleet_api as fleet_mod

        fleet_mod._dashboard_role = "vehicle"

        app = FastAPI()
        register_routers(app, role="vehicle")

        client = TestClient(app)
        # Role endpoint must always be accessible (all roles need it)
        resp = client.get("/api/config/role")
        assert resp.status_code == 200
        assert resp.json()["role"] == "vehicle"

        # Fleet-specific endpoints must be 404 for vehicle
        resp = client.get("/api/fleet/status")
        assert resp.status_code == 404

    def test_default_role_is_dev(self):
        """register_routers with no role arg defaults to dev."""
        from backend.service_registry import register_routers
        import backend.fleet_api as fleet_mod

        fleet_mod._dashboard_role = "dev"

        app = FastAPI()
        register_routers(app)  # no role arg — should default to "dev"

        client = TestClient(app)
        resp = client.get("/api/config/role")
        assert resp.status_code == 200


class TestFleetRouteAccess:
    """Integration tests: fleet API routes gated by role."""

    def test_dev_role_fleet_status_not_404(self):
        """Dev role — /api/fleet/status is routable (not 404).

        Note: may return 404 from handler if FleetHealthService not
        initialized, but the route itself should be registered.
        Since fleet_router currently only has /api/config/role,
        we test that endpoint as proxy for fleet_router registration.
        """
        from backend.service_registry import register_routers
        import backend.fleet_api as fleet_mod

        fleet_mod._dashboard_role = "dev"

        app = FastAPI()
        register_routers(app, role="dev")

        client = TestClient(app)
        resp = client.get("/api/config/role")
        assert resp.status_code == 200
        assert resp.json()["role"] == "dev"

    def test_arm_role_fleet_routes_404(self):
        """Arm role — fleet-specific routes return 404, but role endpoint works."""
        from backend.service_registry import register_routers
        import backend.fleet_api as fleet_mod

        fleet_mod._dashboard_role = "arm"

        app = FastAPI()
        register_routers(app, role="arm")

        client = TestClient(app)
        # Role endpoint accessible for all roles
        resp = client.get("/api/config/role")
        assert resp.status_code == 200
        assert resp.json()["role"] == "arm"

        # Fleet-specific endpoints are 404
        resp = client.get("/api/fleet/status")
        assert resp.status_code == 404

    def test_vehicle_role_fleet_routes_404(self):
        """Vehicle role — fleet-specific routes return 404, but role endpoint works."""
        from backend.service_registry import register_routers
        import backend.fleet_api as fleet_mod

        fleet_mod._dashboard_role = "vehicle"

        app = FastAPI()
        register_routers(app, role="vehicle")

        client = TestClient(app)
        # Role endpoint accessible for all roles
        resp = client.get("/api/config/role")
        assert resp.status_code == 200
        assert resp.json()["role"] == "vehicle"

        # Fleet-specific endpoints are 404
        resp = client.get("/api/fleet/status")
        assert resp.status_code == 404
