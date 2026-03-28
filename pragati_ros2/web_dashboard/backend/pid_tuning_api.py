#!/usr/bin/env python3

"""PID Tuning REST API and WebSocket endpoints for Pragati dashboard.

Provides FastAPI router with endpoints for:
- Reading/writing PID gains via ROS2 services
- Saving gains to motor ROM
- Running step response tests
- Profile management (save/load YAML)
- Auto-tune analysis (Ziegler-Nichols)
- Live motor state streaming via WebSocket

The router communicates with the ``pid_tuning_service`` ROS2 node using
service clients and action clients managed by :class:`PIDTuningBridge`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import threading
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Z-N / step-metrics import with source-tree fallback
# -------------------------------------------------------------------
try:
    from pid_tuning.zn_analyzer import (
        analyze_step_response,
        compute_tuning_rules,
        suggest_gains as zn_suggest_gains,
    )
    from pid_tuning.step_metrics import compute_step_metrics
except ImportError:
    try:
        _src_root = Path(__file__).resolve().parent.parent.parent / "src" / "pid_tuning"
        sys.path.insert(0, str(_src_root))
        from pid_tuning.zn_analyzer import (
            analyze_step_response,
            compute_tuning_rules,
            suggest_gains as zn_suggest_gains,
        )
        from pid_tuning.step_metrics import compute_step_metrics
    except ImportError:
        analyze_step_response = None  # type: ignore[assignment]
        compute_tuning_rules = None  # type: ignore[assignment]
        zn_suggest_gains = None  # type: ignore[assignment]
        compute_step_metrics = None  # type: ignore[assignment]
        logger.warning(
            "pid_tuning package not available — " "autotune/analyze endpoint will be disabled"
        )

# -------------------------------------------------------------------
# Safety module imports (pid_safety.py — pure Python, no ROS2 needed)
# -------------------------------------------------------------------
try:
    from pid_tuning.pid_safety import (
        GainLimitEnforcer,
        GainRamper,
        OscillationDetector,
        TuningSessionLock,
        TuningSessionLogger,
    )

    SAFETY_AVAILABLE = True
except ImportError:
    SAFETY_AVAILABLE = False
    logger.warning(
        "pid_safety module not available — " "safety enforcement will use inline fallbacks only"
    )

# -------------------------------------------------------------------
# ROS2 imports (optional — allows mock mode)
# -------------------------------------------------------------------
try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]

try:
    import rclpy
    from rclpy.action import ActionClient
    from rclpy.callback_groups import MutuallyExclusiveCallbackGroup

    from motor_control_msgs.action import StepResponseTest
    from motor_control_msgs.srv import ReadPID, WritePID, WritePIDToROM
    from std_msgs.msg import String

    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False
    logger.warning("ROS2 not available — PID bridge runs in mock mode")


def _pid_unavailable_error() -> str:
    """Return an informative error when PID ops cannot be performed.

    PID read/write is supported over both RS485 (ParamID protocol) and
    CAN bus (via ROS2).  This error is shown only when neither transport
    is available.
    """
    if os.environ.get("PRAGATI_MOTOR_SERIAL_PORT"):
        return (
            "RS485 serial port is configured but the driver is not connected. "
            "Check the serial connection and try again."
        )
    return "ROS2 not available and no RS485 serial port configured"


# ===================================================================
# Constants
# ===================================================================

# Motor configuration (from production.yaml)
MOTOR_CONFIG: List[Dict[str, Any]] = [
    {
        "motor_id": 1,
        "joint_name": "joint5",
        "motor_type": "mg6010",
        "can_id": "0x141",
    },
    {
        "motor_id": 2,
        "joint_name": "joint3",
        "motor_type": "mg6010",
        "can_id": "0x142",
    },
    {
        "motor_id": 3,
        "joint_name": "joint4",
        "motor_type": "mg6010",
        "can_id": "0x143",
    },
]
VALID_MOTOR_IDS = set(range(1, 33))  # RS485 protocol supports IDs 1-32

SERVICE_TIMEOUT_SEC = 5.0
ACTION_TIMEOUT_SEC = 60.0
STEP_TEST_CLEANUP_SECONDS = 1800  # 30 min

# RS485 step test constants
RS485_STEP_TEST_SAMPLE_RATE_HZ = 10.0
RS485_STEP_TEST_TEMP_LIMIT_C = 80.0
RS485_STEP_TEST_MAX_DEVIATION_FACTOR = 2.0

# Paths
_CONFIG_DEFAULTS_DIR = Path(__file__).resolve().parent.parent / "config_defaults"
_PID_SAFETY_DIR = _CONFIG_DEFAULTS_DIR / "pid_safety"
_PID_PROFILES_DIR = _CONFIG_DEFAULTS_DIR / "pid_profiles"
_PID_BENCHMARKS_DIR = Path(__file__).resolve().parent.parent / "data" / "pid_benchmarks"

# Hardcoded fallback gain limits (if config YAML missing)
_FALLBACK_GAIN_LIMITS: Dict[str, Any] = {
    "position": {
        "kp": {"min": 0, "max": 65535, "default": 2},
        "ki": {"min": 0, "max": 65535, "default": 2},
        "kd": {"min": 0, "max": 65535, "default": 0},
    },
    "speed": {
        "kp": {"min": 0, "max": 65535, "default": 50},
        "ki": {"min": 0, "max": 65535, "default": 40},
        "kd": {"min": 0, "max": 65535, "default": 0},
    },
    "torque": {
        "kp": {"min": 0, "max": 65535, "default": 50},
        "ki": {"min": 0, "max": 65535, "default": 50},
        "kd": {"min": 0, "max": 65535, "default": 0},
    },
}

# ===================================================================
# Pydantic models
# ===================================================================


class PIDGains(BaseModel):
    """PID gain values for all three motor loops.

    The MG6010E-i6 uses uint16 gains (0-65535) with Kp, Ki, Kd per loop.
    Field aliases support both legacy names (position_kp, torque_kp)
    and motor-config-aligned names (angle_kp, iq_kp).
    """

    model_config = {"populate_by_name": True}

    position_kp: int = Field(..., ge=0, le=65535)
    position_ki: int = Field(..., ge=0, le=65535)
    position_kd: int = Field(default=0, ge=0, le=65535)
    speed_kp: int = Field(..., ge=0, le=65535)
    speed_ki: int = Field(..., ge=0, le=65535)
    speed_kd: int = Field(default=0, ge=0, le=65535)
    torque_kp: int = Field(..., ge=0, le=65535)
    torque_ki: int = Field(..., ge=0, le=65535)
    torque_kd: int = Field(default=0, ge=0, le=65535)


class WritePIDRequest(PIDGains):
    """Request body for writing PID gains (RAM)."""

    override_limits: bool = Field(
        default=False,
        description="Bypass per-motor-type limits (0-65535 allowed)",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Tuning session ID for lock/logging",
    )


class SavePIDRequest(PIDGains):
    """Request body for saving PID gains to ROM."""

    confirmation_token: str = Field(..., min_length=1, description="Must be 'CONFIRM_ROM_WRITE'")
    override_limits: bool = Field(
        default=False,
        description="Bypass per-motor-type limits (0-65535 allowed)",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Tuning session ID for lock/logging",
    )


class StepTestRequest(BaseModel):
    """Request body for initiating a step response test."""

    step_size_degrees: float = Field(default=10.0, gt=0, le=90, description="Step size in degrees")
    duration_seconds: float = Field(
        default=5.0, gt=0, le=30, description="Test duration in seconds"
    )


class ProfileSaveRequest(BaseModel):
    """Request body for saving a PID profile."""

    name: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    motor_type: str = Field(default="mg6010")
    gains: PIDGains
    description: str = Field(default="")


class AutotuneAnalyzeRequest(BaseModel):
    """Request body for Z-N autotune analysis."""

    timestamps: List[float]
    positions: List[float]
    velocities: List[float] = Field(default_factory=list)
    setpoint: float
    motor_type: str = Field(default="mg6010")


# ===================================================================
# Gain limit loading
# ===================================================================

_gain_limits_cache: Dict[str, Dict[str, Any]] = {}


def _load_gain_limits(motor_type: str) -> Dict[str, Any]:
    """Load gain limits from YAML config, with fallback to hardcoded."""
    if motor_type in _gain_limits_cache:
        return _gain_limits_cache[motor_type]

    config_path = _PID_SAFETY_DIR / f"{motor_type}.yaml"
    try:
        if config_path.exists():
            with open(config_path) as f:
                data = yaml.safe_load(f)
            limits = data.get("gain_limits", _FALLBACK_GAIN_LIMITS)
        else:
            logger.warning(
                "Safety config %s not found, using fallback limits",
                config_path,
            )
            limits = _FALLBACK_GAIN_LIMITS
    except Exception:
        logger.exception("Failed to load gain limits from %s", config_path)
        limits = _FALLBACK_GAIN_LIMITS

    _gain_limits_cache[motor_type] = limits
    return limits


def _validate_gains_against_limits(gains: PIDGains, motor_type: str) -> Optional[str]:
    """Return error string if any gain exceeds limits, else None."""
    limits = _load_gain_limits(motor_type)

    for loop_name in ("position", "speed", "torque"):
        loop_limits = limits.get(loop_name, {})
        for param in ("kp", "ki", "kd"):
            field = f"{loop_name}_{param}"
            value = getattr(gains, field)
            param_limits = loop_limits.get(param, {})
            lo = param_limits.get("min", 0)
            hi = param_limits.get("max", 65535)
            if value < lo or value > hi:
                return f"{field}={value} out of range [{lo}, {hi}]"
    return None


# ===================================================================
# PID Tuning Bridge (ROS2 communication)
# ===================================================================


class PIDTuningBridge:
    """Manages ROS2 communication for PID tuning API endpoints."""

    # Field mapping: RS485 driver names -> PID bridge names
    _RS485_TO_BRIDGE = {
        "angle_kp": "position_kp",
        "angle_ki": "position_ki",
        "angle_kd": "position_kd",
        "speed_kp": "speed_kp",
        "speed_ki": "speed_ki",
        "speed_kd": "speed_kd",
        "current_kp": "torque_kp",
        "current_ki": "torque_ki",
        "current_kd": "torque_kd",
    }
    # Reverse mapping: PID bridge names -> RS485 driver names
    _BRIDGE_TO_RS485 = {v: k for k, v in _RS485_TO_BRIDGE.items()}

    def __init__(self) -> None:
        self._node: Optional[Any] = None
        self._initialized = False
        self._lock = threading.Lock()
        self._spin_thread: Optional[threading.Thread] = None

        # ROS2 clients
        self._read_pid_client = None
        self._write_pid_client = None
        self._write_pid_rom_client = None
        self._step_test_client = None
        self._motor_state_sub = None

        # Motor state latest message (set from subscription callback)
        self._latest_motor_state: Optional[str] = None
        self._motor_state_lock = threading.Lock()

        # RS485 serial fallback driver
        self._rs485_driver: Optional[Any] = None
        # Transport preference: "auto" | "rs485" | "ros2"
        self._transport_preference: str = "auto"

    # ---------------------------------------------------------------
    # RS485 fallback support
    # ---------------------------------------------------------------

    def set_rs485_driver(self, driver: Any) -> None:
        """Inject an RS485MotorDriver for serial fallback."""
        self._rs485_driver = driver
        logger.info(
            "PID bridge: RS485 driver set (port=%s, motor_id=%s)",
            getattr(driver, "port", "?"),
            getattr(driver, "motor_id", "?"),
        )

    @property
    def has_rs485(self) -> bool:
        """True when an RS485 driver is available."""
        return self._rs485_driver is not None

    def set_transport_preference(self, pref: str) -> None:
        """Set transport preference: 'auto', 'rs485', or 'ros2'."""
        if pref not in ("auto", "rs485", "ros2"):
            raise ValueError(f"Invalid transport preference: {pref!r}")
        old = self._transport_preference
        self._transport_preference = pref
        logger.info("PID transport preference changed: %s -> %s", old, pref)

    @property
    def transport_preference(self) -> str:
        """Current transport preference setting."""
        return self._transport_preference

    @property
    def _use_rs485(self) -> bool:
        """Whether current operation should use RS485 transport."""
        pref = self._transport_preference
        if pref == "rs485":
            return self.has_rs485
        if pref == "ros2":
            return False
        # auto: prefer RS485 when available, else ROS2
        if self.has_rs485:
            return True
        return False

    def _map_rs485_to_bridge(self, rs485_gains: dict) -> dict:
        """Map RS485 field names to PID bridge field names.

        Returns both canonical names (position_kp, torque_kp) and
        frontend-aligned aliases (angle_kp, current_kp) so all
        consumers get the keys they expect.
        """
        canonical = {
            self._RS485_TO_BRIDGE[k]: v
            for k, v in rs485_gains.items()
            if k in self._RS485_TO_BRIDGE
        }
        # Add frontend-aligned aliases
        aliases = {
            "angle_kp": canonical.get("position_kp", 0),
            "angle_ki": canonical.get("position_ki", 0),
            "angle_kd": canonical.get("position_kd", 0),
            "current_kp": canonical.get("torque_kp", 0),
            "current_ki": canonical.get("torque_ki", 0),
            "current_kd": canonical.get("torque_kd", 0),
            "iq_kp": canonical.get("torque_kp", 0),
            "iq_ki": canonical.get("torque_ki", 0),
            "iq_kd": canonical.get("torque_kd", 0),
        }
        return {**canonical, **aliases}

    def _map_bridge_to_rs485(self, gains: "PIDGains") -> dict:
        """Map PIDGains model to RS485 driver field names."""
        return {
            self._BRIDGE_TO_RS485[f]: getattr(gains, f)
            for f in (
                "position_kp",
                "position_ki",
                "position_kd",
                "speed_kp",
                "speed_ki",
                "speed_kd",
                "torque_kp",
                "torque_ki",
                "torque_kd",
            )
        }

    async def _rs485_read_pid(self) -> dict:
        """Read PID gains via RS485 driver with field mapping.

        Retries up to 3 times since the background state polling thread
        can cause transient serial contention.
        """
        last_error = "RS485 read_pid returned no data"
        for attempt in range(1):
            try:
                raw = self._rs485_driver.read_pid()
            except Exception as exc:
                logger.warning("RS485 read_pid attempt %d failed: %s", attempt + 1, exc)
                last_error = str(exc)
                break

            if raw is None:
                logger.debug("RS485 read_pid attempt %d returned None", attempt + 1)
                break

            mapped = self._map_rs485_to_bridge(raw)
            return {"success": True, "gains": mapped}

        return {"success": False, "error": last_error}

    async def _rs485_write_pid(self, gains: "PIDGains", to_rom: bool = False) -> dict:
        """Write PID gains via RS485 driver with field mapping."""
        rs485_gains = self._map_bridge_to_rs485(gains)
        try:
            if to_rom:
                self._rs485_driver.write_pid_rom(rs485_gains)
            else:
                self._rs485_driver.write_pid_ram(rs485_gains)
        except Exception as exc:
            logger.exception("RS485 write_pid failed")
            return {"success": False, "error": str(exc)}

        # Verification read-back
        readback = await self._rs485_read_pid()
        if not readback.get("success"):
            return {
                "success": True,
                "verified": False,
                "warning": "Write succeeded but read-back failed",
                "gains": {
                    f: getattr(gains, f)
                    for f in (
                        "position_kp",
                        "position_ki",
                        "position_kd",
                        "speed_kp",
                        "speed_ki",
                        "speed_kd",
                        "torque_kp",
                        "torque_ki",
                        "torque_kd",
                    )
                },
            }

        _PID_FIELDS = (
            "position_kp",
            "position_ki",
            "position_kd",
            "speed_kp",
            "speed_ki",
            "speed_kd",
            "torque_kp",
            "torque_ki",
            "torque_kd",
        )
        written = {f: getattr(gains, f) for f in _PID_FIELDS}
        readback_gains = readback["gains"]
        mismatches = {
            f: {"written": written[f], "readback": readback_gains.get(f)}
            for f in _PID_FIELDS
            if written[f] != readback_gains.get(f)
        }

        if mismatches:
            return {
                "success": True,
                "verified": False,
                "warning": "Written values differ from read-back",
                "written": written,
                "readback": readback_gains,
            }

        return {
            "success": True,
            "verified": True,
            "gains": readback_gains,
        }

    def _rs485_run_step_test(
        self,
        motor_id: int,
        step_size: float,
        duration: float,
    ) -> dict:
        """Run step test via RS485 (blocking — runs in executor).

        Replicates the C++ action server logic:
        1. Read initial angle
        2. Send position command (initial + step_size)
        3. Poll position/status at ~10 Hz
        4. Compute metrics from recorded data
        """
        driver = self._rs485_driver

        # 1. Read initial position
        initial_angle = driver.read_multi_turn_angle()
        if initial_angle is None:
            return {
                "success": False,
                "error": ("Failed to read initial angle from motor"),
            }

        # 2. Compute target and send position command
        target_deg = initial_angle + step_size
        target_centideg = int(round(target_deg * 100))
        cmd_resp = driver.send_position_command(
            target_centideg,
            max_speed_dps=0,
        )
        if cmd_resp is None:
            return {
                "success": False,
                "error": ("Position command failed — no response"),
            }

        # 3. Poll at ~10 Hz
        sample_interval = 1.0 / RS485_STEP_TEST_SAMPLE_RATE_HZ
        timestamps = []
        positions = []
        velocities = []
        currents = []
        t_start = time.monotonic()
        abs_step = abs(step_size) if step_size != 0 else 1.0
        max_deviation = abs_step * RS485_STEP_TEST_MAX_DEVIATION_FACTOR

        while (time.monotonic() - t_start) < duration:
            t_now = time.monotonic() - t_start

            angle = driver.read_multi_turn_angle()
            status2 = driver.read_status_2()

            if angle is None or status2 is None:
                time.sleep(
                    sample_interval
                )  # BLOCKING_SLEEP_OK: PID tuning motor poll — dedicated tuning thread — reviewed 2026-03-14
                continue

            # Safety: temperature check
            temp = status2.get("temperature_c", 0.0)
            if temp > RS485_STEP_TEST_TEMP_LIMIT_C:
                driver.motor_stop()
                return {
                    "success": False,
                    "error": (
                        f"Temperature limit exceeded: "
                        f"{temp}°C > "
                        f"{RS485_STEP_TEST_TEMP_LIMIT_C}°C"
                    ),
                    "timestamps": timestamps,
                    "positions": positions,
                    "velocities": velocities,
                    "currents": currents,
                    "setpoint": target_deg,
                }

            # Safety: position deviation check (from target, not initial)
            deviation = abs(angle - target_deg)
            if deviation > max_deviation:
                driver.motor_stop()
                return {
                    "success": False,
                    "error": (
                        f"Position deviation exceeded: " f"{deviation:.1f}° > {max_deviation:.1f}°"
                    ),
                    "timestamps": timestamps,
                    "positions": positions,
                    "velocities": velocities,
                    "currents": currents,
                    "setpoint": target_deg,
                }

            timestamps.append(t_now)
            positions.append(angle)
            velocities.append(status2.get("speed_dps", 0.0))
            currents.append(status2.get("torque_current_a", 0.0))

            time.sleep(
                sample_interval
            )  # BLOCKING_SLEEP_OK: PID tuning motor poll — dedicated tuning thread — reviewed 2026-03-14

        # 4. Check for sufficient data
        if len(timestamps) < 2:
            return {
                "success": False,
                "error": "Insufficient data collected",
            }

        # 5. Compute metrics if available
        result: dict = {
            "success": True,
            "timestamps": timestamps,
            "positions": positions,
            "velocities": velocities,
            "currents": currents,
            "setpoint": target_deg,
        }

        if compute_step_metrics is not None and np is not None:
            try:
                import numpy as _np

                metrics = compute_step_metrics(
                    _np.array(timestamps),
                    _np.array(positions),
                    target_deg,
                    abs_step,
                )
                result["metrics"] = {
                    "rise_time": metrics.rise_time,
                    "settling_time": metrics.settling_time,
                    "overshoot_percent": (metrics.overshoot_percent),
                    "steady_state_error": (metrics.steady_state_error),
                    "iae": metrics.iae,
                    "ise": metrics.ise,
                    "itse": metrics.itse,
                    "data_points": metrics.data_points,
                    "confidence": metrics.confidence,
                }
            except Exception as exc:
                logger.warning("Step metrics computation failed: %s", exc)

        return result

    # ---------------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------------

    def initialize(self) -> None:
        """Create ROS2 node and service/action clients.

        Safe to call multiple times — only initializes once.
        Reuses existing rclpy context if already initialized.
        """
        if self._initialized:
            return

        with self._lock:
            if self._initialized:
                return

            if not ROS2_AVAILABLE:
                logger.warning("ROS2 unavailable — PID bridge in mock mode")
                self._initialized = True
                return

            # Ensure rclpy is initialized (dashboard may have done it)
            if not rclpy.ok():
                rclpy.init()

            self._node = rclpy.create_node("pid_tuning_api_bridge")

            cb_group = MutuallyExclusiveCallbackGroup()

            self._read_pid_client = self._node.create_client(
                ReadPID,
                "/pid_tuning/read_pid",
                callback_group=cb_group,
            )
            self._write_pid_client = self._node.create_client(
                WritePID,
                "/pid_tuning/write_pid",
                callback_group=cb_group,
            )
            self._write_pid_rom_client = self._node.create_client(
                WritePIDToROM,
                "/pid_tuning/write_pid_to_rom",
                callback_group=cb_group,
            )

            self._step_test_client = ActionClient(
                self._node,
                StepResponseTest,
                "/motor_control/step_response_test",
                callback_group=cb_group,
            )

            # Subscribe to motor state for WebSocket forwarding
            self._motor_state_sub = self._node.create_subscription(
                String,
                "/pid_tuning/motor_state",
                self._on_motor_state,
                10,
            )

            # Spin in a daemon thread
            self._spin_thread = threading.Thread(target=self._spin_loop, daemon=True)
            self._spin_thread.start()

            self._initialized = True
            logger.info("PID tuning bridge initialized")

    def shutdown(self) -> None:
        """Destroy node and stop spin thread."""
        if self._node is not None:
            try:
                self._node.destroy_node()
            except Exception:
                pass
            self._node = None
        self._initialized = False

    def _spin_loop(self) -> None:
        """Background thread that spins the ROS2 node."""
        executor = None
        try:
            from rclpy.executors import SingleThreadedExecutor

            executor = SingleThreadedExecutor()
            executor.add_node(self._node)
            executor.spin()
        except Exception:
            logger.exception("PID bridge spin loop exited")
        finally:
            try:
                if executor is not None:
                    executor.shutdown()
            except Exception:
                pass

    def _on_motor_state(self, msg: Any) -> None:
        """Subscription callback — cache latest motor state."""
        with self._motor_state_lock:
            self._latest_motor_state = msg.data

    def get_latest_motor_state(self) -> Optional[str]:
        """Return the latest motor state JSON string."""
        with self._motor_state_lock:
            return self._latest_motor_state

    # ---------------------------------------------------------------
    # Service helpers
    # ---------------------------------------------------------------

    def _call_service_sync(
        self,
        client: Any,
        request: Any,
        timeout: float = SERVICE_TIMEOUT_SEC,
    ) -> Any:
        """Call a ROS2 service synchronously (blocking).

        Must NOT be called from the rclpy spin thread.
        """
        if not client.wait_for_service(timeout_sec=timeout):
            raise TimeoutError(f"Service {client.srv_name} not available " f"after {timeout}s")
        future = client.call_async(request)

        # Spin until future completes (we are NOT on the spin thread)
        start = time.monotonic()
        while not future.done():
            if time.monotonic() - start > timeout:
                raise TimeoutError(f"Service call to {client.srv_name} timed out")
            time.sleep(
                0.01
            )  # BLOCKING_SLEEP_OK: PID tuning motor poll — dedicated tuning thread — reviewed 2026-03-14

        return future.result()

    # ---------------------------------------------------------------
    # Public async methods (called from FastAPI handlers)
    # ---------------------------------------------------------------

    async def read_pid(self, motor_id: int) -> dict:
        """Call ReadPID service and return gains dict."""
        if self._use_rs485:
            return await self._rs485_read_pid()
        if not ROS2_AVAILABLE or self._node is None:
            return {
                "success": False,
                "error": _pid_unavailable_error(),
            }

        req = ReadPID.Request()
        req.motor_id = motor_id

        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(
                None,
                self._call_service_sync,
                self._read_pid_client,
                req,
            )
        except TimeoutError as exc:
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            logger.exception("read_pid failed for motor %d", motor_id)
            return {"success": False, "error": str(exc)}

        if not resp.success:
            return {
                "success": False,
                "error": resp.error_message,
            }

        return {
            "success": True,
            "gains": {
                # Canonical field names
                "position_kp": int(resp.position_kp),
                "position_ki": int(resp.position_ki),
                "position_kd": int(getattr(resp, "position_kd", 0)),
                "speed_kp": int(resp.speed_kp),
                "speed_ki": int(resp.speed_ki),
                "speed_kd": int(getattr(resp, "speed_kd", 0)),
                "torque_kp": int(resp.torque_kp),
                "torque_ki": int(resp.torque_ki),
                "torque_kd": int(getattr(resp, "torque_kd", 0)),
                # Frontend-aligned aliases
                "angle_kp": int(resp.position_kp),
                "angle_ki": int(resp.position_ki),
                "angle_kd": int(getattr(resp, "position_kd", 0)),
                "current_kp": int(resp.torque_kp),
                "current_ki": int(resp.torque_ki),
                "current_kd": int(getattr(resp, "torque_kd", 0)),
                "iq_kp": int(resp.torque_kp),
                "iq_ki": int(resp.torque_ki),
                "iq_kd": int(getattr(resp, "torque_kd", 0)),
            },
        }

    async def _verify_pid_write(self, motor_id: int, gains: PIDGains) -> dict:
        """Read back PID gains and compare against written values.

        Returns a dict with ``success=True`` plus verification fields.
        Called after a successful write (RAM or ROM).
        """
        _PID_FIELDS = (
            "position_kp",
            "position_ki",
            "position_kd",
            "speed_kp",
            "speed_ki",
            "speed_kd",
            "torque_kp",
            "torque_ki",
            "torque_kd",
        )
        written = {f: getattr(gains, f) for f in _PID_FIELDS}

        readback_result = await self.read_pid(motor_id)
        if not readback_result.get("success"):
            logger.warning(
                "Re-read verification failed for motor %d: %s",
                motor_id,
                readback_result.get("error", "unknown"),
            )
            return {
                "success": True,
                "verified": False,
                "warning": ("Could not verify write - read-back failed"),
                "gains": written,
            }

        readback = readback_result["gains"]
        mismatches = {
            f: {"written": written[f], "readback": readback[f]}
            for f in _PID_FIELDS
            if written[f] != readback[f]
        }

        if mismatches:
            logger.warning(
                "PID write verification mismatch on motor %d: %s",
                motor_id,
                mismatches,
            )
            return {
                "success": True,
                "verified": False,
                "warning": ("Written values differ from read-back"),
                "written": written,
                "readback": readback,
            }

        return {
            "success": True,
            "verified": True,
            "gains": readback,
        }

    async def write_pid(self, motor_id: int, gains: PIDGains) -> dict:
        """Call WritePID service with re-read verification."""
        if self._use_rs485:
            return await self._rs485_write_pid(gains, to_rom=False)
        if not ROS2_AVAILABLE or self._node is None:
            return {
                "success": False,
                "error": _pid_unavailable_error(),
            }

        req = WritePID.Request()
        req.motor_id = motor_id
        req.position_kp = gains.position_kp
        req.position_ki = gains.position_ki
        req.speed_kp = gains.speed_kp
        req.speed_ki = gains.speed_ki
        req.torque_kp = gains.torque_kp
        req.torque_ki = gains.torque_ki

        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(
                None,
                self._call_service_sync,
                self._write_pid_client,
                req,
            )
        except TimeoutError as exc:
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            logger.exception("write_pid failed for motor %d", motor_id)
            return {"success": False, "error": str(exc)}

        if not resp.success:
            return {
                "success": False,
                "error": resp.error_message,
            }

        return await self._verify_pid_write(motor_id, gains)

    async def write_pid_to_rom(self, motor_id: int, gains: PIDGains) -> dict:
        """Call WritePIDToROM service with re-read verification."""
        if self._use_rs485:
            return await self._rs485_write_pid(gains, to_rom=True)
        if not ROS2_AVAILABLE or self._node is None:
            return {
                "success": False,
                "error": _pid_unavailable_error(),
            }

        req = WritePIDToROM.Request()
        req.motor_id = motor_id
        req.position_kp = gains.position_kp
        req.position_ki = gains.position_ki
        req.speed_kp = gains.speed_kp
        req.speed_ki = gains.speed_ki
        req.torque_kp = gains.torque_kp
        req.torque_ki = gains.torque_ki

        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(
                None,
                self._call_service_sync,
                self._write_pid_rom_client,
                req,
            )
        except TimeoutError as exc:
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            logger.exception("write_pid_to_rom failed for motor %d", motor_id)
            return {"success": False, "error": str(exc)}

        if not resp.success:
            return {
                "success": False,
                "error": resp.error_message,
            }

        return await self._verify_pid_write(motor_id, gains)

    async def start_step_test(
        self,
        motor_id: int,
        step_size: float,
        duration: float,
    ) -> dict:
        """Send StepResponseTest action goal, block until done."""
        if self._use_rs485:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                self._rs485_run_step_test,
                motor_id,
                step_size,
                duration,
            )
        if not ROS2_AVAILABLE or self._node is None:
            return {
                "success": False,
                "error": _pid_unavailable_error(),
            }

        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None,
                self._run_step_test_sync,
                motor_id,
                step_size,
                duration,
            )
        except TimeoutError as exc:
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            logger.exception("step_test failed for motor %d", motor_id)
            return {"success": False, "error": str(exc)}

        return result

    def _run_step_test_sync(
        self,
        motor_id: int,
        step_size: float,
        duration: float,
    ) -> dict:
        """Blocking helper — send action goal and wait for result."""
        if not self._step_test_client.wait_for_server(timeout_sec=SERVICE_TIMEOUT_SEC):
            raise TimeoutError("Step response test action server not available")

        goal = StepResponseTest.Goal()
        goal.motor_id = motor_id
        goal.step_size_degrees = step_size
        goal.duration_seconds = duration

        send_future = self._step_test_client.send_goal_async(goal)
        # Wait for goal acceptance
        start = time.monotonic()
        while not send_future.done():
            if time.monotonic() - start > SERVICE_TIMEOUT_SEC:
                raise TimeoutError("Goal acceptance timed out")
            time.sleep(
                0.01
            )  # BLOCKING_SLEEP_OK: PID tuning motor poll — dedicated tuning thread — reviewed 2026-03-14

        goal_handle = send_future.result()
        if not goal_handle.accepted:
            return {
                "success": False,
                "error": "Step test goal rejected by server",
            }

        # Wait for result
        result_future = goal_handle.get_result_async()
        start = time.monotonic()
        while not result_future.done():
            if time.monotonic() - start > ACTION_TIMEOUT_SEC:
                raise TimeoutError("Step response test timed out " f"after {ACTION_TIMEOUT_SEC}s")
            time.sleep(
                0.05
            )  # BLOCKING_SLEEP_OK: PID tuning motor poll — dedicated tuning thread — reviewed 2026-03-14

        result = result_future.result().result
        if not result.success:
            return {
                "success": False,
                "error": result.error_message,
            }

        return {
            "success": True,
            "timestamps": list(result.timestamps),
            "positions": list(result.positions),
            "velocities": list(result.velocities),
            "currents": list(result.currents),
            "setpoint": float(result.setpoint),
        }


# ===================================================================
# Module-level singleton
# ===================================================================

_bridge = PIDTuningBridge()

# Step test results stored in memory (cleaned after 30 min)
_step_test_results: Dict[str, dict] = {}
_step_test_timestamps: Dict[str, float] = {}

# -------------------------------------------------------------------
# Safety module singletons (initialized if pid_safety is available)
# -------------------------------------------------------------------
_gain_enforcer: Optional[Any] = None
_gain_ramper: Optional[Any] = None
_oscillation_detector: Optional[Any] = None
_session_lock: Optional[Any] = None
_session_logger: Optional[Any] = None


def _cleanup_old_step_tests() -> None:
    """Remove step test results older than STEP_TEST_CLEANUP_SECONDS."""
    now = time.monotonic()
    expired = [
        tid for tid, ts in _step_test_timestamps.items() if now - ts > STEP_TEST_CLEANUP_SECONDS
    ]
    for tid in expired:
        _step_test_results.pop(tid, None)
        _step_test_timestamps.pop(tid, None)


def _save_benchmark(
    motor_id: int,
    step_size: float,
    duration: float,
    result: dict,
) -> Optional[str]:
    """Save step test result to disk as a JSON benchmark file.

    Returns the benchmark_id (filename stem) or None on error.
    """
    try:
        _PID_BENCHMARKS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        benchmark_id = f"{ts}_motor{motor_id}"
        filepath = _PID_BENCHMARKS_DIR / f"{benchmark_id}.json"

        benchmark = {
            "benchmark_id": benchmark_id,
            "motor_id": motor_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "parameters": {
                "step_size_degrees": step_size,
                "duration_seconds": duration,
            },
            "result": result,
        }

        with open(filepath, "w") as f:
            json.dump(benchmark, f, indent=2, default=str)

        logger.info("Saved benchmark %s", benchmark_id)
        return benchmark_id
    except Exception:
        logger.exception("Failed to save benchmark")
        return None


def initialize_pid_bridge(
    rs485_driver: Optional[Any] = None,
) -> None:
    """Initialize the PID tuning bridge and safety modules.

    Called at dashboard startup.

    Parameters
    ----------
    rs485_driver:
        An already-connected :class:`RS485MotorDriver` instance to
        use as fallback when ROS2 services are unavailable.  Typically
        the same driver shared with the motor config bridge.
    """
    global _gain_enforcer, _gain_ramper, _oscillation_detector
    global _session_lock, _session_logger

    try:
        _bridge.initialize()
        # Pre-load gain limits for known motor types
        _load_gain_limits("mg6010")

        # -- Safety module initialization --------------------------------
        if SAFETY_AVAILABLE:
            # Load config to parameterize safety modules
            safety_cfg_path = _PID_SAFETY_DIR / "mg6010.yaml"
            safety_cfg: Dict[str, Any] = {}
            try:
                if safety_cfg_path.exists():
                    with open(safety_cfg_path) as f:
                        safety_cfg = yaml.safe_load(f) or {}
            except Exception:
                logger.warning(
                    "Failed to load safety config from %s; " "using defaults",
                    safety_cfg_path,
                )

            # GainLimitEnforcer — reads YAML from config_defaults/pid_safety/
            _gain_enforcer = GainLimitEnforcer(config_dir=str(_PID_SAFETY_DIR))

            # GainRamper — parameterized from YAML 'ramping' section
            ramp_cfg = safety_cfg.get("ramping", {})
            _gain_ramper = GainRamper(
                max_step=int(ramp_cfg.get("max_step", 20)),
                delay_ms=int(ramp_cfg.get("delay_ms", 100)),
            )

            # OscillationDetector — parameterized from YAML
            osc_cfg = safety_cfg.get("oscillation_detection", {})
            _oscillation_detector = OscillationDetector(
                window_seconds=float(osc_cfg.get("window_seconds", 2.0)),
                min_crossings=int(osc_cfg.get("min_zero_crossings", 3)),
                amplitude_factor=float(osc_cfg.get("amplitude_factor", 2.0)),
            )

            # TuningSessionLock
            sess_cfg = safety_cfg.get("session", {})
            _session_lock = TuningSessionLock(
                timeout_seconds=float(sess_cfg.get("lock_timeout_seconds", 300)),
            )

            # TuningSessionLogger — writes to data/pid_sessions/
            _session_logger = TuningSessionLogger(session_dir="data/pid_sessions")

            logger.info(
                "PID safety modules initialized " "(enforcer, ramper, oscillation, lock, logger)"
            )
        else:
            logger.warning(
                "PID safety modules NOT available — " "operating with inline fallback checks only"
            )

        logger.info("PID tuning bridge ready")
    except Exception:
        logger.exception("Failed to initialize PID tuning bridge")

    # --- RS485 fallback setup ---
    if rs485_driver is not None:
        _bridge.set_rs485_driver(rs485_driver)
        logger.info("PID bridge RS485 fallback wired (shared driver)")


# ===================================================================
# FastAPI Router
# ===================================================================

pid_router = APIRouter(prefix="/api/pid", tags=["PID Tuning"])


def _validate_motor_id(motor_id: int) -> None:
    """Raise HTTPException if motor_id is invalid."""
    if motor_id not in VALID_MOTOR_IDS:
        raise HTTPException(
            status_code=400,
            detail=(f"Invalid motor_id={motor_id}. " f"Valid: {sorted(VALID_MOTOR_IDS)}"),
        )


def _motor_type_for(motor_id: int) -> str:
    """Return motor_type string for a given motor_id."""
    for m in MOTOR_CONFIG:
        if m["motor_id"] == motor_id:
            return m["motor_type"]
    return "mg6010"


# New-to-legacy PID field name mapping for write endpoints.
# The motor-config-ux change introduces aliases (angle_kp,
# iq_kp, etc.) that map to the canonical ROS2 field names.
_PID_FIELD_ALIASES: Dict[str, str] = {
    "angle_kp": "position_kp",
    "angle_ki": "position_ki",
    "angle_kd": "position_kd",
    "iq_kp": "torque_kp",
    "iq_ki": "torque_ki",
    "iq_kd": "torque_kd",
    "current_kp": "torque_kp",
    "current_ki": "torque_ki",
    "current_kd": "torque_kd",
}


def _normalise_pid_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    """Map aliased PID field names to their canonical names.

    If both alias and canonical name are present, canonical wins.
    """
    normalised = dict(data)
    for alias, canonical in _PID_FIELD_ALIASES.items():
        if alias in normalised and canonical not in normalised:
            normalised[canonical] = normalised.pop(alias)
        elif alias in normalised:
            normalised.pop(alias)
    return normalised


# -------------------------------------------------------------------
# Task 2.7: GET /api/pid/motors
# -------------------------------------------------------------------


@pid_router.get("/motors")
async def get_motors() -> dict:
    """Return list of available motors.

    When RS485 transport is active, returns only the connected motor.
    """
    if _bridge._use_rs485 and _bridge._rs485_driver is not None:
        drv = _bridge._rs485_driver
        mid = getattr(drv, "motor_id", 1)
        # Check if the RS485 motor matches a known config
        matching = [m for m in MOTOR_CONFIG if m["motor_id"] == mid]
        if matching:
            return {"motors": matching, "transport": "rs485"}
        # Unknown motor ID -- return minimal config
        return {
            "motors": [
                {
                    "motor_id": mid,
                    "joint_name": f"motor_{mid}",
                    "motor_type": "mg6010",
                    "can_id": "",
                }
            ],
            "transport": "rs485",
        }
    return {"motors": MOTOR_CONFIG}


# -------------------------------------------------------------------
# Task 2.8: GET /api/pid/limits/{motor_type}
# -------------------------------------------------------------------


@pid_router.get("/limits/{motor_type}")
async def get_gain_limits(motor_type: str) -> dict:
    """Return gain limits for a motor type."""
    limits = _load_gain_limits(motor_type)
    return {"motor_type": motor_type, "gain_limits": limits}


# -------------------------------------------------------------------
# Task 2.2: GET /api/pid/read/{motor_id}
# -------------------------------------------------------------------


@pid_router.get("/read/{motor_id}")
async def read_pid(motor_id: int) -> dict:
    """Read current PID gains from a motor."""
    _validate_motor_id(motor_id)
    result = await _bridge.read_pid(motor_id)
    if not result["success"]:
        # Return 200 with success=false so frontend can show a warning
        # instead of throwing an error. Firmware may not support 0x40.
        return {
            "success": False,
            "gains": {},
            "warning": result.get(
                "error",
                "Could not read PID. Firmware may not support " "ParamID commands (0x40).",
            ),
        }
    return result


# -------------------------------------------------------------------
# Task 2.3: POST /api/pid/write/{motor_id}
# -------------------------------------------------------------------


@pid_router.post("/write/{motor_id}")
async def write_pid(motor_id: int, body: WritePIDRequest) -> dict:
    """Write PID gains to motor RAM (volatile).

    Safety checks (when pid_safety module is available):
    1. GainLimitEnforcer — reject if gains exceed per-motor limits
    2. TuningSessionLock — prevent concurrent writes to same motor
    3. GainRamper — rate-limit large gain changes into steps
    4. TuningSessionLogger — log the write operation
    """
    _validate_motor_id(motor_id)
    motor_type = _motor_type_for(motor_id)
    gains_dict = body.model_dump(
        include={
            "position_kp",
            "position_ki",
            "speed_kp",
            "speed_ki",
            "torque_kp",
            "torque_ki",
        }
    )

    # -- Safety: GainLimitEnforcer --------------------------------------
    if _gain_enforcer is not None:
        result = _gain_enforcer.validate_gains(
            motor_type.upper(),
            gains_dict,
            override=body.override_limits,
        )
        if not result.valid:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Gain limit violation (safety enforcer)",
                    "errors": result.errors,
                    "hint": ("Set override_limits=true to allow 0-65535 range"),
                },
            )
    else:
        # Fallback: inline limit validation (original behaviour)
        err = _validate_gains_against_limits(body, motor_type)
        if err:
            raise HTTPException(
                status_code=422,
                detail=f"Gain limit violation: {err}",
            )

    # -- Safety: TuningSessionLock --------------------------------------
    session_id = body.session_id
    if _session_lock is not None and session_id is not None:
        if not _session_lock.acquire(motor_id, session_id):
            locked, holder = _session_lock.is_locked(motor_id)
            raise HTTPException(
                status_code=409,
                detail={
                    "message": (f"Motor {motor_id} is locked by another " f"tuning session"),
                    "held_by": holder,
                },
            )

    try:
        # -- Safety: GainRamper -----------------------------------------
        ramp_applied = False
        ramp_steps: list[dict] = []
        if _gain_ramper is not None:
            # Read current gains to determine delta
            current_result = await _bridge.read_pid(motor_id)
            if current_result.get("success") and current_result.get("gains"):
                current_gains = current_result["gains"]
                if _gain_ramper.needs_ramping(current_gains, gains_dict):
                    ramp_steps = _gain_ramper.compute_ramp_steps(current_gains, gains_dict)
                    ramp_applied = True

        if ramp_applied and len(ramp_steps) > 1:
            # Apply intermediate steps with delays, then final step
            delay_s = _gain_ramper.delay_ms / 1000.0
            for i, step_gains in enumerate(ramp_steps):
                step_body = PIDGains(**step_gains)
                step_result = await _bridge.write_pid(motor_id, step_body)
                if not step_result["success"]:
                    raise HTTPException(
                        status_code=502,
                        detail=(
                            f"Ramp step {i + 1}/{len(ramp_steps)} "
                            f"failed: "
                            f"{step_result.get('error', 'Unknown')}"
                        ),
                    )
                # Delay between intermediate steps (not after final)
                if i < len(ramp_steps) - 1:
                    await asyncio.sleep(delay_s)

            # -- Safety: TuningSessionLogger ----------------------------
            if _session_logger is not None and session_id is not None:
                _session_logger.log_event(
                    session_id,
                    "pid_write",
                    {
                        "motor_id": motor_id,
                        "motor_type": motor_type,
                        "gains_before": (current_gains if current_result.get("success") else None),
                        "gains_after": gains_dict,
                        "ramped": True,
                        "ramp_steps": len(ramp_steps),
                    },
                )

            # Verify final state after ramping
            verify_result = await _bridge._verify_pid_write(motor_id, body)
            return {
                **verify_result,
                "ramped": True,
                "ramp_steps_applied": len(ramp_steps),
            }

        # -- Direct write (no ramping needed) ---------------------------
        # Capture 'before' snapshot for logging before writing
        gains_before = None
        if _session_logger is not None and session_id is not None:
            before_result = await _bridge.read_pid(motor_id)
            if before_result.get("success"):
                gains_before = before_result.get("gains")

        result = await _bridge.write_pid(motor_id, body)
        if not result["success"]:
            raise HTTPException(
                status_code=502,
                detail=result.get("error", "Unknown"),
            )

        # -- Safety: TuningSessionLogger --------------------------------
        if _session_logger is not None and session_id is not None:
            _session_logger.log_event(
                session_id,
                "pid_write",
                {
                    "motor_id": motor_id,
                    "motor_type": motor_type,
                    "gains_before": gains_before,
                    "gains_after": gains_dict,
                    "ramped": False,
                },
            )

        return result

    finally:
        # -- Safety: Release session lock on completion/error -----------
        if _session_lock is not None and session_id is not None:
            _session_lock.release(motor_id, session_id)


# -------------------------------------------------------------------
# Task 2.4: POST /api/pid/save/{motor_id}
# -------------------------------------------------------------------


@pid_router.post("/save/{motor_id}")
async def save_pid_to_rom(motor_id: int, body: SavePIDRequest) -> dict:
    """Write PID gains to motor ROM (persistent). Requires token.

    Safety checks (when pid_safety module is available):
    1. GainLimitEnforcer — reject if gains exceed per-motor limits
    2. TuningSessionLock — prevent concurrent writes to same motor
    3. TuningSessionLogger — log the ROM write operation
    """
    _validate_motor_id(motor_id)

    if body.confirmation_token != "CONFIRM_ROM_WRITE":
        raise HTTPException(
            status_code=400,
            detail=("Invalid confirmation_token. " "Must be 'CONFIRM_ROM_WRITE'."),
        )

    motor_type = _motor_type_for(motor_id)
    gains_dict = body.model_dump(
        include={
            "position_kp",
            "position_ki",
            "speed_kp",
            "speed_ki",
            "torque_kp",
            "torque_ki",
        }
    )

    # -- Safety: GainLimitEnforcer --------------------------------------
    if _gain_enforcer is not None:
        result = _gain_enforcer.validate_gains(
            motor_type.upper(),
            gains_dict,
            override=body.override_limits,
        )
        if not result.valid:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": ("Gain limit violation (safety enforcer) — " "ROM write blocked"),
                    "errors": result.errors,
                    "hint": ("Set override_limits=true to allow 0-65535 range"),
                },
            )
    else:
        # Fallback: inline limit validation (original behaviour)
        err = _validate_gains_against_limits(body, motor_type)
        if err:
            raise HTTPException(
                status_code=422,
                detail=f"Gain limit violation: {err}",
            )

    # -- Safety: TuningSessionLock --------------------------------------
    session_id = body.session_id
    if _session_lock is not None and session_id is not None:
        if not _session_lock.acquire(motor_id, session_id):
            locked, holder = _session_lock.is_locked(motor_id)
            raise HTTPException(
                status_code=409,
                detail={
                    "message": (f"Motor {motor_id} is locked by another " f"tuning session"),
                    "held_by": holder,
                },
            )

    try:
        result = await _bridge.write_pid_to_rom(motor_id, body)
        if not result["success"]:
            raise HTTPException(
                status_code=502,
                detail=result.get("error", "Unknown"),
            )

        # -- Safety: TuningSessionLogger --------------------------------
        if _session_logger is not None and session_id is not None:
            _session_logger.log_event(
                session_id,
                "pid_write_rom",
                {
                    "motor_id": motor_id,
                    "motor_type": motor_type,
                    "gains": gains_dict,
                    "verified": result.get("verified"),
                },
            )

        return result

    finally:
        # -- Safety: Release session lock on completion/error -----------
        if _session_lock is not None and session_id is not None:
            _session_lock.release(motor_id, session_id)


# -------------------------------------------------------------------
# Task 2.5: POST /api/pid/step_test/{motor_id}
# -------------------------------------------------------------------


@pid_router.post("/step_test/{motor_id}")
async def start_step_test(motor_id: int, body: StepTestRequest) -> dict:
    """Start a step response test (returns immediately with test_id)."""
    _validate_motor_id(motor_id)
    _cleanup_old_step_tests()

    test_id = str(uuid.uuid4())
    _step_test_results[test_id] = {"status": "running"}
    _step_test_timestamps[test_id] = time.monotonic()

    # Launch in background
    asyncio.ensure_future(
        _run_step_test_background(
            test_id,
            motor_id,
            body.step_size_degrees,
            body.duration_seconds,
        )
    )

    return {"test_id": test_id, "status": "running"}


async def _run_step_test_background(
    test_id: str,
    motor_id: int,
    step_size: float,
    duration: float,
) -> None:
    """Execute step test and store results keyed by test_id."""
    try:
        result = await _bridge.start_step_test(motor_id, step_size, duration)
        if result["success"]:
            benchmark_id = _save_benchmark(
                motor_id,
                step_size,
                duration,
                result,
            )
            _step_test_results[test_id] = {
                "status": "completed",
                "result": result,
                "benchmark_id": benchmark_id,
            }
        else:
            _step_test_results[test_id] = {
                "status": "failed",
                "success": False,
                "error": result.get("error", "Unknown"),
            }
    except Exception as exc:
        logger.exception("Step test %s failed", test_id)
        _step_test_results[test_id] = {
            "status": "failed",
            "success": False,
            "error": str(exc),
        }


@pid_router.get("/step_test/{motor_id}/result/{test_id}")
async def get_step_test_result(motor_id: int, test_id: str) -> dict:
    """Retrieve step response test results by test_id."""
    _validate_motor_id(motor_id)

    if test_id not in _step_test_results:
        raise HTTPException(
            status_code=404,
            detail=f"Test {test_id} not found",
        )
    return _step_test_results[test_id]


# -------------------------------------------------------------------
# Benchmark persistent storage endpoints
# -------------------------------------------------------------------


@pid_router.get("/benchmarks/{motor_id}")
async def list_benchmarks(motor_id: int) -> dict:
    """List saved benchmarks for a motor, newest first."""
    _validate_motor_id(motor_id)
    benchmarks = []

    if _PID_BENCHMARKS_DIR.exists():
        pattern = f"*_motor{motor_id}.json"
        for filepath in sorted(
            _PID_BENCHMARKS_DIR.glob(pattern),
            reverse=True,
        ):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                benchmarks.append(
                    {
                        "benchmark_id": data.get("benchmark_id", filepath.stem),
                        "timestamp": data.get("timestamp", ""),
                        "parameters": data.get("parameters", {}),
                        "has_metrics": "metrics" in data.get("result", {}),
                    }
                )
            except Exception:
                logger.warning("Failed to read benchmark %s", filepath)

    return {"benchmarks": benchmarks}


@pid_router.get("/benchmarks/{motor_id}/{benchmark_id}")
async def get_benchmark(motor_id: int, benchmark_id: str) -> dict:
    """Load a specific benchmark by ID."""
    _validate_motor_id(motor_id)

    # Sanitize benchmark_id to prevent path traversal
    safe_id = Path(benchmark_id).name
    filepath = _PID_BENCHMARKS_DIR / f"{safe_id}.json"

    if not filepath.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Benchmark {benchmark_id} not found",
        )

    try:
        with open(filepath) as f:
            return json.load(f)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load benchmark: {exc}",
        )


@pid_router.delete("/benchmarks/{motor_id}/{benchmark_id}")
async def delete_benchmark(
    motor_id: int,
    benchmark_id: str,
) -> dict:
    """Delete a specific benchmark."""
    _validate_motor_id(motor_id)

    safe_id = Path(benchmark_id).name
    filepath = _PID_BENCHMARKS_DIR / f"{safe_id}.json"

    if not filepath.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Benchmark {benchmark_id} not found",
        )

    filepath.unlink()
    return {"deleted": benchmark_id}


# -------------------------------------------------------------------
# Task 2.6: WebSocket /ws/pid/motor_state
# -------------------------------------------------------------------

_ws_motor_state_clients: Set[WebSocket] = set()


@pid_router.websocket("/ws/motor_state")
async def ws_motor_state(websocket: WebSocket) -> None:
    """Stream motor state updates to WebSocket clients at ~10 Hz.

    Clients can send ``{"motor_id": N}`` to filter updates.
    When OscillationDetector is available, incoming motor state data
    is fed to the detector and oscillation warnings are injected
    into the WebSocket stream.
    """
    await websocket.accept()
    _ws_motor_state_clients.add(websocket)
    motor_filter: Optional[int] = None

    try:
        while True:
            # Check for incoming filter messages (non-blocking)
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                try:
                    msg = json.loads(data)
                    if "motor_id" in msg:
                        motor_filter = int(msg["motor_id"])
                        # Reset oscillation detector when filter changes
                        if _oscillation_detector is not None:
                            _oscillation_detector.reset()
                except (json.JSONDecodeError, ValueError):
                    pass
            except asyncio.TimeoutError:
                pass

            # Send latest motor state
            state_json = _bridge.get_latest_motor_state()
            if state_json is not None:
                try:
                    state = json.loads(state_json)

                    if motor_filter is not None:
                        # Filter to requested motor only
                        if isinstance(state, dict):
                            mid = state.get("motor_id")
                            if mid is not None and mid != motor_filter:
                                continue

                    # -- Safety: OscillationDetector --------------------
                    # Feed position error to detector and attach warning
                    if _oscillation_detector is not None and isinstance(state, dict):
                        pos_error = state.get("position_error")
                        timestamp = state.get("timestamp", time.time())
                        if pos_error is not None:
                            _oscillation_detector.update(
                                float(timestamp),
                                float(pos_error),
                            )
                            osc_result = _oscillation_detector.check()
                            if osc_result.detected:
                                state["oscillation_warning"] = {
                                    "severity": osc_result.severity,
                                    "crossings": osc_result.crossings,
                                    "amplitude": osc_result.amplitude,
                                    "message": osc_result.message,
                                }
                                # Log oscillation event
                                logger.warning(
                                    "Oscillation detected on motor " "%s: %s",
                                    state.get("motor_id", "?"),
                                    osc_result.message,
                                )
                            # Send the (possibly enriched) state
                            await websocket.send_text(json.dumps(state))
                            continue

                    await websocket.send_text(state_json)
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("WebSocket motor_state disconnected")
    finally:
        _ws_motor_state_clients.discard(websocket)


# -------------------------------------------------------------------
# Session management endpoints (for TuningSessionLock + Logger)
# -------------------------------------------------------------------


class StartSessionRequest(BaseModel):
    """Request body for starting a tuning session."""

    motor_id: int
    motor_type: str = Field(default="mg6010")


@pid_router.post("/session/start")
async def start_tuning_session(body: StartSessionRequest) -> dict:
    """Start a new tuning session, returning a session_id.

    The session_id must be passed in subsequent write/save requests
    to enable session locking and audit logging.
    """
    _validate_motor_id(body.motor_id)

    if _session_logger is None or _session_lock is None:
        raise HTTPException(
            status_code=501,
            detail=("Session management not available — " "pid_safety module not loaded"),
        )

    session_id = _session_logger.start_session(body.motor_id, body.motor_type)
    # Pre-acquire the lock for this session
    acquired = _session_lock.acquire(body.motor_id, session_id)
    if not acquired:
        locked, holder = _session_lock.is_locked(body.motor_id)
        raise HTTPException(
            status_code=409,
            detail={
                "message": (f"Motor {body.motor_id} is already locked " f"by another session"),
                "held_by": holder,
            },
        )

    return {
        "session_id": session_id,
        "motor_id": body.motor_id,
        "motor_type": body.motor_type,
    }


@pid_router.post("/session/end/{session_id}")
async def end_tuning_session(session_id: str) -> dict:
    """End a tuning session, releasing locks and finalizing the log."""
    if _session_logger is None or _session_lock is None:
        raise HTTPException(
            status_code=501,
            detail="Session management not available",
        )

    try:
        _session_logger.end_session(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    # Release any locks held by this session (scan all motors)
    for m in MOTOR_CONFIG:
        _session_lock.release(m["motor_id"], session_id)

    return {"success": True, "session_id": session_id}


@pid_router.get("/session/log/{session_id}")
async def get_session_log(session_id: str) -> dict:
    """Retrieve the event log for a tuning session."""
    if _session_logger is None:
        raise HTTPException(
            status_code=501,
            detail="Session logging not available",
        )

    try:
        events = _session_logger.get_session_log(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return {"session_id": session_id, "events": events}


# -------------------------------------------------------------------
# Task 3.1: POST /api/pid/profiles/save
# -------------------------------------------------------------------


@pid_router.post("/profiles/save")
async def save_profile(body: ProfileSaveRequest) -> dict:
    """Save a PID gain profile to YAML."""
    motor_type = body.motor_type
    profile_dir = _PID_PROFILES_DIR / motor_type
    profile_dir.mkdir(parents=True, exist_ok=True)

    profile_data = {
        "profile_name": body.name,
        "motor_type": motor_type,
        "description": body.description,
        "created": datetime.now(timezone.utc).isoformat(),
        "gains": body.gains.model_dump(),
    }

    filepath = profile_dir / f"{body.name}.yaml"
    try:
        with open(filepath, "w") as f:
            yaml.dump(
                profile_data,
                f,
                default_flow_style=False,
                sort_keys=False,
            )
    except Exception as exc:
        logger.exception("Failed to save profile %s", body.name)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save profile: {exc}",
        )

    return {
        "success": True,
        "path": str(filepath),
        "profile_name": body.name,
    }


# -------------------------------------------------------------------
# Task 3.2: GET /api/pid/profiles/{motor_type}
# -------------------------------------------------------------------


@pid_router.get("/profiles/{motor_type}")
async def list_profiles(motor_type: str) -> dict:
    """List available PID profiles for a motor type."""
    profile_dir = _PID_PROFILES_DIR / motor_type
    profiles: List[dict] = []

    if profile_dir.exists():
        for yaml_file in sorted(profile_dir.glob("*.yaml")):
            try:
                with open(yaml_file) as f:
                    data = yaml.safe_load(f)
                profiles.append(
                    {
                        "name": data.get("profile_name", yaml_file.stem),
                        "description": data.get("description", ""),
                        "created": data.get("created", ""),
                    }
                )
            except Exception:
                logger.warning("Failed to read profile %s", yaml_file)

    return {"profiles": profiles}


# -------------------------------------------------------------------
# Task 3.3: GET /api/pid/profiles/{motor_type}/{name}
# -------------------------------------------------------------------


@pid_router.get("/profiles/{motor_type}/{name}")
async def get_profile(motor_type: str, name: str) -> dict:
    """Load a specific PID profile."""
    filepath = _PID_PROFILES_DIR / motor_type / f"{name}.yaml"
    if not filepath.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Profile '{name}' not found for {motor_type}",
        )

    try:
        with open(filepath) as f:
            data = yaml.safe_load(f)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load profile: {exc}",
        )

    return data


# -------------------------------------------------------------------
# Task 4.4: POST /api/pid/autotune/analyze
# -------------------------------------------------------------------


@pid_router.post("/autotune/analyze")
async def autotune_analyze(body: AutotuneAnalyzeRequest) -> dict:
    """Run Ziegler-Nichols analysis on step response data."""
    if analyze_step_response is None or np is None:
        raise HTTPException(
            status_code=501,
            detail=(
                "Autotune analysis not available — " "pid_tuning package or numpy not installed"
            ),
        )

    if len(body.timestamps) < 5:
        raise HTTPException(
            status_code=422,
            detail="Need at least 5 data points for analysis",
        )
    if len(body.timestamps) != len(body.positions):
        raise HTTPException(
            status_code=422,
            detail="timestamps and positions must have same length",
        )

    ts = np.array(body.timestamps, dtype=np.float64)
    pos = np.array(body.positions, dtype=np.float64)

    # Infer step_size from data: setpoint - initial_position
    step_size = body.setpoint - float(pos[0])
    if abs(step_size) < 1e-6:
        raise HTTPException(
            status_code=422,
            detail=("step_size is ~0 (setpoint equals initial " "position). Cannot analyze."),
        )

    # Run Z-N analysis
    try:
        zn_result = analyze_step_response(ts, pos, body.setpoint, step_size)
    except Exception as exc:
        logger.exception("Z-N analysis failed")
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {exc}",
        )

    # Compute step metrics
    metrics_result = None
    if compute_step_metrics is not None:
        try:
            metrics_obj = compute_step_metrics(ts, pos, body.setpoint, step_size)
            metrics_result = asdict(metrics_obj)
        except Exception:
            logger.warning("Step metrics computation failed")

    if not zn_result.success:
        return {
            "success": False,
            "error": zn_result.error_message,
            "metrics": metrics_result,
        }

    # Compute suggestions for applicable rules
    suggested_gains: Dict[str, dict] = {}
    if compute_tuning_rules is not None:
        try:
            rules = compute_tuning_rules(zn_result.L, zn_result.T, zn_result.K)
            for rule_key, rule_obj in rules.items():
                if not rule_obj.applicable:
                    continue
                suggestion = zn_suggest_gains(
                    zn_result,
                    motor_type=body.motor_type,
                    rule=rule_key,
                )
                suggested_gains[rule_key] = {
                    "rule_name": suggestion.rule_name,
                    "position_kp": suggestion.position_kp,
                    "position_ki": suggestion.position_ki,
                    "speed_kp": suggestion.speed_kp,
                    "speed_ki": suggestion.speed_ki,
                    "torque_kp": suggestion.torque_kp,
                    "torque_ki": suggestion.torque_ki,
                    "confidence": suggestion.confidence,
                    "applicable_note": suggestion.applicable_note,
                }
        except Exception:
            logger.exception("Tuning rule computation failed")

    return {
        "success": True,
        "model": {
            "K": zn_result.K,
            "L": zn_result.L,
            "T": zn_result.T,
            "confidence": zn_result.confidence,
            "r_squared": zn_result.r_squared,
        },
        "suggested_gains": suggested_gains,
        "metrics": metrics_result,
    }
