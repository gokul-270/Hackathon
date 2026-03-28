"""Tests that ros2_monitor uses rclpy graph APIs, not subprocess."""

import ast
import inspect
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# -----------------------------------------------------------------
# Helpers to set up a mock rclpy environment
# -----------------------------------------------------------------


def _mock_rclpy_imports():
    """Return a dict of mock modules for rclpy and its submodules."""
    mock_rclpy = MagicMock()
    mock_node = MagicMock()
    mock_executors = MagicMock()
    mock_qos = MagicMock()
    mock_std_msgs = MagicMock()
    mock_std_msgs_msg = MagicMock()
    mock_sensor_msgs = MagicMock()
    mock_sensor_msgs_msg = MagicMock()

    # The Node class mock needs to be a real class-like thing
    # so ROS2Monitor can inherit from it
    mock_node.Node = MagicMock

    return {
        "rclpy": mock_rclpy,
        "rclpy.node": mock_node,
        "rclpy.executors": mock_executors,
        "rclpy.qos": mock_qos,
        "std_msgs": mock_std_msgs,
        "std_msgs.msg": mock_std_msgs_msg,
        "sensor_msgs": mock_sensor_msgs,
        "sensor_msgs.msg": mock_sensor_msgs_msg,
    }


# -----------------------------------------------------------------
# Tests
# -----------------------------------------------------------------


class TestNoSubprocessUsage:
    """Verify ros2_monitor.py does not import or use subprocess."""

    def test_no_subprocess_import_in_source(self):
        """Parse the source AST to confirm no subprocess import."""
        src_path = Path(__file__).resolve().parent / "ros2_monitor.py"
        tree = ast.parse(src_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "subprocess", "ros2_monitor.py must not import subprocess"
            elif isinstance(node, ast.ImportFrom):
                assert (
                    node.module != "subprocess"
                ), "ros2_monitor.py must not import from subprocess"

    def test_no_subprocess_call_in_source(self):
        """Ensure no subprocess.run or subprocess.Popen calls."""
        src_path = Path(__file__).resolve().parent / "ros2_monitor.py"
        source = src_path.read_text(encoding="utf-8")
        assert "subprocess.run" not in source
        assert "subprocess.Popen" not in source
        assert "subprocess.check_output" not in source


class TestRclpyGraphApiUsage:
    """Verify ROS2Monitor calls rclpy graph introspection methods."""

    def test_update_nodes_calls_get_node_names(self):
        """update_nodes() should call get_node_names_and_namespaces."""
        mocks = _mock_rclpy_imports()
        with patch.dict(sys.modules, mocks):
            # Force reimport with mocked rclpy
            if "backend.ros2_monitor" in sys.modules:
                del sys.modules["backend.ros2_monitor"]
            from backend.ros2_monitor import ROS2Monitor

            monitor = MagicMock(spec=ROS2Monitor)
            monitor._system_state = {
                "nodes": {},
                "topics": {},
                "services": {},
                "parameters": {},
            }
            monitor.get_node_names_and_namespaces = MagicMock(
                return_value=[
                    ("node_a", "/"),
                    ("node_b", "/ns"),
                ]
            )
            monitor.get_logger = MagicMock(return_value=MagicMock())

            # Call the real method on the mock instance
            ROS2Monitor.update_nodes(monitor)
            monitor.get_node_names_and_namespaces.assert_called_once()
            assert "/node_a" in monitor._system_state["nodes"]
            assert "/ns/node_b" in monitor._system_state["nodes"]

    def test_update_topics_calls_get_topic_names(self):
        """update_topics() should call get_topic_names_and_types.

        NOTE: Publishers/subscribers are set to 0 by design to avoid
        expensive per-topic DDS graph queries. They are fetched on-demand.
        """
        mocks = _mock_rclpy_imports()
        with patch.dict(sys.modules, mocks):
            if "backend.ros2_monitor" in sys.modules:
                del sys.modules["backend.ros2_monitor"]
            from backend.ros2_monitor import ROS2Monitor

            monitor = MagicMock(spec=ROS2Monitor)
            monitor._system_state = {
                "nodes": {},
                "topics": {},
                "services": {},
            }
            monitor.get_topic_names_and_types = MagicMock(
                return_value=[
                    ("/joint_states", ["sensor_msgs/msg/JointState"]),
                ]
            )
            monitor.get_logger = MagicMock(return_value=MagicMock())

            ROS2Monitor.update_topics(monitor)
            monitor.get_topic_names_and_types.assert_called_once()
            assert "/joint_states" in monitor._system_state["topics"]
            topic = monitor._system_state["topics"]["/joint_states"]
            assert topic["type"] == "sensor_msgs/msg/JointState"
            # Publishers/subscribers set to 0 by design (expensive DDS queries)
            assert topic["publishers"] == 0
            assert topic["subscribers"] == 0

    def test_update_services_calls_get_service_names(self):
        """update_services() should call get_service_names_and_types."""
        mocks = _mock_rclpy_imports()
        with patch.dict(sys.modules, mocks):
            if "backend.ros2_monitor" in sys.modules:
                del sys.modules["backend.ros2_monitor"]
            from backend.ros2_monitor import ROS2Monitor

            monitor = MagicMock(spec=ROS2Monitor)
            monitor._system_state = {
                "nodes": {},
                "topics": {},
                "services": {},
            }
            monitor.get_service_names_and_types = MagicMock(
                return_value=[
                    ("/joint_homing", ["std_srvs/srv/Trigger"]),
                ]
            )
            monitor.get_logger = MagicMock(return_value=MagicMock())

            ROS2Monitor.update_services(monitor)
            monitor.get_service_names_and_types.assert_called_once()
            assert "/joint_homing" in monitor._system_state["services"]
            svc = monitor._system_state["services"]["/joint_homing"]
            assert svc["type"] == "std_srvs/srv/Trigger"
            assert svc["available"] is True
