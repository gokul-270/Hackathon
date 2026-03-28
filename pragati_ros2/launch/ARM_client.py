#!/usr/bin/env python3
"""
ARM Client MQTT Bridge for ROS-2
=================================
Bridges MQTT commands from vehicle host to ROS-2 yanthra_move system.
Ported from ROS-1 to ROS-2 (pragati/launch_files/ARM_client.py).

MQTT Topics (Subscribe, per-arm):
  - topic/start_switch_input_<client_id>    : Start command for this arm
  - topic/shutdown_switch_input_<client_id>  : Shutdown command for this arm

MQTT Topics (Subscribe, broadcast):
  - topic/start_switch_input_all    : Start command for all arms
  - topic/shutdown_switch_input_all  : Shutdown command for all arms

MQTT Topics (Publish):
  - topic/ArmStatus_<client_id>  : Arm status to host

ROS-2 Topics (Publish):
  - /start_switch/command    : Bool (trigger start)
  - /shutdown_switch/command  : Bool (trigger shutdown)

ROS-2 Services (Call):
  - /yanthra_move/current_arm_status : Get arm status

Dual Logging Design:
  - Python logging module  -> ~/pragati_ros2/logs/arm_client_<client_id>_*.log
    Used for: MQTT traffic, threading, connection events (SCP'd off RPi for debugging)
  - ROS2 self.get_logger() -> ROS2 session log (ros2 launch output)
    Used for: state machine events, service call results, startup/shutdown
  The startup banner (stdout) bridges both by putting key info in the session log.
"""

# =============================================================================
# Task 4.1: argparse BEFORE ROS2/MQTT imports so parse errors exit cleanly
# =============================================================================
import argparse
import os
import sys

_parser = argparse.ArgumentParser(
    description="ARM Client MQTT Bridge for ROS-2",
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
)
_parser.add_argument(
    "--mqtt-address",
    default=None,
    help="MQTT broker IP address (default: 10.42.0.10)",
)
_parser.add_argument(
    "--client-id",
    default="arm1",
    help="ARM client identifier; used as MQTT client_id and topic suffix",
)
_parser.add_argument(
    "--service-wait-timeout",
    type=int,
    default=60,
    help="Maximum seconds to wait for arm_status service before exiting",
)
_args = _parser.parse_args()

# -------------------------------------------------------------------------
# Task 3.1: MQTT address source tracking
# Priority: CLI arg > environment variable > hardcoded default
# -------------------------------------------------------------------------
_MQTT_DEFAULT = "10.42.0.10"
if _args.mqtt_address is not None:
    _mqtt_address_source = "launch_arg"
elif os.environ.get("MQTT_ADDRESS"):
    _args.mqtt_address = os.environ["MQTT_ADDRESS"]
    _mqtt_address_source = "env"
else:
    _args.mqtt_address = _MQTT_DEFAULT
    _mqtt_address_source = "default"

# =============================================================================
# Task 5.2: Wrap rclpy / Node imports in try/except for clear diagnostics
# =============================================================================
try:
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import Bool
except (ModuleNotFoundError, ImportError) as _e:
    print(
        f"FATAL: Failed to import ROS2 modules: {_e}\n"
        "  Ensure the ROS2 workspace is sourced: source install/setup.bash\n"
        "  Exit code 1 (application-level failure, not Python interpreter error)"
    )
    sys.exit(1)

# =============================================================================
# Task 5.1: Wrap yanthra_move service import in try/except
# =============================================================================
try:
    from yanthra_move.srv import ArmStatus
except (ModuleNotFoundError, ImportError) as _e:
    print(
        f"FATAL: Failed to import yanthra_move.srv.ArmStatus: {_e}\n"
        "  Ensure the workspace is built and sourced: colcon build && source install/setup.bash\n"
        "  Exit code 1 (application-level failure, not Python interpreter error)"
    )
    sys.exit(1)

import glob
import queue
import signal
import threading
import time
import traceback
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# MQTT import
try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("FATAL: paho-mqtt not installed. Run: pip3 install paho-mqtt")
    sys.exit(1)


# =============================================================================
# Task 4.2 / 4.3: Use parsed CLI args (no more hardcoded values)
# =============================================================================
MQTT_ADDRESS = _args.mqtt_address
MQTT_ADDRESS_SOURCE = _mqtt_address_source  # Task 3.1: "launch_arg", "env", or "default"
CLIENT_ID = _args.client_id
SERVICE_WAIT_TIMEOUT = _args.service_wait_timeout

# =============================================================================
# CONFIGURATION
# =============================================================================
DEBUGLOG = True
DEBUGLOG1 = False

MQTT_KEEPALIVE_S = 30  # MQTT keepalive interval (broker ping timeout)
STATUS_POLL_INTERVAL_S = 1  # seconds between state machine iterations

# Recovery configuration
MAX_SERVICE_CALL_RETRIES = 3
SERVICE_RETRY_DELAY = 1.0  # seconds
ERROR_STATE_RECOVERY_TIMEOUT = 30.0  # seconds before auto-recovery attempt
MQTT_RECONNECT_DELAY = 5.0  # seconds between reconnection attempts
HEALTH_CHECK_INTERVAL = 10.0  # seconds
MAX_CONSECUTIVE_FAILURES = 5  # Max failures before triggering recovery
MQTT_RECONNECT_CHECK_INTERVAL = 2.0  # aggressive reconnect when disconnected
SERVICE_BACKOFF_THRESHOLD = 10  # consecutive failures before reducing call frequency
HEARTBEAT_PUBLISH_INTERVAL = 5.0  # seconds between unconditional status re-publishes


def _parse_bool_payload(s: str) -> bool:
    """Parse MQTT payload as boolean, case-insensitive.

    Accepts "true", "True", "TRUE", "1", "yes" as truthy.
    Everything else (including "false", "False", "0", "no", "") is falsy.
    """
    return s.strip().lower() in ("true", "1", "yes")


SERVICE_BACKOFF_PROBE_INTERVAL = 10.0  # seconds between probes when in backoff
WATCHDOG_LOG_INTERVAL = 60.0  # seconds between watchdog warnings

# MQTT reason code lookup table
MQTT_RC_CODES = {
    0: "Connection successful",
    1: "Incorrect protocol version",
    2: "Invalid client identifier",
    3: "Server unavailable",
    4: "Bad username or password",
    5: "Not authorized",
    7: "Connection lost (keepalive timeout or network failure)",
}


# =============================================================================
# Task 14.3 / 14.4: Move log setup into function; include client_id in filename
# =============================================================================
def _setup_logging(client_id):
    """Configure file + stdout logging. Returns (logger, log_file_path).

    Moving this out of module-level prevents import-time side effects and
    log-file races when two ARM_client instances start simultaneously.
    """
    log_dir = os.path.expanduser("~/pragati_ros2/logs")
    os.makedirs(log_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"arm_client_{client_id}_{timestamp}.log")

    # Log rotation: keep only last 10 log files per client_id
    existing = sorted(glob.glob(os.path.join(log_dir, f"arm_client_{client_id}_*.log")))
    if len(existing) > 10:
        for old_log in existing[:-10]:
            try:
                os.remove(old_log)
                print(f"Removed old log file: {old_log}")
            except Exception as exc:
                print(f"Warning: Could not remove old log {old_log}: {exc}")

    log = logging.getLogger(f"ARM_CLIENT_{client_id}")
    log.setLevel(logging.DEBUG)
    if not log.handlers:
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        fh = logging.FileHandler(log_file)
        fh.setFormatter(fmt)
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        log.addHandler(fh)
        log.addHandler(sh)

    return log, log_file


# =============================================================================
# Task 8.1: Thread-safe command queue (MQTT -> ROS2 bridge)
# maxsize=50: at 1 Hz, 50 messages = 50 seconds of backlog before drop-oldest
# =============================================================================
command_queue: queue.Queue = queue.Queue(maxsize=50)


# =============================================================================
# Task 14.1: ArmClientState dataclass replaces 13 global variables
# =============================================================================
@dataclass
class ArmClientState:
    """Consolidated state for ARM client. Passed explicitly to functions."""

    # MQTT connection state
    mqtt_status: str = "UNINITIALISED"
    mqtt_connected: bool = False
    mqtt_connection_count: int = 0
    mqtt_reconnect_count: int = 0
    mqtt_disconnect_time: Optional[float] = None  # when disconnect detected

    # ROS2 service health
    last_successful_service_call: float = field(default_factory=time.time)
    consecutive_service_failures: int = 0
    last_service_probe_time: float = 0.0  # last probe in backoff mode

    # Heartbeat: re-publish current status periodically so vehicle never goes stale
    last_heartbeat_publish_time: float = 0.0

    # Watchdog timestamps
    last_mqtt_message_received_time: Optional[float] = None
    last_watchdog_mqtt_warning: float = 0.0
    last_watchdog_service_warning: float = 0.0

    # Error / recovery state
    last_error_state_time: Optional[float] = None
    error_recovery_attempted: bool = False
    error_recovery_attempt_count: int = 0
    error_recovery_window_start: float = field(default_factory=time.time)
    last_recovery_attempt_time: float = 0.0

    # Published status (for error-state throttle)
    last_published_status: str = ""
    last_error_publish_time: float = 0.0

    # Group 9: Signal chain monitoring
    last_received_seq: int = 0
    last_start_switch_time: Optional[float] = None
    last_silence_warning_time: float = 0.0

    # Group 10: MQTT loopback self-test
    selftest_last_sent: float = 0.0
    selftest_last_received: float = 0.0
    selftest_consecutive_failures: int = 0
    selftest_loop_counter: int = 0

    # Shutdown flag (set by signal handler)
    shutdown_requested: bool = False


# Module-level references set in main()
_state: Optional[ArmClientState] = None
_logger: Optional[logging.Logger] = None
_mqtt_client = None
_ros_node = None
_mutex = threading.Lock()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================
def printINFO(txtmsg):
    """Print info messages if DEBUGLOG enabled"""
    if DEBUGLOG and _logger:
        _logger.info(txtmsg)


def printINFO1(txtmsg):
    """Print verbose debug messages if DEBUGLOG1 enabled"""
    if DEBUGLOG1 and _logger:
        _logger.debug(txtmsg)


# =============================================================================
# MQTT CALLBACKS
# =============================================================================
def on_connect(client, userdata, flags, rc):
    """MQTT connection callback"""
    state = _state
    state.mqtt_connection_count += 1

    if rc == 0:
        is_reconnect = state.mqtt_connection_count > 1
        if is_reconnect:
            state.mqtt_reconnect_count += 1
            # Log disconnect duration
            if state.mqtt_disconnect_time is not None:
                disconnect_duration = time.time() - state.mqtt_disconnect_time
                _logger.warning(
                    f"[SIGNAL_CHAIN] MQTT RECONNECTED"
                    f" | downtime={disconnect_duration:.1f}s"
                    f" | attempt={state.mqtt_connection_count}"
                    f" | total_reconnects={state.mqtt_reconnect_count}"
                )
                state.mqtt_disconnect_time = None
            else:
                _logger.warning(
                    f"[SIGNAL_CHAIN] MQTT RECONNECTED"
                    f" | attempt={state.mqtt_connection_count}"
                    f" | total_reconnects={state.mqtt_reconnect_count}"
                )
        else:
            _logger.info(
                f"[SIGNAL_CHAIN] MQTT Connected successfully (initial connection)"
                f" | attempt={state.mqtt_connection_count}"
                f" | total_reconnects={state.mqtt_reconnect_count}"
            )

        state.mqtt_connected = True
        state.consecutive_service_failures = 0  # Reset on reconnect
    else:
        rc_desc = MQTT_RC_CODES.get(rc, "Unknown reason code")
        _logger.error(f"MQTT connection failed (code={rc}: {rc_desc})")
        _logger.error(" *** ARM_client Error in Connecting *** ")
        state.mqtt_connected = False
        return

    # Task 10.1 + 10.2: Subscribe immediately -- no sleep before subscribe
    # Canonical topic names (no trailing underscores); see also task 10.3/13.1/13.2
    client_id = CLIENT_ID
    mqtt_topics = [
        # Task 13.1: per-arm topics derived from client_id
        f"topic/start_switch_input_{client_id}",
        f"topic/shutdown_switch_input_{client_id}",
        # Task 13.2: broadcast topics for commanding all arms simultaneously
        "topic/start_switch_input_all",
        "topic/shutdown_switch_input_all",
    ]
    for topic in mqtt_topics:
        result, mid = client.subscribe(topic)
        if result == mqtt.MQTT_ERR_SUCCESS:
            printINFO(f"Subscribed to topic: {topic} - SUCCESSFUL")
        else:
            _logger.error(f"Subscription to topic {topic} FAILED: error code {result}")

    # Task 10.1: Self-test loopback subscription
    selftest_topic = f"topic/arm_selftest_{client_id}"
    result, mid = client.subscribe(selftest_topic, qos=1)
    if result == mqtt.MQTT_ERR_SUCCESS:
        printINFO(f"Subscribed to self-test topic: {selftest_topic}")

    # On reconnection, re-publish current status so vehicle gets immediate update
    if is_reconnect:
        status_topic = f"topic/ArmStatus_{client_id}"
        try:
            client.publish(status_topic, state.mqtt_status, qos=1)
            _logger.info(f"Reconnect: re-published status '{state.mqtt_status}' to {status_topic}")
        except Exception as exc:
            _logger.warning(f"Failed to re-publish status on reconnect: {exc}")


def on_message(client, userdata, msg):
    """MQTT message received callback.

    Task 8.2 / 8.3: Enqueue commands instead of calling ROS2 publish directly.
    The paho network thread must NOT call ROS2 APIs (thread-unsafe).
    """
    state = _state
    payload_str = (
        msg.payload.decode("utf-8") if isinstance(msg.payload, bytes) else str(msg.payload)
    )
    printINFO(f"Received MQTT message from topic: {msg.topic}, payload: {payload_str}")

    # Watchdog: track last MQTT message time
    state.last_mqtt_message_received_time = time.time()

    # Detect and discard retained (stale) messages from the broker.
    # These are leftover from a previous session and should not trigger actions.
    if msg.retain:
        _logger.warning(
            f"Discarding RETAINED MQTT message on {msg.topic} "
            f"(payload={payload_str}) — stale from previous session"
        )
        return

    client_id = CLIENT_ID

    # Task 10.2: Self-test loopback — intercept before normal processing
    selftest_topic = f"topic/arm_selftest_{client_id}"
    if msg.topic == selftest_topic:
        _state.selftest_last_received = time.monotonic()
        return  # Don't process further

    start_topics = {
        f"topic/start_switch_input_{client_id}",
        "topic/start_switch_input_all",
    }
    shutdown_topics = {
        f"topic/shutdown_switch_input_{client_id}",
        "topic/shutdown_switch_input_all",
    }

    if msg.topic in start_topics:
        # Task 9.1: Parse seq from payload (format: "True|seq=N")
        seq_str = ""
        if "|" in payload_str:
            parts = payload_str.split("|")
            cmd_value = _parse_bool_payload(parts[0])
            for part in parts[1:]:
                if part.startswith("seq="):
                    seq_str = part
                    break
        else:
            cmd_value = _parse_bool_payload(payload_str)

        # Task 9.2: Track sequence gaps
        if seq_str:
            seq_num = int(seq_str.split("=")[1])
            if _state.last_received_seq > 0 and seq_num != _state.last_received_seq + 1:
                expected = _state.last_received_seq + 1
                missed = seq_num - expected
                _logger.warning(
                    f"[SIGNAL_CHAIN] WARN: seq gap detected"
                    f" | expected={expected} received={seq_num} missed={missed}"
                )
            _state.last_received_seq = seq_num

        # Task 9.3: Update silence watchdog timestamp
        _state.last_start_switch_time = time.time()

        # Gate: only enqueue if arm is ready (guard checked in _drain_command_queue)
        cmd_type = "start"
        _logger.info(
            "[SIGNAL_CHAIN] ARM_client: Received start_switch from MQTT"
            " | source=topic/start_switch_input_all dest=/start_switch/command"
            + (f" | {seq_str}" if seq_str else "")
        )
    elif msg.topic in shutdown_topics:
        cmd_type = "shutdown"
        cmd_value = _parse_bool_payload(payload_str)
        _logger.info(
            "[SIGNAL_CHAIN] ARM_client: Received shutdown_switch from MQTT"
            " | source=topic/shutdown_switch_input_all"
            " dest=/shutdown_switch/command"
        )
    else:
        printINFO(f"Ignoring unknown topic: {msg.topic}")
        return

    try:
        command_queue.put_nowait((cmd_type, cmd_value, state.mqtt_status))
    except queue.Full:
        # Task 8.3: Drop oldest on overflow
        _logger.warning("command queue full, dropping oldest to make room for new command")
        try:
            command_queue.get_nowait()
        except queue.Empty:
            pass
        try:
            command_queue.put_nowait((cmd_type, cmd_value, state.mqtt_status))
        except queue.Full:
            _logger.error("command queue still full after dropping oldest -- message lost")


def on_disconnect(client, userdata, rc):
    """MQTT disconnection callback -- triggers automatic reconnection"""
    state = _state
    state.mqtt_connected = False
    state.mqtt_disconnect_time = time.time()
    if rc != 0:
        rc_desc = MQTT_RC_CODES.get(rc, "Unknown reason code")
        _logger.warning(
            f"[SIGNAL_CHAIN] MQTT UNEXPECTED DISCONNECT"
            f" | code={rc} reason={rc_desc}"
            f" | total_reconnects={state.mqtt_reconnect_count}"
        )
    else:
        _logger.info("[SIGNAL_CHAIN] MQTT Disconnected cleanly (code=0: clean disconnect)")


def on_log(client, userdata, level, buf):
    """MQTT logging callback"""
    printINFO1(f"MQTT log: {buf}")


# =============================================================================
# Task 8.4 / 8.5: Drain command queue -- called from main loop after spin_once
# =============================================================================
def _drain_command_queue(ros_node, state):
    """Dequeue all pending MQTT commands and execute corresponding ROS2 publishes.

    Must be called from the ROS2 executor thread (main loop), never from paho callbacks.
    """
    while not command_queue.empty():
        try:
            cmd_type, cmd_value, mqtt_status_at_enqueue = command_queue.get_nowait()
        except queue.Empty:
            break

        if cmd_type == "start":
            if mqtt_status_at_enqueue == "ready" and cmd_value:
                PublishToMARCHostAndUpdate("ACK", state)
            start_msg = Bool()
            start_msg.data = cmd_value
            ros_node.start_pub.publish(start_msg)
            _logger.info(
                "[SIGNAL_CHAIN] ARM_client: Published start_switch to ROS2"
                " | source=MQTT dest=/start_switch/command"
            )
            printINFO(f"Published START={cmd_value} command to ROS-2: /start_switch/command")
        elif cmd_type == "shutdown":
            shutdown_msg = Bool()
            shutdown_msg.data = cmd_value
            ros_node.shutdown_pub.publish(shutdown_msg)
            _logger.info(
                "[SIGNAL_CHAIN] ARM_client: Published shutdown_switch to ROS2"
                " | source=MQTT dest=/shutdown_switch/command"
            )
            printINFO(f"Published SHUTDOWN={cmd_value} command to ROS-2: /shutdown_switch/command")


# =============================================================================
# MQTT PUBLISHER (THREAD-SAFE)
# =============================================================================
def PublishToMARCHostAndUpdate(status, state):
    """Thread-safe update and publish of ARM client status to MQTT.

    Task 9.1 / 9.2: mutex acquire uses timeout=5 to detect deadlocks.
    Task 12.1: skip publish if already in error state (re-publish on state change
               or after 30s heartbeat).
    Task 13.3: publish topic derived from CLIENT_ID.
    """
    now = time.time()

    # Task 12.1: error-state publish throttle
    if status == "error" and state.last_published_status == "error":
        # Only re-publish after 30s heartbeat interval
        if now - state.last_error_publish_time < 30.0:
            return  # Skip -- already published error recently
    if status == "error":
        state.last_error_publish_time = now

    printINFO1(f"PublishToMARCHostAndUpdate status input = {status}")

    # Task 9.1 / 9.2: acquire with 5s timeout to prevent deadlocks
    acquired = _mutex.acquire(timeout=5)
    if not acquired:
        _logger.warning(
            "WARN: mutex acquire timed out after 5s -- possible deadlock; skipping publish"
        )
        return

    try:
        state.mqtt_status = status
        state.last_published_status = status

        max_retries = 3
        for attempt in range(max_retries):
            try:
                if state.mqtt_connected and _mqtt_client:
                    # Task 13.3: topic derived from CLIENT_ID
                    topic = f"topic/ArmStatus_{CLIENT_ID}"
                    result = _mqtt_client.publish(topic, state.mqtt_status)
                    if result.rc == mqtt.MQTT_ERR_SUCCESS:
                        printINFO(f"Published ARM status to MQTT: {state.mqtt_status}")
                        break
                    else:
                        printINFO(
                            f"MQTT publish failed (rc={result.rc}), "
                            f"attempt {attempt + 1}/{max_retries}"
                        )
                else:
                    printINFO("MQTT not connected, skipping publish")
                    break
            except Exception as exc:
                print(f"Exception during MQTT publish (attempt {attempt + 1}): {exc}")

            if attempt < max_retries - 1:
                time.sleep(0.5)
    finally:
        _mutex.release()


# =============================================================================
# ROS-2 NODE CLASS
# =============================================================================
class ARMClientNode(Node):
    """ROS-2 node for ARM client"""

    def __init__(self):
        super().__init__("arm_client_node")

        # Create publishers
        self.start_pub = self.create_publisher(Bool, "/start_switch/command", 10)
        self.shutdown_pub = self.create_publisher(Bool, "/shutdown_switch/command", 10)

        # Create service client for arm status
        self.arm_status_client = self.create_client(ArmStatus, "/yanthra_move/current_arm_status")

        printINFO("ROS-2 ARM Client Node initialized")
        printINFO("  Publishers: /start_switch/command, /shutdown_switch/command")
        printINFO("  Service client: /yanthra_move/current_arm_status")

        # Task 7.1-7.4: Bounded service wait (no more infinite loop)
        max_retries = SERVICE_WAIT_TIMEOUT // 5
        printINFO(
            f"Waiting for /yanthra_move/current_arm_status service "
            f"(timeout={SERVICE_WAIT_TIMEOUT}s, max_retries={max_retries})..."
        )
        for attempt in range(1, max_retries + 1):
            # Task 7.3: exit immediately on SIGTERM/shutdown
            if not rclpy.ok():
                print("FATAL: rclpy shutdown during service wait -- exiting")
                sys.exit(1)
            # Task 7.4: log each retry
            printINFO(f"Waiting for arm_status service... attempt {attempt}/{max_retries}")
            if self.arm_status_client.wait_for_service(timeout_sec=5.0):
                break
            if attempt == max_retries:
                # Task 7.2: FATAL diagnostic + clean exit
                print(
                    f"FATAL: arm_status service not available after {SERVICE_WAIT_TIMEOUT}s "
                    f"-- is yanthra_move_node running?"
                )
                sys.exit(1)

        printINFO("Arm status service is available!")

    def call_arm_status_service(self, state, retry_on_failure=True):
        """Call arm status service with automatic retry and recovery.

        Returns: (status, reason) tuple or (None, None) on failure.
        """
        max_retries = MAX_SERVICE_CALL_RETRIES if retry_on_failure else 1

        for attempt in range(max_retries):
            try:
                request = ArmStatus.Request()
                future = self.arm_status_client.call_async(request)

                # Wait for response with timeout
                rclpy.spin_until_future_complete(self, future, timeout_sec=2.0)

                if future.done():
                    response = future.result()
                    if response:
                        state.last_successful_service_call = time.time()
                        state.consecutive_service_failures = 0
                        return (response.status, response.reason)
                    else:
                        self.get_logger().error("Arm status service returned None")
                else:
                    self.get_logger().warn(
                        f"Arm status service call timed out "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )

            except Exception as exc:
                self.get_logger().error(
                    f"Exception calling arm status service "
                    f"(attempt {attempt + 1}/{max_retries}): {exc}"
                )

            if attempt < max_retries - 1:
                time.sleep(SERVICE_RETRY_DELAY)

        # All retries failed
        state.consecutive_service_failures += 1
        service_available = self.arm_status_client.service_is_ready()
        self.get_logger().warn(
            f"Service call failed (consecutive: {state.consecutive_service_failures}, "
            f"service_in_graph: {service_available})"
        )
        # Prominent diagnostic at thresholds
        if state.consecutive_service_failures in (5, 10, 25, 50, 100):
            elapsed = time.time() - state.last_successful_service_call
            self.get_logger().error(
                f"=== SERVICE FAILURE DIAGNOSTIC ===  "
                f"Service: /yanthra_move/current_arm_status  "
                f"Consecutive failures: {state.consecutive_service_failures}  "
                f"Time since last success: {elapsed:.1f}s  "
                f"Service in ROS2 graph: {service_available}  "
                f"================================="
            )
        return (None, None)


# =============================================================================
# Task 12.2-12.5: Functional error recovery (replaces no-op placeholder)
# =============================================================================
def attempt_error_recovery(ros_node, state):
    """Attempt to recover from error state.

    Task 12.2: checks service availability, attempts one call, returns True on success.
    Task 12.3: returns False after 3+ consecutive failures (unrecoverable).
    Task 12.4: throttle -- max 5 attempts in 60s, then 1 per 30s.
    Task 12.5: log attempts and outcomes at INFO level.
    """
    now = time.time()

    # Task 12.4: Throttle recovery attempts
    recovery_window_elapsed = now - state.error_recovery_window_start
    if recovery_window_elapsed > 60.0:
        # Reset window
        state.error_recovery_attempt_count = 0
        state.error_recovery_window_start = now

    if state.error_recovery_attempt_count >= 5:
        # More than 5 attempts in 60s -- throttle to 1 per 30s
        time_since_last = now - state.last_recovery_attempt_time
        if time_since_last < 30.0:
            return False  # throttled

    state.error_recovery_attempt_count += 1
    state.last_recovery_attempt_time = now

    _logger.info(
        f"Attempting error recovery (attempt #{state.error_recovery_attempt_count} "
        f"in current 60s window, consecutive_failures={state.consecutive_service_failures})"
    )
    state.error_recovery_attempted = True

    # Task 12.3: after 3 consecutive failures, declare unrecoverable
    if state.consecutive_service_failures >= 3:
        _logger.info(
            f"Error recovery: {state.consecutive_service_failures} consecutive failures "
            f"-- unrecoverable, staying in error state"
        )
        return False

    # Task 12.2: check service availability and attempt one call
    if not ros_node.arm_status_client.service_is_ready():
        _logger.info("Error recovery: arm_status service not ready")
        return False

    result_status, result_reason = ros_node.call_arm_status_service(state, retry_on_failure=False)
    if result_status is not None:
        _logger.info(
            f"Error recovery succeeded: service responded with status={result_status}, "
            f"reason={result_reason}"
        )
        state.consecutive_service_failures = 0
        return True
    else:
        _logger.info("Error recovery: service call failed")
        return False


def check_mqtt_connection_health(state):
    """Check MQTT connection and attempt reconnection if needed"""
    if not state.mqtt_connected and _mqtt_client:
        printINFO("MQTT disconnected - attempting reconnection...")
        try:
            _mqtt_client.reconnect()
            printINFO("MQTT reconnection initiated")
        except Exception as exc:
            printINFO1(f"MQTT reconnection attempt failed: {exc}")


def check_ros_service_health(state):
    """Check ROS service health and log periodic status summary."""
    if state.consecutive_service_failures >= MAX_CONSECUTIVE_FAILURES:
        _logger.warning(
            f"WARNING: {state.consecutive_service_failures} consecutive service call failures!"
        )
        _logger.warning(
            f"Last successful call: "
            f"{time.time() - state.last_successful_service_call:.1f} seconds ago"
        )
    else:
        # Always log a brief status line so the log file proves we're alive
        _logger.info(
            f"Health: mqtt={'connected' if state.mqtt_connected else 'DISCONNECTED'}"
            f" status={state.mqtt_status}"
            f" svc_ok (last {time.time() - state.last_successful_service_call:.0f}s ago)"
        )


# =============================================================================
# Task 10.4: Full MQTT client recreation for unrecoverable failures
# =============================================================================
def _recreate_arm_mqtt_client(state):
    """Task 10.4: Full MQTT client recreation for unrecoverable failures."""
    global _mqtt_client
    _logger.warning(
        "[SIGNAL_CHAIN] ARM_client: Recreating MQTT client"
        f" | consecutive_failures={state.selftest_consecutive_failures}"
    )
    try:
        if _mqtt_client is not None:
            _mqtt_client.loop_stop()
            _mqtt_client.disconnect()
    except Exception:
        pass

    _mqtt_client = mqtt.Client(client_id=f"arm_client_{CLIENT_ID}")
    lwt_topic = f"topic/ArmStatus_{CLIENT_ID}"
    _mqtt_client.will_set(lwt_topic, payload="offline", qos=1, retain=True)
    _mqtt_client.on_message = on_message
    _mqtt_client.on_connect = on_connect
    _mqtt_client.on_disconnect = on_disconnect
    _mqtt_client.on_log = on_log
    _mqtt_client.reconnect_delay_set(min_delay=1, max_delay=60)

    try:
        _mqtt_client.connect(MQTT_ADDRESS, 1883, keepalive=MQTT_KEEPALIVE_S)
        _mqtt_client.loop_start()
        state.mqtt_connected = True
        state.selftest_consecutive_failures = 0
        _logger.info("[SIGNAL_CHAIN] ARM_client: MQTT client recreated successfully")
    except Exception as exc:
        state.mqtt_connected = False
        _logger.error(f"[SIGNAL_CHAIN] ARM_client: MQTT client recreation failed: {exc}")


# =============================================================================
# STATE MACHINE
# =============================================================================
def ARM_Yanthra_StateMachine(ros_node, state):
    """Main state machine loop.

    Task 11.1-11.4: Loop order is now:
      spin_once(0.1) -> drain_command_queue -> poll_status -> publish_mqtt -> sleep(1)
    This ensures:
      - ROS2 callbacks are processed before state machine acts on them
      - MQTT commands are dispatched in same iteration as their arrival
      - sleep is at the bottom so first iteration runs immediately (no 1s startup delay)
    """
    printINFO("ARM_Yanthra_StateMachine started")
    PublishToMARCHostAndUpdate("UNINITIALISED", state)

    last_health_check = time.time()
    last_mqtt_reconnect_check = time.time()

    while rclpy.ok() and not state.shutdown_requested:
        try:
            # Task 11.2: spin_once at TOP of loop (processes ROS2 callbacks first)
            rclpy.spin_once(ros_node, timeout_sec=0.1)

            # Task 11.3 / 8.5: drain command queue after spin, before state polling
            _drain_command_queue(ros_node, state)

            current_time = time.time()

            # ── MQTT reconnect (aggressive when disconnected) ───────
            if not state.mqtt_connected:
                if current_time - last_mqtt_reconnect_check >= MQTT_RECONNECT_CHECK_INTERVAL:
                    check_mqtt_connection_health(state)
                    last_mqtt_reconnect_check = current_time

            # ── Periodic health checks (ROS service, etc.) ──────────
            if current_time - last_health_check >= HEALTH_CHECK_INTERVAL:
                check_ros_service_health(state)
                # Also check MQTT if connected (keepalive validation)
                if state.mqtt_connected:
                    check_mqtt_connection_health(state)
                last_health_check = current_time

            # ── Watchdog: warn if no MQTT msgs or no service calls ──
            if state.last_mqtt_message_received_time is not None:
                mqtt_silence = current_time - state.last_mqtt_message_received_time
                if mqtt_silence >= WATCHDOG_LOG_INTERVAL:
                    if current_time - state.last_watchdog_mqtt_warning >= WATCHDOG_LOG_INTERVAL:
                        _logger.warning(
                            f"WATCHDOG: No MQTT message received for {mqtt_silence:.0f}s"
                        )
                        state.last_watchdog_mqtt_warning = current_time

            service_silence = current_time - state.last_successful_service_call
            if service_silence >= WATCHDOG_LOG_INTERVAL:
                if current_time - state.last_watchdog_service_warning >= WATCHDOG_LOG_INTERVAL:
                    _logger.warning(
                        f"WATCHDOG: No successful service call for {service_silence:.0f}s "
                        f"(failures: {state.consecutive_service_failures})"
                    )
                    state.last_watchdog_service_warning = current_time

            # ── Task 9.3: Silence watchdog: no start switch for 120s ──
            if (
                state.last_start_switch_time is not None
                and state.mqtt_connected
                and state.mqtt_status == "ready"
            ):
                silence = current_time - state.last_start_switch_time
                if silence >= 120.0:
                    if current_time - state.last_silence_warning_time >= 120.0:
                        _logger.warning(
                            f"[SIGNAL_CHAIN] WARN: silence watchdog"
                            f" | no start_switch in {silence:.0f}s"
                            f" | mqtt_connected=True arm_status=ready"
                        )
                        state.last_silence_warning_time = current_time

            # ── Call ROS-2 arm status service ───────────────────────
            # Backoff: when persistent failures, probe less frequently
            # to avoid blocking the loop for 6s (3 retries x 2s timeout)
            if state.consecutive_service_failures >= SERVICE_BACKOFF_THRESHOLD:
                if current_time - state.last_service_probe_time >= SERVICE_BACKOFF_PROBE_INTERVAL:
                    state.last_service_probe_time = current_time
                    _logger.info(
                        f"Service backoff: probing "
                        f"(failures={state.consecutive_service_failures})"
                    )
                    status, reason = ros_node.call_arm_status_service(state, retry_on_failure=False)
                    if status is not None:
                        _logger.info("Service recovered from backoff mode")
                else:
                    status, reason = None, None  # skip this iteration
            else:
                # Normal mode: call with full retries
                status, reason = ros_node.call_arm_status_service(state, retry_on_failure=True)

            if status is None:
                printINFO1("Failed to get arm status from service")
                # Continue trying -- recovery mechanisms will handle persistent failures
            else:
                printINFO1(f"Arm status from ROS-2: {status} ({reason})")

                # State machine transitions
                if status == "ready":
                    if state.mqtt_status in ["busy", "ACK", "UNINITIALISED"]:
                        PublishToMARCHostAndUpdate("ready", state)
                    # Reset error recovery flag when back to ready
                    if state.error_recovery_attempted:
                        printINFO("System recovered -- back to ready state")
                        state.error_recovery_attempted = False
                        state.last_error_state_time = None

                elif status == "busy":
                    if state.mqtt_status in ["ACK", "ready", "UNINITIALISED"]:
                        PublishToMARCHostAndUpdate("busy", state)

                elif status == "error":
                    # Task 12.1: publish error (throttled inside PublishToMARCHostAndUpdate)
                    PublishToMARCHostAndUpdate("error", state)
                    if state.last_published_status == "error":
                        printINFO("ARM STATUS ERROR detected")

                    # Track error state entry time
                    if state.last_error_state_time is None:
                        state.last_error_state_time = current_time
                        state.error_recovery_attempted = False

                    # Attempt recovery after timeout
                    time_in_error = current_time - state.last_error_state_time
                    if (
                        time_in_error >= ERROR_STATE_RECOVERY_TIMEOUT
                        and not state.error_recovery_attempted
                    ):
                        printINFO(
                            f"Error state persisted for {time_in_error:.1f}s "
                            f"-- attempting recovery"
                        )
                        attempt_error_recovery(ros_node, state)

                elif status == "uninit":
                    if state.mqtt_status != "UNINITIALISED":
                        PublishToMARCHostAndUpdate("UNINITIALISED", state)

            # Task 11.1: sleep at BOTTOM of loop (first iteration runs immediately)
            # ── Heartbeat: unconditional re-publish every 30s ───────
            # Ensures the vehicle always has fresh status even when
            # the arm state hasn't changed (fixes silent-ready bug).
            if current_time - state.last_heartbeat_publish_time >= HEARTBEAT_PUBLISH_INTERVAL:
                if state.mqtt_connected and state.mqtt_status != "UNINITIALISED":
                    topic = f"topic/ArmStatus_{CLIENT_ID}"
                    try:
                        result = _mqtt_client.publish(topic, state.mqtt_status, qos=1)
                        if result.rc == mqtt.MQTT_ERR_SUCCESS:
                            _logger.debug(
                                f"Heartbeat: published '{state.mqtt_status}' " f"to {topic}"
                            )
                        else:
                            _logger.warning(f"Heartbeat publish failed (rc={result.rc})")
                    except Exception as exc:
                        _logger.warning(f"Heartbeat publish exception: {exc}")
                    state.last_heartbeat_publish_time = current_time

            # ── Task 10.2: Self-test loopback (every 30s) ──────────
            state.selftest_loop_counter += 1
            if state.selftest_loop_counter >= 30:  # 30 * 1s = every 30s
                state.selftest_loop_counter = 0
                if state.mqtt_connected and _mqtt_client:
                    now_mono = time.monotonic()
                    # Check previous self-test result
                    if state.selftest_last_sent > 0:
                        if state.selftest_last_received < state.selftest_last_sent:
                            # Previous ping was NOT echoed
                            elapsed = now_mono - state.selftest_last_sent
                            if elapsed >= 5.0:
                                state.selftest_consecutive_failures += 1
                                _logger.warning(
                                    "[SIGNAL_CHAIN] WARN: MQTT self-test FAILED"
                                    f" | consecutive={state.selftest_consecutive_failures}"
                                    f" | elapsed={elapsed:.1f}s"
                                )
                                if state.selftest_consecutive_failures >= 3:
                                    # Task 10.4: Recreate entire MQTT client
                                    _logger.error(
                                        "[SIGNAL_CHAIN] CRITICAL: 3 consecutive"
                                        " self-test failures, recreating MQTT client"
                                    )
                                    _recreate_arm_mqtt_client(state)
                                else:
                                    # Task 10.3: Force reconnect
                                    _logger.warning(
                                        "[SIGNAL_CHAIN] ARM_client:" " forcing MQTT reconnect"
                                    )
                                    try:
                                        _mqtt_client.disconnect()
                                        _mqtt_client.reconnect()
                                    except Exception as exc:
                                        _logger.warning(f"Self-test reconnect failed: {exc}")
                        else:
                            # Previous ping was echoed -- reset failures
                            if state.selftest_consecutive_failures > 0:
                                _logger.info(
                                    "[SIGNAL_CHAIN] ARM_client: self-test recovered"
                                    " | was_failures="
                                    f"{state.selftest_consecutive_failures}"
                                )
                                state.selftest_consecutive_failures = 0
                    # Send new ping
                    selftest_topic = f"topic/arm_selftest_{CLIENT_ID}"
                    try:
                        _mqtt_client.publish(
                            selftest_topic,
                            f"ping|ts={now_mono}",
                            qos=1,
                        )
                        state.selftest_last_sent = now_mono
                    except Exception as exc:
                        _logger.warning(f"Self-test publish failed: {exc}")

            time.sleep(STATUS_POLL_INTERVAL_S)

        except Exception as exc:
            _logger.error(f"Exception in ARM_Yanthra_StateMachine: {exc}")
            _logger.error(traceback.format_exc())
            time.sleep(1)
            # Continue running despite exceptions

    _logger.info("Exiting ARM_Yanthra_StateMachine")


# =============================================================================
# MQTT SETUP -- Task 6.1: 300s retry with exponential backoff (1s..30s cap)
# =============================================================================
def ARM_server_mqtt_connection_setup(state):
    """Setup MQTT connection with 300s exponential-backoff retry.

    Task 6.1: 300-second timeout loop with exponential backoff (1s initial,
              doubles each time, caps at 30s).
    Task 6.2: reconnect_delay_set(1, 60) before loop; loop_start() after connect.
    """
    global _mqtt_client

    printINFO("Setting up MQTT connection...")
    _mqtt_client = mqtt.Client(client_id=f"arm_client_{CLIENT_ID}")

    # MQTT Last Will and Testament -- broker publishes "offline" to the status
    # topic if this client disconnects ungracefully (power cut, crash, OOM).
    # For graceful shutdown, we publish "offline" explicitly in the finally block
    # because a clean DISCONNECT suppresses LWT per MQTT spec §3.1.2.5.
    lwt_topic = f"topic/ArmStatus_{CLIENT_ID}"
    _mqtt_client.will_set(lwt_topic, payload="offline", qos=1, retain=True)

    # Set callbacks
    _mqtt_client.on_message = on_message
    _mqtt_client.on_connect = on_connect
    _mqtt_client.on_disconnect = on_disconnect
    _mqtt_client.on_log = on_log

    # Task 6.2: Enable automatic reconnection (before connection loop)
    _mqtt_client.reconnect_delay_set(min_delay=1, max_delay=60)

    printINFO(f"Attempting to connect to MQTT broker at {MQTT_ADDRESS}:1883")

    # Task 6.1: 300s timeout with exponential backoff (1s initial, cap 30s)
    deadline = time.time() + 300.0
    delay = 1.0
    attempt = 0
    while True:
        attempt += 1
        elapsed = 300.0 - (deadline - time.time())
        try:
            _mqtt_client.connect(MQTT_ADDRESS, 1883, keepalive=MQTT_KEEPALIVE_S)
            _logger.info(f"Connected to MQTT broker" f" | attempt={attempt} elapsed={elapsed:.1f}s")
            state.mqtt_connected = True
            # Task 6.2: loop_start() after successful connect()
            _mqtt_client.loop_start()
            _logger.info("MQTT loop_start() successful")
            return True
        except Exception as exc:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            next_delay = min(delay, remaining, 30.0)
            _logger.warning(
                f"MQTT connection attempt {attempt} failed: {exc}"
                f" | next_delay={next_delay:.1f}s elapsed={elapsed:.1f}s"
            )
            time.sleep(next_delay)
            delay = min(delay * 2, 30.0)
            if time.time() >= deadline:
                break

    # All retries exhausted (300s)
    # Task 3.3: Include address source in connection failure diagnostic
    _logger.error(
        f"FATAL: MQTT connection failed: broker={MQTT_ADDRESS}:1883"
        f" (source: {MQTT_ADDRESS_SOURCE})"
        f" | attempts={attempt} timeout=300s"
    )
    print(
        f"FATAL: Could not connect to MQTT broker at {MQTT_ADDRESS}:1883 "
        f"(address source: {MQTT_ADDRESS_SOURCE}) "
        f"after {attempt} attempts (300s timeout) -- is the broker running?"
    )
    return False


# =============================================================================
# SIGNAL HANDLERS
# =============================================================================
def signal_handler(signum, frame):
    """Handle termination signals gracefully"""
    sig_name = signal.Signals(signum).name
    if _logger:
        _logger.warning(f"Received signal {sig_name} ({signum}) -- initiating shutdown...")
    if _state:
        _state.shutdown_requested = True


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================
def main():
    """Main entry point for ARM client"""
    global _state, _logger, _mqtt_client, _ros_node

    # Task 14.3: setup logging from main() (not at import time)
    _logger, log_file = _setup_logging(CLIENT_ID)

    # Task 3.1: Log MQTT address and its source at startup
    _logger.info(f"MQTT broker address: {MQTT_ADDRESS} (source: {MQTT_ADDRESS_SOURCE})")

    # Task 3.2: Warn when using the hardcoded default address
    if MQTT_ADDRESS_SOURCE == "default":
        _logger.warning(
            "Using default MQTT address 10.42.0.10"
            " - set MQTT_ADDRESS in /etc/default/pragati-arm for production"
        )

    # Task 6.1: Startup banner to stdout (captured by ROS2 session log)
    print("=" * 60)
    print(f"ARM Client ROS-2 MQTT Bridge Starting")
    print(f"  MQTT address    : {MQTT_ADDRESS} (source: {MQTT_ADDRESS_SOURCE})")
    print(f"  Client ID       : {CLIENT_ID}")
    print(f"  Service timeout : {SERVICE_WAIT_TIMEOUT}s")
    print(f"  Log file        : {log_file}")
    print("=" * 60)

    _state = ArmClientState()

    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    _logger.info("=" * 60)
    _logger.info("ARM Client ROS-2 MQTT Bridge Starting...")
    _logger.info("=" * 60)
    _logger.info(f"Log file: {log_file}")
    _logger.info(f"MQTT Server: {MQTT_ADDRESS}")
    _logger.info(f"Client ID: {CLIENT_ID}")
    _logger.info(f"PID: {os.getpid()}")

    try:
        # Initialize ROS-2
        _logger.info("Initializing ROS-2...")
        rclpy.init()
        _ros_node = ARMClientNode()
        _logger.info("ROS-2 initialized successfully")

        # Setup MQTT connection
        if not ARM_server_mqtt_connection_setup(_state):
            _logger.error("Failed to setup MQTT connection -- exiting")
            return 1

        _logger.info("Starting state machine...")
        # Run state machine (blocks here)
        ARM_Yanthra_StateMachine(_ros_node, _state)

        _logger.info("State machine exited normally")

    except KeyboardInterrupt:
        _logger.info("Keyboard interrupt detected -- shutting down...")
    except Exception as exc:
        _logger.error(f"Fatal error in ARM client: {exc}")
        _logger.error(traceback.format_exc())
        return 1
    finally:
        _logger.info("Cleanup started...")
        if _mqtt_client:
            # Publish "offline" before clean disconnect -- clean DISCONNECT
            # suppresses LWT (MQTT spec §3.1.2.5), so we must publish explicitly.
            try:
                offline_topic = f"topic/ArmStatus_{CLIENT_ID}"
                _mqtt_client.publish(offline_topic, "offline", qos=1, retain=True)
                _logger.info(f"Published 'offline' to {offline_topic}")
                # Brief wait for the publish to flush to the broker
                time.sleep(0.5)
            except Exception as exc:
                _logger.warning(f"Failed to publish offline status: {exc}")
            _logger.info("Stopping MQTT client...")
            _mqtt_client.loop_stop()
            _mqtt_client.disconnect()

        if _ros_node:
            try:
                _logger.info("Destroying ROS node...")
                _ros_node.destroy_node()
            except Exception as exc:
                _logger.warning(f"Error destroying node: {exc}")

        try:
            if rclpy.ok():
                _logger.info("Shutting down ROS-2...")
                rclpy.shutdown()
        except Exception as exc:
            _logger.warning(f"Error during ROS shutdown: {exc}")

        _logger.info("ARM Client stopped")

    return 0


if __name__ == "__main__":
    sys.exit(main())
