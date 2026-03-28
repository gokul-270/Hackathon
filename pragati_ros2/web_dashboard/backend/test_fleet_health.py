"""DEPRECATED: Tests for fleet_health_service.py (legacy fleet polling). The entity
manager (entity_manager.py) replaces fleet health polling. These tests remain until
fleet_health_service.py is removed in a follow-up change.
See openspec/changes/dashboard-entity-core/design.md D7."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import httpx

# ---------------------------------------------------------------------------
# Mock paho-mqtt BEFORE importing implementation modules
# ---------------------------------------------------------------------------
_mock_paho = MagicMock()
_mock_paho_client_instance = MagicMock()
_mock_paho.Client = MagicMock(return_value=_mock_paho_client_instance)

import sys

sys.modules.setdefault("paho", MagicMock())
sys.modules.setdefault("paho.mqtt", MagicMock())
sys.modules.setdefault("paho.mqtt.client", _mock_paho)

from backend.fleet_health_service import FleetHealthService  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_FLEET_CONFIG = {
    "vehicle": {"name": "vehicle-rpi", "ip": "192.168.1.100", "role": "vehicle"},
    "arms": [
        {"name": "arm1-rpi", "ip": "192.168.1.101", "role": "arm"},
        {"name": "arm2-rpi", "ip": "192.168.1.102", "role": "arm"},
    ],
}


def _make_service(fleet_config=None):
    """Create a FleetHealthService with given fleet config."""
    if fleet_config is None:
        fleet_config = SAMPLE_FLEET_CONFIG
    return FleetHealthService(fleet_config)


def _make_health_response(
    status_code=200,
    cpu=45.2,
    memory=62.1,
):
    """Create a mock httpx response with health data."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = {
        "status": "ok",
        "cpu_percent": cpu,
        "memory_percent": memory,
    }
    return mock_resp


# ===================================================================
# Task 4.4 Test 3 — Empty fleet config
# ===================================================================


class TestEmptyFleetConfig:
    """Test empty/absent fleet config returns empty list."""

    def test_none_config_returns_empty_status(self):
        svc = FleetHealthService(None)
        assert svc.get_fleet_status() == []

    def test_empty_dict_returns_empty_status(self):
        svc = FleetHealthService({})
        assert svc.get_fleet_status() == []

    def test_no_arms_no_vehicle_returns_empty_status(self):
        svc = FleetHealthService({"vehicle": None, "arms": None})
        assert svc.get_fleet_status() == []

    def test_empty_arms_list_with_empty_vehicle(self):
        svc = FleetHealthService(
            {"vehicle": {"name": "", "ip": "", "role": "vehicle"}, "arms": []}
        )
        # Vehicle with empty IP should be skipped
        assert svc.get_fleet_status() == []


# ===================================================================
# Task 4.4 Test 4 — Fleet config parsing
# ===================================================================


class TestFleetConfigParsing:
    """Test fleet config produces correct number of members."""

    def test_vehicle_plus_two_arms(self):
        svc = _make_service()
        members = svc.get_fleet_status()
        assert len(members) == 3

    def test_member_names_match_config(self):
        svc = _make_service()
        members = svc.get_fleet_status()
        names = {m["name"] for m in members}
        assert names == {"vehicle-rpi", "arm1-rpi", "arm2-rpi"}

    def test_member_roles_match_config(self):
        svc = _make_service()
        members = svc.get_fleet_status()
        role_map = {m["name"]: m["role"] for m in members}
        assert role_map["vehicle-rpi"] == "vehicle"
        assert role_map["arm1-rpi"] == "arm"
        assert role_map["arm2-rpi"] == "arm"

    def test_member_ips_match_config(self):
        svc = _make_service()
        members = svc.get_fleet_status()
        ip_map = {m["name"]: m["ip"] for m in members}
        assert ip_map["vehicle-rpi"] == "192.168.1.100"
        assert ip_map["arm1-rpi"] == "192.168.1.101"
        assert ip_map["arm2-rpi"] == "192.168.1.102"

    def test_initial_status_is_unknown(self):
        svc = _make_service()
        members = svc.get_fleet_status()
        for m in members:
            assert m["status"] == "unknown"

    def test_initial_metrics_are_none(self):
        svc = _make_service()
        members = svc.get_fleet_status()
        for m in members:
            assert m["cpu_percent"] is None
            assert m["memory_percent"] is None
            assert m["last_seen"] is None

    def test_initial_operational_state(self):
        svc = _make_service()
        members = svc.get_fleet_status()
        for m in members:
            assert m["operational_state"] == "UNKNOWN"
            assert m["pick_count"] == 0

    def test_vehicle_only_config(self):
        config = {
            "vehicle": {"name": "v1", "ip": "10.0.0.1", "role": "vehicle"},
            "arms": [],
        }
        svc = FleetHealthService(config)
        members = svc.get_fleet_status()
        assert len(members) == 1
        assert members[0]["name"] == "v1"

    def test_arms_only_config(self):
        config = {
            "vehicle": None,
            "arms": [{"name": "a1", "ip": "10.0.0.2", "role": "arm"}],
        }
        svc = FleetHealthService(config)
        members = svc.get_fleet_status()
        assert len(members) == 1
        assert members[0]["name"] == "a1"


# ===================================================================
# Task 4.4 Test 1 — HTTP health polling
# ===================================================================


class TestHealthPollingOnline:
    """Test online RPi returns health data with status 'online'."""

    @pytest.mark.asyncio
    async def test_successful_poll_sets_online(self):
        svc = _make_service()
        mock_resp = _make_health_response(cpu=50.0, memory=70.0)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("backend.fleet_health_service.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await svc._poll_member_health(svc._members[0])

        member = svc._members[0]
        assert member["status"] == "online"
        assert member["cpu_percent"] == 50.0
        assert member["memory_percent"] == 70.0
        assert member["last_seen"] is not None


class TestHealthPollingTimeout:
    """Test timeout RPi marked offline, retains last-known metrics."""

    @pytest.mark.asyncio
    async def test_timeout_marks_offline(self):
        svc = _make_service()
        # First, set member to online with metrics
        svc._members[0]["status"] = "online"
        svc._members[0]["cpu_percent"] = 45.0
        svc._members[0]["memory_percent"] = 60.0
        svc._members[0]["last_seen"] = "2026-01-01T00:00:00+00:00"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))

        with patch("backend.fleet_health_service.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await svc._poll_member_health(svc._members[0])

        member = svc._members[0]
        assert member["status"] == "offline"
        # Last-known metrics retained
        assert member["cpu_percent"] == 45.0
        assert member["memory_percent"] == 60.0
        # last_seen NOT updated (stays at old value)
        assert member["last_seen"] == "2026-01-01T00:00:00+00:00"


class TestHealthPollingRecovery:
    """Test recovery after timeout -> status back to online."""

    @pytest.mark.asyncio
    async def test_recovery_updates_to_online(self):
        svc = _make_service()
        # Start offline
        svc._members[0]["status"] = "offline"
        svc._members[0]["cpu_percent"] = 45.0
        svc._members[0]["memory_percent"] = 60.0

        mock_resp = _make_health_response(cpu=55.0, memory=72.0)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("backend.fleet_health_service.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await svc._poll_member_health(svc._members[0])

        member = svc._members[0]
        assert member["status"] == "online"
        assert member["cpu_percent"] == 55.0
        assert member["memory_percent"] == 72.0
        assert member["last_seen"] is not None


class TestHealthPollingConnectionError:
    """Test connection error (not just timeout) also marks offline."""

    @pytest.mark.asyncio
    async def test_connect_error_marks_offline(self):
        svc = _make_service()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))

        with patch("backend.fleet_health_service.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await svc._poll_member_health(svc._members[0])

        assert svc._members[0]["status"] == "offline"


# ===================================================================
# Task 4.4 Test 2 — MQTT message parsing
# ===================================================================


class TestMqttStatusMessage:
    """Test MQTT status message updates operational_state."""

    def test_status_message_updates_operational_state(self):
        svc = _make_service()
        # Simulate MQTT message for arm1-rpi
        svc._on_mqtt_message(
            "pragati/arm1-rpi/status",
            json.dumps({"state": "DETECTING"}),
        )

        members = svc.get_fleet_status()
        arm1 = next(m for m in members if m["name"] == "arm1-rpi")
        assert arm1["operational_state"] == "DETECTING"

    def test_status_message_idle(self):
        svc = _make_service()
        svc._on_mqtt_message(
            "pragati/arm2-rpi/status",
            json.dumps({"state": "IDLE"}),
        )

        members = svc.get_fleet_status()
        arm2 = next(m for m in members if m["name"] == "arm2-rpi")
        assert arm2["operational_state"] == "IDLE"

    def test_status_message_error(self):
        svc = _make_service()
        svc._on_mqtt_message(
            "pragati/arm1-rpi/status",
            json.dumps({"state": "ERROR"}),
        )

        members = svc.get_fleet_status()
        arm1 = next(m for m in members if m["name"] == "arm1-rpi")
        assert arm1["operational_state"] == "ERROR"

    def test_status_message_picking(self):
        svc = _make_service()
        svc._on_mqtt_message(
            "pragati/arm1-rpi/status",
            json.dumps({"state": "PICKING"}),
        )

        members = svc.get_fleet_status()
        arm1 = next(m for m in members if m["name"] == "arm1-rpi")
        assert arm1["operational_state"] == "PICKING"

    def test_status_unknown_member_ignored(self):
        svc = _make_service()
        # Should not raise for unknown member
        svc._on_mqtt_message(
            "pragati/unknown-rpi/status",
            json.dumps({"state": "IDLE"}),
        )
        members = svc.get_fleet_status()
        names = {m["name"] for m in members}
        assert "unknown-rpi" not in names

    def test_invalid_json_ignored(self):
        svc = _make_service()
        # Should not raise
        svc._on_mqtt_message("pragati/arm1-rpi/status", "not json {{{")
        members = svc.get_fleet_status()
        arm1 = next(m for m in members if m["name"] == "arm1-rpi")
        assert arm1["operational_state"] == "UNKNOWN"


class TestMqttPickStart:
    """Test MQTT pick_start message increments pick_count."""

    def test_pick_start_increments_count(self):
        svc = _make_service()
        svc._on_mqtt_message("pragati/arm1-rpi/pick_start", "{}")

        members = svc.get_fleet_status()
        arm1 = next(m for m in members if m["name"] == "arm1-rpi")
        assert arm1["pick_count"] == 1

    def test_multiple_picks_accumulate(self):
        svc = _make_service()
        svc._on_mqtt_message("pragati/arm1-rpi/pick_start", "{}")
        svc._on_mqtt_message("pragati/arm1-rpi/pick_start", "{}")
        svc._on_mqtt_message("pragati/arm1-rpi/pick_start", "{}")

        members = svc.get_fleet_status()
        arm1 = next(m for m in members if m["name"] == "arm1-rpi")
        assert arm1["pick_count"] == 3

    def test_pick_start_different_arms(self):
        svc = _make_service()
        svc._on_mqtt_message("pragati/arm1-rpi/pick_start", "{}")
        svc._on_mqtt_message("pragati/arm2-rpi/pick_start", "{}")
        svc._on_mqtt_message("pragati/arm2-rpi/pick_start", "{}")

        members = svc.get_fleet_status()
        arm1 = next(m for m in members if m["name"] == "arm1-rpi")
        arm2 = next(m for m in members if m["name"] == "arm2-rpi")
        assert arm1["pick_count"] == 1
        assert arm2["pick_count"] == 2

    def test_pick_start_unknown_member_ignored(self):
        svc = _make_service()
        svc._on_mqtt_message("pragati/unknown/pick_start", "{}")
        members = svc.get_fleet_status()
        # No new member added
        assert len(members) == 3


class TestMqttVehicleShutdown:
    """Test MQTT vehicle shutdown message is handled."""

    def test_vehicle_shutdown_logged(self):
        svc = _make_service()
        # Should not raise
        svc._on_mqtt_message(
            "pragati/vehicle/shutdown",
            json.dumps({"reason": "user_request"}),
        )


# ===================================================================
# Lifecycle tests
# ===================================================================


class TestLifecycle:
    """Test start/stop lifecycle methods."""

    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        svc = _make_service()

        # Mock MQTT to not actually connect
        with patch.object(svc, "_start_mqtt"):
            await svc.start()
            assert svc._running is True

            await svc.stop()
            assert svc._running is False

    @pytest.mark.asyncio
    async def test_stop_cancels_poll_task(self):
        svc = _make_service()

        with patch.object(svc, "_start_mqtt"):
            await svc.start()

        # Should have a poll task
        assert svc._poll_task is not None

        await svc.stop()
        assert svc._poll_task is None


class TestMqttBrokerUnreachable:
    """Test MQTT broker unreachable is handled gracefully."""

    def test_mqtt_connect_failure_does_not_raise(self):
        svc = _make_service()
        # Force paho client to raise on connect
        mock_client = MagicMock()
        mock_client.connect.side_effect = OSError("Connection refused")
        svc._mqtt_client = mock_client

        # Should not raise
        svc._start_mqtt()

    def test_no_paho_available_still_works(self):
        """Service works without paho-mqtt installed."""
        svc = _make_service()
        svc._mqtt_client = None

        # start_mqtt should be a no-op
        svc._start_mqtt()

        # Service still returns fleet status
        members = svc.get_fleet_status()
        assert len(members) == 3


# ===================================================================
# Service registry import test (Task 4.3)
# ===================================================================


class TestServiceRegistryIntegration:
    """Test FleetHealthService is importable from service_registry."""

    def test_fleet_health_available_flag_exists(self):
        from backend.service_registry import FLEET_HEALTH_AVAILABLE

        assert isinstance(FLEET_HEALTH_AVAILABLE, bool)

    def test_get_fleet_health_service_accessor(self):
        from backend.service_registry import get_fleet_health_service

        # Initially None (not started)
        result = get_fleet_health_service()
        assert result is None
