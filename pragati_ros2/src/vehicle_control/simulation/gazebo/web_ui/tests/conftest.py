"""
Pytest configuration and fixtures for backend tests.

Mocks rclpy and demo_patterns dependencies so the FastAPI backend
can be imported and tested without a running ROS2 / Gazebo environment.
"""

import sys
import types
from pathlib import Path
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Path setup — make backend.py and demo_patterns.py importable
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent
_WEB_UI_DIR = _THIS_DIR.parent                       # web_ui/
_PROJECT_ROOT = _WEB_UI_DIR.parents[4]                # pragati_ros2/
sys.path.insert(0, str(_WEB_UI_DIR))                  # for `import backend`
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))    # for `import demo_patterns`

# ---------------------------------------------------------------------------
# Mock ROS2 layer before importing the backend
# ---------------------------------------------------------------------------

# Lightweight stand-in for geometry_msgs.msg.Twist
class _MockTwist:
    """Mimics geometry_msgs.msg.Twist with linear.x and angular.z."""

    class _Vec3:
        def __init__(self):
            self.x = 0.0
            self.y = 0.0
            self.z = 0.0

    def __init__(self):
        self.linear = self._Vec3()
        self.angular = self._Vec3()


def _install_rclpy_mocks():
    """Install mock rclpy / geometry_msgs modules into sys.modules."""

    # geometry_msgs
    geometry_msgs = types.ModuleType("geometry_msgs")
    geometry_msgs_msg = types.ModuleType("geometry_msgs.msg")
    geometry_msgs_msg.Twist = _MockTwist
    geometry_msgs.msg = geometry_msgs_msg
    sys.modules["geometry_msgs"] = geometry_msgs
    sys.modules["geometry_msgs.msg"] = geometry_msgs_msg

    # nav_msgs
    nav_msgs = types.ModuleType("nav_msgs")
    nav_msgs_msg = types.ModuleType("nav_msgs.msg")
    nav_msgs_msg.Odometry = mock.MagicMock()
    nav_msgs.msg = nav_msgs_msg
    sys.modules["nav_msgs"] = nav_msgs
    sys.modules["nav_msgs.msg"] = nav_msgs_msg

    # rclpy
    rclpy_mod = types.ModuleType("rclpy")
    rclpy_mod.init = mock.MagicMock()
    rclpy_mod.shutdown = mock.MagicMock()
    rclpy_mod.spin_once = mock.MagicMock()

    mock_node = mock.MagicMock()
    mock_publisher = mock.MagicMock()
    mock_node.create_publisher.return_value = mock_publisher
    rclpy_mod.create_node = mock.MagicMock(return_value=mock_node)

    # rclpy.qos
    rclpy_qos = types.ModuleType("rclpy.qos")
    rclpy_qos.QoSProfile = mock.MagicMock()
    rclpy_mod.qos = rclpy_qos

    # rclpy.parameter (used by demo_patterns)
    rclpy_parameter = types.ModuleType("rclpy.parameter")
    rclpy_parameter.Parameter = mock.MagicMock()
    rclpy_mod.parameter = rclpy_parameter

    sys.modules["rclpy"] = rclpy_mod
    sys.modules["rclpy.qos"] = rclpy_qos
    sys.modules["rclpy.parameter"] = rclpy_parameter


# Install mocks before any import of the backend
_install_rclpy_mocks()

# Also mock demo_patterns heavy helpers so startup doesn't call Gazebo
import demo_patterns  # noqa: E402 — already importable because backend.py adds scripts/ to sys.path

demo_patterns.teleport_to_field_start = mock.MagicMock(return_value=True)
demo_patterns.teleport_robot = mock.MagicMock(return_value=True)
demo_patterns.verify_recording = mock.MagicMock(return_value=True)
demo_patterns.VideoRecorder = mock.MagicMock()

# Now safe to import backend module (it reads HAS_RCLPY at import time)
from backend import (  # noqa: E402
    PATTERN_REGISTRY,
    VelocityRampingEngine,
    _estimate_duration,
    _perpendicular_distance,
    _quaternion_to_yaw,
    app,
    points_to_commands,
    rdp_simplify,
    state,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class MockPublisher:
    """Records every Twist message published for assertion."""

    def __init__(self):
        self.messages: list[_MockTwist] = []

    def publish(self, msg):
        self.messages.append(msg)


@pytest.fixture()
def mock_publisher():
    """Return a fresh MockPublisher."""
    return MockPublisher()


@pytest.fixture()
def engine(mock_publisher):
    """Return a VelocityRampingEngine wired to a MockPublisher."""
    return VelocityRampingEngine(mock_publisher, ramp_duration=0.0)


@pytest.fixture()
def ws_client():
    """Starlette TestClient configured for the FastAPI app.

    Resets global state after each test so tests remain isolated.
    """
    from starlette.testclient import TestClient

    # Provide an engine even without startup event (mock publisher)
    pub = MockPublisher()
    state.engine = VelocityRampingEngine(pub, ramp_duration=0.0)
    state.publisher = pub
    state.clients = set()
    state.execution_task = None
    state.auto_record = False
    state.recorder = mock.MagicMock()
    state.recorder._recording = False
    state.odom_x = 0.0
    state.odom_y = 0.0
    state.odom_theta = 0.0
    state.precision_move_task = None
    state.precision_move_cancel = False

    client = TestClient(app)
    yield client

    # Teardown
    if state.engine:
        state.engine.stop()
    state.clients.clear()
