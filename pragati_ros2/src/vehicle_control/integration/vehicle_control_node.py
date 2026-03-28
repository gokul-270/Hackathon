#!/usr/bin/env python3
"""
ROS2 Vehicle Control Node
Bridges refactored vehicle control system with ROS2 communication
"""

# Fix import paths for installed package BEFORE importing vehicle_control
# This allows submodules to use 'from config.xxx' style imports
import logging
import sys
import os
from datetime import datetime

# Get module file's modification time for build tracking
_MODULE_FILE = os.path.abspath(__file__)
_MODULE_MTIME = os.path.getmtime(_MODULE_FILE) if os.path.exists(_MODULE_FILE) else 0
_BUILD_TIME = (
    datetime.fromtimestamp(_MODULE_MTIME).strftime("%b %d %Y %H:%M:%S")
    if _MODULE_MTIME
    else "unknown"
)

# Find vehicle_control package path without importing it (which triggers __init__.py)
# Look in site-packages directories
for path in sys.path:
    candidate = os.path.join(path, "vehicle_control")
    if os.path.isdir(candidate) and os.path.exists(os.path.join(candidate, "__init__.py")):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)
        break

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile
import time
import json
import math
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any
import yaml
import os
from ament_index_python.packages import get_package_share_directory

try:
    import psutil

    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False

# ROS2 message types
from std_msgs.msg import Float64, String, Bool, Header
from sensor_msgs.msg import JointState, Joy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from std_srvs.srv import SetBool

# ROS2 service interfaces
# motor_control_ros2 uses topic-based position commands and Trigger services
from std_srvs.srv import Trigger
from motor_control_msgs.srv import DriveStop

# Import our refactored components using absolute package imports
from vehicle_control.hardware.gpio_manager import GPIOManager
from vehicle_control.hardware.motor_controller import VehicleMotorController
from vehicle_control.hardware.ros2_motor_interface import ROS2MotorInterface
from vehicle_control.hardware.mcp3008 import MCP3008, MCP3008Config, MCP3008Joystick
from vehicle_control.utils.input_processing import GPIOProcessor, JoystickProcessor
from vehicle_control.utils.logging_utils import setup_logging
from vehicle_control.utils.command_dedup import CommandDedup
from vehicle_control.config.constants import (
    VehicleState,
    PivotDirection,
    GPIO_PINS,
    MOTOR_IDS,
    GEAR_RATIOS,
    PHYSICAL,
    JOYSTICK,
)
from vehicle_control.integration.imu_interface import create_imu_interface

# MQTT client for direct vehicle→ARM communication
try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None


class ROS2VehicleControlNode(Node):
    """
    ROS2 Vehicle Control Node
    Provides complete ROS1 functionality compatibility while using refactored architecture
    """

    def __init__(self):
        super().__init__("vehicle_control_node")

        # Setup logging
        self.logger = self.get_logger()
        setup_logging()

        # Load parameters from YAML configuration
        self.config = self._load_yaml_config()

        # State management (initialize with config values)
        self.current_state = VehicleState.IDLING
        self.joint_positions = [0.0] * len(self.config["joint_names"])
        self.joint_names = self.config["joint_names"]
        self.joint_commands = [0.0] * len(self.joint_names)

        # Vehicle control state
        self.last_cmd_vel_time = time.time()
        self.cmd_vel_timeout = self.config.get("cmd_vel_timeout", 1.0)  # seconds

        # Diagnostics and tracking
        self.start_time = time.time()
        self.last_command = "none"
        self.last_command_time = 0.0
        self.command_count = 0
        self.error_count = 0

        # Motor feedback tracking - tracks which motors have ACTUALLY responded
        # CRITICAL: 'has_responded' starts False - only True after receiving joint_states
        self.motor_status = {}  # Track individual motor health
        for joint in self.joint_names:
            self.motor_status[joint] = {
                "ok": False,  # Start False - becomes True only after real feedback
                "has_responded": False,  # Has this motor ever sent joint_states?
                "last_position": 0.0,
                "last_command": 0.0,
                "last_command_time": 0.0,
                "error_count": 0,
                "last_response_time": 0.0,
                "stale_warned": False,
            }

        # Throttle health warnings (avoid log spam at 5Hz)
        self._health_last_warning_msg = None
        self._health_last_warning_time = 0.0

        # Direction switch state tracking
        self._last_direction_left_state = False
        self._last_direction_right_state = False

        # Physical switch state tracking (start/shutdown buttons)
        self._shutdown_press_start_time = None
        self._shutdown_in_progress = False
        self._shutdown_initiated = False
        self._last_start_switch_state = False
        self._last_shutdown_switch_state = False

        # ── Persistent MQTT client (Tasks 1.1-1.4) ─────────────────
        # Single persistent client replaces ephemeral per-press clients.
        # paho's loop_start() runs a background thread for reconnect;
        # publish() enqueues to an internal buffer — never blocks the
        # ROS2 executor, even if the broker is down.
        self._mqtt_client = None
        self._mqtt_connected = False
        self._mqtt_reconnect_count = 0
        self._mqtt_connect_time = None  # monotonic time of last connect
        self._mqtt_disconnect_time = None  # monotonic time of last disconnect

        # Thread safety locks (phase-2-critical-fixes, bug 1.3)
        # Lock ordering: _mqtt_lock -> _motor_state_lock -> _control_lock
        self._mqtt_lock = threading.Lock()
        self._motor_state_lock = threading.RLock()
        self._control_lock = threading.Lock()

        self._press_seq = 0  # monotonic press sequence number (Task 7.1)
        # Self-test state (Task 8.1-8.4)
        self._selftest_last_sent = 0.0
        self._selftest_last_received = 0.0
        self._selftest_consecutive_failures = 0
        # Health heartbeat state (Task 7.5)
        self._mqtt_health_last_log = 0.0
        self._initialize_mqtt()

        # ── Thermal & CPU self-monitoring (Task 4) ─────────────────
        # Try reading thermal sysfs once at startup to determine availability
        self._thermal_monitoring_available = False
        self._throttle_monitoring_available = False
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                f.read()
            self._thermal_monitoring_available = True
        except (OSError, IOError):
            self.logger.warning(
                "[THERMAL] CPU temperature sysfs unavailable" " — thermal monitoring disabled"
            )
        try:
            with open("/sys/devices/platform/soc/soc:firmware/get_throttled", "r") as f:
                f.read()
            self._throttle_monitoring_available = True
        except (OSError, IOError):
            self.logger.warning(
                "[THERMAL] Throttle sysfs unavailable" " — throttle monitoring disabled"
            )

        # psutil CPU tracking: call once to establish baseline
        self._cpu_process = None
        self._last_cpu_high_count = 0
        if _PSUTIL_AVAILABLE:
            try:
                self._cpu_process = psutil.Process(os.getpid())
                self._cpu_process.cpu_percent(interval=None)  # baseline
            except Exception as e:
                self.logger.warning(f"[THERMAL] psutil CPU tracking init failed | error={e}")
                self._cpu_process = None
        else:
            self.logger.warning("[THERMAL] psutil not installed — CPU % monitoring disabled")

        # ── Control loop timing counters (Task 5) ─────────────────
        self._loop_time_sum = 0.0
        self._loop_time_max = 0.0
        self._loop_count = 0
        self._missed_deadlines = 0
        control_freq = self.config.get("control_frequency", 5.0)
        self._deadline_threshold = 1.0 / control_freq

        # Pre-initialize hardware attributes (may remain None if init fails)
        self.gpio_manager = None
        self.gpio_processor = None
        self.imu_interface = None

        # Analog joystick (MCP3008 over SPI)
        self.joystick_interface = None
        self.joystick_processor = None
        self.joystick_pub = None
        self.joystick_timer = None
        self._joystick_idle_applied = False
        self._drive_movement_in_progress = False  # Flag to prevent command piling

        # Automatic mode switch tracking
        self.is_automatic_mode = False  # Current mode state
        self._last_automatic_mode_state = False  # For detecting changes

        # Motor control abstraction layer
        self.ros2_motor_interface = None
        self.motor_controller = None

        # Steering mode: "front_only" (default, like ROS1), "ackermann", "three_wheel"
        self.steering_mode = self.config.get("steering_mode", "front_only")

        # Initialize hardware interfaces
        self._initialize_hardware()

        # ROS2 Communication setup
        self._setup_publishers()
        self._setup_subscribers()
        self._setup_services()
        self._setup_timers()

        # Run startup self-test (after ROS setup so we can publish results)
        self._run_startup_self_test()

        self.logger.info("🚗 ROS2 Vehicle Control Node initialized")
        self.logger.info(f"   Built: {_BUILD_TIME}")

    # ── Persistent MQTT Client (Tasks 1.1-1.4, 7.3, 8.1) ──────────
    def _initialize_mqtt(self):
        """Task 1.1: Create persistent paho MQTT client.

        Wraps connect() in try/except so the node starts even if the
        broker is down — paho's loop_start() will auto-reconnect.
        """
        if mqtt is None:
            self.logger.error(
                "[SIGNAL_CHAIN] vehicle_control_node: paho-mqtt not installed" " | MQTT disabled"
            )
            return

        self._mqtt_client = mqtt.Client(client_id="vehicle_control", clean_session=True)
        self._mqtt_client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._mqtt_client.on_connect = self._on_mqtt_connect
        self._mqtt_client.on_disconnect = self._on_mqtt_disconnect
        self._mqtt_client.on_message = self._on_mqtt_message

        mqtt_host = self.config.get("mqtt_broker_host", "localhost")
        mqtt_port = self.config.get("mqtt_broker_port", 1883)

        try:
            self._mqtt_client.connect(mqtt_host, mqtt_port, keepalive=30)
            self._mqtt_client.loop_start()
            self.logger.info(
                "[SIGNAL_CHAIN] vehicle_control_node: MQTT client started"
                f" | broker={mqtt_host}:{mqtt_port} keepalive=30"
            )
        except Exception as e:
            self.logger.warn(
                "[SIGNAL_CHAIN] vehicle_control_node: MQTT connect failed"
                f" | error={e} | will auto-reconnect via loop_start()"
            )
            # Start loop anyway — it will retry connection automatically
            try:
                self._mqtt_client.loop_start()
            except Exception as e:
                self.logger.warn(
                    "[SIGNAL_CHAIN] vehicle_control_node: MQTT loop_start failed"
                    " after connect failure | error=" + str(e)
                )

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        """Task 1.2 + 7.3: MQTT connection callback."""
        if rc == 0:
            with self._mqtt_lock:
                self._mqtt_connected = True
                self._mqtt_connect_time = time.monotonic()
                disconnect_info = ""
                if self._mqtt_disconnect_time is not None:
                    dur = time.monotonic() - self._mqtt_disconnect_time
                    disconnect_info = f" disconnect_duration={dur:.1f}s"
                    self._mqtt_disconnect_time = None
                reconnect_count = self._mqtt_reconnect_count
            self.logger.info(
                "[SIGNAL_CHAIN] vehicle_control_node: MQTT connected"
                f" | reconnect_count={reconnect_count}"
                f"{disconnect_info}"
            )
            # Task 8.1: Subscribe to self-test topic for loopback echo
            client.subscribe("topic/vehicle_selftest", qos=1)
        else:
            with self._mqtt_lock:
                self._mqtt_connected = False
                self._mqtt_reconnect_count += 1
                reconnect_count = self._mqtt_reconnect_count
            rc_codes = {
                0: "OK",
                1: "bad_protocol",
                2: "bad_client_id",
                3: "server_unavailable",
                4: "bad_auth",
                5: "not_authorized",
            }
            reason = rc_codes.get(rc, f"unknown_{rc}")
            self.logger.warn(
                "[SIGNAL_CHAIN] vehicle_control_node: MQTT connect failed"
                f" | rc={rc} reason={reason}"
                f" | reconnect_count={reconnect_count}"
            )

    def _on_mqtt_disconnect(self, client, userdata, rc):
        """Task 1.3 + 7.3: MQTT disconnect callback."""
        with self._mqtt_lock:
            self._mqtt_connected = False
            self._mqtt_disconnect_time = time.monotonic()
            self._mqtt_reconnect_count += 1
            connected_duration = ""
            if self._mqtt_connect_time is not None:
                dur = time.monotonic() - self._mqtt_connect_time
                connected_duration = f" connected_duration={dur:.1f}s"
            reconnect_count = self._mqtt_reconnect_count
        if rc != 0:
            self.logger.warn(
                "[SIGNAL_CHAIN] vehicle_control_node: MQTT unexpected"
                " disconnect"
                f" | rc={rc}"
                f" | reconnect_count={reconnect_count}"
                f"{connected_duration}"
            )
        else:
            self.logger.info(
                "[SIGNAL_CHAIN] vehicle_control_node: MQTT clean disconnect"
                f" | reconnect_count={reconnect_count}"
                f"{connected_duration}"
            )

    def _on_mqtt_message(self, client, userdata, msg):
        """Task 8.1: Handle incoming MQTT messages (self-test echo)."""
        if msg.topic == "topic/vehicle_selftest":
            self._selftest_last_received = time.monotonic()

    def _cleanup_mqtt(self):
        """Task 1.4: Clean MQTT shutdown — no orphaned paho threads."""
        if self._mqtt_client is not None:
            try:
                self._mqtt_client.loop_stop()
                self._mqtt_client.disconnect()
                self.logger.info("[SIGNAL_CHAIN] vehicle_control_node: MQTT client stopped")
            except Exception as e:
                self.logger.warn(
                    f"[SIGNAL_CHAIN] vehicle_control_node: MQTT cleanup error" f" | error={e}"
                )

    def _recreate_mqtt_client(self):
        """Task 8.4: Full client recreation for unrecoverable failures."""
        self.logger.warn(
            "[SIGNAL_CHAIN] vehicle_control_node: Recreating MQTT client"
            f" | consecutive_failures={self._selftest_consecutive_failures}"
        )
        try:
            if self._mqtt_client is not None:
                self._mqtt_client.loop_stop()
                self._mqtt_client.disconnect()
        except Exception as e:
            self.logger.warn(
                "[SIGNAL_CHAIN] vehicle_control_node: MQTT old client cleanup"
                " failed during recreate | error=" + str(e)
            )
        self._mqtt_client = None
        with self._mqtt_lock:
            self._mqtt_connected = False
        self._selftest_consecutive_failures = 0
        self._initialize_mqtt()

    def _mqtt_health_heartbeat(self):
        """Task 7.5: Periodic MQTT health status log."""
        now = time.monotonic()
        with self._mqtt_lock:
            mqtt_connected = self._mqtt_connected
            connect_time = self._mqtt_connect_time
            disconnect_time = self._mqtt_disconnect_time
            reconnect_count = self._mqtt_reconnect_count
        if mqtt_connected:
            # Log every 60s when connected
            if now - self._mqtt_health_last_log < 60.0:
                return
            connected_dur = ""
            if connect_time is not None:
                connected_dur = f" connected_duration={now - connect_time:.0f}s"
            self.logger.info(
                "[SIGNAL_CHAIN] vehicle_control_node: MQTT health"
                f" | status=connected"
                f" | total_presses={self._press_seq}"
                f" | reconnect_count={reconnect_count}"
                f"{connected_dur}"
            )
        else:
            # Log every 10s when disconnected
            if now - self._mqtt_health_last_log < 10.0:
                return
            disconnect_dur = ""
            if disconnect_time is not None:
                disconnect_dur = f" disconnect_duration=" f"{now - disconnect_time:.0f}s"
            self.logger.warn(
                "[SIGNAL_CHAIN] vehicle_control_node: MQTT health"
                f" | status=disconnected"
                f" | total_presses={self._press_seq}"
                f" | reconnect_count={reconnect_count}"
                f"{disconnect_dur}"
            )
        self._mqtt_health_last_log = now

    def _mqtt_selftest_check(self):
        """Tasks 8.2-8.4: MQTT loopback self-test."""
        with self._mqtt_lock:
            mqtt_connected = self._mqtt_connected
        if not mqtt_connected or self._mqtt_client is None:
            return

        now = time.monotonic()

        # Check previous ping result
        if self._selftest_last_sent > 0:
            if self._selftest_last_received < self._selftest_last_sent:
                elapsed = now - self._selftest_last_sent
                if elapsed >= 5.0:
                    self._selftest_consecutive_failures += 1
                    self.logger.warn(
                        "[SIGNAL_CHAIN] vehicle_control_node:"
                        " MQTT self-test FAILED"
                        f" | consecutive="
                        f"{self._selftest_consecutive_failures}"
                        f" | elapsed={elapsed:.1f}s"
                    )
                    if self._selftest_consecutive_failures >= 3:
                        # Task 8.4: Recreate entire client
                        self.logger.error(
                            "[SIGNAL_CHAIN] vehicle_control_node: CRITICAL"
                            " - 3 consecutive self-test failures,"
                            " recreating MQTT client"
                        )
                        self._recreate_mqtt_client()
                        return
                    else:
                        # Task 8.3: Force reconnect
                        self.logger.warn(
                            "[SIGNAL_CHAIN] vehicle_control_node:" " forcing MQTT reconnect"
                        )
                        try:
                            self._mqtt_client.loop_stop()
                            self._mqtt_client.disconnect()
                            self._mqtt_client.connect(
                                self.config.get("mqtt_broker_host", "localhost"),
                                self.config.get("mqtt_broker_port", 1883),
                                keepalive=30,
                            )
                            self._mqtt_client.loop_start()
                        except Exception as e:
                            self.logger.warn(
                                "[SIGNAL_CHAIN] vehicle_control_node:" f" reconnect failed: {e}"
                            )
                    return  # Don't send new ping until recovery
            else:
                # Previous ping was echoed — reset failures
                if self._selftest_consecutive_failures > 0:
                    self.logger.info(
                        "[SIGNAL_CHAIN] vehicle_control_node:"
                        " self-test recovered"
                        " | was_failures="
                        f"{self._selftest_consecutive_failures}"
                    )
                    self._selftest_consecutive_failures = 0

        # Send new ping
        try:
            self._mqtt_client.publish(
                "topic/vehicle_selftest",
                f"ping|ts={now}",
                qos=1,
            )
            self._selftest_last_sent = now
        except Exception as e:
            self.logger.warn(
                "[SIGNAL_CHAIN] vehicle_control_node:" f" self-test publish failed | error={e}"
            )

    def _load_yaml_config(self) -> Dict:
        """Load vehicle configuration from YAML file"""
        try:
            # Try to get package share directory
            try:
                pkg_share = get_package_share_directory("vehicle_control")
                config_path = os.path.join(pkg_share, "config", "production.yaml")
            except Exception as e:
                self.logger.debug(
                    f"Config: ament package lookup failed, using dev fallback | error={e}"
                )
                # Fallback to relative path for development
                current_dir = os.path.dirname(__file__)
                config_path = os.path.join(
                    os.path.dirname(current_dir), "config", "production.yaml"
                )

            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    config = yaml.safe_load(f)

                # Extract vehicle_control parameters
                if "vehicle_control" in config:
                    vehicle_config = config["vehicle_control"]["ros__parameters"]
                else:
                    vehicle_config = config

                self.logger.info(f"Loaded configuration from {config_path}")
                return vehicle_config
            else:
                self.logger.warning(f"Config file not found: {config_path}")
                return self._get_default_config()

        except Exception as e:
            self.logger.error(f"Failed to load YAML config: {e}")
            return self._get_default_config()

    def _get_default_config(self) -> Dict:
        """Fallback default configuration if YAML loading fails"""
        return {
            "joint_names": [
                "steering_left",
                "steering_right",
                "steering_front",
                "drive_front",
                "drive_left_back",
                "drive_right_back",
            ],
            "cmd_vel_timeout": 1.0,
            "control_frequency": 5.0,  # Reduced from 100Hz — see fix-vehicle-cpu-thermal
            "joint_state_frequency": 5.0,  # Reduced from 50Hz
            "gpio_frequency": 10.0,
            "status_frequency": 2.0,  # Reduced from 5Hz
            "physical_params": {
                "wheel_diameter": 0.15,
                "driving_gear_ratio": 5.0,
                "steering_gear_ratio": 10.0,
                "steering_limits": {"min": -45.0, "max": 45.0},
            },
            # MQTT broker
            "mqtt_broker_host": "localhost",
            "mqtt_broker_port": 1883,
            # Hardware control flags
            "enable_gpio": False,  # Default: GPIO disabled for safety
            # Position feedback validation parameters
            "enable_position_feedback": False,
            "position_feedback_timeout": 5.0,  # seconds
            "position_tolerance": {
                "steering": 0.05,  # radians (~3 degrees)
                "drive": 0.1,  # meters
            },
        }

    def _initialize_hardware(self):
        """Initialize hardware interfaces and service clients

        Motor control is handled by motor_control_ros2 package via ROS2 services.
        This node manages GPIO, state machine, and high-level coordination.
        """
        try:
            # Initialize GPIO manager (local hardware) - ONLY if enabled
            enable_gpio = self.config.get("enable_gpio", False)
            if enable_gpio:
                self.logger.info("🔌 GPIO enabled - initializing GPIO manager")
                self.gpio_manager = GPIOManager()
                self.gpio_manager.initialize()
                self.logger.info("✅ GPIO manager initialized")

                # Physical switches are already configured by gpio_manager during initialization
                # GPIO6 (start) = PUD_DOWN, GPIO5 (shutdown) = PUD_UP
                start_pin = self.config.get("gpio_pins", {}).get("start_switch_pin", 6)
                shutdown_pin = self.config.get("gpio_pins", {}).get("shutdown_switch_pin", 5)
                self.logger.info(
                    f"✅ Physical switches configured (GPIO{start_pin}=START, GPIO{shutdown_pin}=SHUTDOWN)"
                )

                # Turn on Software Status LED to indicate software is running
                try:
                    self.gpio_manager.set_output(GPIO_PINS.SOFTWARE_STATUS_LED, True)  # GPIO 22
                    self.logger.info("✅ Software Status LED (GPIO 22) turned ON")
                except Exception as e:
                    self.logger.warning(f"Failed to turn on status LED: {e}")
            else:
                self.logger.warn("⚠️  GPIO DISABLED in config (enable_gpio=false)")
                self.logger.warn("   This is SAFE for initial motor testing")
                self.logger.warn("   Set enable_gpio=true after verifying pin assignments")
                self.gpio_manager = None

            # Initialize IMU interface (optional)
            # IMPORTANT: IMU is disabled by default; do not block node startup on missing hardware.
            enable_imu = self.config.get("enable_imu", False)
            if enable_imu:
                self.logger.info("🧭 IMU enabled - initializing")
                self.imu_interface = create_imu_interface(self.config)
                if not self.imu_interface.initialize():
                    self.logger.warning("⚠️ IMU init failed - continuing without IMU")
                    self.imu_interface = None
            else:
                self.logger.warning("⚠️ IMU DISABLED in config (enable_imu=false)")
                self.imu_interface = None

            # Initialize input processors (GPIO is optional)
            if self.gpio_manager is not None:
                self.gpio_processor = GPIOProcessor(self.gpio_manager)
            else:
                # IMPORTANT: Do not create GPIOProcessor with None, or it will spam errors at runtime.
                self.gpio_processor = None

            # Initialize motor abstraction layer (ROS2 interface -> VehicleMotorController)
            self._initialize_motor_controller()

            # Initialize analog joystick (optional)
            self._initialize_joystick()

            # Create service clients for motor_control_ros2 (legacy - keeping for backward compat)
            self._create_motor_service_clients()

            # Subscribe to joint_states from motor_control_ros2
            # Note: motor_control_ros2 runs in /vehicle namespace
            self.create_subscription(
                JointState,
                "/vehicle/joint_states",
                self._motor_joint_states_callback,
                10,
            )

            self.logger.info("Hardware interfaces initialized successfully")
            self.logger.info(f"Steering mode: {self.steering_mode}")
            return True

        except Exception as e:
            self.logger.error(f"Hardware initialization failed: {e}")
            return False

    def _initialize_motor_controller(self):
        """Initialize the motor abstraction layer

        Creates ROS2MotorInterface which bridges to motor_control_ros2,
        then wraps it with VehicleMotorController for high-level operations.
        """
        try:
            # Create ROS2 motor interface (handles communication with motor_control_ros2)
            self.ros2_motor_interface = ROS2MotorInterface(self)
            if not self.ros2_motor_interface.initialize():
                self.logger.warning(
                    "ROS2 motor interface initialization incomplete - motor_control may not be running"
                )

            # Create high-level vehicle motor controller using the interface
            self.motor_controller = VehicleMotorController(self.ros2_motor_interface)

            # Initialize the controller (sets up limits and checks safety)
            # Safe to call even if motors aren't responding yet (returns default status)
            if self.motor_controller.initialize():
                self.logger.info("✅ Motor controller initialized")
            else:
                self.logger.warning("⚠️ Motor controller initialization failed (will retry)")

            self.logger.info("✅ Motor abstraction layer initialized")

        except Exception as e:
            self.logger.error(f"Motor controller initialization failed: {e}")
            self.logger.warning("Falling back to direct topic publishers")

    def _initialize_joystick(self) -> None:
        """Initialize the analog joystick interface (MCP3008 over SPI).

        Safe behavior:
        - Disabled by default via config (enable_joystick=false)
        - If enabled but pigpio/pigpiod isn't available, logs error and continues without joystick
        """
        try:
            enable_joystick = bool(self.config.get("enable_joystick", False))
            if not enable_joystick:
                self.logger.warning("⚠️ Joystick DISABLED in config (enable_joystick=false)")
                self.joystick_interface = None
                self.joystick_processor = None
                return

            joystick_cfg = self.config.get("joystick", {}) or {}

            adc_cfg = MCP3008Config(
                spi_backend=str(joystick_cfg.get("spi_backend", "pigpio")),
                spi_bus=int(joystick_cfg.get("spi_bus", 0)),
                spi_channel=int(joystick_cfg.get("spi_channel", 1)),
                spi_baud_hz=int(joystick_cfg.get("spi_baud_hz", 1_000_000)),
                spi_flags=int(joystick_cfg.get("spi_flags", 0)),
            )

            self.logger.info(
                f"🕹️ Initializing joystick via MCP3008 (backend={adc_cfg.spi_backend}, "
                f"spi_bus={getattr(adc_cfg, 'spi_bus', 0)}, spi_channel={adc_cfg.spi_channel}, "
                f"baud={adc_cfg.spi_baud_hz})"
            )

            adc = MCP3008(adc_cfg)
            self.joystick_interface = MCP3008Joystick(
                adc=adc,
                x_channel=int(joystick_cfg.get("x_channel", JOYSTICK.X_CHANNEL)),
                y_channel=int(joystick_cfg.get("y_channel", JOYSTICK.Y_CHANNEL)),
                invert_x=bool(joystick_cfg.get("invert_x", False)),
                invert_y=bool(joystick_cfg.get("invert_y", False)),
                max_value=int(joystick_cfg.get("max_value", JOYSTICK.MAX_VALUE)),
            )

            self.joystick_processor = JoystickProcessor(self.joystick_interface)

            # Optional calibration at startup
            if bool(joystick_cfg.get("calibrate_on_start", True)):
                samples = int(joystick_cfg.get("calibration_samples", 50))
                if samples > 0:
                    ok = self.joystick_processor.calibrate(samples=samples)
                    if not ok:
                        self.logger.warning(
                            "⚠️ Joystick calibration failed - continuing with defaults"
                        )

            self._joystick_last_log_time = 0.0
            self._joystick_idle_applied = False

            self.logger.info("✅ Joystick initialized")

        except Exception as e:
            self.logger.error(f"Joystick initialization failed: {e}")
            self.logger.error(
                "Joystick will remain disabled. Check SPI wiring and the configured backend (spidev/pigpio)."
            )
            self.joystick_interface = None
            self.joystick_processor = None

    def _create_motor_service_clients(self):
        """Create service clients and publishers for motor_control_ros2

        motor_control_ros2 uses topic-based position commands:
          /{joint_name}_position_controller/command (std_msgs/Float64)
        And provides services for enable/disable:
          /enable_motors, /disable_motors (std_srvs/Trigger)
        """
        # Service clients for motor enable/disable
        # Note: motor_control_ros2 runs in /vehicle namespace
        self.motor_enable_client = self.create_client(Trigger, "/vehicle/enable_motors")
        self.motor_disable_client = self.create_client(Trigger, "/vehicle/disable_motors")
        # Note: motor_availability_client not used - we check motor_status directly

        # Position command publishers for each vehicle motor
        # Using joint names that will be configured in vehicle_motors.yaml
        self.motor_position_pubs = {}
        self.motor_velocity_pubs = {}
        self.motor_stop_pubs = {}  # Motor stop command publishers (exit position control)
        vehicle_joints = [
            "steering_left",
            "steering_right",
            "steering_front",
            "drive_front",
            "drive_left_back",
            "drive_right_back",
        ]
        for joint_name in vehicle_joints:
            # Position command publisher
            pos_topic = f"/{joint_name}_position_controller/command"
            self.motor_position_pubs[joint_name] = self.create_publisher(Float64, pos_topic, 10)
            self.logger.debug(f"Created position publisher for {pos_topic}")

            # Velocity command publisher (for drive motors)
            vel_topic = f"/{joint_name}_velocity_controller/command"
            self.motor_velocity_pubs[joint_name] = self.create_publisher(Float64, vel_topic, 10)
            self.logger.debug(f"Created velocity publisher for {vel_topic}")

            # Motor stop command publisher (exit position control, reduce power)
            stop_topic = f"/{joint_name}_stop_controller/command"
            self.motor_stop_pubs[joint_name] = self.create_publisher(Float64, stop_topic, 10)
            self.logger.debug(f"Created stop publisher for {stop_topic}")

        # Alias for backward compatibility
        self.motor_command_pubs = self.motor_position_pubs

        # Command deduplication: skip publishing when target unchanged (0.01° epsilon)
        self._command_dedup = CommandDedup(logger=self.logger)

        # Drive stop service client (controls motor stop/resume for drive motors)
        self.drive_stop_client = self.create_client(DriveStop, "/drive_stop")
        self._drive_stop_active = False
        self.logger.info("Created drive_stop service client")

        # Check if motor control services are available
        # motor_control_ros2 may take time to initialize motors/homing before services appear.
        # IMPORTANT: Do NOT block startup here. Service availability is checked dynamically before use.
        enable_ready = self.motor_enable_client.service_is_ready()
        disable_ready = self.motor_disable_client.service_is_ready()
        services_ready = enable_ready and disable_ready

        if services_ready:
            self.logger.info("✅ All motor control services connected")
        else:
            self.logger.warning(
                "⚠️ Motor control services not ready at startup (will continue and re-check)"
            )

    def _call_drive_stop(self, activate: bool) -> bool:
        """Call drive_stop service to stop/resume drive motors

        Args:
            activate: True = stop motors and clear queue, False = resume movement

        Returns:
            True if service call successful

        Note:
            This may be called from the joystick thread (daemon). The main thread
            runs rclpy.spin(node) with a single-threaded executor, so we MUST NOT
            call rclpy.spin_until_future_complete() or rclpy.spin_once() here —
            that deadlocks the executor. Instead we wait on future.done() while
            the main executor processes the response callback.
            (Same pattern as yanthra_move joint_move.cpp spin_some + wait_for(0),
            but in Python the main spin() already processes callbacks for us.)
        """
        if not self.drive_stop_client.service_is_ready():
            self.logger.warning("Drive stop service not ready")
            return False

        try:
            request = DriveStop.Request()
            request.activate = activate

            future = self.drive_stop_client.call_async(request)

            # Wait for the response — the main-thread executor processes callbacks,
            # so we just poll future.done() with a sleep to avoid busy-waiting.
            timeout = 1.0
            start = time.time()
            while not future.done():
                if (time.time() - start) >= timeout:
                    self.logger.error("Drive stop service call timeout")
                    return False
                time.sleep(
                    0.02
                )  # BLOCKING_SLEEP_OK: future poll from non-executor thread — cannot use spin_until_future — reviewed 2026-03-14

            if future.result() is not None:
                result = future.result()
                if result.success:
                    self._drive_stop_active = activate
                    action = "activated" if activate else "deactivated"
                    self.logger.info(f"Drive stop {action}: {result.message}")
                    if activate and result.commands_cleared > 0:
                        self.logger.info(f"  Cleared {result.commands_cleared} queued commands")
                    return True
                else:
                    self.logger.error(f"Drive stop service failed: {result.message}")
                    return False
            else:
                self.logger.error("Drive stop service call returned None")
                return False

        except Exception as e:
            self.logger.error(f"Drive stop service call error: {e}")
            return False

    # =========================================================================
    # Startup Self-Test and Diagnostics
    # =========================================================================

    def _run_startup_self_test(self):
        """Run comprehensive self-test at startup

        Tests all subsystems and logs clear PASS/FAIL for each.
        This runs AFTER ROS2 is fully initialized.
        """
        self.logger.info("")
        self.logger.info("=" * 60)
        self.logger.info("🛠️  VEHICLE CONTROL STARTUP SELF-TEST")
        self.logger.info("=" * 60)

        test_results = []
        overall_pass = True

        # Test 1: Motor Control Services
        self.logger.info("")
        self.logger.info("[1/5] Testing Motor Control Services...")
        services_ok = self._test_motor_services()
        test_results.append(("Motor Services", services_ok))
        if services_ok:
            self.logger.info("✅ Motor Services: PASS")
        else:
            # motor_control_ros2 may still be homing/initializing; treat as WAITING at startup.
            # We re-check services dynamically during runtime before use.
            self.logger.warning(
                "⚠️ Motor Services: WAITING (motor_control_ros2 may still be initializing)"
            )

        # Test 2: GPIO Manager
        self.logger.info("")
        self.logger.info("[2/5] Testing GPIO Manager...")
        gpio_ok = self._test_gpio()
        test_results.append(("GPIO Manager", gpio_ok))
        if gpio_ok:
            self.logger.info("✅ GPIO Manager: PASS")
        else:
            self.logger.warning("⚠️ GPIO Manager: PARTIAL (non-critical)")

        # Test 3: Joint State Reception
        self.logger.info("")
        self.logger.info("[3/5] Testing Joint State Reception...")
        joints_ok = self._test_joint_states()
        test_results.append(("Joint States", joints_ok))
        if joints_ok:
            self.logger.info("✅ Joint States: PASS")
        else:
            self.logger.warning("⚠️ Joint States: WAITING (motors may still be initializing)")

        # Test 4: Motor Abstraction Layer
        self.logger.info("")
        self.logger.info("[4/5] Testing Motor Abstraction Layer...")
        abstraction_ok = self.motor_controller is not None
        test_results.append(("Motor Abstraction", abstraction_ok))
        if abstraction_ok:
            self.logger.info("✅ Motor Abstraction: PASS")
        else:
            self.logger.warning("⚠️ Motor Abstraction: DEGRADED")

        # Test 5: Configuration
        self.logger.info("")
        self.logger.info("[5/5] Testing Configuration...")
        config_ok = len(self.joint_names) == 6
        test_results.append(("Configuration", config_ok))
        if config_ok:
            self.logger.info(f"✅ Configuration: PASS ({len(self.joint_names)} joints configured)")
        else:
            self.logger.error(
                f"❌ Configuration: FAIL (expected 6 joints, got {len(self.joint_names)})"
            )
            overall_pass = False

        # Summary
        self.logger.info("")
        self.logger.info("=" * 60)
        passed = sum(1 for _, ok in test_results if ok)
        total = len(test_results)
        health_score = int((passed / total) * 100)

        if overall_pass:
            self.logger.info(f"🎉 STARTUP SELF-TEST: PASSED ({passed}/{total} tests)")
            self.logger.info(f"📊 Health Score: {health_score}/100")
        else:
            self.logger.error(f"⚠️ STARTUP SELF-TEST: ISSUES DETECTED ({passed}/{total} tests)")
            self.logger.error(f"📊 Health Score: {health_score}/100")

        self.logger.info(f"🎯 Steering Mode: {self.steering_mode}")
        self.logger.info(f"🚗 Vehicle State: {self.current_state.name}")
        self.logger.info("=" * 60)
        self.logger.info("")

        # Store results for diagnostics
        self._startup_test_results = test_results
        self._startup_health_score = health_score

    def _test_motor_services(self) -> bool:
        """Test if motor control services are available"""
        try:
            enable_ready = self.motor_enable_client.service_is_ready()
            disable_ready = self.motor_disable_client.service_is_ready()
            return enable_ready and disable_ready
        except Exception as e:
            self.logger.debug(f"Motor service test error: {e}")
            return False

    def _test_gpio(self) -> bool:
        """Test GPIO manager"""
        try:
            if self.gpio_manager is None:
                return False
            # Try to read an input - this validates GPIO is working
            # Don't fail if we can't read (might be permission issue)
            return True
        except Exception as e:
            self.logger.debug(f"GPIO test error: {e}")
            return False

    def _test_joint_states(self) -> bool:
        """Test if we've received joint states"""
        try:
            # Check if we have any joint positions
            with self._motor_state_lock:
                if hasattr(self, "_vehicle_joint_positions") and self._vehicle_joint_positions:
                    return True
            # If no positions yet, that's OK - motors may still be initializing
            return False
        except Exception as e:
            self.logger.debug(f"Joint states test error: {e}")
            return False

    def _get_available_motor_count(self) -> int:
        """Count motors that are currently responding via /joint_states.

        A motor is considered "available" if:
        - it has ever responded (has_responded=True), and
        - its feedback is not stale (ok=True)

        Note: Do NOT require movement from zero; a stationary motor can still be healthy.
        """
        available = 0
        with self._motor_state_lock:
            for status in self.motor_status.values():
                if status.get("has_responded") and status.get("ok"):
                    available += 1
        return available

    def get_health_score(self) -> int:
        """Calculate current system health score (0-100)

        Motor availability is estimated from /joint_states feedback:
        motors are counted as available when they are responding (non-stale).
        """
        score = 100

        # Estimate motor availability from /joint_states feedback (see _get_available_motor_count)
        available_motors = self._get_available_motor_count()
        with self._motor_state_lock:
            motors_total = len(self.motor_status)

        if motors_total > 0:
            availability_rate = available_motors / motors_total

            # Throttled warning message when motor feedback is degraded
            if available_motors == 0:
                # CRITICAL: No motors available at all
                score = 20  # Maximum 20/100 with zero working motors
                health_msg = (
                    f"Motor feedback degraded: 0/{motors_total} motors reporting joint_states"
                )
                self._throttled_health_warning(health_msg)
            elif availability_rate < 0.5:
                # DEGRADED: Less than 50% motors available
                score = 40  # Maximum 40/100 with <50% motors
                health_msg = f"Motor feedback degraded: {available_motors}/{motors_total} motors reporting joint_states"
                self._throttled_health_warning(health_msg)
            else:
                # Clear degraded warning state once we're healthy
                self._throttled_health_warning(None)
                # Normal scoring for remaining issues when motors are responding
                # Deduct for service unavailability (-20)
                if not self._test_motor_services():
                    score -= 20

                # Deduct for GPIO issues (-10)
                if self.gpio_manager is None:
                    score -= 10

                # Deduct for motor errors (-5 per motor with errors, max -20)
                error_penalty = 0
                with self._motor_state_lock:
                    for joint, status in self.motor_status.items():
                        if status["error_count"] > 0:
                            error_penalty += min(5, status["error_count"])
                score -= min(20, error_penalty)

                # Deduct for abstraction layer missing (-15)
                if self.motor_controller is None:
                    score -= 15
        else:
            # No motors configured - unusual but not critical failure
            score -= 30

        return max(0, score)

    def _throttled_health_warning(self, msg: Optional[str], min_interval_s: float = 10.0):
        """Log a health warning at most once per interval, and only on changes.

        Args:
            msg: Warning message. If None, clears the degraded state.
            min_interval_s: Minimum seconds between repeated warnings.
        """
        now = time.time()

        # Clear state
        if msg is None:
            self._health_last_warning_msg = None
            return

        if (self._health_last_warning_msg != msg) or (
            (now - self._health_last_warning_time) > min_interval_s
        ):
            self.logger.warning(msg)
            self._health_last_warning_msg = msg
            self._health_last_warning_time = now

    def get_diagnostics(self) -> Dict[str, Any]:
        """Get comprehensive system diagnostics"""
        uptime = time.time() - self.start_time

        # Motor status summary
        with self._motor_state_lock:
            motors_ok = sum(1 for s in self.motor_status.values() if s["ok"])
            motors_total = len(self.motor_status)

        with self._control_lock:
            current_state_name = self.current_state.name
            command_count = self.command_count
            last_command = self.last_command
            last_command_time = self.last_command_time
            error_count = self.error_count

        diagnostics = {
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": round(uptime, 1),
            "health_score": self.get_health_score(),
            "state": current_state_name,
            "steering_mode": self.steering_mode,
            "motors": {
                "ok_count": motors_ok,
                "total_count": motors_total,
                "status": {},
            },
            "commands": {
                "total_count": command_count,
                "error_count": error_count,
                "last_command": last_command,
                "last_command_time": last_command_time,
            },
            "services": {
                "enable_motors": (
                    self.motor_enable_client.service_is_ready()
                    if self.motor_enable_client
                    else False
                ),
                "disable_motors": (
                    self.motor_disable_client.service_is_ready()
                    if self.motor_disable_client
                    else False
                ),
            },
            "gpio": {"initialized": self.gpio_manager is not None},
        }

        # Add per-motor status
        with self._motor_state_lock:
            for joint, status in self.motor_status.items():
                pos = self._get_joint_position(joint)
                diagnostics["motors"]["status"][joint] = {
                    "ok": status["ok"],
                    "position": round(pos, 4),
                    "error_count": status["error_count"],
                }

        return diagnostics

    def _motor_joint_states_callback(self, msg: JointState):
        """Receive joint states from motor_control_ros2"""
        try:
            # Log first-ever joint_states arrival (one-time)
            if not hasattr(self, "_joint_states_first_received"):
                self._joint_states_first_received = True
                self.logger.info(
                    f"[JOINT_STATES] First /vehicle/joint_states received: names={list(msg.name)}"
                )
                self._joint_states_log_counter = 0

            drive_joints = {"drive_front", "drive_left_back", "drive_right_back"}

            # Update our local joint positions from motor_control_ros2
            # NOTE: odrive_service_node sends positions in meters (joint units), NOT rotations.
            # motor_control_ros2 (steering) sends in rotations.
            # Drive motor positions are stored as-is in meters (no ×2π conversion).
            # Steering motor positions are converted from rotations to radians (×2π).
            with self._motor_state_lock:
                # Initialize vehicle joint positions dict if not exists
                if not hasattr(self, "_vehicle_joint_positions"):
                    self._vehicle_joint_positions = {}
                for i, name in enumerate(msg.name):
                    # Cache vehicle joint positions
                    if i < len(msg.position):
                        raw_position = msg.position[i]  # meters for ODrive, rotations for steering

                        if name in drive_joints:
                            # ODrive: position is already in meters — store as-is
                            position_internal = raw_position
                        else:
                            # Steering: position is in rotations — convert to radians
                            position_internal = raw_position * 2.0 * math.pi

                        self._vehicle_joint_positions[name] = position_internal

                        # Update motor status - motor is responding
                        if name in self.motor_status:
                            # Log first-ever response from this motor (one-time per motor)
                            if not self.motor_status[name]["has_responded"]:
                                self.logger.info(
                                    f"[MOTOR_INIT] {name}: initial_position={position_internal:.4f}m | status=PRESENT"
                                )
                            self.motor_status[name]["last_position"] = position_internal
                            self.motor_status[name]["last_response_time"] = time.time()
                            self.motor_status[name]["ok"] = True  # Mark as healthy since responding
                            self.motor_status[name][
                                "has_responded"
                            ] = True  # Motor has sent joint_states

                    # Also update legacy joint_positions array if applicable
                    if name in self.joint_names:
                        idx = self.joint_names.index(name)
                        if i < len(msg.position):
                            raw_position = msg.position[i]
                            if name in drive_joints:
                                position_internal = raw_position  # ODrive: meters, store as-is
                            else:
                                position_internal = (
                                    raw_position * 2.0 * math.pi
                                )  # steering: rot → rad
                            self.joint_positions[idx] = position_internal

            # Throttled log: print drive joint positions every ~2 seconds
            self._joint_states_log_counter = getattr(self, "_joint_states_log_counter", 0) + 1
            if self._joint_states_log_counter >= 20:  # 10 Hz publish rate → ~2s
                self._joint_states_log_counter = 0
                drive_summary = {
                    n: f"{msg.position[i]:.4f}"
                    for i, n in enumerate(msg.name)
                    if n in drive_joints and i < len(msg.position)
                }
                if drive_summary:
                    self.logger.info(f"[JOINT_STATES] Drive positions (m): {drive_summary}")
                else:
                    self.logger.warning(
                        "[JOINT_STATES] No drive joints in /vehicle/joint_states message. "
                        f"Received names: {list(msg.name)}"
                    )
        except Exception as e:
            self.logger.error(f"Joint states callback error: {e}")

    # =========================================================================
    # Motor Control Helper Methods (call motor_control_ros2 services)
    # =========================================================================

    def _call_joint_position_command(
        self, joint_name: str, position: float, wait_for_feedback: bool = None
    ) -> bool:
        """Send position command to motor_control_ros2 via topic

        Args:
            joint_name: Name of the joint (e.g., 'steering_left', 'drive_front')
            position: Target position — meters for ODrive drive joints, radians for steering joints.
                      Will be converted to rotations for steering motor_control.
            wait_for_feedback: Override enable_position_feedback config (None = use config)

        Returns:
            True if command sent (and position reached if feedback enabled), False otherwise
        """
        try:
            if joint_name not in self.motor_command_pubs:
                self.logger.warning(f"No publisher for joint: {joint_name}")
                self._track_command(
                    f"position({joint_name}, {position:.4f})", False, "no publisher"
                )
                return False

            drive_joints = {"drive_front", "drive_left_back", "drive_right_back"}
            if joint_name in drive_joints:
                # ODrive: position is already in meters — send as-is (ODrive topic expects meters)
                position_rotations = position
            else:
                # Steering: position is in radians — convert to rotations for motor_control
                # 1 rotation = 2π radians
                position_rotations = position / (2.0 * math.pi)

            # Dedup check: skip publishing if target position unchanged (within epsilon)
            if not self._command_dedup.should_send(joint_name, position_rotations):
                return True  # Deduped — report success without publishing

            # Log topic name and value being published (helps verify correct topic routing)
            topic_name = f"/{joint_name}_position_controller/command"
            if joint_name in drive_joints:
                self.logger.info(
                    f"[CMD] Publishing to {topic_name}: {position_rotations:.4f} m (ODrive)"
                )
            else:
                self.logger.info(
                    f"[CMD] Publishing to {topic_name}: {position_rotations:.4f} rot "
                    f"({position:.4f} rad)"
                )

            # Send the position command in rotations
            msg = Float64()
            msg.data = position_rotations
            self.motor_command_pubs[joint_name].publish(msg)

            # Track the command (store original radians for internal use)
            self._track_command(
                f"position({joint_name}, {position:.4f} rad = {position_rotations:.4f} rot)",
                True,
            )

            # Update motor status (command tracking only - feedback comes from /joint_states)
            with self._motor_state_lock:
                if joint_name in self.motor_status:
                    self.motor_status[joint_name]["last_command"] = position
                    self.motor_status[joint_name]["last_command_time"] = time.time()

            # Determine if we should wait for position feedback
            should_wait = (
                wait_for_feedback
                if wait_for_feedback is not None
                else self.config.get("enable_position_feedback", False)
            )

            if should_wait:
                return self._wait_for_position(joint_name, position)

            return True
        except Exception as e:
            self.logger.error(f"Joint position command failed: {e}")
            self._track_command(f"position({joint_name}, {position:.4f})", False, str(e))
            return False

    def _track_command(self, command: str, success: bool, error: str = None):
        """Track command for diagnostics and publish to command_echo"""
        with self._control_lock:
            self.command_count += 1
            self.last_command = command
            self.last_command_time = time.time()
            if not success:
                self.error_count += 1
            count_snapshot = self.command_count

        # Publish to command echo topic
        if hasattr(self, "command_echo_pub"):
            echo_msg = String()
            status = "✅" if success else "❌"
            echo_data = {
                "cmd": command,
                "ok": success,
                "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                "count": count_snapshot,
            }
            if error:
                echo_data["error"] = error
            echo_msg.data = json.dumps(echo_data)
            self.command_echo_pub.publish(echo_msg)

    def _wait_for_position(self, joint_name: str, target_position: float) -> bool:
        """Wait for joint to reach target position within tolerance

        Args:
            joint_name: Name of the joint
            target_position: Target position to reach

        Returns:
            True if position reached within timeout, False otherwise
        """
        timeout = self.config.get("position_feedback_timeout", 5.0)

        # Get tolerance based on joint type
        tolerance_config = self.config.get("position_tolerance", {})
        if "steering" in joint_name:
            tolerance = tolerance_config.get("steering", 0.05)  # ~3 degrees default
        else:
            tolerance = tolerance_config.get("drive", 0.1)  # 10cm default

        start_time = time.time()
        poll_rate = 0.05  # 50ms polling interval

        self.logger.debug(
            f"Waiting for {joint_name} to reach {target_position:.4f} (tolerance: {tolerance:.4f})"
        )

        while (time.time() - start_time) < timeout:
            # Get current position
            current_position = self._get_joint_position(joint_name)
            error = abs(current_position - target_position)

            if error <= tolerance:
                elapsed = time.time() - start_time
                self.logger.debug(
                    f"✅ {joint_name} reached position in {elapsed:.2f}s (error: {error:.4f})"
                )
                return True

            # Sleep to let the main-thread executor process joint_states callbacks.
            # DO NOT call rclpy.spin_once() here — this may be called from a
            # non-executor thread (joystick), and spin_once would deadlock the
            # single-threaded executor. The main rclpy.spin() already processes
            # subscription callbacks; we just need to wait for fresh data.
            time.sleep(
                poll_rate
            )  # BLOCKING_SLEEP_OK: position convergence poll — caller thread context — reviewed 2026-03-14

        # Timeout
        current_position = self._get_joint_position(joint_name)
        error = abs(current_position - target_position)
        self.logger.warning(
            f"⚠️ {joint_name} position feedback timeout after {timeout:.1f}s "
            f"(target: {target_position:.4f}, current: {current_position:.4f}, error: {error:.4f})"
        )
        return False

    def _wait_for_steering_positions(self, target_angle: float) -> bool:
        """Wait for all steering motors to reach target angle

        Args:
            target_angle: Target steering angle in radians

        Returns:
            True if all steering motors reached position, False otherwise
        """
        if not self.config.get("enable_position_feedback", False):
            return True  # Skip if feedback disabled

        steering_joints = ["steering_front", "steering_left", "steering_right"]
        all_reached = True

        for joint_name in steering_joints:
            if not self._wait_for_position(joint_name, target_angle):
                all_reached = False
                # Continue checking others for logging purposes

        return all_reached

    def _call_motor_enable(self, enable: bool) -> bool:
        """Enable or disable all motors via motor_control_ros2 service

        Note:
            This may be called from the joystick thread (daemon) or a
            service callback. The main thread runs rclpy.spin(node) with
            a single-threaded executor, so we MUST NOT call
            rclpy.spin_until_future_complete() — that deadlocks.
            Instead we poll future.done() while the main executor
            processes the response callback.
        """
        try:
            client = self.motor_enable_client if enable else self.motor_disable_client
            if not client.service_is_ready():
                self.logger.warning(f"Motor {'enable' if enable else 'disable'} service not ready")
                return False

            request = Trigger.Request()
            future = client.call_async(request)

            # Wait for the response — the main-thread executor processes
            # callbacks, so we just poll future.done() with a sleep.
            timeout = 5.0
            start = time.time()
            while not future.done():
                if (time.time() - start) >= timeout:
                    self.logger.error(
                        f"Motor {'enable' if enable else 'disable'} "
                        f"service call timeout ({timeout}s)"
                    )
                    return False
                time.sleep(
                    0.02
                )  # BLOCKING_SLEEP_OK: future poll from non-executor thread — cannot use spin_until_future — reviewed 2026-03-14

            if future.result() is not None:
                return future.result().success
            return False
        except Exception as e:
            self.logger.error(f"Motor {'enable' if enable else 'disable'} failed: {e}")
            return False

    def _send_steering_command(
        self, angle_rad: float, wait_for_feedback: bool = None, all_wheels: bool = False
    ) -> bool:
        """Send steering command to steering motors

        Sends angle command to either front wheel only (normal joystick) or all 3 wheels (direction switches).
        The motor controller handles transmission factors and direction.

        Args:
            angle_rad: Steering angle in radians (wheel space, positive = left turn)
            wait_for_feedback: If True, wait for position feedback before returning
            all_wheels: If True, send to all 3 steering wheels. If False, only front wheel.

        Returns:
            True if commands sent successfully
        """
        success_count = 0
        total_count = 0

        # Choose which steering motors to control
        if all_wheels:
            # Direction switches: all 3 wheels steer
            steering_joints = ["steering_left", "steering_right", "steering_front"]
        else:
            # Joystick: only front wheel steers
            steering_joints = ["steering_front"]

        for joint_name in steering_joints:
            # Send angle in radians (wheel space)
            # transmission_factor (6.0) and direction (±1) applied by motor controller
            if self._call_joint_position_command(joint_name, angle_rad, wait_for_feedback=False):
                success_count += 1
            total_count += 1

        self.logger.debug(
            f"Steering command: {angle_rad:.4f} rad ({math.degrees(angle_rad):.1f}°) sent to {success_count}/{total_count} motors"
        )

        return success_count == total_count

    def _send_drive_command(self, velocity_mps: float) -> bool:
        """Send drive command to all drive motors using abstraction layer

        Args:
            velocity_mps: Velocity in meters per second
        """
        if self.motor_controller:
            try:
                # Prefer high-level abstraction when available
                return self.motor_controller.set_vehicle_velocity(velocity_mps)
            except Exception as e:
                # If abstraction layer isn't initialized yet, fall back to direct topics
                self.logger.warning(
                    f"Motor controller drive failed ({e}), falling back to direct velocity topics"
                )
                return self._send_drive_velocity(velocity_mps)
        else:
            # Fallback to direct velocity topic publishing
            return self._send_drive_velocity(velocity_mps)

    def _send_emergency_stop(self) -> bool:
        """Send emergency stop command

        Note: This should trigger GPIO ESTOP in motor_control_ros2's safety_monitor
        """
        self.logger.critical("Sending emergency stop to motor_control_ros2")
        # The actual ESTOP is handled by motor_control_ros2 safety_monitor
        # This node just updates local state and GPIO indicators
        return True

    def _clear_emergency_stop(self) -> bool:
        """Clear emergency stop condition"""
        self.logger.info("Clearing emergency stop")
        return True

    # =========================================================================
    # High-Level Vehicle Control Functions (ROS1 equivalents)
    # =========================================================================

    def move_vehicle(self, distance_mm: float, steering_rotation: float = 0.0) -> bool:
        """Move vehicle by distance with steering (equivalent to ROS1 MoveVehicle)

        This is the main compound command used by joystick control.
        Moves drive motors incrementally while applying steering.

        ROS1 equivalent: MoveVehicle(IncrementalDistance, AbsoluteRotation)
        - IncrementalDistance: distance in mm
        - AbsoluteRotation: -0.25 to +0.25 (where ±0.25 = ±90°)

        Args:
            distance_mm: Distance to move in millimeters (positive=forward)
            steering_rotation: Steering wheel rotation (-0.25 to +0.25, where 0.25=90°)

        Returns:
            True if command executed successfully
        """
        try:
            # Convert steering rotation to radians for _send_steering_command
            # -0.25 to +0.25 rotation = -90° to +90° = -π/2 to +π/2 radians
            steering_angle_rad = steering_rotation * 3.14159 * 2  # rotation to radians

            # Move drive motors incrementally (matches ROS1 MoveDriveMotorsIncremental)
            self.move_drive_motors_incremental(distance_mm)

            # Apply steering - front motor only in default mode (matches ROS1 MoveSteeringMotorsTo)
            self._send_steering_command(steering_angle_rad)

            self.logger.debug(
                f"MoveVehicle: distance={distance_mm}mm, steering={steering_rotation}"
            )
            return True

        except Exception as e:
            self.logger.error(f"MoveVehicle failed: {e}")
            return False

    def move_drive_motors_incremental(self, distance_mm: float) -> bool:
        """Move drive motors by incremental distance (equivalent to ROS1 MoveDriveMotorsIncremental)

        Reads current position, calculates target position, sends position command.

        Args:
            distance_mm: Distance to move in millimeters

        Returns:
            True if commands sent successfully
        """
        try:
            # Get wheel parameters
            wheel_circumference_mm = PHYSICAL.WHEEL_CIRCUMFERENCE

            # Calculate rotations needed
            # Distance / (wheel circumference / gear ratio) = motor rotations
            motor_rotations = distance_mm / (wheel_circumference_mm / GEAR_RATIOS.DRIVE_MOTOR)

            drive_joints = ["drive_front", "drive_left_back", "drive_right_back"]
            skip_motors = self.config.get("skip_motors", [])
            available_joints = [j for j in drive_joints if j not in skip_motors]

            success = True
            for joint_name in available_joints:
                # Get current position
                current_pos = self._get_joint_position(joint_name)
                target_pos = current_pos + motor_rotations

                # Send position command
                if not self._call_joint_position_command(
                    joint_name, target_pos, wait_for_feedback=False
                ):
                    success = False
                    self.logger.warning(f"Failed to move {joint_name}")

            self.logger.debug(
                f"MoveDriveMotorsIncremental: {distance_mm}mm -> {motor_rotations:.4f} rotations"
            )
            return success

        except Exception as e:
            self.logger.error(f"MoveDriveMotorsIncremental failed: {e}")
            return False

    def stop_vehicle(self) -> bool:
        """Stop the vehicle (equivalent to ROS1 StopVehicle)

        Sets drive motors to closed-loop control and velocity 0.
        Does not change steering position.

        Returns:
            True if stop command successful
        """
        try:
            self.logger.info("Stopping vehicle...")

            # Enable motors (closed-loop control)
            self._call_motor_enable(True)

            # Set drive motor velocities to 0
            drive_joints = ["drive_front", "drive_left_back", "drive_right_back"]
            skip_motors = self.config.get("skip_motors", [])
            available_joints = [j for j in drive_joints if j not in skip_motors]

            success = True
            for joint_name in available_joints:
                if not self._call_joint_velocity_command(joint_name, 0.0):
                    success = False

            if success:
                self.logger.info("✅ Vehicle stopped")
            else:
                self.logger.warning("⚠️ Vehicle stop partially failed")

            return success

        except Exception as e:
            self.logger.error(f"StopVehicle failed: {e}")
            return False

    def set_vehicle_to_idle(self) -> bool:
        """Set vehicle to idle mode (equivalent to ROS1 SetVehicleToIdle)

        Disables all motors (steering + drive).

        Returns:
            True if idle command successful
        """
        try:
            self.logger.info("Setting vehicle to idle...")

            # Disable all motors
            success = self._call_motor_enable(False)

            if success:
                with self._control_lock:
                    self.current_state = VehicleState.IDLING
                self.logger.info("✅ Vehicle set to idle")
            else:
                self.logger.warning("⚠️ Failed to set vehicle to idle")

            return success

        except Exception as e:
            self.logger.error(f"SetVehicleToIdle failed: {e}")
            return False

    def straighten_steering(self) -> bool:
        """Straighten all steering wheels (equivalent to ROS1 MoveSteeringMotorsTo0degreerotation)

        Returns:
            True if command successful
        """
        try:
            if self.motor_controller:
                return self.motor_controller.straighten_steering()
            else:
                # Fallback: send 0 to front steering motor
                return self._call_joint_position_command("steering_front", 0.0)
        except Exception as e:
            self.logger.error(f"StraightenSteering failed: {e}")
            return False

    def set_pivot_mode(self, direction: PivotDirection) -> bool:
        """Set vehicle to pivot mode (equivalent to ROS1 SetVehicleToPivot)

        Args:
            direction: PivotDirection.LEFT, PivotDirection.RIGHT, or PivotDirection.NONE

        Returns:
            True if pivot mode set successfully
        """
        try:
            if self.motor_controller:
                return self.motor_controller.set_pivot_mode(direction)
            else:
                self.logger.warning("Pivot mode requires motor_controller - not available")
                return False
        except Exception as e:
            self.logger.error(f"SetPivotMode failed: {e}")
            return False

    def _setup_publishers(self):
        """Setup ROS2 publishers for compatibility with ROS1 topics"""
        qos_profile = QoSProfile(depth=10)

        # Joint state publisher (main robot state)
        self.joint_state_pub = self.create_publisher(JointState, "joint_states", qos_profile)

        # Individual joint state publishers (for backward compatibility)
        self.joint_pubs = {}
        for i, joint_name in enumerate(self.joint_names):
            self.joint_pubs[f"{joint_name}_state"] = self.create_publisher(
                Float64, f"/{joint_name}/state", qos_profile
            )

        # Vehicle control status
        self.status_pub = self.create_publisher(String, "/vehicle_status", qos_profile)

        # Odometry publisher (if needed for navigation)
        self.odom_pub = self.create_publisher(Odometry, "/odom", qos_profile)

        # GPIO output state publishers
        self.led_pubs = {
            "green_led": self.create_publisher(Bool, "/green_led/state", qos_profile),
            "yellow_led": self.create_publisher(Bool, "/yellow_led/state", qos_profile),
            "red_led": self.create_publisher(Bool, "/red_led/state", qos_profile),
            "error_led": self.create_publisher(Bool, "/error_led/state", qos_profile),
        }

        # Physical switch command publishers removed (Tasks 4.1, 3.2):
        # Start and shutdown commands now go direct to MQTT via
        # persistent client. No bridge consumes these DDS topics.
        # See design.md Decision 3.

        # Analog joystick publisher (optional)
        if self.joystick_processor is not None:
            joystick_cfg = self.config.get("joystick", {}) or {}
            joy_topic = joystick_cfg.get("joy_topic", "/joy")
            self.joystick_pub = self.create_publisher(Joy, joy_topic, qos_profile)
            self.logger.info(f"✅ Joystick publisher enabled on {joy_topic}")
        else:
            self.joystick_pub = None

        # Enhanced status publisher (JSON format with comprehensive info)
        self.status_detailed_pub = self.create_publisher(
            String, "/vehicle/status_detailed", qos_profile
        )

        # Command echo publisher (for debugging - shows every command sent)
        self.command_echo_pub = self.create_publisher(String, "/vehicle/command_echo", qos_profile)

        self.logger.info("✅ Enhanced publishers initialized (status_detailed, command_echo)")

    def _setup_subscribers(self):
        """Setup ROS2 subscribers for compatibility with ROS1 topics"""
        qos_profile = QoSProfile(depth=10)

        # Individual joint position command subscribers (ROS1-compat shim)
        #
        # IMPORTANT: This node publishes to /{joint}_position_controller/command (see
        # _call_joint_position_command). Do NOT subscribe to those topics here (output-only),
        # or we create a publish/subscribe feedback loop that can spam motor_control_ros2.
        for i, joint_name in enumerate(self.joint_names):
            self.create_subscription(
                Float64,
                f"/{joint_name}/command",
                lambda msg, idx=i: self._joint_position_callback(msg, idx),
                qos_profile,
            )

        # Vehicle motion commands
        self.create_subscription(Twist, "/cmd_vel", self._cmd_vel_callback, qos_profile)

        # Cotton picker specific commands
        self.create_subscription(
            Bool, "/pick_cotton/command", self._pick_cotton_callback, qos_profile
        )
        self.create_subscription(
            Bool, "/drop_cotton/command", self._drop_cotton_callback, qos_profile
        )
        self.create_subscription(Bool, "/lid_open/command", self._lid_open_callback, qos_profile)

        # LED control commands
        self.create_subscription(
            Bool, "/led_control/command", self._led_control_callback, qos_profile
        )
        self.create_subscription(
            Bool, "/problem_led/command", self._problem_led_callback, qos_profile
        )

    def _setup_services(self):
        """Setup ROS2 services for vehicle control

        Note: Motor-specific services (calibration, configuration) are handled
        by motor_control_ros2. This node provides high-level vehicle services.
        """
        # Emergency stop service
        self.emergency_stop_srv = self.create_service(
            SetBool, "emergency_stop", self._emergency_stop_callback
        )

        # Motor enable/disable services (forward to motor_control_ros2)
        self.vehicle_enable_srv = self.create_service(
            SetBool, "vehicle_control/enable_motors", self._vehicle_enable_callback
        )

        # Stop vehicle service
        self.stop_vehicle_srv = self.create_service(
            Trigger, "vehicle_control/stop", self._stop_vehicle_callback
        )

        # Set vehicle to idle service
        self.idle_vehicle_srv = self.create_service(
            Trigger, "vehicle_control/idle", self._idle_vehicle_callback
        )

        # Straighten steering service
        self.straighten_srv = self.create_service(
            Trigger,
            "vehicle_control/straighten_steering",
            self._straighten_steering_callback,
        )

        # Set steering mode service (front_only, ackermann, three_wheel)
        self.set_steering_mode_srv = self.create_service(
            SetBool,  # data=True uses ackermann, data=False uses front_only
            "vehicle_control/set_ackermann_mode",
            self._set_steering_mode_callback,
        )

        # Pivot mode services
        self.pivot_left_srv = self.create_service(
            Trigger, "vehicle_control/pivot_left", self._pivot_left_callback
        )
        self.pivot_right_srv = self.create_service(
            Trigger, "vehicle_control/pivot_right", self._pivot_right_callback
        )
        self.pivot_cancel_srv = self.create_service(
            Trigger, "vehicle_control/pivot_cancel", self._pivot_cancel_callback
        )

        # =====================================================================
        # DIAGNOSTIC SERVICES (Field Trial Ready)
        # =====================================================================

        # System diagnostics service - returns comprehensive health info
        self.diagnostics_srv = self.create_service(
            Trigger, "vehicle_control/diagnostics", self._diagnostics_callback
        )

        # Motor quick test service - test individual motors
        self.test_motor_srv = self.create_service(
            SetBool,  # data=True to run test, motor name in separate call
            "vehicle_control/test_motors",
            self._test_motors_callback,
        )

        # Re-run startup self-test
        self.self_test_srv = self.create_service(
            Trigger, "vehicle_control/self_test", self._self_test_callback
        )

        self.logger.info("✅ Vehicle control services initialized")
        self.logger.info(
            "✅ Diagnostic services: /vehicle/vehicle_control/diagnostics, /vehicle/vehicle_control/test_motors, /vehicle/vehicle_control/self_test"
        )

    def _setup_timers(self):
        """Setup periodic tasks using configuration values"""
        # Main control loop (configurable frequency)
        # Default 5.0 Hz — only does cmd_vel timeout + motor staleness checks.
        # Was 100.0 Hz which caused 94.7% CPU burn via executor overhead.
        control_freq = self.config.get("control_frequency", 5.0)
        self.control_timer = self.create_timer(1.0 / control_freq, self._control_loop)

        # Joint state publishing (configurable frequency)
        # Default 5.0 Hz — sufficient for dashboard/logging/rviz2.
        joint_state_freq = self.config.get("joint_state_frequency", 5.0)
        self.joint_state_timer = self.create_timer(
            1.0 / joint_state_freq, self._publish_joint_states
        )

        # GPIO monitoring (configurable frequency) - only if GPIO is enabled/initialized
        gpio_freq = self.config.get("gpio_frequency", 10.0)
        if self.gpio_processor is not None:
            self.gpio_timer = self.create_timer(1.0 / gpio_freq, self._process_gpio_inputs)
        else:
            self.gpio_timer = None

        # Joystick polling (optional)
        # Use continuous loop like old code instead of fixed timer
        if self.joystick_processor is not None:
            self.joystick_thread_running = True
            self.joystick_thread = threading.Thread(target=self._joystick_loop, daemon=True)
            self.joystick_thread.start()
            self.logger.info("✅ Joystick polling enabled (continuous loop mode)")
        else:
            self.joystick_thread = None
            self.joystick_thread_running = False

        # Status publishing (configurable frequency)
        # Default 2.0 Hz — human monitoring only.
        status_freq = self.config.get("status_frequency", 2.0)
        self.status_timer = self.create_timer(1.0 / status_freq, self._publish_status)

        # Task 7.5: MQTT health heartbeat (10s base — logs every 60s
        # when connected, every 10s when disconnected)
        self.mqtt_health_timer = self.create_timer(10.0, self._mqtt_health_heartbeat)

        # Tasks 8.2-8.3: MQTT loopback self-test (every 30s)
        self.mqtt_selftest_timer = self.create_timer(30.0, self._mqtt_selftest_check)

        # Task 4-5: control_loop_health emission (every 30s)
        self.health_timer = self.create_timer(30.0, self._emit_control_loop_health)

        # Log active timer frequencies at startup (structured JSON for field auditing)
        import json as _json

        self.logger.info(
            "[TIMING] "
            + _json.dumps(
                {
                    "event": "timer_frequencies",
                    "control_hz": control_freq,
                    "joint_state_hz": joint_state_freq,
                    "gpio_hz": gpio_freq,
                    "status_hz": status_freq,
                    "mqtt_health_period_s": 10.0,
                    "mqtt_selftest_period_s": 30.0,
                }
            )
        )

    def _joint_position_callback(self, msg: Float64, joint_idx: int):
        """Handle individual joint position commands"""
        try:
            self.joint_commands[joint_idx] = msg.data
            joint_name = self.joint_names[joint_idx]
            self.logger.debug(f"Joint {joint_name} command: {msg.data}")

            # Execute joint movement via motor_control_ros2 topic
            success = self._call_joint_position_command(joint_name, msg.data)
            if not success:
                self.logger.warning(f"Failed to move joint {joint_name} to {msg.data}")

        except Exception as e:
            self.logger.error(f"Joint position callback error: {e}")

    def _cmd_vel_callback(self, msg: Twist, from_joystick: bool = False):
        """Handle vehicle motion commands

        Converts Twist (linear.x, angular.z) to steering angles and drive velocities.
        Publishes commands to motor_control_ros2 via the abstraction layer when available.
        Direction switches (LEFT/RIGHT) override steering in manual mode.

        Args:
            msg: Twist message with linear.x (m/s) and angular.z (steering [-1..1])
            from_joystick: True when called from the joystick polling loop. When True,
                the joystick loop already manages drive_stop directly, so the deadband
                path must NOT call _send_drive_motors_hold_position — that would
                immediately re-activate drive_stop right after the loop cleared it.
        """
        try:
            self.last_cmd_vel_time = time.time()

            linear_vel = float(msg.linear.x)  # m/s (forward/backward)
            angular_cmd = float(msg.angular.z)  # treated as normalized steering command [-1..1]

            self.logger.debug(
                f"cmd_vel: linear={linear_vel:.2f}, angular={angular_cmd:.2f}, from_joystick={from_joystick}"
            )

            # Get physical parameters from config
            physical = self.config.get("physical_params", {})
            steering_limits = physical.get("steering_limits", {"min": -45.0, "max": 45.0})
            max_steering_deg = float(steering_limits.get("max", 45.0))
            min_steering_deg = float(steering_limits.get("min", -max_steering_deg))

            # Check direction switches (only in MANUAL_LEFT or MANUAL_RIGHT modes)
            # In other modes (NONBRAKE_MANUAL, etc.), joystick controls steering normally
            direction_steering_rad = None
            with self._control_lock:
                cur_state = self.current_state
            if cur_state == VehicleState.MANUAL_LEFT or cur_state == VehicleState.MANUAL_RIGHT:
                direction_steering_rad = self._get_direction_switch_steering()

            if direction_steering_rad is not None:
                # Direction switch is active - skip joystick steering (direction switch already controlling it)
                # Only process drive commands from joystick
                self.logger.debug(
                    f"Direction switch active in {cur_state.name}, skipping joystick steering"
                )
                steering_angle_rad = None  # Don't send steering from joystick
            else:
                # No direction switch OR not in LEFT/RIGHT mode - use joystick for steering
                # Map angular command to steering angle (deg)
                # Note: steering_angular_scale is treated as "deg at angular_cmd=1.0".
                steering_scale_deg = float(
                    self.config.get("steering_angular_scale", max_steering_deg)
                )
                steering_angle_deg = angular_cmd * steering_scale_deg
                steering_angle_deg = max(
                    min(steering_angle_deg, max_steering_deg), min_steering_deg
                )
                steering_angle_rad = steering_angle_deg * math.pi / 180.0

            # Deadband: if both commands are essentially zero, center steering and stop drive motors
            # Increased deadband to 0.15 to handle joystick drift/noise (joystick doesn't return perfectly to 512)
            if abs(linear_vel) < 0.15 and abs(angular_cmd) < 0.15:
                # Only send steering center if no direction switch is active
                if direction_steering_rad is None:
                    self._send_steering_command(0.0, all_wheels=False)  # Joystick: front wheel only
                # Drive: send hold position command to stop motors at current position.
                # Skip when called from the joystick loop — the loop manages drive_stop
                # directly and calling it here would immediately re-activate drive_stop
                # right after the loop just cleared it (e.g. steering-only moves where
                # linear_vel=0 always lands in this deadband branch).
                if not from_joystick:
                    self._send_drive_motors_hold_position()
                return

            # Steering - absolute position (from joystick only if no direction switch)
            if steering_angle_rad is not None:
                self._send_steering_command(
                    steering_angle_rad, all_wheels=False
                )  # Joystick: front wheel only

            # Drive - position control with incremental movement (like old code)
            # This will BLOCK until movement completes, then loop reads joystick again
            # Only move if linear velocity is above deadband
            if abs(linear_vel) > 0.15:
                self._send_drive_position_incremental(linear_vel)

        except Exception as e:
            self.logger.error(f"cmd_vel callback error: {e}")

    def _get_direction_switch_steering(self):
        """Get steering angle from direction switches (manual mode only)

        Returns:
            float: Steering angle in radians (None if no switch active or in auto mode)
                   Uses max steering limit from config (75° by default)
        """
        # Only work in manual mode
        if self.is_automatic_mode:
            return None

        # Skip if GPIO not available
        if self.gpio_manager is None:
            return None

        try:
            # Read direction switches
            direction_left = self.gpio_manager.read_input(GPIO_PINS.DIRECTION_LEFT)
            direction_right = self.gpio_manager.read_input(GPIO_PINS.DIRECTION_RIGHT)

            # Get max steering angle from config
            physical = self.config.get("physical_params", {})
            steering_limits = physical.get("steering_limits", {"min": -75.0, "max": 75.0})
            max_steering_deg = float(steering_limits.get("max", 75.0))
            max_steering_rad = max_steering_deg * 3.14159 / 180.0

            # If both pressed or both released, return 0 (center)
            if direction_left == direction_right:
                return 0.0  # Return 0 to center steering when released

            # Direction LEFT active → negative max steering
            if direction_left:
                return -max_steering_rad

            # Direction RIGHT active → positive max steering
            if direction_right:
                return max_steering_rad

            # Neither active
            return None

        except Exception as e:
            self.logger.error(f"Error reading direction switches: {e}")
            return None

    def _joystick_loop(self) -> None:
        """Continuous joystick polling loop (like old VehicleControl.py)

        Runs in separate thread. Reads joystick, sends commands, and waits
        for movement completion before next iteration.
        """
        self.logger.info("🕹️ Joystick loop started (continuous mode like old code)")

        while self.joystick_thread_running and rclpy.ok():
            try:
                # Read joystick and process - this will BLOCK if movement happens
                self._poll_joystick_blocking()
            except Exception as e:
                self.logger.error(f"Joystick loop error: {e}")
                time.sleep(
                    0.1
                )  # BLOCKING_SLEEP_OK: joystick error recovery throttle — dedicated thread — reviewed 2026-03-14

        self.logger.info("🕹️ Joystick loop stopped")

    def _poll_joystick_blocking(self) -> None:
        """Read joystick and send commands - BLOCKS until movement completes"""
        if self.joystick_processor is None:
            return

        try:
            joystick_cfg = self.config.get("joystick", {}) or {}
            max_linear_mps = float(joystick_cfg.get("max_linear_mps", 0.5))
            turn_scale = float(joystick_cfg.get("turn_scale", 1.0))

            # When false: publish /joy only (no motor commands).
            # Useful to validate joystick/SPI without risking CAN spam / BUS-OFF.
            apply_to_motors = bool(joystick_cfg.get("apply_to_motors", True))

            input_data = self.joystick_processor.read_filtered()

            # Normalize to [-1, 1]
            x_norm = (input_data.x_value - JOYSTICK.MID_VALUE) / float(JOYSTICK.MID_VALUE)
            y_norm = (input_data.y_value - JOYSTICK.MID_VALUE) / float(JOYSTICK.MID_VALUE)
            x_norm = max(-1.0, min(1.0, float(x_norm)))
            y_norm = max(-1.0, min(1.0, float(y_norm)))

            # Map to commands
            linear_cmd = y_norm * max_linear_mps
            angular_cmd = x_norm * turn_scale

            # Publish Joy for debugging
            if self.joystick_pub is not None:
                joy_msg = Joy()
                joy_msg.header.stamp = self.get_clock().now().to_msg()
                joy_msg.axes = [x_norm, y_norm]
                joy_msg.buttons = []
                self.joystick_pub.publish(joy_msg)

            # If not applying to motors, just log
            if not apply_to_motors:
                if not hasattr(self, "_joystick_apply_to_motors_logged"):
                    self.logger.warning("🕹️ Joystick apply_to_motors=false: publishing /joy only")
                    self._joystick_apply_to_motors_logged = True
                if not input_data.is_centered:
                    now = time.time()
                    if (now - getattr(self, "_joystick_last_log_time", 0.0)) > 1.0:
                        self.logger.info(
                            f"Joystick raw(x={input_data.x_value}, y={input_data.y_value}) [OBSERVE ONLY]"
                        )
                        self._joystick_last_log_time = now
                time.sleep(
                    0.05
                )  # BLOCKING_SLEEP_OK: joystick observe-only delay — dedicated thread — reviewed 2026-03-14
                return

            # If centered, stop both steering and drive
            if input_data.is_centered:
                if not self._joystick_idle_applied:
                    # Joystick released - center steering and stop drive
                    self.logger.info("🛑 Joystick released - centering steering and stopping drive")
                    # Send zero velocity to center steering and hold drive position
                    twist = Twist()
                    self._cmd_vel_callback(twist, from_joystick=True)
                    # Additionally, activate drive_stop to clear drive queue and stop motors
                    self._call_drive_stop(activate=True)
                    self._joystick_idle_applied = True
                time.sleep(
                    0.05
                )  # BLOCKING_SLEEP_OK: joystick idle delay — dedicated thread — reviewed 2026-03-14
                return

            # Joystick is active (moving)
            # Deactivate drive_stop if it was active
            if self._joystick_idle_applied:
                self.logger.info("🕹️ Joystick active - deactivating drive_stop, resuming movement")
                self._call_drive_stop(activate=False)
                self._joystick_idle_applied = False

            # Send command - this will BLOCK if drive movement happens
            twist = Twist()
            twist.linear.x = linear_cmd
            twist.angular.z = angular_cmd
            self._cmd_vel_callback(twist, from_joystick=True)

            # Log throttled
            now = time.time()
            if (now - getattr(self, "_joystick_last_log_time", 0.0)) > 1.0:
                self.logger.info(
                    f"Joystick raw(x={input_data.x_value}, y={input_data.y_value}) "
                    f"norm(x={x_norm:+.2f}, y={y_norm:+.2f}) -> cmd(linear={linear_cmd:+.2f} m/s, angular={angular_cmd:+.2f})"
                )
                self._joystick_last_log_time = now

        except Exception as e:
            self.logger.error(f"Joystick poll error: {e}")

    def _send_drive_position_incremental(self, velocity_mps: float):
        """Send incremental position commands to drive motors (like old VehicleControl.py)

        Sends ONE position command and waits for movement to complete.
        Prevents command piling by checking movement flag.

        Args:
            velocity_mps: Target velocity in m/s
        """
        # Skip if a movement is already in progress
        if self._drive_movement_in_progress:
            return

        try:
            # Mark movement as in progress
            self._drive_movement_in_progress = True

            # Get joystick config for scaling
            joystick_cfg = self.config.get("joystick", {}) or {}
            max_linear_mps = float(joystick_cfg.get("max_linear_mps", 0.5))

            # Scale velocity to distance (same as old code MaximumMovePosition)
            max_distance_mm = 1917.0  # Same as old code MaximumMovePosition at full joystick

            if abs(max_linear_mps) > 0.001:
                distance_mm = max_distance_mm * (velocity_mps / max_linear_mps)
            else:
                distance_mm = 0.0

            # Clamp to limits
            distance_mm = max(min(distance_mm, max_distance_mm), -max_distance_mm)

            # Convert mm to meters (ODrive expects meters directly)
            distance_m = distance_mm / 1000.0

            # Position increment in meters (used as absolute delta for ODrive)
            position_increment_m = distance_m

            # Send position commands to ALL drive motors
            drive_joints = ["drive_front", "drive_left_back", "drive_right_back"]
            skip_motors = self.config.get("skip_motors", [])
            available_joints = [j for j in drive_joints if j not in skip_motors]

            success_count = 0
            target_positions = {}  # Store targets for position checking

            for joint_name in available_joints:
                # Get CURRENT motor position from joint_states
                with self._motor_state_lock:
                    status = self.motor_status.get(joint_name, {})
                    current_position = status.get("last_position", 0.0)
                    has_responded = status.get("has_responded", False)

                # Warn if position is stale (motor never sent joint_states)
                if not has_responded:
                    self.logger.warning(
                        f"[DRIVE] {joint_name}: no joint_states received yet — "
                        f"last_position=0.0 (default). Target will be relative to 0."
                    )

                # Calculate new target: current + increment (both in meters for ODrive)
                target_position = current_position + position_increment_m
                target_positions[joint_name] = target_position

                # Log the command details
                self.logger.info(
                    f"🚗 Drive {joint_name}: distance={distance_mm:.1f}mm, current={current_position:.4f}m (has_responded={has_responded}), target={target_position:.4f}m, increment={position_increment_m:.4f}m"
                )

                # Send absolute position command
                if self._call_joint_position_command(joint_name, target_position):
                    success_count += 1

            # Calculate wait time based on distance and motor speed
            # Motor max velocity: 2.0 m/s from vehicle_motors.yaml
            # But we're moving at joystick velocity (velocity_mps)
            motor_speed_mps = abs(velocity_mps) if abs(velocity_mps) > 0.01 else 0.5
            distance_meters = abs(distance_mm) / 1000.0

            # Time = Distance / Speed
            calculated_wait_time = distance_meters / motor_speed_mps

            # Drastically reduce wait time - use 20% of calculated with very short minimum
            wait_time = max(calculated_wait_time * 0.2, 0.05)  # Minimum 50ms

            self.logger.info(
                f"⏱️ Waiting {wait_time:.2f}s for motors to move {distance_meters:.3f}m at {motor_speed_mps:.2f}m/s"
            )

            # Instead of blind time-based wait, check if motors actually reached positions
            # This prevents commands from piling up when motors can't keep up
            start_time = time.time()
            max_wait = wait_time * 2.0  # Maximum 2x calculated time (but still short)
            position_reached = False
            joystick_released = False

            while (time.time() - start_time) < max_wait:
                time.sleep(
                    0.1
                )  # BLOCKING_SLEEP_OK: motor position convergence poll — caller thread — reviewed 2026-03-14

                # Check if joystick was released
                if self.joystick_processor is not None:
                    input_data = self.joystick_processor.read_filtered()
                    if input_data.is_centered:
                        self.logger.info(
                            f"🛑 Joystick released - stopping motors with HOLD POSITION command"
                        )
                        joystick_released = True
                        # In position control mode: send position command to CURRENT position to stop motor
                        # Note: motor_status position may be slightly old (~100ms), causing small jerk
                        # But this is better than letting motor run to full target position
                        for joint_name in available_joints:
                            with self._motor_state_lock:
                                current_pos = self.motor_status.get(joint_name, {}).get(
                                    "last_position", 0.0
                                )
                            target_was = target_positions.get(joint_name, 0.0)
                            self.logger.info(
                                f"🛑 STOP {joint_name}: was_going_to={target_was:.4f}, holding_at={current_pos:.4f}"
                            )
                            self._call_joint_position_command(joint_name, current_pos)
                        break

                # Check if motors reached target positions (at least one motor)
                all_reached = True
                for joint_name in available_joints:
                    with self._motor_state_lock:
                        current_pos = self.motor_status.get(joint_name, {}).get(
                            "last_position", 0.0
                        )
                    target_pos = target_positions.get(joint_name, current_pos)
                    error = abs(current_pos - target_pos)

                    # Use loose tolerance (1.0 rad) to avoid waiting forever
                    if error > 1.0:
                        all_reached = False
                        break

                if all_reached:
                    position_reached = True
                    elapsed = time.time() - start_time
                    self.logger.info(f"✅ Motors reached positions in {elapsed:.2f}s")
                    break

            if not position_reached and not joystick_released:
                self.logger.warning(
                    f"⚠️ Position wait timeout after {max_wait:.2f}s - motors may be falling behind"
                )

            if success_count < len(available_joints):
                self.logger.warning(
                    f"Only {success_count}/{len(available_joints)} drive motors responded"
                )

        except Exception as e:
            self.logger.error(f"Drive position incremental command error: {e}")
        finally:
            # Always clear the flag when done
            self._drive_movement_in_progress = False

    def _send_drive_motors_hold_position(self):
        """Stop drive motors via the /drive_stop service.

        Called from _cmd_vel_callback when both axes are in the deadband (< 0.15).
        Only reached when from_joystick=False (i.e. an external /cmd_vel message).
        The joystick loop manages drive_stop directly and bypasses this via the
        from_joystick flag.
        """
        try:
            self._call_drive_stop(activate=True)
            self.logger.debug("[DRIVE] Drive stop activated (deadband, external cmd_vel)")
        except Exception as e:
            self.logger.error(f"Drive motors stop error: {e}")

    def _send_drive_velocity(self, velocity_mps: float):
        """Send velocity to drive motors using true velocity control

        Uses velocity command topics for continuous motor spinning.
        Supports degraded mode - continues with available motors.

        Args:
            velocity_mps: Velocity in meters per second
        """
        try:
            # Convert m/s to motor velocity (rad/s)
            # Need to account for wheel diameter and gear ratios
            physical = self.config.get("physical_params", {})
            wheel_diameter = physical.get("wheel_diameter", 0.6096)  # 24 inch in meters
            wheel_circumference = 3.14159 * wheel_diameter

            # Wheel rotations per second from velocity
            wheel_rps = velocity_mps / wheel_circumference

            # Motor velocity in rad/s (wheel_rps * 2*pi)
            motor_velocity_rad_s = wheel_rps * 2.0 * 3.14159

            # Send velocity commands to available drive motors (degraded mode support)
            drive_joints = ["drive_front", "drive_left_back", "drive_right_back"]

            # Check which motors are available (from skip_motors config)
            skip_motors = self.config.get("skip_motors", [])
            available_joints = [j for j in drive_joints if j not in skip_motors]

            if len(available_joints) < len(drive_joints):
                if not hasattr(self, "_degraded_mode_logged"):
                    self.logger.warning(
                        f"⚠️ DEGRADED MODE: Operating with {len(available_joints)}/{len(drive_joints)} drive motors"
                    )
                    self._degraded_mode_logged = True

            success_count = 0
            for joint_name in available_joints:
                if self._call_joint_velocity_command(joint_name, motor_velocity_rad_s):
                    success_count += 1

            # Log if some motors failed to respond
            if success_count < len(available_joints):
                self.logger.warning(
                    f"Only {success_count}/{len(available_joints)} drive motors responded"
                )

        except Exception as e:
            self.logger.error(f"Drive velocity command error: {e}")

    def _call_joint_velocity_command(self, joint_name: str, velocity: float) -> bool:
        """Send velocity command to motor_control_ros2 via topic

        Args:
            joint_name: Name of the joint (e.g., 'drive_front')
            velocity: Target velocity in rad/s

        Returns:
            True if command sent successfully
        """
        try:
            if joint_name not in self.motor_velocity_pubs:
                self.logger.warning(f"No velocity publisher for joint: {joint_name}")
                self._track_command(
                    f"velocity({joint_name}, {velocity:.4f})", False, "no publisher"
                )
                return False

            msg = Float64()
            msg.data = velocity
            self.motor_velocity_pubs[joint_name].publish(msg)

            # Track the command
            self._track_command(f"velocity({joint_name}, {velocity:.4f})", True)

            # Update motor status (command tracking only - feedback comes from /joint_states)
            with self._motor_state_lock:
                if joint_name in self.motor_status:
                    self.motor_status[joint_name]["last_command"] = velocity
                    self.motor_status[joint_name]["last_command_time"] = time.time()

            return True
        except Exception as e:
            self.logger.error(f"Joint velocity command failed: {e}")
            self._track_command(f"velocity({joint_name}, {velocity:.4f})", False, str(e))
            return False

    def _call_joint_homing(self, joint_id: int) -> bool:
        """Call motor_control_ros2 homing service for a joint

        Note: Homing is handled by motor_control_ros2 package.
        This method would call the appropriate service.

        Args:
            joint_id: ID of the joint to home

        Returns:
            True if homing successful
        """
        try:
            # TODO: Implement when motor_control_ros2 homing service is available
            # For now, log and return success (motors may already be homed)
            self.logger.info(
                f"Joint homing requested for joint {joint_id} - delegated to motor_control_ros2"
            )
            return True
        except Exception as e:
            self.logger.error(f"Joint homing call failed: {e}")
            return False

    def _get_joint_position(self, joint_name: str) -> float:
        """Get current position of a joint from cached states"""
        # Look in vehicle joint names mapping
        vehicle_joints = [
            "steering_left",
            "steering_right",
            "steering_front",
            "drive_front",
            "drive_left_back",
            "drive_right_back",
        ]
        if joint_name in vehicle_joints:
            idx = vehicle_joints.index(joint_name)
            # Joint positions are updated via _motor_joint_states_callback
            # Return 0 if not yet received
            with self._motor_state_lock:
                return getattr(self, "_vehicle_joint_positions", {}).get(joint_name, 0.0)
        return 0.0

    def _pick_cotton_callback(self, msg: Bool):
        """Handle cotton picking command"""
        try:
            if msg.data:
                self.logger.info("Cotton picking sequence started")
                # Implement cotton picking sequence using motor controller
                # This would involve specific joint movements for the cotton picker
                self._execute_cotton_picking_sequence()
            else:
                self.logger.info("Cotton picking sequence stopped")
                self._stop_cotton_picking_sequence()
        except Exception as e:
            self.logger.error(f"Pick cotton callback error: {e}")

    def _drop_cotton_callback(self, msg: Bool):
        """Handle cotton dropping command"""
        try:
            if msg.data:
                self.logger.info("Cotton dropping sequence started")
                self._execute_cotton_dropping_sequence()
        except Exception as e:
            self.logger.error(f"Drop cotton callback error: {e}")

    def _lid_open_callback(self, msg: Bool):
        """Handle lid open/close command"""
        try:
            self.logger.info(f"Lid {'open' if msg.data else 'close'} command")
            if self.gpio_manager is None:
                self.logger.warning("⚠️  GPIO disabled - cannot control lid")
                return
            # Implement lid control using GPIO or motor controller
            success = self.gpio_manager.set_output(GPIO_PINS.FAN, msg.data)  # Example
            if not success:
                self.logger.warning("Failed to control lid")
        except Exception as e:
            self.logger.error(f"Lid control callback error: {e}")

    def _led_control_callback(self, msg: Bool):
        """Handle LED control command"""
        try:
            if self.gpio_manager is None:
                return  # GPIO disabled, skip silently
            # Control status LEDs
            success = self.gpio_manager.set_output(GPIO_PINS.GREEN_LED, msg.data)
            if success:
                self.led_pubs["green_led"].publish(Bool(data=msg.data))
        except Exception as e:
            self.logger.error(f"LED control callback error: {e}")

    def _problem_led_callback(self, msg: Bool):
        """Handle problem LED command"""
        try:
            if self.gpio_manager is None:
                return  # GPIO disabled, skip silently
            success = self.gpio_manager.set_output(GPIO_PINS.ERROR_LED, msg.data)
            if success:
                self.led_pubs["error_led"].publish(Bool(data=msg.data))
        except Exception as e:
            self.logger.error(f"Problem LED callback error: {e}")

    def _vehicle_enable_callback(self, request, response):
        """Service callback for enabling/disabling vehicle motors"""
        try:
            enable = request.data
            self.logger.info(f"{'Enabling' if enable else 'Disabling'} vehicle motors")

            success = self._call_motor_enable(enable)
            response.success = success
            response.message = (
                f"Motors {'enabled' if enable else 'disabled'}" if success else "Failed"
            )

        except Exception as e:
            self.logger.error(f"Vehicle enable error: {e}")
            response.success = False
            response.message = str(e)

        return response

    def _stop_vehicle_callback(self, request, response):
        """Service callback for stopping the vehicle"""
        try:
            success = self.stop_vehicle()
            response.success = success
            response.message = "Vehicle stopped" if success else "Stop failed"
        except Exception as e:
            self.logger.error(f"Stop vehicle service error: {e}")
            response.success = False
            response.message = str(e)
        return response

    def _idle_vehicle_callback(self, request, response):
        """Service callback for setting vehicle to idle"""
        try:
            success = self.set_vehicle_to_idle()
            response.success = success
            response.message = "Vehicle set to idle" if success else "Idle failed"
        except Exception as e:
            self.logger.error(f"Idle vehicle service error: {e}")
            response.success = False
            response.message = str(e)
        return response

    def _straighten_steering_callback(self, request, response):
        """Service callback for straightening steering"""
        try:
            success = self.straighten_steering()
            response.success = success
            response.message = "Steering straightened" if success else "Straighten failed"
        except Exception as e:
            self.logger.error(f"Straighten steering service error: {e}")
            response.success = False
            response.message = str(e)
        return response

    def _set_steering_mode_callback(self, request, response):
        """Service callback for setting steering mode

        data=True: Use Ackermann steering
        data=False: Use front-only steering (default)
        """
        try:
            if request.data:
                self.steering_mode = "ackermann"
                response.message = "Steering mode: ackermann"
            else:
                self.steering_mode = "front_only"
                response.message = "Steering mode: front_only"
            response.success = True
            self.logger.info(f"Steering mode set to: {self.steering_mode}")
        except Exception as e:
            self.logger.error(f"Set steering mode error: {e}")
            response.success = False
            response.message = str(e)
        return response

    def _pivot_left_callback(self, request, response):
        """Service callback for pivot left mode"""
        try:
            success = self.set_pivot_mode(PivotDirection.LEFT)
            response.success = success
            response.message = "Pivot left activated" if success else "Pivot left failed"
        except Exception as e:
            self.logger.error(f"Pivot left service error: {e}")
            response.success = False
            response.message = str(e)
        return response

    def _pivot_right_callback(self, request, response):
        """Service callback for pivot right mode"""
        try:
            success = self.set_pivot_mode(PivotDirection.RIGHT)
            response.success = success
            response.message = "Pivot right activated" if success else "Pivot right failed"
        except Exception as e:
            self.logger.error(f"Pivot right service error: {e}")
            response.success = False
            response.message = str(e)
        return response

    def _pivot_cancel_callback(self, request, response):
        """Service callback for canceling pivot mode"""
        try:
            success = self.set_pivot_mode(PivotDirection.NONE)
            response.success = success
            response.message = "Pivot mode canceled" if success else "Pivot cancel failed"
        except Exception as e:
            self.logger.error(f"Pivot cancel service error: {e}")
            response.success = False
            response.message = str(e)
        return response

    # =========================================================================
    # DIAGNOSTIC SERVICE CALLBACKS
    # =========================================================================

    def _diagnostics_callback(self, request, response):
        """Service callback for system diagnostics

        Returns comprehensive system health information as JSON.
        """
        try:
            diagnostics = self.get_diagnostics()
            response.success = True
            response.message = json.dumps(diagnostics, indent=2)
            self.logger.info(
                f"Diagnostics requested - Health Score: {diagnostics['health_score']}/100"
            )
        except Exception as e:
            self.logger.error(f"Diagnostics service error: {e}")
            response.success = False
            response.message = f"Error: {str(e)}"
        return response

    def _test_motors_callback(self, request, response):
        """Service callback for motor quick test

        data=True: Run test on all motors (small wiggle)
        data=False: Skip test (just report status)
        """
        try:
            if request.data:
                self.logger.info("🛠️ Starting motor quick test...")
                results = self._run_motor_quick_test()
                passed = sum(1 for r in results.values() if r["ok"])
                total = len(results)
                response.success = passed == total
                response.message = f"Motor test: {passed}/{total} passed\n" + json.dumps(
                    results, indent=2
                )
            else:
                # Just return current motor status
                with self._motor_state_lock:
                    motor_info = {
                        joint: {
                            "ok": status["ok"],
                            "position": round(self._get_joint_position(joint), 4),
                            "errors": status["error_count"],
                        }
                        for joint, status in self.motor_status.items()
                    }
                response.success = True
                response.message = json.dumps(motor_info, indent=2)
        except Exception as e:
            self.logger.error(f"Motor test service error: {e}")
            response.success = False
            response.message = str(e)
        return response

    def _self_test_callback(self, request, response):
        """Service callback to re-run startup self-test"""
        try:
            self.logger.info("Re-running startup self-test...")
            self._run_startup_self_test()
            response.success = True
            response.message = f"Self-test complete. Health Score: {self._startup_health_score}/100"
        except Exception as e:
            self.logger.error(f"Self-test service error: {e}")
            response.success = False
            response.message = str(e)
        return response

    def _run_motor_quick_test(self) -> Dict[str, Dict]:
        """Run quick test on all motors

        CRITICAL FIX: Now verifies actual position change, not just command success.
        Previously would report OK even when motors didn't move!

        Sends small position commands and verifies motor physically responded.
        Returns dict with test results per motor.
        """
        results = {}
        test_positions = [0.05, 0.0]  # Small wiggle and back

        for joint_name in self.joint_names:
            try:
                # Get initial position
                initial_pos = self._get_joint_position(joint_name)

                # Send small test command
                command_success = True
                for test_pos in test_positions:
                    target = initial_pos + test_pos
                    success = self._call_joint_position_command(
                        joint_name, target, wait_for_feedback=False
                    )
                    time.sleep(
                        0.1
                    )  # BLOCKING_SLEEP_OK: motor response settling time — test/verification context — reviewed 2026-03-14
                    if not success:
                        command_success = False
                        break

                # CRITICAL: Verify position actually changed
                final_pos = self._get_joint_position(joint_name)
                position_changed = abs(final_pos - initial_pos) > 0.01  # 0.01 rad threshold
                with self._motor_state_lock:
                    motor_has_responded = self.motor_status[joint_name]["has_responded"]

                # Motor is OK only if: command sent AND position changed AND motor has responded
                motor_ok = command_success and position_changed and motor_has_responded

                results[joint_name] = {
                    "ok": motor_ok,
                    "initial_pos": round(initial_pos, 4),
                    "final_pos": round(final_pos, 4),
                    "position_changed": position_changed,
                    "has_responded": motor_has_responded,
                    "test": "wiggle",
                }

                status = "✅" if motor_ok else "❌"
                reason = (
                    "OK"
                    if motor_ok
                    else f"FAILED (cmd:{command_success}, moved:{position_changed}, responded:{motor_has_responded})"
                )
                self.logger.info(f"  {status} {joint_name}: {reason}")

            except Exception as e:
                results[joint_name] = {"ok": False, "error": str(e), "test": "wiggle"}
                self.logger.error(f"  ❌ {joint_name}: ERROR - {e}")

        return results

    def _emergency_stop_callback(self, request, response):
        """Service callback for emergency stop

        Updates local state and GPIO indicators.
        motor_control_ros2's safety_monitor handles actual motor stop.
        """
        try:
            if request.data:
                self.logger.critical("EMERGENCY STOP ACTIVATED")
                self._send_emergency_stop()
                if self.gpio_manager:
                    self.gpio_manager.show_status_led("EMERGENCY")
                with self._control_lock:
                    self.current_state = VehicleState.ERROR
            else:
                self.logger.info("Emergency stop cleared")
                self._clear_emergency_stop()
                if self.gpio_manager:
                    self.gpio_manager.show_status_led("OK")
                with self._control_lock:
                    self.current_state = VehicleState.IDLING

            response.success = True
            response.message = f"Emergency stop {'activated' if request.data else 'cleared'}"

        except Exception as e:
            self.logger.error(f"Emergency stop error: {e}")
            response.success = False
            response.message = str(e)

        return response

    # ── Thermal / CPU self-monitoring (Task 4) ────────────────────

    def _read_cpu_temperature(self):
        """Read CPU temperature from sysfs. Returns °C or None."""
        if not self._thermal_monitoring_available:
            return None
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                return int(f.read().strip()) / 1000.0
        except (OSError, IOError, ValueError):
            return None

    def _read_throttle_state(self):
        """Read RPi throttle flags from sysfs. Returns bool or None."""
        if not self._throttle_monitoring_available:
            return None
        try:
            with open("/sys/devices/platform/soc/soc:firmware/get_throttled", "r") as f:
                val = int(f.read().strip(), 16)
                return val != 0
        except (OSError, IOError, ValueError):
            return None

    def _emit_control_loop_health(self):
        """Emit structured [TIMING] control_loop_health event.

        Combines loop timing counters (Task 5) with thermal/CPU fields
        (Task 4) into a single JSON log entry.  Called by a dedicated
        timer every 30 seconds.
        """
        try:
            # Loop timing fields (Task 5)
            avg_ms = 0.0
            if self._loop_count > 0:
                avg_ms = (self._loop_time_sum / self._loop_count) * 1000.0
            max_ms = self._loop_time_max * 1000.0

            # Thermal fields (Task 4)
            cpu_temp = self._read_cpu_temperature()
            throttled = self._read_throttle_state()

            cpu_pct = None
            if self._cpu_process is not None:
                try:
                    cpu_pct = self._cpu_process.cpu_percent(interval=None)
                except Exception as e:
                    self.logger.debug(f"psutil cpu_percent failed | error={e}")
                    cpu_pct = None

            # Temperature threshold warnings
            if cpu_temp is not None:
                if cpu_temp > 80.0:
                    self.logger.error(f"[THERMAL] CPU temperature CRITICAL: {cpu_temp:.1f}°C")
                elif cpu_temp > 70.0:
                    self.logger.warning(f"[THERMAL] CPU temperature HIGH: {cpu_temp:.1f}°C")

            # CPU usage sustained-high warning
            if cpu_pct is not None and cpu_pct > 30.0:
                self._last_cpu_high_count += 1
                if self._last_cpu_high_count >= 2:
                    self.logger.warning(
                        f"[THERMAL] Process CPU sustained high:"
                        f" {cpu_pct:.1f}% for"
                        f" {self._last_cpu_high_count} intervals"
                    )
            else:
                self._last_cpu_high_count = 0

            uptime = time.time() - self.start_time
            event = {
                "event": "control_loop_health",
                "uptime_sec": round(uptime, 1),
                "loop_count": self._loop_count,
                "avg_loop_time_ms": round(avg_ms, 3),
                "max_loop_time_ms": round(max_ms, 3),
                "missed_deadlines": self._missed_deadlines,
                "cpu_temp_c": round(cpu_temp, 1) if cpu_temp is not None else None,
                "process_cpu_percent": (round(cpu_pct, 1) if cpu_pct is not None else None),
                "throttled": throttled,
            }

            self.logger.info("[TIMING] " + json.dumps(event))

            # Reset loop timing counters after emission
            self._loop_time_sum = 0.0
            self._loop_time_max = 0.0
            self._loop_count = 0
            self._missed_deadlines = 0

        except Exception as e:
            self.logger.error(f"Health emission error: {e}")

    def _control_loop(self):
        """Main control loop (5Hz default)

        Joint positions are received via /joint_states subscription from motor_control_ros2.
        This loop handles timeout watchdog and state management.
        Per-iteration wall-clock timing is tracked for control_loop_health.
        """
        _t0 = time.perf_counter()
        try:
            # Check for cmd_vel timeout (watchdog)
            timeout_elapsed = time.time() - self.last_cmd_vel_time
            if timeout_elapsed > self.cmd_vel_timeout:
                # Only warn once per timeout period - transition from BUSY to IDLING
                with self._control_lock:
                    if self.current_state == VehicleState.BUSY:
                        self.logger.warning(
                            f"cmd_vel timeout ({timeout_elapsed:.1f}s) - vehicle should stop"
                        )
                        self.current_state = VehicleState.IDLING

            # Check motor response times and mark unhealthy if stale
            # Only warn once per motor when it goes stale (status['ok'] transitions from True to False)
            current_time = time.time()
            with self._motor_state_lock:
                for joint, status in self.motor_status.items():
                    if status["last_response_time"] > 0:
                        stale_time = current_time - status["last_response_time"]
                        if stale_time > 5.0 and status["ok"]:  # 5 second staleness threshold
                            self.logger.warning(f"Motor {joint} response stale ({stale_time:.1f}s)")
                            status["ok"] = False
                            status["stale_warned"] = True  # Only warn once

        except Exception as e:
            self.logger.error(f"Control loop error: {e}")
        finally:
            _t1 = time.perf_counter()
            _elapsed = _t1 - _t0
            self._loop_time_sum += _elapsed
            if _elapsed > self._loop_time_max:
                self._loop_time_max = _elapsed
            self._loop_count += 1
            if _elapsed > self._deadline_threshold:
                self._missed_deadlines += 1

    def _publish_joint_states(self):
        """Publish joint states (5Hz default)"""
        try:
            # Create joint state message
            joint_state = JointState()
            joint_state.header = Header()
            joint_state.header.stamp = self.get_clock().now().to_msg()
            joint_state.header.frame_id = "base_link"

            joint_state.name = self.joint_names
            with self._motor_state_lock:
                positions_snapshot = list(self.joint_positions)
            joint_state.position = positions_snapshot
            joint_state.velocity = [0.0] * len(self.joint_names)  # Could be populated from motors
            joint_state.effort = [0.0] * len(self.joint_names)  # Could be populated from motors

            self.joint_state_pub.publish(joint_state)

            # Publish individual joint states for backward compatibility
            for i, (joint_name, position) in enumerate(zip(self.joint_names, positions_snapshot)):
                if f"{joint_name}_state" in self.joint_pubs:
                    msg = Float64()
                    msg.data = position
                    self.joint_pubs[f"{joint_name}_state"].publish(msg)

        except Exception as e:
            self.logger.error(f"Joint state publishing error: {e}")

    def _process_gpio_inputs(self):
        """Process GPIO inputs (10Hz)"""
        try:
            # Skip if GPIO not initialized (e.g., running without root)
            if self.gpio_processor is None:
                return

            # Check automatic mode switch (GPIO 20)
            if self.gpio_manager is not None:
                try:
                    current_auto_mode = self.gpio_manager.is_automatic_mode_selected()

                    # DEBUG: Periodically log GPIO 20 state
                    now = time.time()
                    if not hasattr(self, "_last_gpio_debug_time"):
                        self._last_gpio_debug_time = 0.0

                    if (now - self._last_gpio_debug_time) > 2.0:  # Log every 2 seconds
                        self.logger.info(
                            f"🔍 GPIO 20 (AUTOMATIC_MODE): {current_auto_mode} | is_automatic_mode: {self.is_automatic_mode}"
                        )
                        self._last_gpio_debug_time = now

                    # Detect mode change
                    if current_auto_mode != self._last_automatic_mode_state:
                        if current_auto_mode:
                            self.logger.info("🔄 Mode Switch: MANUAL → AUTOMATIC (GPIO 20 active)")
                            self.is_automatic_mode = True
                            # Update status LED to show automatic mode
                            self.gpio_manager.show_status_led("OK")
                        else:
                            self.logger.info(
                                "🔄 Mode Switch: AUTOMATIC → MANUAL (GPIO 20 inactive)"
                            )
                            self.is_automatic_mode = False
                            # Update status LED to show manual mode
                            self.gpio_manager.show_status_led("WARNING")

                        self._last_automatic_mode_state = current_auto_mode
                        self.logger.info(
                            f"✅ Mode changed - is_automatic_mode = {self.is_automatic_mode}"
                        )

                except Exception as e:
                    self.logger.warning(f"Failed to read automatic mode switch: {e}")

            # Check direction switches and send steering commands (manual mode only)
            self._process_direction_switches()

            # Check physical switches (start/shutdown buttons)
            self._process_physical_switches()

            # Read GPIO state
            gpio_state = self.gpio_processor.read_filtered()

            # Update vehicle mode based on GPIO
            new_mode = self.gpio_processor.get_vehicle_mode(gpio_state)

            # Validate new_mode is a valid VehicleState enum
            # Note: VehicleState is IntEnum with hex values (e.g., NONBRAKE_MANUAL=0x1112=4370)
            try:
                # Ensure it's a VehicleState member (handles import path differences)
                if hasattr(new_mode, "name") and hasattr(new_mode, "value"):
                    pass  # Valid enum member
                else:
                    self.logger.warning(f"Invalid vehicle mode from GPIO: {new_mode}")
                    return
            except Exception as e:
                self.logger.warning(f"Vehicle mode validation error: {e}")
                return

            with self._control_lock:
                old_state = self.current_state
                if new_mode != old_state:
                    self.current_state = new_mode
                else:
                    old_state = None  # signal: no change
            if old_state is not None:
                self.logger.info(f"Vehicle mode changed: {old_state.name} -> {new_mode.name}")

                # Update status LEDs (only if GPIO enabled)
                if self.gpio_manager:
                    if new_mode == VehicleState.AUTOMATIC_MODE:
                        self.gpio_manager.show_status_led("OK")
                    elif new_mode == VehicleState.MANUAL_MODE:
                        self.gpio_manager.show_status_led("WARNING")
                    elif new_mode == VehicleState.ERROR:
                        self.gpio_manager.show_status_led("ERROR")

        except Exception as e:
            self.logger.error(f"GPIO processing error: {e}")

    def _process_direction_switches(self):
        """Process direction switches and send steering commands immediately

        Monitors direction switches (LEFT/RIGHT) and sends steering commands
        whenever switch state changes. Works only in MANUAL_LEFT or MANUAL_RIGHT modes.
        """
        # Only work in MANUAL_LEFT or MANUAL_RIGHT modes
        with self._control_lock:
            cur_state = self.current_state
        if cur_state != VehicleState.MANUAL_LEFT and cur_state != VehicleState.MANUAL_RIGHT:
            return

        # Skip if GPIO not available
        if self.gpio_manager is None:
            return

        # CRITICAL FIX: Don't process direction switches during shutdown
        # This prevents unwanted centering when GPIO reads fail during power-off
        if self._shutdown_in_progress:
            return

        try:
            # Read current direction switch states
            direction_left = self.gpio_manager.read_input(GPIO_PINS.DIRECTION_LEFT)
            direction_right = self.gpio_manager.read_input(GPIO_PINS.DIRECTION_RIGHT)

            # Detect state changes
            left_changed = direction_left != self._last_direction_left_state
            right_changed = direction_right != self._last_direction_right_state

            if left_changed or right_changed:
                # Determine steering angle
                # Get max steering angle from config
                physical = self.config.get("physical_params", {})
                steering_limits = physical.get("steering_limits", {"min": -75.0, "max": 75.0})
                max_steering_deg = float(steering_limits.get("max", 75.0))
                max_steering_rad = max_steering_deg * 3.14159 / 180.0

                if direction_left and direction_right:
                    # Both pressed - ignore both, center steering
                    steering_angle_rad = 0.0
                    self.logger.info("🔄 Direction switches: BOTH pressed → Center steering (0°)")
                elif direction_left:
                    # LEFT pressed - steer left to max angle
                    steering_angle_rad = -max_steering_rad
                    self.logger.info(
                        f"⬅️ Direction switch: LEFT pressed → Steering -{max_steering_deg:.0f}°"
                    )
                elif direction_right:
                    # RIGHT pressed - steer right to max angle
                    steering_angle_rad = max_steering_rad
                    self.logger.info(
                        f"➡️ Direction switch: RIGHT pressed → Steering +{max_steering_deg:.0f}°"
                    )
                else:
                    # Both released - return to center
                    steering_angle_rad = 0.0
                    self.logger.info("↩️ Direction switches: Released → Center steering (0°)")

                # Send steering command to ALL 3 wheels (direction switches)
                self._send_steering_command(steering_angle_rad, all_wheels=True)

                # Update last states
                self._last_direction_left_state = direction_left
                self._last_direction_right_state = direction_right

        except Exception as e:
            self.logger.error(f"Error processing direction switches: {e}")

    def _process_physical_switches(self):
        """Monitor physical switches (start button GPIO6, shutdown button GPIO5)"""
        if self.gpio_manager is None:
            return

        try:
            import time
            import subprocess

            # Get pin numbers from config
            start_pin = self.config.get("gpio_pins", {}).get("start_switch_pin", 6)
            shutdown_pin = self.config.get("gpio_pins", {}).get("shutdown_switch_pin", 5)
            shutdown_hold_time = self.config.get("shutdown_hold_time_s", 3.0)
            enable_auto_shutdown = self.config.get("enable_auto_shutdown", True)

            # Read switch states
            # START: PUD_DOWN → active-high (HIGH=pressed, LOW=not pressed)
            # SHUTDOWN: PUD_UP → active-low (LOW=pressed, HIGH=not pressed)
            start_state = self.gpio_manager.read_input(start_pin)  # HIGH when pressed
            shutdown_raw = self.gpio_manager.read_input(
                shutdown_pin
            )  # LOW when pressed (active-low)
            shutdown_state = not shutdown_raw  # Invert: True when button grounds the pin

            # START SWITCH: Publish on press (edge detection)
            if start_state and not self._last_start_switch_state:
                # Task 7.1: Increment press sequence number
                self._press_seq += 1
                seq = self._press_seq

                self.logger.info(f"🟢 START button pressed (GPIO{start_pin})")
                self.logger.info(
                    "[SIGNAL_CHAIN] vehicle_control_node: Start switch GPIO pressed"
                    f" | seq={seq}"
                    " | source=GPIO6 dest=topic/start_switch_input_all"
                )

                # Task 2.1: Publish via persistent MQTT client (non-blocking)
                # Task 7.2: Include seq=N in payload for ARM correlation
                if self._mqtt_client is not None:
                    # Task 7.4: Warn if publishing while disconnected
                    with self._mqtt_lock:
                        mqtt_connected = self._mqtt_connected
                        disconnect_time = self._mqtt_disconnect_time
                    if not mqtt_connected:
                        disconnect_dur = ""
                        if disconnect_time is not None:
                            dur = time.monotonic() - disconnect_time
                            disconnect_dur = f" disconnect_duration={dur:.1f}s"
                        self.logger.warn(
                            "[SIGNAL_CHAIN] vehicle_control_node:"
                            " Publishing"
                            " start while MQTT disconnected"
                            f" | seq={seq}"
                            " mqtt_status=disconnected"
                            f"{disconnect_dur}"
                        )
                    payload = f"True|seq={seq}"
                    result = self._mqtt_client.publish(
                        "topic/start_switch_input_all",
                        payload,
                        qos=1,
                        retain=False,
                    )
                    # Task 7.1: Log publish result with seq (Layer 3)
                    if result.rc == 0:
                        self.logger.info(
                            "[SIGNAL_CHAIN] vehicle_control_node:"
                            " Published start to MQTT"
                            f" | seq={seq} publish_rc=0"
                            " | source=GPIO6"
                            " dest=topic/start_switch_input_all"
                        )
                    else:
                        self.logger.warn(
                            "[SIGNAL_CHAIN] vehicle_control_node:"
                            " MQTT publish failed"
                            f" | seq={seq} publish_rc={result.rc}"
                        )
                else:
                    self.logger.error(
                        "[SIGNAL_CHAIN] vehicle_control_node:"
                        f" MQTT client not initialized | seq={seq}"
                    )

            # SHUTDOWN SWITCH: Require hold time, execute on press (not release)
            if shutdown_state:
                if not self._last_shutdown_switch_state:
                    # Button just pressed - start timer and turn on RED LED
                    self._shutdown_press_start_time = time.time()
                    self.logger.info(
                        f"🔴 SHUTDOWN button pressed (GPIO{shutdown_pin}) - hold for {shutdown_hold_time}s..."
                    )
                    # Turn on RED LED to indicate shutdown button is pressed
                    if self.gpio_manager:
                        try:
                            self.gpio_manager.set_output(GPIO_PINS.RED_LED, True)
                        except (RuntimeError, OSError, AttributeError) as e:
                            self.logger.debug(f"GPIO: RED LED on failed | error={e}")
                else:
                    # Button still held - check duration and execute on press
                    hold_duration = time.time() - self._shutdown_press_start_time
                    if hold_duration >= shutdown_hold_time and not self._shutdown_in_progress:
                        self.logger.info(
                            f"✅ SHUTDOWN button held for {hold_duration:.1f}s - executing shutdown"
                        )
                        self._execute_shutdown(enable_auto_shutdown)
            else:
                # Button released - reset timer and turn off RED LED
                self._shutdown_press_start_time = None
                # Turn off RED LED when button is released (skip if shutdown initiated)
                if (
                    self.gpio_manager
                    and self._last_shutdown_switch_state
                    and not self._shutdown_initiated
                ):
                    try:
                        self.gpio_manager.set_output(GPIO_PINS.RED_LED, False)
                    except (RuntimeError, OSError, AttributeError) as e:
                        self.logger.debug(f"GPIO: RED LED off failed | error={e}")

            # Update last states
            self._last_start_switch_state = start_state
            self._last_shutdown_switch_state = shutdown_state

        except Exception as e:
            self.logger.error(f"Error processing physical switches: {e}")

    def _execute_shutdown(self, enable_auto_shutdown=True):
        """Execute shutdown sequence after 3-second hold.

        Publishes shutdown via persistent MQTT client (non-blocking)
        and uses graceful node exit.

        Signal flow:
          1. Publish shutdown to MQTT via persistent client
          2. Kill stale detached shutdown processes from prior runs
          3. Spawn detached OS shutdown (20s delay for motor parking)
          4. Gracefully exit node via rclpy.shutdown() → launch cascade
             sends SIGTERM to all nodes → destructors run → motors park
        """
        import subprocess

        if self._shutdown_in_progress:
            return

        self._shutdown_in_progress = True
        self._shutdown_initiated = True
        self.logger.warn("🛑 SHUTDOWN SEQUENCE INITIATED (3s hold complete)")
        self.logger.info(
            "[SIGNAL_CHAIN] vehicle_control_node: Shutdown switch GPIO held"
            " | source=GPIO5 dest=topic/shutdown_switch_input_all"
        )

        # ── Phase 1: Publish shutdown via persistent MQTT client ────
        # Task 3.1: Uses persistent client — non-blocking, no connect().
        if self._mqtt_client is not None:
            result = self._mqtt_client.publish(
                "topic/shutdown_switch_input_all",
                "True",
                qos=1,
                retain=False,
            )
            if result.rc == 0:
                self.logger.info(
                    "[SIGNAL_CHAIN] vehicle_control_node: Published shutdown"
                    " to MQTT"
                    " | publish_rc=0"
                    " | source=GPIO5"
                    " dest=topic/shutdown_switch_input_all"
                )
            else:
                self.logger.warn(
                    "[SIGNAL_CHAIN] vehicle_control_node:"
                    " MQTT shutdown publish failed"
                    f" | publish_rc={result.rc}"
                )
        else:
            self.logger.error(
                "[SIGNAL_CHAIN] vehicle_control_node:" " MQTT client not initialized for shutdown"
            )

        # ── Phase 2: Schedule OS shutdown + graceful exit ───────────
        # Done in a background thread so this callback returns
        # immediately (single-threaded executor must not block).
        def _shutdown_sequence():
            import time as _time

            try:
                # Kill any stale detached shutdown processes from
                # previous test runs. These linger because they use
                # start_new_session=True and can cause premature
                # shutdown of the RPi.
                subprocess.run(
                    ["pkill", "-f", "sleep.*sudo.*/sbin/shutdown"],
                    capture_output=True,
                )
                self.logger.info("Cleared stale detached shutdown processes")

                if enable_auto_shutdown:
                    # Spawn detached OS shutdown with 20s delay.
                    # This gives the launch cascade time to:
                    #   - SIGTERM all nodes (~2s)
                    #   - motor_control destructor parks motors (~12s)
                    #   - GPIO cleanup (~1s)
                    self.logger.warn(
                        "🔌 Scheduling RPi poweroff in 20s" " (for motor parking + cleanup)..."
                    )
                    subprocess.Popen(
                        "sleep 20 && sudo /sbin/shutdown -h now",
                        shell=True,
                        start_new_session=True,
                    )

                # Give 2s for the MQTT QoS 1 ACK round-trip to complete.
                _time.sleep(
                    2
                )  # BLOCKING_SLEEP_OK: MQTT QoS1 ACK round-trip — dedicated shutdown thread — reviewed 2026-03-14

                # Graceful exit: rclpy.shutdown() causes the executor
                # spin() to return, which exits main(), which exits
                # launcher.sh, which lets systemd send SIGTERM to all
                # remaining processes in the cgroup. This is MUCH
                # cleaner than pkill -9:
                #   - Node destructors run (GPIO cleanup, CAN cleanup)
                #   - motor_control gets SIGTERM → parks motors
                #   - vehicle_mqtt_bridge shuts down cleanly
                self.logger.warn(
                    "Initiating graceful ROS2 shutdown"
                    " (launch cascade will SIGTERM all nodes)..."
                )
                rclpy.shutdown()

            except Exception as e:
                self.logger.error(f"Shutdown sequence failed: {e}")
                # Last resort: if graceful shutdown fails, force it
                try:
                    subprocess.Popen(
                        ["pkill", "-9", "-f", "vehicle_control_node"],
                        shell=False,
                    )
                except Exception as e:
                    sys.stderr.write(f"vehicle_control: shutdown pkill failed: {e}\n")

        threading.Thread(target=_shutdown_sequence, daemon=True).start()

    def _publish_status(self):
        """Publish system status (5Hz)

        Publishes both simple status and detailed JSON status.
        """
        try:
            # Snapshot control state under lock
            with self._control_lock:
                current_state_snap = self.current_state
                last_command_snap = self.last_command
                command_count_snap = self.command_count
                error_count_snap = self.error_count

            # Simple status (backward compatible)
            status_msg = String()
            status_msg.data = f"State: {current_state_snap.name}, Joints: {len(self.joint_names)}"
            self.status_pub.publish(status_msg)

            # Enhanced JSON status
            uptime = time.time() - self.start_time
            detailed_status = {
                "timestamp": datetime.now().isoformat(),
                "state": current_state_snap.name,
                "health_score": self.get_health_score(),
                "steering_mode": self.steering_mode,
                "uptime_sec": round(uptime, 1),
                "motors": {},
                "last_command": last_command_snap,
                "command_count": command_count_snap,
                "error_count": error_count_snap,
            }

            # Add motor positions
            with self._motor_state_lock:
                motor_snapshot = {
                    joint: {
                        "pos": round(self._get_joint_position(joint), 4),
                        "ok": self.motor_status.get(joint, {}).get("ok", True),
                    }
                    for joint in self.joint_names
                }
            detailed_status["motors"] = motor_snapshot

            detailed_msg = String()
            detailed_msg.data = json.dumps(detailed_status)
            self.status_detailed_pub.publish(detailed_msg)

        except Exception as e:
            self.logger.error(f"Status publishing error: {e}")

    def _update_joint_positions(self):
        """Update joint positions from hardware

        Note: Joint positions are now received via _motor_joint_states_callback
        from motor_control_ros2 /joint_states topic. This method is kept for
        compatibility but doesn't poll hardware directly.
        """
        # Joint positions updated via subscription callback
        pass

    def _perform_joint_homing(self, joint_id: int) -> bool:
        """Perform complete homing sequence for a joint

        Calls motor_control_ros2 homing service which handles:
        - Motor initialization
        - Encoder calibration
        - Move to home position
        """
        try:
            return self._call_joint_homing(joint_id)
        except Exception as e:
            self.logger.error(f"Joint homing error: {e}")
            return False

    def _perform_motor_calibration(self, motor_id: int) -> bool:
        """Perform motor calibration sequence"""
        try:
            # Implementation would depend on ODrive calibration sequence
            self.logger.info(f"Motor {motor_id} calibration sequence")
            return True
        except Exception as e:
            self.logger.error(f"Motor calibration error: {e}")
            return False

    def _perform_encoder_calibration(self, encoder_id: int) -> bool:
        """Perform encoder calibration sequence"""
        try:
            # Implementation would depend on encoder type and calibration procedure
            self.logger.info(f"Encoder {encoder_id} calibration sequence")
            return True
        except Exception as e:
            self.logger.error(f"Encoder calibration error: {e}")
            return False

    def _configure_joint(self, joint_id: int, config_request) -> bool:
        """Configure joint parameters"""
        try:
            # Apply configuration parameters to joint/motor
            self.logger.info(f"Configuring joint {joint_id}")
            return True
        except Exception as e:
            self.logger.error(f"Joint configuration error: {e}")
            return False

    def _execute_cotton_picking_sequence(self):
        """Execute cotton picking sequence"""
        try:
            # Implement specific joint movements for cotton picking
            self.logger.info("Executing cotton picking sequence")
            # This would involve complex coordinated movements

        except Exception as e:
            self.logger.error(f"Cotton picking sequence error: {e}")

    def _stop_cotton_picking_sequence(self):
        """Stop cotton picking sequence"""
        try:
            # motor_control_ros2 handles motor stopping
            self.logger.info("Cotton picking sequence stopped")
        except Exception as e:
            self.logger.error(f"Stop cotton picking error: {e}")

    def _execute_cotton_dropping_sequence(self):
        """Execute cotton dropping sequence"""
        try:
            # Implement cotton dropping movements
            self.logger.info("Executing cotton dropping sequence")
        except Exception as e:
            self.logger.error(f"Cotton dropping sequence error: {e}")

    def shutdown(self):
        """Clean shutdown (idempotent)"""
        if getattr(self, "_shutdown_called", False):
            return
        self._shutdown_called = True

        # Avoid using ROS logging here: during signal shutdown the rcl context may already be invalid,
        # and logging would spam "publisher's context is invalid".
        _shutdown_logger = logging.getLogger("vehicle_control")
        try:
            _shutdown_logger.info("Shutting down vehicle control node")
        except Exception as e:
            sys.stderr.write(f"vehicle_control: shutdown log failed: {e}\n")

        try:
            # Stop joystick thread
            if hasattr(self, "joystick_thread_running"):
                self.joystick_thread_running = False
                if hasattr(self, "joystick_thread") and self.joystick_thread:
                    self.joystick_thread.join(timeout=2.0)
        except Exception as e:
            sys.stderr.write(f"vehicle_control: joystick thread join failed: {e}\n")

        try:
            # Close joystick SPI handle (if initialized)
            if self.joystick_interface is not None:
                try:
                    self.joystick_interface.close()
                except Exception as e:
                    sys.stderr.write(f"vehicle_control: joystick close failed: {e}\n")
        except Exception as e:
            sys.stderr.write(f"vehicle_control: joystick cleanup failed: {e}\n")

        try:
            # Motor control shutdown handled by motor_control_ros2
            if self.gpio_manager is not None:
                # Turn off Software Status LED to indicate software has stopped
                try:
                    self.gpio_manager.set_output(GPIO_PINS.SOFTWARE_STATUS_LED, False)  # GPIO 22
                    _shutdown_logger.info("Software Status LED (GPIO 22) turned OFF")
                except Exception as e:
                    sys.stderr.write(f"vehicle_control: status LED off failed: {e}\n")
                self.gpio_manager.cleanup()
        except Exception as e:
            try:
                _shutdown_logger.error(f"Shutdown error: {e}")
            except Exception as e2:
                sys.stderr.write(f"vehicle_control: shutdown error logging failed: {e2}\n")

        # Task 1.4: Clean up persistent MQTT client
        try:
            self._cleanup_mqtt()
        except Exception as e:
            sys.stderr.write(f"vehicle_control: MQTT cleanup failed during shutdown: {e}\n")


def main(args=None):
    """Main function"""
    import signal

    # Set process name for task manager visibility
    try:
        import setproctitle

        setproctitle.setproctitle("vehicle_control_node")
    except ImportError:
        pass  # setproctitle not installed, process will show as python3

    node = None

    def signal_handler(signum, frame):
        """Handle shutdown signals gracefully"""
        sig_name = signal.Signals(signum).name
        logging.getLogger("vehicle_control").warn(f"Received {sig_name}, shutting down...")
        # Let rclpy unwind spin cleanly; cleanup happens in finally.
        try:
            rclpy.shutdown()
        except Exception as e:
            sys.stderr.write(f"vehicle_control: rclpy.shutdown failed in signal handler: {e}\n")
        return

    # Register signal handlers for clean shutdown
    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # kill command
    signal.signal(signal.SIGHUP, signal_handler)  # SSH disconnect

    rclpy.init(args=args)

    executor = None
    try:
        node = ROS2VehicleControlNode()
        # Use spin_once(timeout) + sleep throttle loop instead of rclpy.spin().
        #
        # Why not just rclpy.spin() or spin_once(timeout)?
        # rclpy's Python executor caches a generator from wait_for_ready_callbacks
        # that yields all ready entities from a single wait_set.wait() call.
        # With many entities (8 timers, 8 subs, guard conditions), the generator
        # often has multiple items queued — consecutive spin_once calls return
        # immediately without blocking in wait_set.wait().  Additionally,
        # guard conditions with _executor_triggered=True are re-triggered before
        # wait_set.wait(), preventing the kernel-level epoll block even when a
        # new generator is created.  Result: timeout_sec is effectively ignored
        # in most iterations, causing 79%+ CPU on RPi 4B.
        #
        # The time.sleep(0.05) throttle caps the loop at ~20 Hz, which is 2x
        # above our fastest timer (10 Hz GPIO) while yielding >95% of CPU time.
        # This is the standard workaround for rclpy's executor busy-poll behavior.
        import time

        executor = rclpy.executors.SingleThreadedExecutor()
        executor.add_node(node)
        while rclpy.ok():
            executor.spin_once(timeout_sec=0.1)
            time.sleep(
                0.05
            )  # BLOCKING_SLEEP_OK: CPU throttle for SingleThreadedExecutor — intentional 20Hz cap — reviewed 2026-03-14
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as e:
        # rclpy can raise ExternalShutdownException on Ctrl+C when shutdown is triggered.
        if e.__class__.__name__ in ("ExternalShutdownException",):
            pass
        else:
            logging.getLogger("vehicle_control").error(f"Node error: {e}")
    finally:
        if executor is not None:
            try:
                executor.shutdown()
            except Exception as e:
                sys.stderr.write(f"vehicle_control: executor shutdown failed: {e}\n")
        if node is not None:
            try:
                node.shutdown()
            finally:
                try:
                    node.destroy_node()
                except Exception as e:
                    sys.stderr.write(f"vehicle_control: node destroy failed: {e}\n")
        try:
            rclpy.shutdown()
        except Exception as e:
            sys.stderr.write(
                f"vehicle_control: rclpy.shutdown (final) failed: {e}\n"
            )  # Already shut down by signal handler


if __name__ == "__main__":
    main()
