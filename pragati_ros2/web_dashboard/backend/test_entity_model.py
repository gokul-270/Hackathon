"""Unit tests for Entity data model (Task 2.1, 2.10a).

Tests cover:
- Entity creation with required and default fields
- to_dict() serialization (including datetime handling)
- add_error() with capping at 10 entries
- Default system_metrics structure
- Edge cases: empty strings, None values
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.entity_model import Entity

# ===================================================================
# Entity creation
# ===================================================================


class TestEntityCreation:
    """Test Entity dataclass instantiation."""

    def test_minimal_creation(self):
        e = Entity(id="arm1", name="Arm 1", entity_type="arm", source="remote")
        assert e.id == "arm1"
        assert e.name == "Arm 1"
        assert e.entity_type == "arm"
        assert e.source == "remote"

    def test_default_ip_is_none(self):
        e = Entity(id="local", name="Local", entity_type="vehicle", source="local")
        assert e.ip is None

    def test_default_status_is_unknown(self):
        e = Entity(id="arm1", name="Arm 1", entity_type="arm", source="remote")
        assert e.status == "unknown"

    def test_default_health_has_all_layer_fields(self):
        e = Entity(id="arm1", name="Arm 1", entity_type="arm", source="remote")
        assert e.health == {
            "network": "unknown",
            "network_latency_ms": None,
            "agent": "unknown",
            "agent_warnings": [],
            "mqtt": "unknown",
            "mqtt_arm_state": None,
            "mqtt_last_seen": None,
            "ros2": "unknown",
            "ros2_node_count": None,
            "composite": "unknown",
            "diagnostic": "Health check initializing",
        }

    def test_default_last_seen_is_none(self):
        e = Entity(id="arm1", name="Arm 1", entity_type="arm", source="remote")
        assert e.last_seen is None

    def test_default_ros2_available_is_false(self):
        e = Entity(id="arm1", name="Arm 1", entity_type="arm", source="remote")
        assert e.ros2_available is False

    def test_default_ros2_state_is_none(self):
        e = Entity(id="arm1", name="Arm 1", entity_type="arm", source="remote")
        assert e.ros2_state is None

    def test_default_services_is_empty_list(self):
        e = Entity(id="arm1", name="Arm 1", entity_type="arm", source="remote")
        assert e.services == []

    def test_default_errors_is_empty_list(self):
        e = Entity(id="arm1", name="Arm 1", entity_type="arm", source="remote")
        assert e.errors == []

    def test_default_metadata_is_empty_dict(self):
        e = Entity(id="arm1", name="Arm 1", entity_type="arm", source="remote")
        assert e.metadata == {}

    def test_with_ip(self):
        e = Entity(
            id="arm1",
            name="Arm 1",
            entity_type="arm",
            source="remote",
            ip="192.168.1.10",
        )
        assert e.ip == "192.168.1.10"

    def test_with_all_fields(self):
        now = datetime.now(timezone.utc)
        e = Entity(
            id="arm1",
            name="Arm 1",
            entity_type="arm",
            source="remote",
            ip="192.168.1.10",
            status="online",
            last_seen=now,
            ros2_available=True,
            ros2_state={"node_count": 5, "topic_count": 10},
            services=[{"name": "motor_control"}],
            errors=["timeout once"],
            metadata={"user": "ubuntu"},
        )
        assert e.status == "online"
        assert e.last_seen == now
        assert e.ros2_available is True
        assert e.ros2_state["node_count"] == 5
        assert len(e.services) == 1
        assert len(e.errors) == 1
        assert e.metadata["user"] == "ubuntu"


# ===================================================================
# Default system_metrics structure
# ===================================================================


class TestDefaultSystemMetrics:
    """Test default system_metrics dict has expected keys."""

    def test_has_cpu_percent(self):
        e = Entity(id="arm1", name="Arm 1", entity_type="arm", source="remote")
        assert "cpu_percent" in e.system_metrics
        assert e.system_metrics["cpu_percent"] is None

    def test_has_memory_percent(self):
        e = Entity(id="arm1", name="Arm 1", entity_type="arm", source="remote")
        assert "memory_percent" in e.system_metrics
        assert e.system_metrics["memory_percent"] is None

    def test_has_temperature_c(self):
        e = Entity(id="arm1", name="Arm 1", entity_type="arm", source="remote")
        assert "temperature_c" in e.system_metrics
        assert e.system_metrics["temperature_c"] is None

    def test_has_disk_percent(self):
        e = Entity(id="arm1", name="Arm 1", entity_type="arm", source="remote")
        assert "disk_percent" in e.system_metrics
        assert e.system_metrics["disk_percent"] is None

    def test_has_uptime_seconds(self):
        e = Entity(id="arm1", name="Arm 1", entity_type="arm", source="remote")
        assert "uptime_seconds" in e.system_metrics
        assert e.system_metrics["uptime_seconds"] is None

    def test_system_metrics_not_shared_between_instances(self):
        """Each Entity gets its own metrics dict (no mutable default sharing)."""
        e1 = Entity(id="arm1", name="A1", entity_type="arm", source="remote")
        e2 = Entity(id="arm2", name="A2", entity_type="arm", source="remote")
        e1.system_metrics["cpu_percent"] = 50.0
        assert e2.system_metrics["cpu_percent"] is None

    def test_system_metrics_has_motor_temperatures_default_none(self):
        e = Entity(id="arm1", name="Arm 1", entity_type="arm", source="remote")
        assert "motor_temperatures" in e.system_metrics
        assert e.system_metrics["motor_temperatures"] is None

    def test_system_metrics_has_camera_temperature_default_none(self):
        e = Entity(id="arm1", name="Arm 1", entity_type="arm", source="remote")
        assert "camera_temperature_c" in e.system_metrics
        assert e.system_metrics["camera_temperature_c"] is None

    def test_system_metrics_motor_temperatures_updated(self):
        e = Entity(id="arm1", name="Arm 1", entity_type="arm", source="remote")
        e.system_metrics["motor_temperatures"] = {"joint1": 45.2}
        assert e.system_metrics["motor_temperatures"] == {"joint1": 45.2}

    def test_system_metrics_camera_temperature_updated(self):
        e = Entity(id="arm1", name="Arm 1", entity_type="arm", source="remote")
        e.system_metrics["camera_temperature_c"] = 52.3
        assert e.system_metrics["camera_temperature_c"] == 52.3


# ===================================================================
# to_dict() serialization
# ===================================================================


class TestToDict:
    """Test to_dict() produces JSON-safe output."""

    def test_returns_dict(self):
        e = Entity(id="arm1", name="Arm 1", entity_type="arm", source="remote")
        result = e.to_dict()
        assert isinstance(result, dict)

    def test_all_keys_present(self):
        e = Entity(id="arm1", name="Arm 1", entity_type="arm", source="remote")
        result = e.to_dict()
        expected_keys = {
            "id",
            "member_id",
            "name",
            "entity_type",
            "source",
            "ip",
            "port",
            "network_context",
            "group_id",
            "slot",
            "membership_state",
            "status",
            "health",
            "last_seen",
            "system_metrics",
            "ros2_available",
            "ros2_state",
            "services",
            "errors",
            "metadata",
        }
        assert set(result.keys()) == expected_keys

    def test_last_seen_none_serializes_to_none(self):
        e = Entity(id="arm1", name="Arm 1", entity_type="arm", source="remote")
        result = e.to_dict()
        assert result["last_seen"] is None

    def test_last_seen_datetime_serializes_to_isoformat(self):
        now = datetime(2026, 3, 9, 12, 0, 0, tzinfo=timezone.utc)
        e = Entity(
            id="arm1",
            name="Arm 1",
            entity_type="arm",
            source="remote",
            last_seen=now,
        )
        result = e.to_dict()
        assert result["last_seen"] == "2026-03-09T12:00:00+00:00"

    def test_values_match_fields(self):
        e = Entity(
            id="arm1",
            name="Arm 1",
            entity_type="arm",
            source="remote",
            ip="10.0.0.1",
            status="online",
        )
        result = e.to_dict()
        assert result["id"] == "arm1"
        assert result["name"] == "Arm 1"
        assert result["entity_type"] == "arm"
        assert result["source"] == "remote"
        assert result["ip"] == "10.0.0.1"
        assert result["status"] == "online"

    def test_health_object_serializes_in_api_dict(self):
        e = Entity(id="arm1", name="Arm 1", entity_type="arm", source="remote")
        result = e.to_dict()
        assert result["health"] == e.health


class TestCompositeHealth:
    """Test composite health derivation and backward compatibility."""

    @pytest.mark.parametrize(
        ("health", "expected_composite", "expected_diagnostic"),
        [
            (
                {
                    "network": "reachable",
                    "agent": "alive",
                    "mqtt": "active",
                    "ros2": "healthy",
                },
                "online",
                "All systems operational",
            ),
            (
                {
                    "network": "unreachable",
                    "agent": "alive",
                    "mqtt": "active",
                    "ros2": "healthy",
                },
                "unreachable",
                "Host not reachable on network",
            ),
            (
                {
                    "network": "reachable",
                    "agent": "down",
                    "mqtt": "disabled",
                    "ros2": "healthy",
                },
                "offline",
                "Agent not responding",
            ),
        ],
    )
    def test_status_mirrors_composite_health(self, health, expected_composite, expected_diagnostic):
        e = Entity(id="arm1", name="Arm 1", entity_type="arm", source="remote")
        e.update_health(**health)
        assert e.health["composite"] == expected_composite
        assert e.health["diagnostic"] == expected_diagnostic
        assert e.status == expected_composite

    @pytest.mark.parametrize(
        ("health", "expected_composite", "expected_diagnostic"),
        [
            (
                {
                    "network": "reachable",
                    "agent": "alive",
                    "mqtt": "active",
                    "ros2": "down",
                },
                "degraded",
                "ROS2 stack is down",
            ),
            (
                {
                    "network": "reachable",
                    "agent": "down",
                    "mqtt": "active",
                    "ros2": "healthy",
                },
                "degraded",
                "Agent not responding but ARM application is active via MQTT",
            ),
            (
                {
                    "network": "reachable",
                    "agent": "alive",
                    "mqtt": "disabled",
                    "ros2": "healthy",
                },
                "online",
                "MQTT not configured",
            ),
            (
                {
                    "network": "unknown",
                    "agent": "unknown",
                    "mqtt": "unknown",
                    "ros2": "unknown",
                },
                "unknown",
                "Health check initializing",
            ),
            # MQTT broker down but ROS2 healthy → online (non-critical)
            (
                {
                    "network": "reachable",
                    "agent": "alive",
                    "mqtt": "broker_down",
                    "ros2": "healthy",
                },
                "online",
                "MQTT broker unreachable (non-critical)",
            ),
            # MQTT broker down AND ROS2 down → degraded (ROS2 check takes priority)
            (
                {
                    "network": "reachable",
                    "agent": "alive",
                    "mqtt": "broker_down",
                    "ros2": "down",
                },
                "degraded",
                "ROS2 stack is down",
            ),
        ],
    )
    def test_additional_composite_health_priority_rules(
        self, health, expected_composite, expected_diagnostic
    ):
        e = Entity(id="arm1", name="Arm 1", entity_type="arm", source="remote")
        e.update_health(**health)
        assert e.health["composite"] == expected_composite
        assert e.health["diagnostic"] == expected_diagnostic

    def test_system_metrics_in_dict(self):
        e = Entity(id="arm1", name="Arm 1", entity_type="arm", source="remote")
        e.system_metrics["cpu_percent"] = 42.5
        result = e.to_dict()
        assert result["system_metrics"]["cpu_percent"] == 42.5

    def test_ros2_state_in_dict(self):
        e = Entity(
            id="arm1",
            name="Arm 1",
            entity_type="arm",
            source="remote",
            ros2_state={"node_count": 3},
        )
        result = e.to_dict()
        assert result["ros2_state"]["node_count"] == 3

    def test_services_in_dict(self):
        e = Entity(
            id="arm1",
            name="Arm 1",
            entity_type="arm",
            source="remote",
            services=[{"name": "svc1"}],
        )
        result = e.to_dict()
        assert result["services"] == [{"name": "svc1"}]

    def test_metadata_in_dict(self):
        e = Entity(
            id="arm1",
            name="Arm 1",
            entity_type="arm",
            source="remote",
            metadata={"user": "ubuntu"},
        )
        result = e.to_dict()
        assert result["metadata"]["user"] == "ubuntu"


# ===================================================================
# add_error() with capping
# ===================================================================


class TestAddError:
    """Test add_error() appends and caps at 10."""

    def test_add_single_error(self):
        e = Entity(id="arm1", name="Arm 1", entity_type="arm", source="remote")
        e.add_error("connection timeout")
        assert len(e.errors) == 1
        assert e.errors[0] == "connection timeout"

    def test_add_multiple_errors(self):
        e = Entity(id="arm1", name="Arm 1", entity_type="arm", source="remote")
        e.add_error("error 1")
        e.add_error("error 2")
        e.add_error("error 3")
        assert len(e.errors) == 3

    def test_cap_at_10(self):
        e = Entity(id="arm1", name="Arm 1", entity_type="arm", source="remote")
        for i in range(15):
            e.add_error(f"error {i}")
        assert len(e.errors) == 10

    def test_cap_keeps_most_recent(self):
        e = Entity(id="arm1", name="Arm 1", entity_type="arm", source="remote")
        for i in range(15):
            e.add_error(f"error {i}")
        # Should keep errors 5-14 (the last 10)
        assert e.errors[0] == "error 5"
        assert e.errors[-1] == "error 14"

    def test_exactly_10_errors_no_truncation(self):
        e = Entity(id="arm1", name="Arm 1", entity_type="arm", source="remote")
        for i in range(10):
            e.add_error(f"error {i}")
        assert len(e.errors) == 10
        assert e.errors[0] == "error 0"
        assert e.errors[-1] == "error 9"

    def test_11th_error_drops_first(self):
        e = Entity(id="arm1", name="Arm 1", entity_type="arm", source="remote")
        for i in range(11):
            e.add_error(f"error {i}")
        assert len(e.errors) == 10
        assert e.errors[0] == "error 1"
        assert e.errors[-1] == "error 10"
