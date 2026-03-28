"""Tests for field-name alignment between frontend and backend.

Validates the dashboard-tab-wiring-fix change ensures:
- Launch status uses 'status' field (not 'state')
- Sync config uses 'target_ips' (not 'recent_ips') for PUT
- Sync status uses 'running' boolean (not 'state' string)
- service_registry checks 'performance_metrics' (not 'performance_monitoring')
"""

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# -----------------------------------------------------------------
# Launch status field names
# -----------------------------------------------------------------


class TestLaunchStatusFieldNames:
    """Verify /api/launch/arm/status and /api/launch/vehicle/status use 'status' not 'state'."""

    def _make_client(self):
        from backend.launch_api import (
            launch_router,
            set_process_manager,
            set_audit_logger,
        )
        import backend.launch_api as mod

        app = FastAPI()
        app.include_router(launch_router)
        pm = MagicMock()
        pm.get_status = MagicMock(
            return_value={"status": "running", "pid": 123, "return_code": None}
        )
        mod.set_process_manager(pm)
        mod.set_audit_logger(MagicMock())
        return TestClient(app), mod

    def test_arm_status_has_status_not_state(self):
        client, mod = self._make_client()
        resp = client.get("/api/launch/arm/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "state" not in data

    def test_vehicle_status_has_status_not_state(self):
        client, mod = self._make_client()
        resp = client.get("/api/launch/vehicle/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "state" not in data

    def test_arm_status_not_running_has_status_field(self):
        from backend.launch_api import launch_router, set_process_manager
        import backend.launch_api as mod

        app = FastAPI()
        app.include_router(launch_router)
        pm = MagicMock()
        pm.get_status = MagicMock(return_value=None)
        mod.set_process_manager(pm)
        client = TestClient(app)
        resp = client.get("/api/launch/arm/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert data["status"] == "not_running"
        assert "state" not in data

    def test_vehicle_subsystems_use_status_not_state(self):
        """Subsystem entries use 'status' field."""
        from backend.launch_api import launch_router, set_process_manager
        import backend.launch_api as mod

        app = FastAPI()
        app.include_router(launch_router)
        pm = MagicMock()
        pm.get_status = MagicMock(return_value=None)  # vehicle not running
        mod.set_process_manager(pm)
        client = TestClient(app)
        resp = client.get("/api/launch/vehicle/subsystems")
        assert resp.status_code == 200
        data = resp.json()
        assert "subsystems" in data
        for sub in data["subsystems"]:
            assert "status" in sub
            assert "state" not in sub


# -----------------------------------------------------------------
# Sync config field names
# -----------------------------------------------------------------


class TestSyncConfigFieldNames:
    """Verify sync config uses 'target_ips' not 'recent_ips' for PUT body."""

    def _make_client(self, tmp_path):
        from backend.sync_api import sync_router, SyncManager
        import backend.sync_api as mod

        app = FastAPI()
        app.include_router(sync_router)
        mgr = SyncManager(sync_sh_path="", data_dir=str(tmp_path))
        orig = mod._sync_manager
        mod._sync_manager = mgr
        return TestClient(app), mod, orig

    def test_put_config_accepts_target_ips(self, tmp_path):
        client, mod, orig = self._make_client(tmp_path)
        try:
            resp = client.put(
                "/api/sync/config",
                json={"target_ips": ["192.168.1.100"]},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"
        finally:
            mod._sync_manager = orig

    def test_put_config_rejects_recent_ips_as_body(self, tmp_path):
        """PUT with 'recent_ips' instead of 'target_ips' should fail validation (422)."""
        client, mod, orig = self._make_client(tmp_path)
        try:
            resp = client.put(
                "/api/sync/config",
                json={"recent_ips": ["192.168.1.100"]},
            )
            # Pydantic should reject because target_ips is required
            assert resp.status_code == 422
        finally:
            mod._sync_manager = orig

    def test_get_config_returns_target_ips(self, tmp_path):
        client, mod, orig = self._make_client(tmp_path)
        try:
            resp = client.get("/api/sync/config")
            assert resp.status_code == 200
            data = resp.json()
            assert "target_ips" in data
        finally:
            mod._sync_manager = orig


# -----------------------------------------------------------------
# Sync status field names
# -----------------------------------------------------------------


class TestSyncStatusFieldNames:
    """Verify /api/sync/status uses 'running' boolean not 'state' string."""

    def _make_client(self, tmp_path):
        from backend.sync_api import sync_router, SyncManager
        import backend.sync_api as mod

        app = FastAPI()
        app.include_router(sync_router)
        mgr = SyncManager(sync_sh_path="", data_dir=str(tmp_path))
        orig = mod._sync_manager
        mod._sync_manager = mgr
        return TestClient(app), mod, orig

    def test_status_has_running_not_state(self, tmp_path):
        client, mod, orig = self._make_client(tmp_path)
        try:
            resp = client.get("/api/sync/status")
            assert resp.status_code == 200
            data = resp.json()
            assert "running" in data
            assert isinstance(data["running"], bool)
            assert "state" not in data
        finally:
            mod._sync_manager = orig

    def test_status_running_is_false_when_idle(self, tmp_path):
        client, mod, orig = self._make_client(tmp_path)
        try:
            resp = client.get("/api/sync/status")
            data = resp.json()
            assert data["running"] is False
        finally:
            mod._sync_manager = orig


# -----------------------------------------------------------------
# Performance metrics capability
# -----------------------------------------------------------------


class TestPerformanceMetricsCapability:
    """Verify 'performance_metrics' (not 'performance_monitoring') is the capability name."""

    def test_performance_metrics_recognized(self):
        from backend.capabilities import CapabilitiesManager

        mgr = CapabilitiesManager.__new__(CapabilitiesManager)
        mgr.capabilities = {"performance_metrics": True}
        mgr.server_config = {}
        assert mgr.is_enabled("performance_metrics") is True

    def test_performance_monitoring_not_recognized(self):
        from backend.capabilities import CapabilitiesManager

        mgr = CapabilitiesManager.__new__(CapabilitiesManager)
        mgr.capabilities = {"performance_metrics": True}
        mgr.server_config = {}
        assert mgr.is_enabled("performance_monitoring") is False

    def test_service_registry_uses_performance_metrics(self):
        """The string 'performance_metrics' (not 'performance_monitoring') appears."""
        from backend import service_registry

        source = inspect.getsource(service_registry)
        assert 'is_enabled("performance_metrics")' in source
        assert 'is_enabled("performance_monitoring")' not in source
