"""Tests for no-ROS2 graceful degradation (task 2.5).

Validates that the dashboard backend functions correctly when ROS2 (rclpy)
is not installed or not running:

1. system_state defaults to ros2_available=False
2. /api/performance/summary returns psutil data with null ROS2 fields
3. HealthMonitoringService reports subsystems as "unavailable" when ROS2 is down
4. _enhanced_services_available() dynamically re-evaluates at runtime
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ── 1. system_state defaults to ros2_available=False ──────────────────────


class TestSystemStateRos2AvailableDefault:
    """Verify system_state["ros2_available"] is False at import time."""

    def test_system_state_ros2_available_false_by_default(self):
        """system_state starts with ros2_available=False before any
        ROS2Monitor has updated it."""
        from backend.ros2_monitor import system_state

        assert "ros2_available" in system_state
        assert system_state["ros2_available"] is False

    def test_system_state_has_required_keys(self):
        """system_state has the expected top-level keys for degraded mode."""
        from backend.ros2_monitor import system_state

        expected_keys = {
            "ros2_available",
            "nodes",
            "topics",
            "services",
            "parameters",
            "system_health",
            "pragati_status",
            "logs",
            "last_update",
        }
        assert expected_keys.issubset(system_state.keys())


# ── 2. /api/performance/summary returns psutil data with null ROS2 ────────


class TestPerformanceSummaryDegradedMode:
    """GET /api/performance/summary returns 200 with psutil metrics and
    null ROS2 fields when enhanced services are not available."""

    def _make_app(self) -> FastAPI:
        """Create a minimal FastAPI app with the performance router."""
        from backend.api_routes_performance import (
            init_performance_deps,
            router,
        )
        from backend.ros2_monitor import system_state

        app = FastAPI()
        app.include_router(router)
        init_performance_deps(system_state)
        return app

    def test_summary_returns_200(self):
        """Endpoint returns 200 even without enhanced services."""
        client = TestClient(self._make_app())
        resp = client.get("/api/performance/summary")
        assert resp.status_code == 200

    def test_summary_has_system_psutil_fields(self):
        """Response contains system.cpu_percent, memory_percent,
        disk_usage_percent populated from psutil."""
        client = TestClient(self._make_app())
        data = client.get("/api/performance/summary").json()

        system = data["system"]
        assert "cpu_percent" in system
        assert "memory_percent" in system
        assert "disk_usage_percent" in system
        # psutil values are numeric, not None
        assert isinstance(system["cpu_percent"], (int, float))
        assert isinstance(system["memory_percent"], (int, float))
        assert isinstance(system["disk_usage_percent"], (int, float))

    def test_summary_ros2_fields_null_when_no_monitor(self):
        """ROS2-specific fields are null when the enhanced performance
        monitor is not running."""
        # Patch _enhanced_services_available to return False
        with patch(
            "backend.api_routes_performance._enhanced_services_available",
            return_value=False,
        ):
            client = TestClient(self._make_app())
            data = client.get("/api/performance/summary").json()

        ros2 = data["ros2"]
        assert ros2["node_count"] is None
        assert ros2["topic_count"] is None

    def test_summary_has_timestamp(self):
        """Response includes an ISO timestamp."""
        client = TestClient(self._make_app())
        data = client.get("/api/performance/summary").json()
        assert "timestamp" in data
        assert isinstance(data["timestamp"], str)


# ── 3. HealthMonitoringService subsystem statuses = "unavailable" ─────────


class TestHealthMonitoringServiceDegradedMode:
    """When ROS2 is not available, get_system_health() reports all
    subsystems as "unavailable"."""

    def _make_service(self):
        """Create a fresh HealthMonitoringService (no ROS2 node)."""
        from backend.health_monitoring_service import (
            HealthMonitoringService,
        )

        return HealthMonitoringService(node=None)

    @patch("backend.ros2_monitor.ROS2_AVAILABLE", False)
    def test_motors_status_unavailable_when_ros2_down(self):
        """motors.status is "unavailable" when ROS2 is not available."""
        svc = self._make_service()
        health = svc.get_system_health()
        assert health["motors"]["status"] == "unavailable"

    @patch("backend.ros2_monitor.ROS2_AVAILABLE", False)
    def test_can_bus_status_unavailable_when_ros2_down(self):
        """can_bus.status is "unavailable" when ROS2 is not available."""
        svc = self._make_service()
        health = svc.get_system_health()
        assert health["can_bus"]["status"] == "unavailable"

    @patch("backend.ros2_monitor.ROS2_AVAILABLE", False)
    def test_safety_status_unavailable_when_ros2_down(self):
        """safety.status is "unavailable" when ROS2 is not available."""
        svc = self._make_service()
        health = svc.get_system_health()
        assert health["safety"]["status"] == "unavailable"

    @patch("backend.ros2_monitor.ROS2_AVAILABLE", False)
    def test_detection_status_unavailable_when_ros2_down(self):
        """detection.status is "unavailable" when ROS2 is not available."""
        svc = self._make_service()
        health = svc.get_system_health()
        assert health["detection"]["status"] == "unavailable"

    @patch("backend.ros2_monitor.ROS2_AVAILABLE", False)
    def test_overall_status_unknown_when_ros2_down(self):
        """overall_status is "unknown" when ROS2 is not available."""
        svc = self._make_service()
        health = svc.get_system_health()
        assert health["overall_status"] == "unknown"

    @patch("backend.ros2_monitor.ROS2_AVAILABLE", False)
    def test_health_response_structure(self):
        """get_system_health() returns all expected top-level keys."""
        svc = self._make_service()
        health = svc.get_system_health()
        expected_keys = {
            "timestamp",
            "overall_status",
            "motors",
            "can_bus",
            "safety",
            "detection",
            "summary",
        }
        assert expected_keys == set(health.keys())

    @patch("backend.ros2_monitor.ROS2_AVAILABLE", False)
    def test_summary_counts_zero_when_ros2_down(self):
        """summary.critical_issues / errors / warnings / healthy are
        all 0 when ROS2 is down and no motors are registered."""
        svc = self._make_service()
        health = svc.get_system_health()
        summary = health["summary"]
        assert summary["critical_issues"] == 0
        assert summary["errors"] == 0
        assert summary["warnings"] == 0
        assert summary["healthy"] == 0


# ── 4. _enhanced_services_available() runtime re-evaluation ───────────────


class TestEnhancedServicesAvailableRuntime:
    """_enhanced_services_available() should dynamically check if the
    performance monitor is available at call time."""

    def test_returns_false_when_get_performance_monitor_is_none(self):
        """Returns False when get_performance_monitor is None
        (enhanced services failed to import)."""
        with patch(
            "backend.api_routes_performance.get_performance_monitor",
            None,
        ):
            from backend.api_routes_performance import (
                _enhanced_services_available,
            )

            assert _enhanced_services_available() is False

    def test_returns_false_when_monitor_returns_none(self):
        """Returns False when get_performance_monitor() returns None
        (monitor not yet initialized)."""
        mock_getter = MagicMock(return_value=None)
        with patch(
            "backend.api_routes_performance.get_performance_monitor",
            mock_getter,
        ):
            from backend.api_routes_performance import (
                _enhanced_services_available,
            )

            assert _enhanced_services_available() is False

    def test_returns_true_when_monitor_is_available(self):
        """Returns True when get_performance_monitor() returns a real
        monitor object."""
        mock_monitor = MagicMock()
        mock_getter = MagicMock(return_value=mock_monitor)
        with patch(
            "backend.api_routes_performance.get_performance_monitor",
            mock_getter,
        ):
            from backend.api_routes_performance import (
                _enhanced_services_available,
            )

            assert _enhanced_services_available() is True

    def test_reevaluates_on_each_call(self):
        """Successive calls reflect changes in monitor availability
        (not cached from import time)."""
        from backend.api_routes_performance import (
            _enhanced_services_available,
        )

        # First call: monitor not available
        mock_getter_none = MagicMock(return_value=None)
        with patch(
            "backend.api_routes_performance.get_performance_monitor",
            mock_getter_none,
        ):
            assert _enhanced_services_available() is False

        # Second call: monitor becomes available
        mock_monitor = MagicMock()
        mock_getter_real = MagicMock(return_value=mock_monitor)
        with patch(
            "backend.api_routes_performance.get_performance_monitor",
            mock_getter_real,
        ):
            assert _enhanced_services_available() is True

    def test_returns_false_on_exception(self):
        """Returns False if get_performance_monitor raises an exception."""
        mock_getter = MagicMock(side_effect=RuntimeError("boom"))
        with patch(
            "backend.api_routes_performance.get_performance_monitor",
            mock_getter,
        ):
            from backend.api_routes_performance import (
                _enhanced_services_available,
            )

            assert _enhanced_services_available() is False
