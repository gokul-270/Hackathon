"""Tests for Safety Controls API endpoints.

Validates:
- POST /api/estop activates E-stop, sends CAN, stops processes
- POST /api/estop logs action via AuditLogger
- POST /api/estop/reset clears E-stop state
- POST /api/estop/reset requires confirmation
- GET /api/safety/status returns all fields
- GET /api/safety/status reflects E-stop state changes
- POST /api/emergency-shutdown requires token
- POST /api/emergency-shutdown rejects wrong token
- POST /api/emergency-shutdown initiates with correct token
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# -----------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------


def _make_app():
    """Create a fresh FastAPI app with safety router for each test."""
    # Import fresh to avoid state leaking between tests
    from backend.safety_api import (
        SafetyManager,
        safety_router,
        set_audit_logger,
        set_process_manager,
    )

    app = FastAPI()
    app.include_router(safety_router)

    # Create fresh SafetyManager for isolation
    manager = SafetyManager()

    # Wire it into the module, resetting all state for isolation
    import backend.safety_api as mod

    mod._safety_manager = manager
    mod._process_manager = None
    mod._audit_logger = None

    return app, manager, mod


def _make_mock_process_manager():
    """Create a mock ProcessManager with async stop_all."""
    pm = MagicMock()
    pm.stop_all = AsyncMock()
    pm._registry = {
        "proc1": {"status": "running"},
        "proc2": {"status": "running"},
        "proc3": {"status": "stopped"},
    }
    return pm


def _make_mock_audit_logger():
    """Create a mock AuditLogger."""
    al = MagicMock()
    al.log = MagicMock()
    al.get_recent = MagicMock(return_value=[])
    return al


# -----------------------------------------------------------------
# Tests: POST /api/estop (Task 2.1)
# -----------------------------------------------------------------


class TestEstopEndpoint:
    """Tests for E-stop activation."""

    def test_estop_returns_correct_response(self):
        """POST /api/estop returns estop_activated status with CAN and process info."""
        app, manager, mod = _make_app()
        pm = _make_mock_process_manager()
        al = _make_mock_audit_logger()
        mod.set_process_manager(pm)
        mod.set_audit_logger(al)

        with patch.object(mod, "_send_can_estop", return_value=True):
            client = TestClient(app)
            resp = client.post("/api/estop")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "estop_activated"
        assert "can_sent" in data
        assert "processes_stopped" in data

    def test_estop_sets_state_active(self):
        """POST /api/estop sets SafetyManager estop_active to True."""
        app, manager, mod = _make_app()
        pm = _make_mock_process_manager()
        al = _make_mock_audit_logger()
        mod.set_process_manager(pm)
        mod.set_audit_logger(al)

        with patch.object(mod, "_send_can_estop", return_value=True):
            client = TestClient(app)
            client.post("/api/estop")

        assert manager.estop_active is True
        assert manager.estop_timestamp is not None

    def test_estop_calls_process_manager_stop_all(self):
        """POST /api/estop calls stop_all on ProcessManager."""
        app, manager, mod = _make_app()
        pm = _make_mock_process_manager()
        al = _make_mock_audit_logger()
        mod.set_process_manager(pm)
        mod.set_audit_logger(al)

        with patch.object(mod, "_send_can_estop", return_value=True):
            client = TestClient(app)
            client.post("/api/estop")

        pm.stop_all.assert_called_once()

    def test_estop_sends_can_frame(self):
        """POST /api/estop sends CAN emergency stop frame."""
        app, manager, mod = _make_app()
        pm = _make_mock_process_manager()
        al = _make_mock_audit_logger()
        mod.set_process_manager(pm)
        mod.set_audit_logger(al)

        with patch.object(mod, "_send_can_estop", return_value=True) as mock_can:
            client = TestClient(app)
            client.post("/api/estop")

        mock_can.assert_called_once()

    def test_estop_logs_action(self):
        """POST /api/estop logs the action via AuditLogger."""
        app, manager, mod = _make_app()
        pm = _make_mock_process_manager()
        al = _make_mock_audit_logger()
        mod.set_process_manager(pm)
        mod.set_audit_logger(al)

        with patch.object(mod, "_send_can_estop", return_value=True):
            client = TestClient(app)
            client.post("/api/estop")

        al.log.assert_called_once()
        call_args = al.log.call_args
        assert call_args[0][0] == "estop"  # action name

    def test_estop_handles_can_failure_gracefully(self):
        """POST /api/estop still succeeds if CAN send fails."""
        app, manager, mod = _make_app()
        pm = _make_mock_process_manager()
        al = _make_mock_audit_logger()
        mod.set_process_manager(pm)
        mod.set_audit_logger(al)

        with patch.object(mod, "_send_can_estop", return_value=False):
            client = TestClient(app)
            resp = client.post("/api/estop")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "estop_activated"
        assert data["can_sent"] is False

    def test_estop_works_without_process_manager(self):
        """POST /api/estop works even if no ProcessManager is set."""
        app, manager, mod = _make_app()
        al = _make_mock_audit_logger()
        mod.set_audit_logger(al)
        # Don't set process manager -- leave as None

        with patch.object(mod, "_send_can_estop", return_value=True):
            client = TestClient(app)
            resp = client.post("/api/estop")

        assert resp.status_code == 200
        data = resp.json()
        assert data["processes_stopped"] == 0


# -----------------------------------------------------------------
# Tests: POST /api/estop/reset (Task 2.3)
# -----------------------------------------------------------------


class TestEstopResetEndpoint:
    """Tests for E-stop reset."""

    def test_reset_requires_confirmation(self):
        """POST /api/estop/reset returns 400 without confirm: true."""
        app, manager, mod = _make_app()
        client = TestClient(app)

        resp = client.post("/api/estop/reset", json={})
        assert resp.status_code == 400

    def test_reset_rejects_false_confirmation(self):
        """POST /api/estop/reset returns 400 with confirm: false."""
        app, manager, mod = _make_app()
        client = TestClient(app)

        resp = client.post("/api/estop/reset", json={"confirm": False})
        assert resp.status_code == 400

    def test_reset_clears_estop_state(self):
        """POST /api/estop/reset with confirm: true clears E-stop."""
        app, manager, mod = _make_app()
        al = _make_mock_audit_logger()
        mod.set_audit_logger(al)

        # Activate E-stop first
        manager.estop_active = True
        manager.estop_timestamp = "2026-01-01T00:00:00Z"

        client = TestClient(app)
        resp = client.post("/api/estop/reset", json={"confirm": True})

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "estop_cleared"
        assert manager.estop_active is False

    def test_reset_logs_action(self):
        """POST /api/estop/reset logs the action via AuditLogger."""
        app, manager, mod = _make_app()
        al = _make_mock_audit_logger()
        mod.set_audit_logger(al)

        manager.estop_active = True
        manager.estop_timestamp = "2026-01-01T00:00:00Z"

        client = TestClient(app)
        client.post("/api/estop/reset", json={"confirm": True})

        al.log.assert_called_once()
        call_args = al.log.call_args
        assert call_args[0][0] == "estop_reset"


# -----------------------------------------------------------------
# Tests: GET /api/safety/status (Task 2.4)
# -----------------------------------------------------------------


class TestSafetyStatusEndpoint:
    """Tests for safety status reporting."""

    def test_status_returns_all_fields(self):
        """GET /api/safety/status returns all required fields."""
        app, manager, mod = _make_app()
        client = TestClient(app)

        resp = client.get("/api/safety/status")

        assert resp.status_code == 200
        data = resp.json()
        assert "estop_active" in data
        assert "active_arms" in data
        assert "can_connected" in data
        assert "last_estop" in data

    def test_status_defaults(self):
        """GET /api/safety/status returns correct defaults."""
        app, manager, mod = _make_app()
        client = TestClient(app)

        resp = client.get("/api/safety/status")
        data = resp.json()

        assert data["estop_active"] is False
        assert data["active_arms"] == 1
        assert data["last_estop"] is None

    def test_status_reflects_estop_active(self):
        """GET /api/safety/status reflects E-stop state after activation."""
        app, manager, mod = _make_app()
        pm = _make_mock_process_manager()
        al = _make_mock_audit_logger()
        mod.set_process_manager(pm)
        mod.set_audit_logger(al)

        # Activate E-stop
        with patch.object(mod, "_send_can_estop", return_value=True):
            client = TestClient(app)
            client.post("/api/estop")

            # Now check status
            resp = client.get("/api/safety/status")

        data = resp.json()
        assert data["estop_active"] is True
        assert data["last_estop"] is not None

    def test_status_reflects_estop_cleared(self):
        """GET /api/safety/status reflects cleared state after reset."""
        app, manager, mod = _make_app()
        al = _make_mock_audit_logger()
        mod.set_audit_logger(al)

        # Set then clear
        manager.estop_active = True
        manager.estop_timestamp = "2026-01-01T00:00:00Z"

        client = TestClient(app)
        client.post("/api/estop/reset", json={"confirm": True})
        resp = client.get("/api/safety/status")

        data = resp.json()
        assert data["estop_active"] is False


# -----------------------------------------------------------------
# Tests: POST /api/emergency-shutdown (Task 2.6)
# -----------------------------------------------------------------


class TestEmergencyShutdownEndpoint:
    """Tests for emergency shutdown."""

    def test_shutdown_requires_token(self):
        """POST /api/emergency-shutdown returns 400 without token."""
        app, manager, mod = _make_app()
        client = TestClient(app)

        resp = client.post("/api/emergency-shutdown", json={})
        assert resp.status_code == 400

    def test_shutdown_rejects_wrong_token(self):
        """POST /api/emergency-shutdown returns 400 with wrong token."""
        app, manager, mod = _make_app()
        client = TestClient(app)

        resp = client.post("/api/emergency-shutdown", json={"token": "WRONG"})
        assert resp.status_code == 400

    def test_shutdown_with_correct_token_initiates(self):
        """POST /api/emergency-shutdown with SHUTDOWN token succeeds."""
        app, manager, mod = _make_app()
        pm = _make_mock_process_manager()
        al = _make_mock_audit_logger()
        mod.set_process_manager(pm)
        mod.set_audit_logger(al)

        with (
            patch.object(mod, "_send_can_estop", return_value=True),
            patch.object(mod, "_schedule_shutdown") as mock_shutdown,
        ):
            client = TestClient(app)
            resp = client.post("/api/emergency-shutdown", json={"token": "SHUTDOWN"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "shutdown_initiated"

    def test_shutdown_activates_estop_first(self):
        """POST /api/emergency-shutdown activates E-stop before shutdown."""
        app, manager, mod = _make_app()
        pm = _make_mock_process_manager()
        al = _make_mock_audit_logger()
        mod.set_process_manager(pm)
        mod.set_audit_logger(al)

        with (
            patch.object(mod, "_send_can_estop", return_value=True),
            patch.object(mod, "_schedule_shutdown"),
        ):
            client = TestClient(app)
            client.post("/api/emergency-shutdown", json={"token": "SHUTDOWN"})

        assert manager.estop_active is True

    def test_shutdown_schedules_system_shutdown(self):
        """POST /api/emergency-shutdown schedules sudo shutdown."""
        app, manager, mod = _make_app()
        pm = _make_mock_process_manager()
        al = _make_mock_audit_logger()
        mod.set_process_manager(pm)
        mod.set_audit_logger(al)

        with (
            patch.object(mod, "_send_can_estop", return_value=True),
            patch.object(mod, "_schedule_shutdown") as mock_shutdown,
        ):
            client = TestClient(app)
            client.post("/api/emergency-shutdown", json={"token": "SHUTDOWN"})

        mock_shutdown.assert_called_once()

    def test_shutdown_logs_action(self):
        """POST /api/emergency-shutdown logs the action."""
        app, manager, mod = _make_app()
        pm = _make_mock_process_manager()
        al = _make_mock_audit_logger()
        mod.set_process_manager(pm)
        mod.set_audit_logger(al)

        with (
            patch.object(mod, "_send_can_estop", return_value=True),
            patch.object(mod, "_schedule_shutdown"),
        ):
            client = TestClient(app)
            client.post("/api/emergency-shutdown", json={"token": "SHUTDOWN"})

        # Should have logged both estop and shutdown
        assert al.log.call_count >= 2
        actions = [call[0][0] for call in al.log.call_args_list]
        assert "emergency_shutdown" in actions


# -----------------------------------------------------------------
# Tests: SafetyManager class (Task 2.2)
# -----------------------------------------------------------------


class TestSafetyManager:
    """Tests for SafetyManager state tracking."""

    def test_initial_state(self):
        """SafetyManager starts with estop_active=False."""
        from backend.safety_api import SafetyManager

        sm = SafetyManager()
        assert sm.estop_active is False
        assert sm.estop_timestamp is None
        assert sm.active_arms == 1

    def test_can_connectivity_check(self):
        """SafetyManager.can_connected reflects CAN availability."""
        from backend.safety_api import SafetyManager

        sm = SafetyManager()
        # can_connected is a property -- should return bool
        assert isinstance(sm.can_connected, bool)

    def test_activate_estop(self):
        """SafetyManager.activate_estop sets state correctly."""
        from backend.safety_api import SafetyManager

        sm = SafetyManager()
        sm.activate_estop()
        assert sm.estop_active is True
        assert sm.estop_timestamp is not None

    def test_clear_estop(self):
        """SafetyManager.clear_estop resets state."""
        from backend.safety_api import SafetyManager

        sm = SafetyManager()
        sm.activate_estop()
        sm.clear_estop()
        assert sm.estop_active is False

    def test_get_status_dict(self):
        """SafetyManager.get_status returns proper dict."""
        from backend.safety_api import SafetyManager

        sm = SafetyManager()
        status = sm.get_status()
        assert "estop_active" in status
        assert "active_arms" in status
        assert "can_connected" in status
        assert "last_estop" in status


# -----------------------------------------------------------------
# Tests: Schema contract validation (dashboard-tab-wiring-fix 10.3)
# -----------------------------------------------------------------


class TestSafetyApiSchemaContract:
    """Validate safety API response schemas match frontend expectations.

    These tests verify the exact response shapes that SafetyTab.mjs
    depends on, as documented in the dashboard-tab-wiring-fix change.
    """

    def test_estop_response_schema(self):
        """POST /api/estop response has exactly the expected fields."""
        app, manager, mod = _make_app()
        pm = _make_mock_process_manager()
        al = _make_mock_audit_logger()
        mod.set_process_manager(pm)
        mod.set_audit_logger(al)

        with patch.object(mod, "_send_can_estop", return_value=True):
            client = TestClient(app)
            resp = client.post("/api/estop")

        data = resp.json()
        expected_keys = {"status", "can_sent", "processes_stopped"}
        assert set(data.keys()) == expected_keys
        assert data["status"] == "estop_activated"
        assert isinstance(data["can_sent"], bool)
        assert isinstance(data["processes_stopped"], int)

    def test_estop_reset_response_schema(self):
        """POST /api/estop/reset response has exactly the expected fields."""
        app, manager, mod = _make_app()
        al = _make_mock_audit_logger()
        mod.set_audit_logger(al)
        manager.estop_active = True

        client = TestClient(app)
        resp = client.post("/api/estop/reset", json={"confirm": True})

        data = resp.json()
        assert set(data.keys()) == {"status"}
        assert data["status"] == "estop_cleared"

    def test_safety_status_response_schema(self):
        """GET /api/safety/status response has exactly the expected fields."""
        app, manager, mod = _make_app()
        client = TestClient(app)

        resp = client.get("/api/safety/status")

        data = resp.json()
        expected_keys = {
            "estop_active",
            "active_arms",
            "can_connected",
            "last_estop",
        }
        assert set(data.keys()) == expected_keys
        assert isinstance(data["estop_active"], bool)
        assert isinstance(data["active_arms"], int)
        assert isinstance(data["can_connected"], bool)

    def test_safety_status_types_after_estop(self):
        """Status field types remain correct after E-stop activation."""
        app, manager, mod = _make_app()
        pm = _make_mock_process_manager()
        al = _make_mock_audit_logger()
        mod.set_process_manager(pm)
        mod.set_audit_logger(al)

        with patch.object(mod, "_send_can_estop", return_value=True):
            client = TestClient(app)
            client.post("/api/estop")
            resp = client.get("/api/safety/status")

        data = resp.json()
        assert data["estop_active"] is True
        assert isinstance(data["last_estop"], str)
        assert isinstance(data["active_arms"], int)
