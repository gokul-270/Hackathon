"""Motor config service node — bridges FastAPI backend to motor controller.

This node acts as a relay between the web-based motor configuration dashboard
(via FastAPI) and the C++ motor controller node. It provides:
- Service relay with e-stop safety checks for PID, motor command/lifecycle,
  motor limits, encoder, angles, error clearing, and state reading
- Action client for step response tests
- Tiered CAN telemetry: 10Hz JointState + 1Hz ReadMotorState polling
- Enhanced JSON motor state publishing on /motor_config/motor_state

Backward compatibility: the old ``/pid_tuning/`` namespace service servers
and topics remain active alongside the new ``/motor_config/`` namespace.
"""

import json
import math
import time
from dataclasses import dataclass, field

import rclpy
from rclpy.action import ActionClient
from rclpy.callback_groups import (
    MutuallyExclusiveCallbackGroup,
    ReentrantCallbackGroup,
)
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from motor_control_msgs.action import StepResponseTest
from motor_control_msgs.srv import (
    ClearMotorErrors,
    MotorCommand,
    MotorLifecycle,
    ReadEncoder,
    ReadMotorAngles,
    ReadMotorLimits,
    ReadMotorState,
    ReadPID,
    WriteEncoderZero,
    WriteMotorLimits,
    WritePID,
    WritePIDToROM,
)
from sensor_msgs.msg import JointState
from std_msgs.msg import String

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default timeout for service calls to the C++ motor controller (seconds).
DEFAULT_SERVICE_TIMEOUT_SEC = 5.0

# Motor ID to joint name mapping (from production.yaml).
MOTOR_JOINT_MAP: dict[int, str] = {1: "joint5", 2: "joint3", 3: "joint4"}
JOINT_MOTOR_MAP: dict[str, int] = {v: k for k, v in MOTOR_JOINT_MAP.items()}

# Lifecycle actions that are safe even during e-stop.
_ESTOP_SAFE_LIFECYCLE_ACTIONS: set[int] = {
    MotorLifecycle.Request.OFF,
    MotorLifecycle.Request.STOP,
    MotorLifecycle.Request.SAVE_PID_ROM,
    MotorLifecycle.Request.SAVE_ZERO_ROM,
}

# Error flag bit names (bit 0 → LSB).
_ERROR_FLAG_NAMES: tuple[str, ...] = (
    "uvp",   # bit 0 — undervoltage
    "ovp",   # bit 1 — overvoltage
    "dtp",   # bit 2 — driver thermal protection
    "mtp",   # bit 3 — motor thermal protection
    "ocp",   # bit 4 — overcurrent protection
    "scp",   # bit 5 — short circuit protection
    "sp",    # bit 6 — stall protection
    "lip",   # bit 7 — lock-in protection
)

# Seconds without a successful ReadMotorState before marking motor "unknown".
_STALE_TIMEOUT_SEC = 2.0


# ---------------------------------------------------------------------------
# Telemetry cache
# ---------------------------------------------------------------------------

@dataclass
class MotorTelemetry:
    """Per-motor telemetry cache merging JointState + ReadMotorState data."""

    # --- fast path (10 Hz from JointState) ---
    position_deg: float = 0.0
    velocity_dps: float = 0.0
    torque_current_a: float = 0.0
    js_timestamp: float = 0.0

    # --- slow path (1 Hz from ReadMotorState) ---
    temperature_c: float = 0.0
    voltage_v: float = 0.0
    speed_dps: float = 0.0
    encoder_position: int = 0
    multi_turn_deg: float = 0.0
    single_turn_deg: float = 0.0
    phase_current_a: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    error_flags: int = 0
    slow_timestamp: float = 0.0

    # --- inferred state ---
    motor_state: str = "unknown"


def _decode_error_flags(flags: int) -> dict[str, bool]:
    """Decode an 8-bit error flags byte into a named dict."""
    return {name: bool(flags & (1 << i)) for i, name in enumerate(_ERROR_FLAG_NAMES)}


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

class MotorConfigService(Node):
    """ROS2 relay node between FastAPI backend and motor controller C++ node.

    Creates service servers on ``/motor_config/`` (and legacy ``/pid_tuning/``)
    namespaces that the FastAPI backend calls, and forwards requests to the C++
    motor controller services on ``/motor_control/`` after applying e-stop
    safety checks.
    """

    def __init__(self) -> None:
        super().__init__("motor_config_service")

        # -- Parameters -------------------------------------------------------
        self.declare_parameter("target_motor_id", 0)

        # -- Callback groups --------------------------------------------------
        # Separate group for service *clients* vs *servers* to avoid deadlock.
        self._client_cb_group = MutuallyExclusiveCallbackGroup()
        self._server_cb_group = MutuallyExclusiveCallbackGroup()
        self._sub_cb_group = ReentrantCallbackGroup()

        # -- Service clients (to C++ motor controller) ------------------------
        self._create_service_clients()

        # -- Action client ----------------------------------------------------
        self._step_test_client = ActionClient(
            self,
            StepResponseTest,
            "/motor_control/step_response_test",
            callback_group=self._client_cb_group,
        )

        # -- Service servers --------------------------------------------------
        self._create_service_servers()

        # -- Publishers -------------------------------------------------------
        self._motor_state_pub = self.create_publisher(
            String, "/motor_config/motor_state", 10
        )
        self._legacy_motor_state_pub = self.create_publisher(
            String, "/pid_tuning/motor_state", 10
        )

        # -- Timers -----------------------------------------------------------
        # 10 Hz — publish merged telemetry from JointState cache.
        self._fast_timer = self.create_timer(
            0.1,
            self._publish_motor_state,
            callback_group=self._sub_cb_group,
        )
        # 1 Hz — poll ReadMotorState for slow-changing CAN data.
        self._slow_timer = self.create_timer(
            1.0,
            self._poll_motor_state_slow,
            callback_group=self._sub_cb_group,
        )

        # -- Subscriptions ----------------------------------------------------
        self._joint_state_sub = self.create_subscription(
            JointState,
            "/joint_states",
            self._joint_state_cb,
            10,
            callback_group=self._sub_cb_group,
        )
        self._estop_sub = self.create_subscription(
            String,
            "/safety/emergency_stop",
            self._estop_cb,
            10,
            callback_group=self._sub_cb_group,
        )

        # -- Internal state ---------------------------------------------------
        self._estop_active: bool = False
        self._latest_joint_state: JointState | None = None
        self._active_step_test = None  # Goal handle for in-progress test
        self._telemetry: dict[int, MotorTelemetry] = {
            mid: MotorTelemetry() for mid in MOTOR_JOINT_MAP
        }
        # Round-robin index for slow poll (cycles through motor IDs).
        self._slow_poll_ids: list[int] = list(MOTOR_JOINT_MAP.keys())
        self._slow_poll_idx: int = 0

        self.get_logger().info("Motor config service node initialized")

    # =======================================================================
    # Client / server creation helpers
    # =======================================================================

    def _create_service_clients(self) -> None:
        """Create all service clients to the C++ motor controller."""
        cbg = self._client_cb_group

        # PID services
        self._read_pid_client = self.create_client(
            ReadPID, "/motor_control/read_pid", callback_group=cbg,
        )
        self._write_pid_client = self.create_client(
            WritePID, "/motor_control/write_pid", callback_group=cbg,
        )
        self._write_pid_rom_client = self.create_client(
            WritePIDToROM, "/motor_control/write_pid_to_rom", callback_group=cbg,
        )

        # Motor command / lifecycle
        self._motor_command_client = self.create_client(
            MotorCommand, "/motor_control/motor_command", callback_group=cbg,
        )
        self._motor_lifecycle_client = self.create_client(
            MotorLifecycle, "/motor_control/motor_lifecycle", callback_group=cbg,
        )

        # Motor limits
        self._read_motor_limits_client = self.create_client(
            ReadMotorLimits, "/motor_control/read_motor_limits",
            callback_group=cbg,
        )
        self._write_motor_limits_client = self.create_client(
            WriteMotorLimits, "/motor_control/write_motor_limits",
            callback_group=cbg,
        )

        # Encoder & angles
        self._read_encoder_client = self.create_client(
            ReadEncoder, "/motor_control/read_encoder", callback_group=cbg,
        )
        self._write_encoder_zero_client = self.create_client(
            WriteEncoderZero, "/motor_control/write_encoder_zero",
            callback_group=cbg,
        )
        self._read_motor_angles_client = self.create_client(
            ReadMotorAngles, "/motor_control/read_motor_angles",
            callback_group=cbg,
        )

        # Error clearing & state
        self._clear_motor_errors_client = self.create_client(
            ClearMotorErrors, "/motor_control/clear_motor_errors",
            callback_group=cbg,
        )
        self._read_motor_state_client = self.create_client(
            ReadMotorState, "/motor_control/read_motor_state",
            callback_group=cbg,
        )

    def _create_service_servers(self) -> None:
        """Create all service servers (new + legacy namespaces)."""
        cbg = self._server_cb_group

        # -- PID servers (new /motor_config/ + legacy /pid_tuning/) -----------
        self._read_pid_srv = self.create_service(
            ReadPID, "/motor_config/read_pid",
            self._handle_read_pid, callback_group=cbg,
        )
        self._write_pid_srv = self.create_service(
            WritePID, "/motor_config/write_pid",
            self._handle_write_pid, callback_group=cbg,
        )
        self._write_pid_rom_srv = self.create_service(
            WritePIDToROM, "/motor_config/write_pid_to_rom",
            self._handle_write_pid_to_rom, callback_group=cbg,
        )

        # Legacy PID servers (backward compat)
        self._legacy_read_pid_srv = self.create_service(
            ReadPID, "/pid_tuning/read_pid",
            self._handle_read_pid, callback_group=cbg,
        )
        self._legacy_write_pid_srv = self.create_service(
            WritePID, "/pid_tuning/write_pid",
            self._handle_write_pid, callback_group=cbg,
        )
        self._legacy_write_pid_rom_srv = self.create_service(
            WritePIDToROM, "/pid_tuning/write_pid_to_rom",
            self._handle_write_pid_to_rom, callback_group=cbg,
        )

        # -- Motor command / lifecycle servers --------------------------------
        self._motor_command_srv = self.create_service(
            MotorCommand, "/motor_config/motor_command",
            self._handle_motor_command, callback_group=cbg,
        )
        self._motor_lifecycle_srv = self.create_service(
            MotorLifecycle, "/motor_config/motor_lifecycle",
            self._handle_motor_lifecycle, callback_group=cbg,
        )

        # -- Motor limits servers ---------------------------------------------
        self._read_motor_limits_srv = self.create_service(
            ReadMotorLimits, "/motor_config/read_motor_limits",
            self._handle_read_motor_limits, callback_group=cbg,
        )
        self._write_motor_limits_srv = self.create_service(
            WriteMotorLimits, "/motor_config/write_motor_limits",
            self._handle_write_motor_limits, callback_group=cbg,
        )

        # -- Encoder & angles servers -----------------------------------------
        self._read_encoder_srv = self.create_service(
            ReadEncoder, "/motor_config/read_encoder",
            self._handle_read_encoder, callback_group=cbg,
        )
        self._write_encoder_zero_srv = self.create_service(
            WriteEncoderZero, "/motor_config/write_encoder_zero",
            self._handle_write_encoder_zero, callback_group=cbg,
        )
        self._read_motor_angles_srv = self.create_service(
            ReadMotorAngles, "/motor_config/read_motor_angles",
            self._handle_read_motor_angles, callback_group=cbg,
        )

        # -- Error clearing & state servers -----------------------------------
        self._clear_motor_errors_srv = self.create_service(
            ClearMotorErrors, "/motor_config/clear_motor_errors",
            self._handle_clear_motor_errors, callback_group=cbg,
        )
        self._read_motor_state_srv = self.create_service(
            ReadMotorState, "/motor_config/read_motor_state",
            self._handle_read_motor_state, callback_group=cbg,
        )

    # =======================================================================
    # Generic service relay helper
    # =======================================================================

    def _call_service_synced(self, client, request, timeout: float = DEFAULT_SERVICE_TIMEOUT_SEC):
        """Call a service client synchronously with timeout.

        Parameters
        ----------
        client:
            The ROS2 service client to call.
        request:
            The service request message.
        timeout:
            Maximum seconds to wait for service availability and response.

        Returns
        -------
        The service response, or ``None`` if the service is unavailable or
        the call times out.
        """
        if not client.wait_for_service(timeout_sec=timeout):
            self.get_logger().error(
                f"Service {client.srv_name} not available after {timeout}s"
            )
            return None

        future = client.call_async(request)
        rclpy.spin_until_future_complete(self, future, timeout_sec=timeout)

        if future.done():
            return future.result()

        self.get_logger().error(
            f"Service call to {client.srv_name} timed out"
        )
        return None

    @staticmethod
    def _fail_response(response, error_message: str):
        """Set ``success=False`` and ``error_message`` on a response."""
        response.success = False
        response.error_message = error_message
        return response

    # =======================================================================
    # PID service handlers
    # =======================================================================

    def _handle_read_pid(self, request, response):
        """Forward ReadPID to the motor controller."""
        result = self._call_service_synced(self._read_pid_client, request)
        if result is None:
            return self._fail_response(
                response, "Motor controller service unavailable"
            )
        return result

    def _handle_write_pid(self, request, response):
        """Forward WritePID with e-stop check."""
        if self._estop_active:
            return self._fail_response(response, "E-stop active")
        result = self._call_service_synced(self._write_pid_client, request)
        if result is None:
            return self._fail_response(
                response, "Motor controller service unavailable"
            )
        return result

    def _handle_write_pid_to_rom(self, request, response):
        """Forward WritePIDToROM with e-stop check."""
        if self._estop_active:
            return self._fail_response(response, "E-stop active")
        result = self._call_service_synced(
            self._write_pid_rom_client, request
        )
        if result is None:
            return self._fail_response(
                response, "Motor controller service unavailable"
            )
        return result

    # =======================================================================
    # Motor command / lifecycle handlers (4.3)
    # =======================================================================

    def _handle_motor_command(self, request, response):
        """Forward MotorCommand — blocked entirely when e-stop is active."""
        if self._estop_active:
            return self._fail_response(response, "E-stop active")
        result = self._call_service_synced(
            self._motor_command_client, request
        )
        if result is None:
            return self._fail_response(
                response, "Motor controller service unavailable"
            )
        return result

    def _handle_motor_lifecycle(self, request, response):
        """Forward MotorLifecycle with selective e-stop enforcement.

        E-stop blocks ON and REBOOT actions. OFF, STOP, SAVE_PID_ROM, and
        SAVE_ZERO_ROM are always allowed (safety-critical or non-actuating).
        """
        if (
            self._estop_active
            and request.action not in _ESTOP_SAFE_LIFECYCLE_ACTIONS
        ):
            return self._fail_response(response, "E-stop active")

        result = self._call_service_synced(
            self._motor_lifecycle_client, request
        )
        if result is None:
            return self._fail_response(
                response, "Motor controller service unavailable"
            )

        # Update motor state tracking from lifecycle result.
        self._update_motor_state_from_lifecycle(
            request.motor_id, request.action, result,
        )
        return result

    def _update_motor_state_from_lifecycle(
        self, motor_id: int, action: int, result
    ) -> None:
        """Infer motor state from a successful lifecycle response."""
        if not result.success:
            return
        telem = self._telemetry.get(motor_id)
        if telem is None:
            return

        _STATE_MAP: dict[int, str] = {
            MotorLifecycle.Request.ON: "running",
            MotorLifecycle.Request.OFF: "off",
            MotorLifecycle.Request.STOP: "stopped",
            MotorLifecycle.Request.REBOOT: "off",
        }
        new_state = _STATE_MAP.get(action)
        if new_state is not None:
            telem.motor_state = new_state

    # =======================================================================
    # Motor limits handlers (4.4)
    # =======================================================================

    def _handle_read_motor_limits(self, request, response):
        """Forward ReadMotorLimits (no e-stop check — read only)."""
        result = self._call_service_synced(
            self._read_motor_limits_client, request
        )
        if result is None:
            return self._fail_response(
                response, "Motor controller service unavailable"
            )
        return result

    def _handle_write_motor_limits(self, request, response):
        """Forward WriteMotorLimits with e-stop check."""
        if self._estop_active:
            return self._fail_response(response, "E-stop active")
        result = self._call_service_synced(
            self._write_motor_limits_client, request
        )
        if result is None:
            return self._fail_response(
                response, "Motor controller service unavailable"
            )
        return result

    # =======================================================================
    # Encoder & angles handlers (4.5)
    # =======================================================================

    def _handle_read_encoder(self, request, response):
        """Forward ReadEncoder (read only)."""
        result = self._call_service_synced(
            self._read_encoder_client, request
        )
        if result is None:
            return self._fail_response(
                response, "Motor controller service unavailable"
            )
        return result

    def _handle_write_encoder_zero(self, request, response):
        """Forward WriteEncoderZero with e-stop check."""
        if self._estop_active:
            return self._fail_response(response, "E-stop active")
        result = self._call_service_synced(
            self._write_encoder_zero_client, request
        )
        if result is None:
            return self._fail_response(
                response, "Motor controller service unavailable"
            )
        return result

    def _handle_read_motor_angles(self, request, response):
        """Forward ReadMotorAngles (read only)."""
        result = self._call_service_synced(
            self._read_motor_angles_client, request
        )
        if result is None:
            return self._fail_response(
                response, "Motor controller service unavailable"
            )
        return result

    # =======================================================================
    # Clear errors & read state handlers (4.6)
    # =======================================================================

    def _handle_clear_motor_errors(self, request, response):
        """Forward ClearMotorErrors (always allowed — safety operation)."""
        result = self._call_service_synced(
            self._clear_motor_errors_client, request
        )
        if result is None:
            return self._fail_response(
                response, "Motor controller service unavailable"
            )
        return result

    def _handle_read_motor_state(self, request, response):
        """Forward ReadMotorState (read only)."""
        result = self._call_service_synced(
            self._read_motor_state_client, request
        )
        if result is None:
            return self._fail_response(
                response, "Motor controller service unavailable"
            )
        return result

    # =======================================================================
    # Action client (step response test)
    # =======================================================================

    def send_step_test_goal(
        self,
        motor_id: int,
        step_size_degrees: float,
        duration_seconds: float,
    ):
        """Send a step response test goal to the motor controller.

        Returns a future that resolves to the goal handle, or ``None`` if
        blocked by e-stop or the action server is unavailable.
        """
        if self._estop_active:
            self.get_logger().warn("Step test blocked: e-stop active")
            return None

        if not self._step_test_client.wait_for_server(
            timeout_sec=DEFAULT_SERVICE_TIMEOUT_SEC
        ):
            self.get_logger().error(
                "Step response test action server unavailable"
            )
            return None

        goal = StepResponseTest.Goal()
        goal.motor_id = motor_id
        goal.step_size_degrees = step_size_degrees
        goal.duration_seconds = duration_seconds

        self.get_logger().info(
            f"Sending step test: motor={motor_id}, "
            f"step={step_size_degrees}deg, duration={duration_seconds}s"
        )

        send_goal_future = self._step_test_client.send_goal_async(
            goal, feedback_callback=self._step_test_feedback_cb
        )
        send_goal_future.add_done_callback(self._step_test_goal_response_cb)
        return send_goal_future

    def _step_test_goal_response_cb(self, future) -> None:
        """Handle goal acceptance/rejection response."""
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().warn(
                "Step test goal rejected by motor controller"
            )
            return

        self.get_logger().info("Step test goal accepted")
        self._active_step_test = goal_handle

        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self._step_test_result_cb)

    def _step_test_feedback_cb(self, feedback_msg) -> None:
        """Log step test progress."""
        fb = feedback_msg.feedback
        self.get_logger().debug(
            f"Step test progress: {fb.progress_percent:.0f}% "
            f"pos={fb.current_position:.2f}deg "
            f"t={fb.elapsed_seconds:.2f}s"
        )

    def _step_test_result_cb(self, future) -> None:
        """Handle step test completion."""
        self._active_step_test = None
        result = future.result().result
        if result.success:
            self.get_logger().info(
                f"Step test complete: {len(result.timestamps)} samples"
            )
        else:
            self.get_logger().error(
                f"Step test failed: {result.error_message}"
            )

    def _cancel_active_step_test(self) -> None:
        """Cancel any in-progress step test."""
        if self._active_step_test is not None:
            self.get_logger().warn(
                "Cancelling active step test due to e-stop"
            )
            self._active_step_test.cancel_goal_async()
            self._active_step_test = None

    # =======================================================================
    # Subscription callbacks
    # =======================================================================

    def _joint_state_cb(self, msg: JointState) -> None:
        """Cache latest JointState and update fast telemetry."""
        self._latest_joint_state = msg
        stamp_sec = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9

        for idx, name in enumerate(msg.name):
            motor_id = JOINT_MOTOR_MAP.get(name)
            if motor_id is None:
                continue
            telem = self._telemetry.get(motor_id)
            if telem is None:
                continue

            telem.position_deg = (
                math.degrees(msg.position[idx])
                if idx < len(msg.position)
                else 0.0
            )
            telem.velocity_dps = (
                math.degrees(msg.velocity[idx])
                if idx < len(msg.velocity)
                else 0.0
            )
            telem.torque_current_a = (
                msg.effort[idx] if idx < len(msg.effort) else 0.0
            )
            telem.js_timestamp = stamp_sec

    def _estop_cb(self, msg: String) -> None:
        """Handle emergency stop messages."""
        text = msg.data.strip().upper()
        if text == "STOP":
            if not self._estop_active:
                self.get_logger().warn(
                    "E-stop activated — blocking motor writes/commands"
                )
            self._estop_active = True
            self._cancel_active_step_test()
        elif text == "CLEAR":
            if self._estop_active:
                self.get_logger().info("E-stop cleared")
            self._estop_active = False

    # =======================================================================
    # Tiered telemetry polling (4.8)
    # =======================================================================

    def _poll_motor_state_slow(self) -> None:
        """1 Hz poll: call ReadMotorState for one motor per cycle.

        Round-robins through all configured motor IDs so each motor is
        polled every ``len(MOTOR_JOINT_MAP)`` seconds.
        """
        if not self._slow_poll_ids:
            return

        motor_id = self._slow_poll_ids[
            self._slow_poll_idx % len(self._slow_poll_ids)
        ]
        self._slow_poll_idx += 1

        req = ReadMotorState.Request()
        req.motor_id = motor_id
        result = self._call_service_synced(
            self._read_motor_state_client, req, timeout=2.0
        )

        telem = self._telemetry.get(motor_id)
        if telem is None:
            return

        now = time.monotonic()

        if result is not None and result.success:
            telem.temperature_c = float(result.temperature_c)
            telem.voltage_v = float(result.voltage_v)
            telem.speed_dps = float(result.speed_dps)
            telem.encoder_position = int(result.encoder_position)
            telem.multi_turn_deg = float(result.multi_turn_deg)
            telem.single_turn_deg = float(result.single_turn_deg)
            telem.phase_current_a = [
                float(result.phase_a),
                float(result.phase_b),
                float(result.phase_c),
            ]
            telem.error_flags = int(result.error_flags)
            telem.slow_timestamp = now

            # Infer state from error flags.
            if telem.error_flags != 0:
                telem.motor_state = "error"
        else:
            # Service call failed — check staleness.
            if now - telem.slow_timestamp > _STALE_TIMEOUT_SEC:
                telem.motor_state = "unknown"

    # =======================================================================
    # Motor state publishing (4.9 — enhanced JSON payload)
    # =======================================================================

    def _publish_motor_state(self) -> None:
        """10 Hz: publish enhanced JSON telemetry per motor.

        Merges fast JointState data with cached slow ReadMotorState data.
        """
        target_id = (
            self.get_parameter("target_motor_id")
            .get_parameter_value()
            .integer_value
        )

        for motor_id, telem in self._telemetry.items():
            if target_id != 0 and motor_id != target_id:
                continue
            # Skip if we have never received any JointState for this motor.
            if telem.js_timestamp == 0.0:
                continue

            payload = {
                "motor_id": motor_id,
                "timestamp": round(telem.js_timestamp, 3),
                "temperature_c": round(telem.temperature_c, 1),
                "voltage_v": round(telem.voltage_v, 1),
                "torque_current_a": round(telem.torque_current_a, 3),
                "speed_dps": round(telem.velocity_dps, 3),
                "encoder_position": telem.encoder_position,
                "multi_turn_deg": round(telem.multi_turn_deg, 2),
                "single_turn_deg": round(telem.single_turn_deg, 2),
                "phase_current_a": [
                    round(v, 3) for v in telem.phase_current_a
                ],
                "error_flags": _decode_error_flags(telem.error_flags),
                "motor_state": telem.motor_state,
            }

            msg = String()
            msg.data = json.dumps(payload)
            self._motor_state_pub.publish(msg)
            self._legacy_motor_state_pub.publish(msg)


# ===========================================================================
# Entry point
# ===========================================================================

def main(args=None) -> None:
    """Entry point — runs the node with a multi-threaded executor."""
    rclpy.init(args=args)
    node = MotorConfigService()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
