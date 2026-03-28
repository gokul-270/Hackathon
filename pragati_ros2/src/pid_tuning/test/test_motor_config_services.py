"""Unit tests for MotorConfigService relay node — motor config services.

Tests cover two scopes:

**Task 8.1 — Command/Lifecycle services:**
- MotorCommand message structure and all 8 command modes
- MotorLifecycle message structure and all 6 lifecycle actions
- E-stop blocking logic (commands blocked; lifecycle selectively blocked)
- Timeout / service-unavailable handling

**Task 8.2 — Limit/Encoder/State services:**
- ReadMotorLimits / WriteMotorLimits message structures
- ReadEncoder / WriteEncoderZero message structures (both modes)
- ReadMotorState / ClearMotorErrors message structures
- ReadMotorAngles message structure
- E-stop blocking on write operations
- Timeout handling for all relay callbacks

Approach: ROS2 modules are mocked via ``sys.modules`` before importing the
relay node, following the pattern established in ``test_integration.py``.
Service callback logic is tested by instantiating a mock-backed
``MotorConfigService`` and calling handler methods directly.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

# ---------------------------------------------------------------------------
# Mock ROS2 / message modules BEFORE importing the relay node
# ---------------------------------------------------------------------------
# We need fine-grained control over the service message types, so we create
# real-ish Request/Response classes for each .srv type used by the node.
# The rest of ROS2 is fully mocked.

_rclpy_mock = MagicMock()
sys.modules["rclpy"] = _rclpy_mock

# Provide a real base class for Node so MotorConfigService's MRO works
# normally (real Python methods, not MagicMock attribute access).
_node_mod = MagicMock()


class _FakeNode:
    """Minimal stand-in for rclpy.node.Node."""

    def __init__(self, name: str = "", **kwargs):
        pass

    # Provide no-op stubs for methods called in MotorConfigService.__init__
    def declare_parameter(self, *a, **kw):
        return MagicMock()

    def create_client(self, *a, **kw):
        return MagicMock()

    def create_service(self, *a, **kw):
        return MagicMock()

    def create_publisher(self, *a, **kw):
        return MagicMock()

    def create_timer(self, *a, **kw):
        return MagicMock()

    def create_subscription(self, *a, **kw):
        return MagicMock()

    def get_logger(self):
        return MagicMock()

    def get_parameter(self, *a, **kw):
        return MagicMock()


_node_mod.Node = _FakeNode
sys.modules["rclpy.node"] = _node_mod
sys.modules["rclpy.action"] = MagicMock()
sys.modules["rclpy.callback_groups"] = MagicMock()
sys.modules["rclpy.executors"] = MagicMock()
sys.modules["sensor_msgs"] = MagicMock()
sys.modules["sensor_msgs.msg"] = MagicMock()
sys.modules["std_msgs"] = MagicMock()
sys.modules["std_msgs.msg"] = MagicMock()
sys.modules["std_srvs"] = MagicMock()
sys.modules["std_srvs.srv"] = MagicMock()
sys.modules["action_msgs"] = MagicMock()
sys.modules["action_msgs.msg"] = MagicMock()


# ---------------------------------------------------------------------------
# Lightweight message stubs for motor_control_msgs.srv
# ---------------------------------------------------------------------------
# These give us real attribute storage so ``req.motor_id = 1`` works as
# expected, while still being importable as ``motor_control_msgs.srv.X``.


class _SimpleMsg:
    """Base message class — stores any attribute set on it."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def _make_srv(name: str, req_defaults: dict, resp_defaults: dict, req_consts=None):
    """Create a fake ROS2 .srv type with Request/Response inner classes."""

    req_consts = req_consts or {}

    class Request(_SimpleMsg):
        def __init__(self, **kw):
            merged = {**req_defaults, **kw}
            super().__init__(**merged)

    # Attach constants to the Request class (e.g. TORQUE=0)
    for cname, cval in req_consts.items():
        setattr(Request, cname, cval)

    class Response(_SimpleMsg):
        def __init__(self, **kw):
            merged = {**resp_defaults, **kw}
            super().__init__(**merged)

    srv_type = type(name, (), {"Request": Request, "Response": Response})
    return srv_type


# -- MotorCommand -----------------------------------------------------------
MotorCommand = _make_srv(
    "MotorCommand",
    req_defaults=dict(
        motor_id=0, command_type=0, value=0.0, max_speed=0.0, direction=0
    ),
    resp_defaults=dict(
        success=False,
        error_message="",
        temperature=0,
        torque_current=0,
        speed=0,
        encoder=0,
    ),
    req_consts=dict(
        TORQUE=0,
        SPEED=1,
        MULTI_ANGLE_1=2,
        MULTI_ANGLE_2=3,
        SINGLE_ANGLE_1=4,
        SINGLE_ANGLE_2=5,
        INCREMENT_1=6,
        INCREMENT_2=7,
    ),
)

# -- MotorLifecycle ---------------------------------------------------------
MotorLifecycle = _make_srv(
    "MotorLifecycle",
    req_defaults=dict(motor_id=0, action=0),
    resp_defaults=dict(
        success=False,
        motor_state=0,
        error_message="",
    ),
    req_consts=dict(
        ON=0,
        OFF=1,
        STOP=2,
        REBOOT=3,
        SAVE_PID_ROM=4,
        SAVE_ZERO_ROM=5,
    ),
)

# -- ReadMotorLimits / WriteMotorLimits ------------------------------------
ReadMotorLimits = _make_srv(
    "ReadMotorLimits",
    req_defaults=dict(motor_id=0),
    resp_defaults=dict(
        success=False, error_message="", max_torque_ratio=0, acceleration=0.0
    ),
)
WriteMotorLimits = _make_srv(
    "WriteMotorLimits",
    req_defaults=dict(
        motor_id=0,
        max_torque_ratio=0,
        acceleration=0.0,
        set_max_torque=False,
        set_acceleration=False,
    ),
    resp_defaults=dict(success=False, error_message=""),
)

# -- ReadEncoder / WriteEncoderZero ----------------------------------------
ReadEncoder = _make_srv(
    "ReadEncoder",
    req_defaults=dict(motor_id=0),
    resp_defaults=dict(
        success=False,
        error_message="",
        raw_value=0,
        offset=0,
        original_value=0,
    ),
)
WriteEncoderZero = _make_srv(
    "WriteEncoderZero",
    req_defaults=dict(motor_id=0, mode=0, encoder_value=0),
    resp_defaults=dict(success=False, error_message=""),
    req_consts=dict(SET_VALUE=0, SET_CURRENT_POS=1),
)

# -- ReadMotorAngles -------------------------------------------------------
ReadMotorAngles = _make_srv(
    "ReadMotorAngles",
    req_defaults=dict(motor_id=0),
    resp_defaults=dict(
        success=False,
        error_message="",
        multi_turn_angle=0.0,
        single_turn_angle=0.0,
    ),
)

# -- ClearMotorErrors / ReadMotorState -------------------------------------
ClearMotorErrors = _make_srv(
    "ClearMotorErrors",
    req_defaults=dict(motor_id=0),
    resp_defaults=dict(
        success=False,
        error_message="",
        error_flags_after=0,
    ),
)
ReadMotorState = _make_srv(
    "ReadMotorState",
    req_defaults=dict(motor_id=0),
    resp_defaults=dict(
        success=False,
        error_message="",
        temperature_c=0.0,
        voltage_v=0.0,
        torque_current_a=0.0,
        speed_dps=0.0,
        encoder_position=0,
        multi_turn_deg=0.0,
        single_turn_deg=0.0,
        phase_a=0.0,
        phase_b=0.0,
        phase_c=0.0,
        error_flags=0,
    ),
)

# -- PID types (needed for node import but not the focus of these tests) ----
ReadPID = _make_srv(
    "ReadPID",
    req_defaults=dict(motor_id=0),
    resp_defaults=dict(
        success=False,
        error_message="",
        angle_kp=0,
        angle_ki=0,
        speed_kp=0,
        speed_ki=0,
        current_kp=0,
        current_ki=0,
    ),
)
WritePID = _make_srv(
    "WritePID",
    req_defaults=dict(
        motor_id=0,
        angle_kp=0,
        angle_ki=0,
        speed_kp=0,
        speed_ki=0,
        current_kp=0,
        current_ki=0,
    ),
    resp_defaults=dict(success=False, error_message=""),
)
WritePIDToROM = _make_srv(
    "WritePIDToROM",
    req_defaults=dict(
        motor_id=0,
        angle_kp=0,
        angle_ki=0,
        speed_kp=0,
        speed_ki=0,
        current_kp=0,
        current_ki=0,
    ),
    resp_defaults=dict(success=False, error_message=""),
)

# Wire into sys.modules so ``from motor_control_msgs.srv import ...`` works.
_srv_module = MagicMock()
_srv_module.MotorCommand = MotorCommand
_srv_module.MotorLifecycle = MotorLifecycle
_srv_module.ReadMotorLimits = ReadMotorLimits
_srv_module.WriteMotorLimits = WriteMotorLimits
_srv_module.ReadEncoder = ReadEncoder
_srv_module.WriteEncoderZero = WriteEncoderZero
_srv_module.ReadMotorAngles = ReadMotorAngles
_srv_module.ClearMotorErrors = ClearMotorErrors
_srv_module.ReadMotorState = ReadMotorState
_srv_module.ReadPID = ReadPID
_srv_module.WritePID = WritePID
_srv_module.WritePIDToROM = WritePIDToROM
sys.modules["motor_control_msgs"] = MagicMock()
sys.modules["motor_control_msgs.srv"] = _srv_module
sys.modules["motor_control_msgs.action"] = MagicMock()

# Ensure the source is importable
_repo_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_repo_root / "src" / "pid_tuning"))

# NOW import the relay node module.  The ``Node`` base class is _FakeNode so
# MotorConfigService.__init__ runs cleanly and all methods resolve normally.
from pid_tuning.pid_tuning_node import (  # noqa: E402
    DEFAULT_SERVICE_TIMEOUT_SEC,
    MOTOR_JOINT_MAP,
    MotorConfigService,
    MotorTelemetry,
    _ESTOP_SAFE_LIFECYCLE_ACTIONS,
    _decode_error_flags,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def node():
    """Create a MotorConfigService with all ROS2 infrastructure mocked."""
    n = MotorConfigService()
    # Ensure internal state is at a known baseline.
    n._estop_active = False
    return n


def _make_successful_future(result):
    """Create a mock future that looks complete with the given result."""
    future = MagicMock()
    future.done.return_value = True
    future.result.return_value = result
    return future


# ===================================================================
# TASK 8.1 — MotorCommand / MotorLifecycle message structures
# ===================================================================


class TestMotorCommandMessage:
    """Verify MotorCommand .srv message structure and constants."""

    def test_request_fields(self):
        req = MotorCommand.Request()
        req.motor_id = 1
        req.command_type = 0
        req.value = 500.0
        req.max_speed = 100.0
        req.direction = 1
        assert req.motor_id == 1
        assert req.value == 500.0

    @pytest.mark.parametrize(
        "mode,value",
        [
            ("TORQUE", 0),
            ("SPEED", 1),
            ("MULTI_ANGLE_1", 2),
            ("MULTI_ANGLE_2", 3),
            ("SINGLE_ANGLE_1", 4),
            ("SINGLE_ANGLE_2", 5),
            ("INCREMENT_1", 6),
            ("INCREMENT_2", 7),
        ],
    )
    def test_command_type_constants(self, mode, value):
        assert getattr(MotorCommand.Request, mode) == value

    def test_response_fields(self):
        resp = MotorCommand.Response()
        resp.success = True
        resp.error_message = ""
        resp.temperature = 42
        resp.torque_current = 300
        resp.speed = 120
        resp.encoder = 16384
        assert resp.success is True
        assert resp.encoder == 16384


class TestMotorLifecycleMessage:
    """Verify MotorLifecycle .srv message structure and constants."""

    def test_request_fields(self):
        req = MotorLifecycle.Request()
        req.motor_id = 2
        req.action = MotorLifecycle.Request.ON
        assert req.motor_id == 2
        assert req.action == 0

    @pytest.mark.parametrize(
        "action,value",
        [
            ("ON", 0),
            ("OFF", 1),
            ("STOP", 2),
            ("REBOOT", 3),
            ("SAVE_PID_ROM", 4),
            ("SAVE_ZERO_ROM", 5),
        ],
    )
    def test_lifecycle_action_constants(self, action, value):
        assert getattr(MotorLifecycle.Request, action) == value

    def test_response_fields(self):
        resp = MotorLifecycle.Response()
        resp.success = True
        resp.motor_state = 1
        resp.error_message = ""
        assert resp.success is True
        assert resp.motor_state == 1


# ===================================================================
# TASK 8.1 — MotorCommand relay logic
# ===================================================================


class TestMotorCommandRelay:
    """Test _handle_motor_command relay logic."""

    def test_command_forwards_to_controller(self, node):
        """Successful command is forwarded and returns the controller result."""
        req = MotorCommand.Request(motor_id=1, command_type=0, value=200.0)
        resp = MotorCommand.Response()

        controller_resp = MotorCommand.Response(
            success=True,
            temperature=40,
            torque_current=200,
            speed=0,
            encoder=1000,
        )
        future = _make_successful_future(controller_resp)
        node._motor_command_client.wait_for_service.return_value = True
        node._motor_command_client.call_async.return_value = future

        result = node._handle_motor_command(req, resp)
        assert result.success is True
        assert result.temperature == 40

    def test_command_blocked_by_estop(self, node):
        """ALL motor commands are blocked when e-stop is active."""
        node._estop_active = True
        req = MotorCommand.Request(motor_id=1, command_type=0, value=100.0)
        resp = MotorCommand.Response()

        result = node._handle_motor_command(req, resp)
        assert result.success is False
        assert "E-stop" in result.error_message

    @pytest.mark.parametrize("cmd_type", range(8))
    def test_all_command_modes_blocked_by_estop(self, node, cmd_type):
        """Every command mode (0-7) is blocked by e-stop."""
        node._estop_active = True
        req = MotorCommand.Request(motor_id=1, command_type=cmd_type)
        resp = MotorCommand.Response()

        result = node._handle_motor_command(req, resp)
        assert result.success is False
        assert "E-stop" in result.error_message

    def test_command_service_unavailable(self, node):
        """Returns failure when the downstream service is unavailable."""
        req = MotorCommand.Request(motor_id=1, command_type=0, value=50.0)
        resp = MotorCommand.Response()

        node._motor_command_client.wait_for_service.return_value = False

        result = node._handle_motor_command(req, resp)
        assert result.success is False
        assert "unavailable" in result.error_message.lower()

    def test_command_service_timeout(self, node):
        """Returns failure when the service call times out."""
        req = MotorCommand.Request(motor_id=1, command_type=1, value=300.0)
        resp = MotorCommand.Response()

        # Service available but future never completes
        node._motor_command_client.wait_for_service.return_value = True
        timeout_future = MagicMock()
        timeout_future.done.return_value = False
        node._motor_command_client.call_async.return_value = timeout_future

        result = node._handle_motor_command(req, resp)
        assert result.success is False
        assert "unavailable" in result.error_message.lower()


# ===================================================================
# TASK 8.1 — MotorLifecycle relay logic
# ===================================================================


class TestMotorLifecycleRelay:
    """Test _handle_motor_lifecycle relay logic with e-stop enforcement."""

    def _make_lifecycle_result(self, success=True, motor_state=1):
        return MotorLifecycle.Response(
            success=success,
            motor_state=motor_state,
            error_message="",
        )

    def _setup_client_success(self, node, result):
        future = _make_successful_future(result)
        node._motor_lifecycle_client.wait_for_service.return_value = True
        node._motor_lifecycle_client.call_async.return_value = future

    def test_lifecycle_on_forwarded(self, node):
        """ON action is forwarded when e-stop is not active."""
        result = self._make_lifecycle_result(success=True, motor_state=1)
        self._setup_client_success(node, result)

        req = MotorLifecycle.Request(motor_id=1, action=MotorLifecycle.Request.ON)
        resp = MotorLifecycle.Response()
        out = node._handle_motor_lifecycle(req, resp)
        assert out.success is True

    def test_lifecycle_on_blocked_by_estop(self, node):
        """ON is blocked when e-stop is active."""
        node._estop_active = True
        req = MotorLifecycle.Request(motor_id=1, action=MotorLifecycle.Request.ON)
        resp = MotorLifecycle.Response()

        out = node._handle_motor_lifecycle(req, resp)
        assert out.success is False
        assert "E-stop" in out.error_message

    def test_lifecycle_reboot_blocked_by_estop(self, node):
        """REBOOT is blocked when e-stop is active."""
        node._estop_active = True
        req = MotorLifecycle.Request(
            motor_id=1,
            action=MotorLifecycle.Request.REBOOT,
        )
        resp = MotorLifecycle.Response()

        out = node._handle_motor_lifecycle(req, resp)
        assert out.success is False
        assert "E-stop" in out.error_message

    @pytest.mark.parametrize(
        "action",
        [
            MotorLifecycle.Request.OFF,
            MotorLifecycle.Request.STOP,
            MotorLifecycle.Request.SAVE_PID_ROM,
            MotorLifecycle.Request.SAVE_ZERO_ROM,
        ],
    )
    def test_estop_safe_actions_allowed(self, node, action):
        """OFF, STOP, SAVE_PID_ROM, SAVE_ZERO_ROM work even with e-stop."""
        node._estop_active = True
        result = self._make_lifecycle_result(success=True, motor_state=0)
        self._setup_client_success(node, result)

        req = MotorLifecycle.Request(motor_id=1, action=action)
        resp = MotorLifecycle.Response()

        out = node._handle_motor_lifecycle(req, resp)
        assert out.success is True

    def test_lifecycle_service_unavailable(self, node):
        """Returns failure when the downstream lifecycle service is unavailable."""
        node._motor_lifecycle_client.wait_for_service.return_value = False
        req = MotorLifecycle.Request(
            motor_id=1,
            action=MotorLifecycle.Request.STOP,
        )
        resp = MotorLifecycle.Response()

        out = node._handle_motor_lifecycle(req, resp)
        assert out.success is False
        assert "unavailable" in out.error_message.lower()

    def test_lifecycle_updates_telemetry_state(self, node):
        """Successful ON updates the telemetry cache motor_state."""
        result = self._make_lifecycle_result(success=True, motor_state=1)
        self._setup_client_success(node, result)

        req = MotorLifecycle.Request(motor_id=1, action=MotorLifecycle.Request.ON)
        resp = MotorLifecycle.Response()
        node._handle_motor_lifecycle(req, resp)

        assert node._telemetry[1].motor_state == "running"

    def test_lifecycle_off_updates_telemetry(self, node):
        """Successful OFF sets telemetry state to 'off'."""
        node._telemetry[1].motor_state = "running"
        result = self._make_lifecycle_result(success=True, motor_state=0)
        self._setup_client_success(node, result)

        req = MotorLifecycle.Request(motor_id=1, action=MotorLifecycle.Request.OFF)
        resp = MotorLifecycle.Response()
        node._handle_motor_lifecycle(req, resp)

        assert node._telemetry[1].motor_state == "off"

    def test_lifecycle_stop_updates_telemetry(self, node):
        """Successful STOP sets telemetry state to 'stopped'."""
        result = self._make_lifecycle_result(success=True, motor_state=2)
        self._setup_client_success(node, result)

        req = MotorLifecycle.Request(
            motor_id=1,
            action=MotorLifecycle.Request.STOP,
        )
        resp = MotorLifecycle.Response()
        node._handle_motor_lifecycle(req, resp)

        assert node._telemetry[1].motor_state == "stopped"

    def test_lifecycle_failure_does_not_update_telemetry(self, node):
        """Failed lifecycle result does not change telemetry state."""
        node._telemetry[1].motor_state = "unknown"
        result = self._make_lifecycle_result(success=False, motor_state=3)
        self._setup_client_success(node, result)

        req = MotorLifecycle.Request(motor_id=1, action=MotorLifecycle.Request.ON)
        resp = MotorLifecycle.Response()
        node._handle_motor_lifecycle(req, resp)

        assert node._telemetry[1].motor_state == "unknown"


# ===================================================================
# TASK 8.2 — ReadMotorLimits / WriteMotorLimits message structures
# ===================================================================


class TestMotorLimitsMessages:
    """Verify ReadMotorLimits / WriteMotorLimits message structures."""

    def test_read_limits_request_fields(self):
        req = ReadMotorLimits.Request(motor_id=2)
        assert req.motor_id == 2

    def test_read_limits_response_fields(self):
        resp = ReadMotorLimits.Response(
            success=True,
            max_torque_ratio=1500,
            acceleration=10.5,
        )
        assert resp.success is True
        assert resp.max_torque_ratio == 1500
        assert resp.acceleration == pytest.approx(10.5)

    def test_write_limits_request_fields(self):
        req = WriteMotorLimits.Request(
            motor_id=1,
            max_torque_ratio=2000,
            acceleration=5.0,
            set_max_torque=True,
            set_acceleration=True,
        )
        assert req.max_torque_ratio == 2000
        assert req.set_max_torque is True

    def test_write_limits_response_fields(self):
        resp = WriteMotorLimits.Response(success=True, error_message="")
        assert resp.success is True


# ===================================================================
# TASK 8.2 — Motor limits relay logic
# ===================================================================


class TestMotorLimitsRelay:
    """Test _handle_read_motor_limits and _handle_write_motor_limits."""

    def test_read_limits_forwarded(self, node):
        """ReadMotorLimits is a read-only relay — no e-stop check."""
        controller_resp = ReadMotorLimits.Response(
            success=True,
            max_torque_ratio=1200,
            acceleration=8.0,
        )
        future = _make_successful_future(controller_resp)
        node._read_motor_limits_client.wait_for_service.return_value = True
        node._read_motor_limits_client.call_async.return_value = future

        req = ReadMotorLimits.Request(motor_id=1)
        resp = ReadMotorLimits.Response()
        out = node._handle_read_motor_limits(req, resp)
        assert out.success is True
        assert out.max_torque_ratio == 1200

    def test_read_limits_works_during_estop(self, node):
        """ReadMotorLimits is allowed even with e-stop active."""
        node._estop_active = True
        controller_resp = ReadMotorLimits.Response(
            success=True,
            max_torque_ratio=500,
            acceleration=2.0,
        )
        future = _make_successful_future(controller_resp)
        node._read_motor_limits_client.wait_for_service.return_value = True
        node._read_motor_limits_client.call_async.return_value = future

        req = ReadMotorLimits.Request(motor_id=2)
        resp = ReadMotorLimits.Response()
        out = node._handle_read_motor_limits(req, resp)
        assert out.success is True

    def test_write_limits_blocked_by_estop(self, node):
        """WriteMotorLimits is blocked when e-stop active."""
        node._estop_active = True
        req = WriteMotorLimits.Request(
            motor_id=1,
            max_torque_ratio=1000,
            set_max_torque=True,
        )
        resp = WriteMotorLimits.Response()
        out = node._handle_write_motor_limits(req, resp)
        assert out.success is False
        assert "E-stop" in out.error_message

    def test_write_limits_forwarded(self, node):
        """WriteMotorLimits is forwarded when e-stop is not active."""
        controller_resp = WriteMotorLimits.Response(
            success=True,
            error_message="",
        )
        future = _make_successful_future(controller_resp)
        node._write_motor_limits_client.wait_for_service.return_value = True
        node._write_motor_limits_client.call_async.return_value = future

        req = WriteMotorLimits.Request(
            motor_id=1,
            max_torque_ratio=800,
            acceleration=3.0,
            set_max_torque=True,
            set_acceleration=True,
        )
        resp = WriteMotorLimits.Response()
        out = node._handle_write_motor_limits(req, resp)
        assert out.success is True

    def test_write_limits_service_unavailable(self, node):
        """WriteMotorLimits fails gracefully on timeout."""
        node._write_motor_limits_client.wait_for_service.return_value = False
        req = WriteMotorLimits.Request(motor_id=1, max_torque_ratio=100)
        resp = WriteMotorLimits.Response()
        out = node._handle_write_motor_limits(req, resp)
        assert out.success is False
        assert "unavailable" in out.error_message.lower()


# ===================================================================
# TASK 8.2 — ReadEncoder / WriteEncoderZero message structures
# ===================================================================


class TestEncoderMessages:
    """Verify ReadEncoder / WriteEncoderZero message structures."""

    def test_read_encoder_request(self):
        req = ReadEncoder.Request(motor_id=3)
        assert req.motor_id == 3

    def test_read_encoder_response_fields(self):
        resp = ReadEncoder.Response(
            success=True,
            raw_value=32768,
            offset=100,
            original_value=32668,
        )
        assert resp.raw_value == 32768
        assert resp.offset == 100
        assert resp.original_value == 32668

    def test_write_encoder_zero_set_value_mode(self):
        req = WriteEncoderZero.Request(
            motor_id=1,
            mode=WriteEncoderZero.Request.SET_VALUE,
            encoder_value=16384,
        )
        assert req.mode == 0
        assert req.encoder_value == 16384

    def test_write_encoder_zero_set_current_pos_mode(self):
        req = WriteEncoderZero.Request(
            motor_id=2,
            mode=WriteEncoderZero.Request.SET_CURRENT_POS,
        )
        assert req.mode == 1

    def test_write_encoder_zero_response(self):
        resp = WriteEncoderZero.Response(success=True, error_message="")
        assert resp.success is True


# ===================================================================
# TASK 8.2 — Encoder relay logic
# ===================================================================


class TestEncoderRelay:
    """Test _handle_read_encoder and _handle_write_encoder_zero."""

    def test_read_encoder_forwarded(self, node):
        """ReadEncoder is read-only — no e-stop check."""
        controller_resp = ReadEncoder.Response(
            success=True,
            raw_value=40000,
            offset=200,
            original_value=39800,
        )
        future = _make_successful_future(controller_resp)
        node._read_encoder_client.wait_for_service.return_value = True
        node._read_encoder_client.call_async.return_value = future

        req = ReadEncoder.Request(motor_id=1)
        resp = ReadEncoder.Response()
        out = node._handle_read_encoder(req, resp)
        assert out.success is True
        assert out.raw_value == 40000

    def test_read_encoder_during_estop(self, node):
        """ReadEncoder works even with e-stop (read-only)."""
        node._estop_active = True
        controller_resp = ReadEncoder.Response(
            success=True,
            raw_value=10000,
            offset=0,
            original_value=10000,
        )
        future = _make_successful_future(controller_resp)
        node._read_encoder_client.wait_for_service.return_value = True
        node._read_encoder_client.call_async.return_value = future

        req = ReadEncoder.Request(motor_id=2)
        resp = ReadEncoder.Response()
        out = node._handle_read_encoder(req, resp)
        assert out.success is True

    def test_write_encoder_zero_blocked_by_estop(self, node):
        """WriteEncoderZero is blocked when e-stop active."""
        node._estop_active = True
        req = WriteEncoderZero.Request(
            motor_id=1,
            mode=WriteEncoderZero.Request.SET_CURRENT_POS,
        )
        resp = WriteEncoderZero.Response()
        out = node._handle_write_encoder_zero(req, resp)
        assert out.success is False
        assert "E-stop" in out.error_message

    def test_write_encoder_zero_forwarded_set_value(self, node):
        """SET_VALUE mode is forwarded when e-stop clear."""
        controller_resp = WriteEncoderZero.Response(
            success=True,
            error_message="",
        )
        future = _make_successful_future(controller_resp)
        node._write_encoder_zero_client.wait_for_service.return_value = True
        node._write_encoder_zero_client.call_async.return_value = future

        req = WriteEncoderZero.Request(
            motor_id=1,
            mode=WriteEncoderZero.Request.SET_VALUE,
            encoder_value=16384,
        )
        resp = WriteEncoderZero.Response()
        out = node._handle_write_encoder_zero(req, resp)
        assert out.success is True

    def test_write_encoder_zero_forwarded_set_current_pos(self, node):
        """SET_CURRENT_POS mode is forwarded when e-stop clear."""
        controller_resp = WriteEncoderZero.Response(
            success=True,
            error_message="",
        )
        future = _make_successful_future(controller_resp)
        node._write_encoder_zero_client.wait_for_service.return_value = True
        node._write_encoder_zero_client.call_async.return_value = future

        req = WriteEncoderZero.Request(
            motor_id=2,
            mode=WriteEncoderZero.Request.SET_CURRENT_POS,
        )
        resp = WriteEncoderZero.Response()
        out = node._handle_write_encoder_zero(req, resp)
        assert out.success is True

    def test_write_encoder_service_unavailable(self, node):
        """WriteEncoderZero returns failure on service unavailable."""
        node._write_encoder_zero_client.wait_for_service.return_value = False
        req = WriteEncoderZero.Request(
            motor_id=1,
            mode=WriteEncoderZero.Request.SET_VALUE,
            encoder_value=0,
        )
        resp = WriteEncoderZero.Response()
        out = node._handle_write_encoder_zero(req, resp)
        assert out.success is False
        assert "unavailable" in out.error_message.lower()


# ===================================================================
# TASK 8.2 — ReadMotorAngles message structure
# ===================================================================


class TestReadMotorAnglesMessage:
    """Verify ReadMotorAngles .srv message structure."""

    def test_request_fields(self):
        req = ReadMotorAngles.Request(motor_id=3)
        assert req.motor_id == 3

    def test_response_fields(self):
        resp = ReadMotorAngles.Response(
            success=True,
            multi_turn_angle=3.14159,
            single_turn_angle=1.5708,
        )
        assert resp.multi_turn_angle == pytest.approx(3.14159)
        assert resp.single_turn_angle == pytest.approx(1.5708)


# ===================================================================
# TASK 8.2 — ReadMotorAngles relay logic
# ===================================================================


class TestReadMotorAnglesRelay:
    """Test _handle_read_motor_angles."""

    def test_read_angles_forwarded(self, node):
        """ReadMotorAngles is a read-only relay."""
        controller_resp = ReadMotorAngles.Response(
            success=True,
            multi_turn_angle=6.283,
            single_turn_angle=3.14,
        )
        future = _make_successful_future(controller_resp)
        node._read_motor_angles_client.wait_for_service.return_value = True
        node._read_motor_angles_client.call_async.return_value = future

        req = ReadMotorAngles.Request(motor_id=1)
        resp = ReadMotorAngles.Response()
        out = node._handle_read_motor_angles(req, resp)
        assert out.success is True
        assert out.multi_turn_angle == pytest.approx(6.283)

    def test_read_angles_during_estop(self, node):
        """ReadMotorAngles works even with e-stop (read-only)."""
        node._estop_active = True
        controller_resp = ReadMotorAngles.Response(
            success=True,
            multi_turn_angle=0.0,
            single_turn_angle=0.0,
        )
        future = _make_successful_future(controller_resp)
        node._read_motor_angles_client.wait_for_service.return_value = True
        node._read_motor_angles_client.call_async.return_value = future

        req = ReadMotorAngles.Request(motor_id=2)
        resp = ReadMotorAngles.Response()
        out = node._handle_read_motor_angles(req, resp)
        assert out.success is True

    def test_read_angles_service_unavailable(self, node):
        """Returns failure when angles service is unavailable."""
        node._read_motor_angles_client.wait_for_service.return_value = False
        req = ReadMotorAngles.Request(motor_id=1)
        resp = ReadMotorAngles.Response()
        out = node._handle_read_motor_angles(req, resp)
        assert out.success is False


# ===================================================================
# TASK 8.2 — ReadMotorState / ClearMotorErrors message structures
# ===================================================================


class TestReadMotorStateMessage:
    """Verify ReadMotorState .srv message structure."""

    def test_request_fields(self):
        req = ReadMotorState.Request(motor_id=1)
        assert req.motor_id == 1

    def test_response_all_fields(self):
        resp = ReadMotorState.Response(
            success=True,
            temperature_c=45.0,
            voltage_v=24.1,
            torque_current_a=1.5,
            speed_dps=120.0,
            encoder_position=32000,
            multi_turn_deg=720.5,
            single_turn_deg=180.25,
            phase_a=0.5,
            phase_b=0.6,
            phase_c=0.4,
            error_flags=0,
        )
        assert resp.temperature_c == pytest.approx(45.0)
        assert resp.voltage_v == pytest.approx(24.1)
        assert resp.encoder_position == 32000
        assert resp.error_flags == 0


class TestClearMotorErrorsMessage:
    """Verify ClearMotorErrors .srv message structure."""

    def test_request_fields(self):
        req = ClearMotorErrors.Request(motor_id=2)
        assert req.motor_id == 2

    def test_response_fields(self):
        resp = ClearMotorErrors.Response(
            success=True,
            error_flags_after=0,
        )
        assert resp.success is True
        assert resp.error_flags_after == 0

    def test_response_partial_clear(self):
        """Not all flags cleared — error_flags_after is nonzero."""
        resp = ClearMotorErrors.Response(
            success=True,
            error_flags_after=0b00000100,
        )
        assert resp.error_flags_after == 4


# ===================================================================
# TASK 8.2 — ReadMotorState / ClearMotorErrors relay logic
# ===================================================================


class TestReadMotorStateRelay:
    """Test _handle_read_motor_state."""

    def test_read_state_forwarded(self, node):
        """ReadMotorState is read-only — no e-stop check."""
        controller_resp = ReadMotorState.Response(
            success=True,
            temperature_c=38.0,
            voltage_v=23.8,
            speed_dps=0.0,
            encoder_position=16000,
        )
        future = _make_successful_future(controller_resp)
        node._read_motor_state_client.wait_for_service.return_value = True
        node._read_motor_state_client.call_async.return_value = future

        req = ReadMotorState.Request(motor_id=1)
        resp = ReadMotorState.Response()
        out = node._handle_read_motor_state(req, resp)
        assert out.success is True
        assert out.temperature_c == pytest.approx(38.0)

    def test_read_state_during_estop(self, node):
        """ReadMotorState works during e-stop (read-only)."""
        node._estop_active = True
        controller_resp = ReadMotorState.Response(
            success=True,
            temperature_c=50.0,
            voltage_v=24.0,
        )
        future = _make_successful_future(controller_resp)
        node._read_motor_state_client.wait_for_service.return_value = True
        node._read_motor_state_client.call_async.return_value = future

        req = ReadMotorState.Request(motor_id=3)
        resp = ReadMotorState.Response()
        out = node._handle_read_motor_state(req, resp)
        assert out.success is True

    def test_read_state_service_unavailable(self, node):
        """ReadMotorState returns failure on timeout."""
        node._read_motor_state_client.wait_for_service.return_value = False
        req = ReadMotorState.Request(motor_id=1)
        resp = ReadMotorState.Response()
        out = node._handle_read_motor_state(req, resp)
        assert out.success is False


class TestClearMotorErrorsRelay:
    """Test _handle_clear_motor_errors."""

    def test_clear_errors_forwarded(self, node):
        """ClearMotorErrors is always allowed (safety operation)."""
        controller_resp = ClearMotorErrors.Response(
            success=True,
            error_flags_after=0,
        )
        future = _make_successful_future(controller_resp)
        node._clear_motor_errors_client.wait_for_service.return_value = True
        node._clear_motor_errors_client.call_async.return_value = future

        req = ClearMotorErrors.Request(motor_id=1)
        resp = ClearMotorErrors.Response()
        out = node._handle_clear_motor_errors(req, resp)
        assert out.success is True
        assert out.error_flags_after == 0

    def test_clear_errors_during_estop(self, node):
        """ClearMotorErrors works even with e-stop (no e-stop check)."""
        node._estop_active = True
        controller_resp = ClearMotorErrors.Response(
            success=True,
            error_flags_after=0,
        )
        future = _make_successful_future(controller_resp)
        node._clear_motor_errors_client.wait_for_service.return_value = True
        node._clear_motor_errors_client.call_async.return_value = future

        req = ClearMotorErrors.Request(motor_id=2)
        resp = ClearMotorErrors.Response()
        out = node._handle_clear_motor_errors(req, resp)
        assert out.success is True

    def test_clear_errors_service_unavailable(self, node):
        """ClearMotorErrors returns failure on service unavailable."""
        node._clear_motor_errors_client.wait_for_service.return_value = False
        req = ClearMotorErrors.Request(motor_id=1)
        resp = ClearMotorErrors.Response()
        out = node._handle_clear_motor_errors(req, resp)
        assert out.success is False


# ===================================================================
# Cross-cutting: E-stop callback, _fail_response, error flag decoding
# ===================================================================


class TestEstopCallback:
    """Test the _estop_cb subscription callback."""

    def test_estop_stop_activates(self, node):
        """Receiving 'STOP' on the e-stop topic activates e-stop."""
        msg = MagicMock()
        msg.data = "STOP"
        node._estop_cb(msg)
        assert node._estop_active is True

    def test_estop_clear_deactivates(self, node):
        """Receiving 'CLEAR' on the e-stop topic deactivates e-stop."""
        node._estop_active = True
        msg = MagicMock()
        msg.data = "CLEAR"
        node._estop_cb(msg)
        assert node._estop_active is False

    def test_estop_stop_case_insensitive(self, node):
        """E-stop message is case-insensitive (uppercased internally)."""
        msg = MagicMock()
        msg.data = "  stop  "
        node._estop_cb(msg)
        assert node._estop_active is True

    def test_estop_clear_case_insensitive(self, node):
        msg = MagicMock()
        msg.data = "  clear  "
        node._estop_active = True
        node._estop_cb(msg)
        assert node._estop_active is False


class TestFailResponse:
    """Test the _fail_response static helper."""

    def test_sets_success_false_and_message(self):
        resp = MotorCommand.Response()
        result = MotorConfigService._fail_response(resp, "test error")
        assert result.success is False
        assert result.error_message == "test error"
        assert result is resp  # mutates and returns same object


class TestDecodeErrorFlags:
    """Test the _decode_error_flags utility function."""

    def test_no_errors(self):
        flags = _decode_error_flags(0)
        assert all(v is False for v in flags.values())
        assert len(flags) == 8

    def test_single_flag(self):
        flags = _decode_error_flags(0b00000001)
        assert flags["uvp"] is True
        assert flags["ovp"] is False

    def test_multiple_flags(self):
        flags = _decode_error_flags(0b00010010)
        assert flags["ovp"] is True
        assert flags["ocp"] is True
        assert flags["uvp"] is False

    def test_all_flags_set(self):
        flags = _decode_error_flags(0xFF)
        assert all(v is True for v in flags.values())


class TestServiceTimeoutConstant:
    """Verify the service timeout constant value."""

    def test_default_timeout_value(self):
        assert DEFAULT_SERVICE_TIMEOUT_SEC == 5.0


class TestMotorTelemetryDefaults:
    """Verify MotorTelemetry dataclass defaults."""

    def test_default_values(self):
        t = MotorTelemetry()
        assert t.position_deg == 0.0
        assert t.velocity_dps == 0.0
        assert t.motor_state == "unknown"
        assert t.error_flags == 0
        assert len(t.phase_current_a) == 3
