"""Tests for callable functions extracted from ros2_monitor.py (Task 2.9).

These functions allow entity_ros2_router to call directly for local entity
data instead of going through HTTP. Each function reads from the shared
system_state dict or uses the rclpy node for graph introspection.

Test patterns:
- Mock system_state with known data, verify output format
- Mock _ros2_monitor for functions needing rclpy node access
- Test error cases (ROS2 not available, node not found, timeout)
- Use pytest with unittest.mock
"""

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_system_state():
    """Reset system_state to defaults before each test."""
    from backend.ros2_monitor import system_state

    original = {
        "ros2_available": False,
        "nodes": {},
        "topics": {},
        "services": {},
        "parameters": {},
        "system_health": "unknown",
        "pragati_status": {
            "arm_position": "unknown",
            "homing_status": "unknown",
            "cotton_detection": "idle",
            "operation_mode": "unknown",
            "initialization_progress": 0,
            "last_cycle_time": None,
            "error_count": 0,
        },
        "logs": [],
        "last_update": None,
    }
    system_state.update(original)
    yield
    system_state.update(original)


@pytest.fixture()
def populated_topics():
    """Populate system_state with sample topics."""
    from backend.ros2_monitor import system_state

    system_state["topics"] = {
        "/joint_states": {
            "type": "sensor_msgs/msg/JointState",
            "publishers": 2,
            "subscribers": 1,
            "last_message": None,
            "rate": 0.0,
        },
        "/cmd_vel": {
            "type": "geometry_msgs/msg/Twist",
            "publishers": 1,
            "subscribers": 3,
            "last_message": None,
            "rate": 10.0,
        },
        "/web_dashboard_monitor/topic": {
            "type": "std_msgs/msg/String",
            "publishers": 1,
            "subscribers": 0,
            "last_message": None,
            "rate": 0.0,
        },
    }


@pytest.fixture()
def populated_services():
    """Populate system_state with sample services."""
    from backend.ros2_monitor import system_state

    system_state["services"] = {
        "/joint_homing": {
            "type": "std_srvs/srv/Trigger",
            "available": True,
            "last_called": None,
        },
        "/joint_status": {
            "type": "custom_msgs/srv/JointStatus",
            "available": True,
            "last_called": None,
        },
        "/web_dashboard_monitor/get_type": {
            "type": "rcl_interfaces/srv/GetParameterTypes",
            "available": True,
            "last_called": None,
        },
    }


@pytest.fixture()
def populated_nodes():
    """Populate system_state with sample nodes."""
    from backend.ros2_monitor import system_state

    system_state["nodes"] = {
        "/yanthra_move": {
            "status": "active",
            "last_seen": "2025-01-01T00:00:00",
            "info_available": True,
            "subscribers": [],
            "publishers": [],
            "services": [],
        },
        "/robot_state_publisher": {
            "status": "active",
            "last_seen": "2025-01-01T00:00:00",
            "info_available": True,
            "subscribers": [],
            "publishers": [],
            "services": [],
        },
        "/web_dashboard_monitor": {
            "status": "active",
            "last_seen": "2025-01-01T00:00:00",
            "info_available": True,
            "subscribers": [],
            "publishers": [],
            "services": [],
        },
    }


# ===================================================================
# 1. get_topics()
# ===================================================================


class TestGetTopics:
    """get_topics() returns topics from system_state formatted as list[dict]."""

    def test_returns_list(self, populated_topics):
        from backend.ros2_monitor import get_topics

        result = get_topics()
        assert isinstance(result, list)

    def test_each_item_has_required_keys(self, populated_topics):
        from backend.ros2_monitor import get_topics

        result = get_topics()
        required_keys = {"name", "type", "publisher_count", "subscriber_count"}
        for item in result:
            assert required_keys.issubset(item.keys()), f"Missing keys in {item}"

    def test_correct_values(self, populated_topics):
        from backend.ros2_monitor import get_topics

        result = get_topics()
        by_name = {t["name"]: t for t in result}
        assert "/joint_states" in by_name
        js = by_name["/joint_states"]
        assert js["type"] == "sensor_msgs/msg/JointState"
        assert js["publisher_count"] == 2
        assert js["subscriber_count"] == 1

    def test_filters_dashboard_internals(self, populated_topics):
        """Dashboard internal topics should be filtered out."""
        from backend.ros2_monitor import get_topics

        with patch(
            "backend.ros2_monitor.should_hide_dashboard_internal",
            side_effect=lambda n: "web_dashboard" in n,
        ):
            result = get_topics()
            names = [t["name"] for t in result]
            assert "/web_dashboard_monitor/topic" not in names
            assert "/joint_states" in names

    def test_returns_empty_list_when_no_topics(self):
        from backend.ros2_monitor import get_topics

        result = get_topics()
        assert result == []


# ===================================================================
# 2. get_services()
# ===================================================================


class TestGetServices:
    """get_services() returns services from system_state as list[dict]."""

    def test_returns_list(self, populated_services):
        from backend.ros2_monitor import get_services

        result = get_services()
        assert isinstance(result, list)

    def test_each_item_has_required_keys(self, populated_services):
        from backend.ros2_monitor import get_services

        result = get_services()
        required_keys = {"name", "type"}
        for item in result:
            assert required_keys.issubset(item.keys()), f"Missing keys in {item}"

    def test_correct_values(self, populated_services):
        from backend.ros2_monitor import get_services

        result = get_services()
        by_name = {s["name"]: s for s in result}
        assert "/joint_homing" in by_name
        assert by_name["/joint_homing"]["type"] == "std_srvs/srv/Trigger"

    def test_filters_dashboard_internals(self, populated_services):
        from backend.ros2_monitor import get_services

        with patch(
            "backend.ros2_monitor.should_hide_dashboard_internal",
            side_effect=lambda n: "web_dashboard" in n,
        ):
            result = get_services()
            names = [s["name"] for s in result]
            assert "/web_dashboard_monitor/get_type" not in names
            assert "/joint_homing" in names

    def test_returns_empty_list_when_no_services(self):
        from backend.ros2_monitor import get_services

        result = get_services()
        assert result == []


# ===================================================================
# 3. get_nodes()
# ===================================================================


class TestGetNodes:
    """get_nodes() returns nodes from system_state as list[dict]."""

    def test_returns_list(self, populated_nodes):
        from backend.ros2_monitor import get_nodes

        result = get_nodes()
        assert isinstance(result, list)

    def test_each_item_has_required_keys(self, populated_nodes):
        from backend.ros2_monitor import get_nodes

        result = get_nodes()
        required_keys = {"name", "namespace", "lifecycle_state"}
        for item in result:
            assert required_keys.issubset(item.keys()), f"Missing keys in {item}"

    def test_parses_namespace_from_full_name(self, populated_nodes):
        """Node full_name '/yanthra_move' => namespace='/', name='yanthra_move'."""
        from backend.ros2_monitor import get_nodes

        result = get_nodes()
        by_name = {n["name"]: n for n in result}
        assert "yanthra_move" in by_name
        assert by_name["yanthra_move"]["namespace"] == "/"

    def test_filters_dashboard_internals(self, populated_nodes):
        from backend.ros2_monitor import get_nodes

        with patch(
            "backend.ros2_monitor.should_hide_dashboard_internal",
            side_effect=lambda n: "web_dashboard" in n,
        ):
            result = get_nodes()
            names = [n["name"] for n in result]
            assert "web_dashboard_monitor" not in names
            assert "yanthra_move" in names

    def test_lifecycle_state_is_null_by_default(self, populated_nodes):
        from backend.ros2_monitor import get_nodes

        result = get_nodes()
        for node in result:
            assert node["lifecycle_state"] is None

    def test_returns_empty_list_when_no_nodes(self):
        from backend.ros2_monitor import get_nodes

        result = get_nodes()
        assert result == []

    def test_handles_nested_namespace(self):
        """Node '/ns1/ns2/node_name' => namespace='/ns1/ns2', name='node_name'."""
        from backend.ros2_monitor import system_state, get_nodes

        system_state["nodes"] = {
            "/ns1/ns2/deep_node": {
                "status": "active",
                "last_seen": "2025-01-01T00:00:00",
                "info_available": True,
                "subscribers": [],
                "publishers": [],
                "services": [],
            },
        }
        result = get_nodes()
        assert len(result) == 1
        assert result[0]["name"] == "deep_node"
        assert result[0]["namespace"] == "/ns1/ns2"


# ===================================================================
# 4. get_node_detail()
# ===================================================================


class TestGetNodeDetail:
    """get_node_detail() returns detailed info for a single node."""

    def test_returns_none_when_node_not_found(self, populated_nodes):
        from backend.ros2_monitor import get_node_detail

        result = get_node_detail("nonexistent_node")
        assert result is None

    def test_returns_dict_for_known_node(self, populated_nodes):
        from backend.ros2_monitor import get_node_detail

        result = get_node_detail("yanthra_move")
        assert isinstance(result, dict)

    def test_has_required_keys(self, populated_nodes):
        from backend.ros2_monitor import get_node_detail

        result = get_node_detail("yanthra_move")
        assert result is not None
        required_keys = {
            "name",
            "namespace",
            "publishers",
            "subscribers",
            "services",
            "parameters",
        }
        assert required_keys.issubset(result.keys())

    def test_uses_rclpy_introspection_when_monitor_available(self, populated_nodes):
        """When _ros2_monitor is available, uses rclpy graph APIs."""
        from backend.ros2_monitor import get_node_detail

        mock_node = MagicMock()
        mock_node.get_publisher_names_and_types_by_node.return_value = [
            ("/topic_a", ["std_msgs/msg/String"]),
        ]
        mock_node.get_subscriber_names_and_types_by_node.return_value = [
            ("/topic_b", ["sensor_msgs/msg/Image"]),
        ]
        mock_node.get_service_names_and_types_by_node.return_value = [
            ("/srv_a", ["std_srvs/srv/Trigger"]),
        ]

        with patch("backend.ros2_monitor._ros2_monitor", mock_node):
            result = get_node_detail("yanthra_move")

        assert result is not None
        assert len(result["publishers"]) == 1
        assert result["publishers"][0]["name"] == "/topic_a"
        assert len(result["subscribers"]) == 1
        assert len(result["services"]) == 1

    def test_returns_basic_info_when_no_monitor(self, populated_nodes):
        """When _ros2_monitor is None, returns basic info from system_state."""
        from backend.ros2_monitor import get_node_detail

        with patch("backend.ros2_monitor._ros2_monitor", None):
            result = get_node_detail("yanthra_move")

        assert result is not None
        assert result["name"] == "yanthra_move"
        assert result["namespace"] == "/"


# ===================================================================
# 5. get_parameters()
# ===================================================================


class TestGetParameters:
    """get_parameters() returns parameters grouped by node."""

    def test_returns_dict_with_nodes_key(self, populated_nodes):
        from backend.ros2_monitor import get_parameters

        result = get_parameters()
        assert isinstance(result, dict)
        assert "nodes" in result

    def test_nodes_is_list(self, populated_nodes):
        from backend.ros2_monitor import get_parameters

        result = get_parameters()
        assert isinstance(result["nodes"], list)

    def test_each_node_has_name_and_parameters(self, populated_nodes):
        from backend.ros2_monitor import get_parameters

        result = get_parameters()
        for node_entry in result["nodes"]:
            assert "name" in node_entry
            assert "parameters" in node_entry
            assert isinstance(node_entry["parameters"], list)

    def test_returns_empty_nodes_when_no_data(self):
        from backend.ros2_monitor import get_parameters

        result = get_parameters()
        assert result == {"nodes": []}

    def test_uses_system_state_parameters_when_available(self):
        """When system_state has parameter data, returns it."""
        from backend.ros2_monitor import system_state, get_parameters

        system_state["parameters"] = {
            "/yanthra_move": {
                "max_velocity": {"type": "double", "value": 1.5},
                "use_sim": {"type": "bool", "value": True},
            },
        }
        system_state["nodes"] = {
            "/yanthra_move": {"status": "active"},
        }
        result = get_parameters()
        assert len(result["nodes"]) >= 1
        node_entry = next(n for n in result["nodes"] if n["name"] == "/yanthra_move")
        assert len(node_entry["parameters"]) == 2

    def test_filters_dashboard_internals(self, populated_nodes):
        from backend.ros2_monitor import get_parameters

        with patch(
            "backend.ros2_monitor.should_hide_dashboard_internal",
            side_effect=lambda n: "web_dashboard" in n,
        ):
            result = get_parameters()
            node_names = [n["name"] for n in result["nodes"]]
            assert "/web_dashboard_monitor" not in node_names


# ===================================================================
# 6. set_parameter()
# ===================================================================


class TestSetParameter:
    """set_parameter() sets a parameter on a ROS2 node."""

    def test_raises_when_ros2_not_available(self):
        from backend.ros2_monitor import set_parameter

        with patch("backend.ros2_monitor.ROS2_AVAILABLE", False):
            with pytest.raises(RuntimeError, match="ROS2.*not available"):
                set_parameter("/yanthra_move", "max_vel", 2.0)

    def test_raises_when_no_monitor(self):
        from backend.ros2_monitor import set_parameter

        with patch("backend.ros2_monitor.ROS2_AVAILABLE", True), patch(
            "backend.ros2_monitor._ros2_monitor", None
        ):
            with pytest.raises(RuntimeError, match="monitor.*not running"):
                set_parameter("/yanthra_move", "max_vel", 2.0)

    def test_returns_success_dict_on_success(self):
        """Returns {'success': True, 'name': ..., 'value': ...}."""
        from backend.ros2_monitor import set_parameter

        mock_node = MagicMock()
        mock_client = MagicMock()
        mock_node.create_client.return_value = mock_client
        mock_client.wait_for_service.return_value = True

        mock_future = MagicMock()
        mock_result = MagicMock()
        mock_result.results = [MagicMock(successful=True)]
        mock_future.result.return_value = mock_result
        mock_client.call_async.return_value = mock_future

        with patch("backend.ros2_monitor.ROS2_AVAILABLE", True), patch(
            "backend.ros2_monitor._ros2_monitor", mock_node
        ), patch("backend.ros2_monitor.rclpy"):
            result = set_parameter("/yanthra_move", "max_vel", 2.0)

        assert result["success"] is True
        assert result["name"] == "max_vel"
        assert result["value"] == 2.0


# ===================================================================
# 7. call_service()
# ===================================================================


class TestCallService:
    """call_service() calls a ROS2 service and returns the response."""

    def test_raises_when_ros2_not_available(self):
        from backend.ros2_monitor import call_service

        with patch("backend.ros2_monitor.ROS2_AVAILABLE", False):
            with pytest.raises(RuntimeError, match="ROS2.*not available"):
                call_service("/joint_homing", "std_srvs/srv/Trigger", {})

    def test_raises_when_no_monitor(self):
        from backend.ros2_monitor import call_service

        with patch("backend.ros2_monitor.ROS2_AVAILABLE", True), patch(
            "backend.ros2_monitor._ros2_monitor", None
        ):
            with pytest.raises(RuntimeError, match="monitor.*not running"):
                call_service("/joint_homing", "std_srvs/srv/Trigger", {})

    def test_returns_response_dict_with_duration(self):
        """Returns {'response': {...}, 'duration_ms': N}."""
        from backend.ros2_monitor import call_service

        mock_node = MagicMock()
        mock_client = MagicMock()
        mock_node.create_client.return_value = mock_client
        mock_client.wait_for_service.return_value = True

        mock_future = MagicMock()
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.message = "done"
        # Make get_fields_and_field_types return something serializable
        mock_response.get_fields_and_field_types.return_value = {
            "success": "bool",
            "message": "string",
        }
        mock_future.result.return_value = mock_response
        mock_client.call_async.return_value = mock_future

        # Mock the service type import
        mock_srv_module = MagicMock()
        mock_srv_class = MagicMock()
        mock_srv_class.Request.return_value = MagicMock()
        mock_srv_module.Trigger = mock_srv_class

        with patch("backend.ros2_monitor.ROS2_AVAILABLE", True), patch(
            "backend.ros2_monitor._ros2_monitor", mock_node
        ), patch("backend.ros2_monitor.rclpy"), patch(
            "backend.ros2_monitor._import_service_type",
            return_value=mock_srv_class,
        ):
            result = call_service("/joint_homing", "std_srvs/srv/Trigger", {})

        assert "response" in result
        assert "duration_ms" in result
        assert isinstance(result["duration_ms"], (int, float))


# ===================================================================
# 8. lifecycle_transition()
# ===================================================================


class TestLifecycleTransition:
    """lifecycle_transition() sends a lifecycle state transition."""

    def test_raises_when_ros2_not_available(self):
        from backend.ros2_monitor import lifecycle_transition

        with patch("backend.ros2_monitor.ROS2_AVAILABLE", False):
            with pytest.raises(RuntimeError, match="ROS2.*not available"):
                lifecycle_transition("/my_node", "activate")

    def test_raises_when_no_monitor(self):
        from backend.ros2_monitor import lifecycle_transition

        with patch("backend.ros2_monitor.ROS2_AVAILABLE", True), patch(
            "backend.ros2_monitor._ros2_monitor", None
        ):
            with pytest.raises(RuntimeError, match="monitor.*not running"):
                lifecycle_transition("/my_node", "activate")

    def test_returns_success_dict(self):
        """Returns {'success': True, 'node': ..., 'transition': ...}."""
        from backend.ros2_monitor import lifecycle_transition

        mock_node = MagicMock()
        mock_client = MagicMock()
        mock_node.create_client.return_value = mock_client
        mock_client.wait_for_service.return_value = True

        mock_future = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_future.result.return_value = mock_result
        mock_client.call_async.return_value = mock_future

        with patch("backend.ros2_monitor.ROS2_AVAILABLE", True), patch(
            "backend.ros2_monitor._ros2_monitor", mock_node
        ), patch("backend.ros2_monitor.rclpy"):
            result = lifecycle_transition("/my_node", "activate")

        assert result["success"] is True
        assert result["node"] == "/my_node"
        assert result["transition"] == "activate"

    def test_invalid_transition_raises(self):
        """Invalid transition name raises ValueError."""
        from backend.ros2_monitor import lifecycle_transition

        with patch("backend.ros2_monitor.ROS2_AVAILABLE", True), patch(
            "backend.ros2_monitor._ros2_monitor", MagicMock()
        ):
            with pytest.raises(ValueError, match="Invalid.*transition"):
                lifecycle_transition("/my_node", "invalid_transition_xyz")


# ===================================================================
# Cross-cutting: ROS2 not available
# ===================================================================


class TestRos2NotAvailable:
    """When ROS2_AVAILABLE is False, read-only functions return empty data."""

    def test_get_topics_returns_empty_when_ros2_unavailable(self):
        from backend.ros2_monitor import get_topics

        # system_state is already empty from fixture reset
        result = get_topics()
        assert result == []

    def test_get_services_returns_empty_when_ros2_unavailable(self):
        from backend.ros2_monitor import get_services

        result = get_services()
        assert result == []

    def test_get_nodes_returns_empty_when_ros2_unavailable(self):
        from backend.ros2_monitor import get_nodes

        result = get_nodes()
        assert result == []

    def test_get_parameters_returns_empty_when_ros2_unavailable(self):
        from backend.ros2_monitor import get_parameters

        result = get_parameters()
        assert result == {"nodes": []}
