#!/usr/bin/env python3

"""Motor Configuration REST API and WebSocket endpoints for Pragati dashboard.

Provides FastAPI router with endpoints for:
- Sending motor commands (torque, speed, angle, increment)
- Motor lifecycle management (on, off, stop, reboot, save to ROM)
- Reading/writing motor limits (max torque current, acceleration)
- Encoder reading and zero-setting
- Motor angle reading (multi-turn, single-turn)
- Motor state reading and live streaming via WebSocket
- Error flag clearing
- Validation range metadata

The router communicates with the ``motor_config_service`` ROS2 node using
service clients and a subscription managed by :class:`MotorConfigBridge`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import threading
import time
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Body, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# ROS2 imports (optional -- allows mock mode)
# -------------------------------------------------------------------
try:
    import rclpy
    from rclpy.callback_groups import MutuallyExclusiveCallbackGroup

    from motor_control_msgs.srv import (
        ClearMotorErrors,
        MotorCommand,
        MotorLifecycle,
        ReadEncoder,
        ReadMotorAngles,
        ReadMotorLimits,
        ReadMotorState,
        WriteEncoderZero,
        WriteMotorLimits,
    )
    from std_msgs.msg import String

    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False
    logger.warning("ROS2 not available -- Motor config bridge runs in mock mode")

# -------------------------------------------------------------------
# RS485 imports (optional -- allows direct serial motor communication)
# -------------------------------------------------------------------
try:
    from backend.rs485_driver import (
        RS485MotorDriver,
        decode_error_flags_short,
        _lookup_motor_poles,
        _lookup_reduction_ratio,
    )

    RS485_AVAILABLE = True
except ImportError:
    RS485_AVAILABLE = False
    RS485MotorDriver = None  # type: ignore[assignment,misc]
    decode_error_flags_short = None  # type: ignore[assignment]
    logger.info("RS485 driver not available")

# ===================================================================
# Constants
# ===================================================================

# Motor configuration (from production.yaml -- same as pid_tuning_api)
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

# Error flag bit definitions
ERROR_FLAG_NAMES = {
    0: "undervoltage_protection",
    1: "overvoltage_protection",
    2: "drive_temperature_protection",
    3: "motor_temperature_protection",
    4: "overcurrent_protection",
    5: "short_circuit_protection",
    6: "stall_protection",
    7: "locked_rotor_protection",
}

# ===================================================================
# Pydantic request models
# ===================================================================


class MotorCommandRequest(BaseModel):
    """Request body for sending a motor command."""

    mode: int = Field(
        ...,
        ge=0,
        le=7,
        description=(
            "Control mode: 0=TORQUE, 1=SPEED, "
            "2=MULTI_ANGLE_1, 3=MULTI_ANGLE_2, "
            "4=SINGLE_ANGLE_1, 5=SINGLE_ANGLE_2, "
            "6=INCREMENT_1, 7=INCREMENT_2"
        ),
    )
    value: float = Field(
        ...,
        description=(
            "Command value: torque as raw iq (-2048..2048), "
            "speed in dps, angle in degrees (converted to cdeg internally)"
        ),
    )
    max_speed: float = Field(
        0.0,
        ge=0,
        description="Max speed for angle+speed commands (dps)",
    )
    direction: int = Field(
        0,
        ge=0,
        le=1,
        description="Direction for single-loop: 0=CW, 1=CCW",
    )


class MotorLifecycleRequest(BaseModel):
    """Request body for motor lifecycle operations."""

    action: int = Field(
        ...,
        ge=0,
        le=5,
        description=("Action: 0=ON, 1=OFF, 2=STOP, 3=REBOOT, " "4=SAVE_PID_ROM, 5=SAVE_ZERO_ROM"),
    )
    confirmation_token: Optional[str] = Field(
        None,
        description=("Required for SAVE_ZERO_ROM: 'CONFIRM_ENCODER_ZERO'"),
    )


class MaxTorqueCurrentRequest(BaseModel):
    """Request body for setting max torque current ratio."""

    value: int = Field(
        ...,
        ge=0,
        le=2000,
        description="Max torque current ratio (0-2000)",
    )


class AccelerationRequest(BaseModel):
    """Request body for setting acceleration."""

    value: float = Field(..., description="Acceleration in dps/s")


class EncoderZeroRequest(BaseModel):
    """Request body for setting encoder zero."""

    mode: int = Field(
        ...,
        ge=0,
        le=1,
        description="0=SET_VALUE, 1=SET_CURRENT_POS",
    )
    encoder_value: int = Field(
        0,
        ge=0,
        le=65535,
        description="Encoder value for SET_VALUE mode",
    )
    confirmation_token: str = Field(..., description="Must be 'CONFIRM_ENCODER_ZERO'")


# ===================================================================
# Pydantic response models
# ===================================================================


class MotorCommandResponse(BaseModel):
    """Response from a motor command."""

    success: bool
    temperature: int = 0
    torque_current: int = 0
    speed: int = 0
    encoder: int = 0
    error_message: str = ""


class MotorStateResponse(BaseModel):
    """Response from a motor state read."""

    success: bool
    temperature_c: float = 0.0
    voltage_v: float = 0.0
    torque_current_a: float = 0.0
    speed_dps: float = 0.0
    encoder_position: int = 0
    multi_turn_deg: float = 0.0
    single_turn_deg: float = 0.0
    phase_current_a: list = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    error_flags: dict = Field(default_factory=dict)
    error_message: str = ""


class EncoderResponse(BaseModel):
    """Response from an encoder read."""

    success: bool
    raw_value: int = 0
    offset: int = 0
    original_value: int = 0
    error_message: str = ""


class AnglesResponse(BaseModel):
    """Response from a motor angles read."""

    success: bool
    multi_turn_deg: float = 0.0
    single_turn_deg: float = 0.0
    error_message: str = ""


class LimitsResponse(BaseModel):
    """Response from a motor limits read."""

    success: bool
    max_torque_ratio: int = 0
    acceleration_dps: float = 0.0
    error_message: str = ""


# ===================================================================
# Helper functions
# ===================================================================


def _decode_error_flags(flags_byte: int) -> Dict[str, bool]:
    """Decode error flags byte into a named dict."""
    result: Dict[str, bool] = {}
    for bit, name in ERROR_FLAG_NAMES.items():
        result[name] = bool(flags_byte & (1 << bit))
    return result


def _validate_motor_id(motor_id: int) -> None:
    """Raise HTTPException if motor_id is invalid."""
    if motor_id not in VALID_MOTOR_IDS:
        raise HTTPException(
            status_code=400,
            detail=(f"Invalid motor_id={motor_id}. " f"Valid: {sorted(VALID_MOTOR_IDS)}"),
        )


# ===================================================================
# Motor Config Bridge (ROS2 communication)
# ===================================================================


class MotorConfigBridge:
    """Manages ROS2 communication for motor configuration API endpoints."""

    def __init__(self) -> None:
        self._node: Optional[Any] = None
        self._initialized = False
        self._lock = threading.Lock()
        self._spin_thread: Optional[threading.Thread] = None

        # ROS2 service clients
        self._motor_command_client = None
        self._motor_lifecycle_client = None
        self._read_motor_limits_client = None
        self._write_motor_limits_client = None
        self._read_encoder_client = None
        self._write_encoder_zero_client = None
        self._read_motor_angles_client = None
        self._clear_motor_errors_client = None
        self._read_motor_state_client = None

        # Subscription
        self._motor_state_sub = None

        # Motor state latest message (set from subscription callback)
        self._latest_motor_state: Optional[str] = None
        self._motor_state_lock = threading.Lock()

        # RS485 direct serial fallback
        self._rs485_driver: Optional[Any] = None
        self._rs485_poll_thread: Optional[threading.Thread] = None
        self._rs485_poll_stop = threading.Event()

        # Per-field cache of last-known good RS485 state to prevent
        # flickering when individual commands timeout.
        self._last_good_state: dict = {}

        # Track RS485 motor lifecycle state (set by lifecycle commands)
        # Maps motor_id -> state code (0=OFF, 1=RUNNING, 2=STOPPED, 4=UNKNOWN)
        self._rs485_lifecycle_state: dict = {}

        # Transport preference: "auto" | "rs485" | "ros2"
        # "auto" = RS485 preferred when available, else ROS2
        self._transport_preference: str = "auto"

    # ---------------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------------

    def initialize(self) -> None:
        """Create ROS2 node and service clients.

        Safe to call multiple times -- only initializes once.
        Reuses existing rclpy context if already initialized.
        """
        if self._initialized:
            return

        with self._lock:
            if self._initialized:
                return

            if not ROS2_AVAILABLE:
                logger.warning("ROS2 unavailable -- Motor config bridge in mock mode")
                self._initialized = True
                return

            # Ensure rclpy is initialized (dashboard may have done it)
            if not rclpy.ok():
                rclpy.init()

            self._node = rclpy.create_node("motor_config_api_bridge")

            cb_group = MutuallyExclusiveCallbackGroup()

            self._motor_command_client = self._node.create_client(
                MotorCommand,
                "/motor_config/motor_command",
                callback_group=cb_group,
            )
            self._motor_lifecycle_client = self._node.create_client(
                MotorLifecycle,
                "/motor_config/motor_lifecycle",
                callback_group=cb_group,
            )
            self._read_motor_limits_client = self._node.create_client(
                ReadMotorLimits,
                "/motor_config/read_motor_limits",
                callback_group=cb_group,
            )
            self._write_motor_limits_client = self._node.create_client(
                WriteMotorLimits,
                "/motor_config/write_motor_limits",
                callback_group=cb_group,
            )
            self._read_encoder_client = self._node.create_client(
                ReadEncoder,
                "/motor_config/read_encoder",
                callback_group=cb_group,
            )
            self._write_encoder_zero_client = self._node.create_client(
                WriteEncoderZero,
                "/motor_config/write_encoder_zero",
                callback_group=cb_group,
            )
            self._read_motor_angles_client = self._node.create_client(
                ReadMotorAngles,
                "/motor_config/read_motor_angles",
                callback_group=cb_group,
            )
            self._clear_motor_errors_client = self._node.create_client(
                ClearMotorErrors,
                "/motor_config/clear_motor_errors",
                callback_group=cb_group,
            )
            self._read_motor_state_client = self._node.create_client(
                ReadMotorState,
                "/motor_config/read_motor_state",
                callback_group=cb_group,
            )

            # Subscribe to motor state for WebSocket forwarding
            self._motor_state_sub = self._node.create_subscription(
                String,
                "/motor_config/motor_state",
                self._on_motor_state,
                10,
            )

            # Spin in a daemon thread
            self._spin_thread = threading.Thread(target=self._spin_loop, daemon=True)
            self._spin_thread.start()

            self._initialized = True
            logger.info("Motor config bridge initialized")

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
        try:
            rclpy.spin(self._node)
        except Exception:
            logger.exception("Motor config bridge spin loop exited")

    def _on_motor_state(self, msg: Any) -> None:
        """Subscription callback -- cache latest motor state."""
        with self._motor_state_lock:
            self._latest_motor_state = msg.data

    def get_latest_motor_state(self) -> Optional[str]:
        """Return the latest motor state JSON string."""
        with self._motor_state_lock:
            return self._latest_motor_state

    # ---------------------------------------------------------------
    # RS485 fallback support
    # ---------------------------------------------------------------

    def set_rs485_driver(self, driver: Any) -> None:
        """Inject an RS485MotorDriver for direct serial communication."""
        self._rs485_driver = driver
        logger.info(
            "RS485 driver set: port=%s motor_id=%d",
            getattr(driver, "port", "?"),
            getattr(driver, "motor_id", 0),
        )

    @property
    def has_rs485(self) -> bool:
        """Whether an RS485 driver is available and connected."""
        drv = self._rs485_driver
        if drv is None:
            return False
        ser = getattr(drv, "_serial", None)
        return ser is not None and getattr(ser, "is_open", False)

    @property
    def transport_mode(self) -> str:
        """Return current transport: 'ros2', 'rs485', or 'none'."""
        return self.active_transport

    def set_transport_preference(self, pref: str) -> None:
        """Set transport preference: 'auto', 'rs485', or 'ros2'."""
        if pref not in ("auto", "rs485", "ros2"):
            raise ValueError(f"Invalid transport preference: {pref!r}")
        old = self._transport_preference
        self._transport_preference = pref
        logger.info("Transport preference changed: %s -> %s", old, pref)

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

    @property
    def active_transport(self) -> str:
        """Return which transport is actually being used right now."""
        if self._use_rs485:
            return "rs485"
        if ROS2_AVAILABLE and self._node is not None:
            return "ros2"
        return "none"

    def _rs485_motor_id_check(self, motor_id: int) -> Optional[dict]:
        """Check motor_id vs RS485 driver — now a pass-through.

        The driver's motor_id is updated via the /connection endpoint,
        so API callers may legitimately use any valid ID (1-32).
        The frame builder in RS485Driver already uses self.motor_id.
        """
        return None

    def start_rs485_polling(self, interval: float = 0.1) -> None:
        """Start background thread that polls motor state via RS485."""
        if self._rs485_poll_thread is not None:
            return
        self._rs485_poll_stop.clear()
        self._rs485_poll_thread = threading.Thread(
            target=self._rs485_poll_loop,
            args=(interval,),
            daemon=True,
        )
        self._rs485_poll_thread.start()
        logger.info("RS485 state polling started (%.1f Hz)", 1.0 / interval)

    def stop_rs485_polling(self) -> None:
        """Stop the RS485 polling thread."""
        self._rs485_poll_stop.set()
        thread = self._rs485_poll_thread
        if thread is not None:
            thread.join(timeout=2.0)
        self._rs485_poll_thread = None
        logger.info("RS485 state polling stopped")

    def _rs485_poll_loop(self, interval: float) -> None:
        """Background loop: read motor state via RS485 and cache as JSON."""
        drv = self._rs485_driver
        if drv is None:
            return

        while not self._rs485_poll_stop.is_set():
            try:
                state = self._rs485_read_full_state(drv)
                if state is not None:
                    state_json = json.dumps(state)
                    with self._motor_state_lock:
                        self._latest_motor_state = state_json
            except Exception:
                logger.debug("RS485 poll error", exc_info=True)

            self._rs485_poll_stop.wait(interval)

    def _rs485_read_full_state(self, drv: Any) -> Optional[dict]:
        """Read full motor state from RS485 driver, return WS-format dict.

        Small sleeps between transactions yield the serial lock so that
        on-demand commands (PID read, motor command, etc.) can interleave.

        Uses ``_last_good_state`` to hold the last successful value for
        each field so that a single command timeout does not zero-out the
        UI (prevents flickering).
        """
        cache = self._last_good_state

        s1 = drv.read_status_1()
        time.sleep(
            0.01
        )  # BLOCKING_SLEEP_OK: RS485 status read timing — sync thread context — reviewed 2026-03-14
        s2 = drv.read_status_2()
        if s1 is None and s2 is None:
            # Total comms failure — return cached state if available
            return dict(cache) if cache else None

        time.sleep(
            0.01
        )  # BLOCKING_SLEEP_OK: RS485 status read timing — sync thread context — reviewed 2026-03-14
        s3 = drv.read_status_3()
        time.sleep(
            0.01
        )  # BLOCKING_SLEEP_OK: RS485 status read timing — sync thread context — reviewed 2026-03-14
        multi = drv.read_multi_turn_angle()
        single = drv.read_single_turn_angle()

        # Extract fields, falling back to last-known good values
        if s1 is not None:
            cache["temperature_c"] = s1.get("temperature_c", 0.0)
            cache["voltage_v"] = s1.get("voltage_v", 0.0)
            cache["_error_byte"] = s1.get("error_byte", 0)
        if s2 is not None:
            # s2 also reports temperature — prefer it when available
            cache["temperature_c"] = s2.get("temperature_c", cache.get("temperature_c", 0.0))
            cache["torque_current_a"] = s2.get("torque_current_a", 0.0)
            cache["speed_dps"] = s2.get("speed_dps", 0.0)
            cache["encoder_position"] = s2.get("encoder_position", 0)
        if s3 is not None:
            cache["phase_current_a"] = s3.get("phase_current_a", [0.0, 0.0, 0.0])
        if multi is not None:
            cache["multi_turn_deg"] = multi
        if single is not None:
            cache["single_turn_deg"] = single

        return {
            "motor_id": drv.motor_id,
            "temperature_c": cache.get("temperature_c", 0.0),
            "voltage_v": cache.get("voltage_v", 0.0),
            "torque_current_a": cache.get("torque_current_a", 0.0),
            "speed_dps": cache.get("speed_dps", 0.0),
            "encoder_position": cache.get("encoder_position", 0),
            "multi_turn_deg": cache.get("multi_turn_deg", 0.0),
            "single_turn_deg": cache.get("single_turn_deg", 0.0),
            "phase_current_a": cache.get("phase_current_a", [0.0, 0.0, 0.0]),
            "error_flags": decode_error_flags_short(cache.get("_error_byte", 0)),
            "motor_state": _MOTOR_STATE_NAMES.get(
                self._rs485_lifecycle_state.get(drv.motor_id, 4), "UNKNOWN"
            ),
            "transport": "rs485",
        }

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

        # Poll until future completes (we are NOT on the spin thread)
        start = time.monotonic()
        while not future.done():
            if time.monotonic() - start > timeout:
                raise TimeoutError(f"Service call to {client.srv_name} timed out")
            time.sleep(
                0.01
            )  # BLOCKING_SLEEP_OK: ROS2 service call poll — sync thread context — reviewed 2026-03-14

        return future.result()

    # ---------------------------------------------------------------
    # Public async methods (called from FastAPI handlers)
    # ---------------------------------------------------------------

    async def motor_command(
        self,
        motor_id: int,
        command_type: int,
        value: float,
        max_speed: float = 0.0,
        direction: int = 0,
    ) -> dict:
        """Call MotorCommand service, or fall back to RS485."""
        if self._use_rs485:
            return await self._rs485_motor_command(
                motor_id, command_type, value, max_speed, direction
            )
        if not ROS2_AVAILABLE or self._node is None:
            return {
                "success": False,
                "error": "ROS2 not available",
            }

        req = MotorCommand.Request()
        req.motor_id = motor_id
        req.command_type = command_type
        req.value = value
        req.max_speed = max_speed
        req.direction = direction

        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(
                None,
                self._call_service_sync,
                self._motor_command_client,
                req,
            )
        except TimeoutError as exc:
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            logger.exception("motor_command failed for motor %d", motor_id)
            return {"success": False, "error": str(exc)}

        return {
            "success": resp.success,
            "temperature": int(resp.temperature),
            "torque_current": int(resp.torque_current),
            "speed": int(resp.speed),
            "encoder": int(resp.encoder),
            "error_message": resp.error_message,
        }

    async def motor_lifecycle(self, motor_id: int, action: int) -> dict:
        """Call MotorLifecycle service, or fall back to RS485."""
        if self._use_rs485:
            return await self._rs485_motor_lifecycle(motor_id, action)
        if not ROS2_AVAILABLE or self._node is None:
            return {
                "success": False,
                "error": "ROS2 not available",
            }

        req = MotorLifecycle.Request()
        req.motor_id = motor_id
        req.action = action

        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(
                None,
                self._call_service_sync,
                self._motor_lifecycle_client,
                req,
            )
        except TimeoutError as exc:
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            logger.exception("motor_lifecycle failed for motor %d", motor_id)
            return {"success": False, "error": str(exc)}

        return {
            "success": resp.success,
            "motor_state": int(resp.motor_state),
            "error_message": resp.error_message,
        }

    async def read_motor_limits(self, motor_id: int) -> dict:
        """Call ReadMotorLimits service, or fall back to RS485."""
        if self._use_rs485:
            return await self._rs485_read_motor_limits(motor_id)
        if not ROS2_AVAILABLE or self._node is None:
            return {
                "success": False,
                "error": "ROS2 not available",
            }

        req = ReadMotorLimits.Request()
        req.motor_id = motor_id

        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(
                None,
                self._call_service_sync,
                self._read_motor_limits_client,
                req,
            )
        except TimeoutError as exc:
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            logger.exception("read_motor_limits failed for motor %d", motor_id)
            return {"success": False, "error": str(exc)}

        if not resp.success:
            return {
                "success": False,
                "error": resp.error_message,
            }

        # Convert acceleration from rad/s^2 to dps/s
        accel_dps = math.degrees(resp.acceleration)

        return {
            "success": True,
            "max_torque_ratio": int(resp.max_torque_ratio),
            "acceleration_dps": accel_dps,
            "error_message": "",
        }

    async def write_motor_limits(
        self,
        motor_id: int,
        max_torque_ratio: int = 0,
        acceleration_dps: float = 0.0,
        set_max_torque: bool = False,
        set_acceleration: bool = False,
    ) -> dict:
        """Call WriteMotorLimits service, or fall back to RS485."""
        if self._use_rs485:
            return await self._rs485_write_motor_limits(
                motor_id,
                max_torque_ratio,
                acceleration_dps,
                set_max_torque,
                set_acceleration,
            )
        if not ROS2_AVAILABLE or self._node is None:
            return {
                "success": False,
                "error": "ROS2 not available",
            }

        req = WriteMotorLimits.Request()
        req.motor_id = motor_id
        req.max_torque_ratio = max_torque_ratio
        # Convert acceleration from dps/s to rad/s^2 for ROS2 service
        req.acceleration = math.radians(acceleration_dps)
        req.set_max_torque = set_max_torque
        req.set_acceleration = set_acceleration

        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(
                None,
                self._call_service_sync,
                self._write_motor_limits_client,
                req,
            )
        except TimeoutError as exc:
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            logger.exception("write_motor_limits failed for motor %d", motor_id)
            return {"success": False, "error": str(exc)}

        return {
            "success": resp.success,
            "error_message": resp.error_message,
        }

    async def read_encoder(self, motor_id: int) -> dict:
        """Call ReadEncoder service, or fall back to RS485."""
        if self._use_rs485:
            return await self._rs485_read_encoder(motor_id)
        if not ROS2_AVAILABLE or self._node is None:
            return {
                "success": False,
                "error": "ROS2 not available",
            }

        req = ReadEncoder.Request()
        req.motor_id = motor_id

        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(
                None,
                self._call_service_sync,
                self._read_encoder_client,
                req,
            )
        except TimeoutError as exc:
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            logger.exception("read_encoder failed for motor %d", motor_id)
            return {"success": False, "error": str(exc)}

        if not resp.success:
            return {
                "success": False,
                "error": resp.error_message,
            }

        return {
            "success": True,
            "raw_value": int(resp.raw_value),
            "offset": int(resp.offset),
            "original_value": int(resp.original_value),
            "error_message": "",
        }

    async def write_encoder_zero(
        self,
        motor_id: int,
        mode: int,
        encoder_value: int = 0,
    ) -> dict:
        """Call WriteEncoderZero service, or fall back to RS485."""
        if self._use_rs485:
            return await self._rs485_write_encoder_zero(motor_id, mode, encoder_value)
        if not ROS2_AVAILABLE or self._node is None:
            return {
                "success": False,
                "error": "ROS2 not available",
            }

        req = WriteEncoderZero.Request()
        req.motor_id = motor_id
        req.mode = mode
        req.encoder_value = encoder_value

        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(
                None,
                self._call_service_sync,
                self._write_encoder_zero_client,
                req,
            )
        except TimeoutError as exc:
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            logger.exception("write_encoder_zero failed for motor %d", motor_id)
            return {"success": False, "error": str(exc)}

        return {
            "success": resp.success,
            "error_message": resp.error_message,
        }

    async def read_motor_angles(self, motor_id: int) -> dict:
        """Call ReadMotorAngles service, or fall back to RS485."""
        if self._use_rs485:
            return await self._rs485_read_motor_angles(motor_id)
        if not ROS2_AVAILABLE or self._node is None:
            return {
                "success": False,
                "error": "ROS2 not available",
            }

        req = ReadMotorAngles.Request()
        req.motor_id = motor_id

        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(
                None,
                self._call_service_sync,
                self._read_motor_angles_client,
                req,
            )
        except TimeoutError as exc:
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            logger.exception("read_motor_angles failed for motor %d", motor_id)
            return {"success": False, "error": str(exc)}

        if not resp.success:
            return {
                "success": False,
                "error": resp.error_message,
            }

        # Convert angles from radians to degrees for the API
        return {
            "success": True,
            "multi_turn_deg": math.degrees(resp.multi_turn_angle),
            "single_turn_deg": math.degrees(resp.single_turn_angle),
            "error_message": "",
        }

    async def clear_motor_errors(self, motor_id: int) -> dict:
        """Call ClearMotorErrors service, or fall back to RS485."""
        if self._use_rs485:
            return await self._rs485_clear_motor_errors(motor_id)
        if not ROS2_AVAILABLE or self._node is None:
            return {
                "success": False,
                "error": "ROS2 not available",
            }

        req = ClearMotorErrors.Request()
        req.motor_id = motor_id

        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(
                None,
                self._call_service_sync,
                self._clear_motor_errors_client,
                req,
            )
        except TimeoutError as exc:
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            logger.exception("clear_motor_errors failed for motor %d", motor_id)
            return {"success": False, "error": str(exc)}

        return {
            "success": resp.success,
            "error_flags_after": _decode_error_flags(resp.error_flags_after),
            "error_message": resp.error_message,
        }

    async def read_motor_state(self, motor_id: int) -> dict:
        """Call ReadMotorState service, or fall back to RS485."""
        if self._use_rs485:
            return await self._rs485_read_motor_state(motor_id)
        if not ROS2_AVAILABLE or self._node is None:
            return {
                "success": False,
                "error": "ROS2 not available",
            }

        req = ReadMotorState.Request()
        req.motor_id = motor_id

        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(
                None,
                self._call_service_sync,
                self._read_motor_state_client,
                req,
            )
        except TimeoutError as exc:
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            logger.exception("read_motor_state failed for motor %d", motor_id)
            return {"success": False, "error": str(exc)}

        if not resp.success:
            return {
                "success": False,
                "error": resp.error_message,
            }

        return {
            "success": True,
            "temperature_c": float(resp.temperature_c),
            "voltage_v": float(resp.voltage_v),
            "torque_current_a": float(resp.torque_current_a),
            "speed_dps": float(resp.speed_dps),
            "encoder_position": int(resp.encoder_position),
            "multi_turn_deg": float(resp.multi_turn_deg),
            "single_turn_deg": float(resp.single_turn_deg),
            "phase_current_a": [
                float(resp.phase_a),
                float(resp.phase_b),
                float(resp.phase_c),
            ],
            "error_flags": _decode_error_flags(resp.error_flags),
            "error_message": "",
        }

    # ---------------------------------------------------------------
    # RS485 fallback implementations
    # ---------------------------------------------------------------

    async def _rs485_motor_command(
        self,
        motor_id: int,
        command_type: int,
        value: float,
        max_speed: float,
        direction: int,
    ) -> dict:
        """Execute motor command via RS485 serial."""
        id_err = self._rs485_motor_id_check(motor_id)
        if id_err:
            return id_err

        drv = self._rs485_driver
        loop = asyncio.get_event_loop()

        try:
            if command_type == 0:
                # TORQUE: value is raw iq_control (-2048..2048)
                iq_raw = int(value)
                resp = await loop.run_in_executor(None, drv.send_torque_command, iq_raw)
            elif command_type == 1:
                # SPEED: value is in dps, driver expects 0.01 dps units
                speed_centideg = int(value * 100)
                resp = await loop.run_in_executor(None, drv.send_speed_command, speed_centideg)
            elif command_type == 2:
                # MULTI_ANGLE_1 (0xA3): angle only, no speed limit
                angle_centideg = int(value * 100)
                resp = await loop.run_in_executor(
                    None,
                    drv.send_position_command_no_speed,
                    angle_centideg,
                )
            elif command_type == 3:
                # MULTI_ANGLE_2 (0xA4): angle + speed limit
                angle_centideg = int(value * 100)
                max_speed_dps = int(max_speed) if max_speed else 0
                resp = await loop.run_in_executor(
                    None,
                    drv.send_position_command,
                    angle_centideg,
                    max_speed_dps,
                )
            elif command_type == 4:
                # SINGLE_ANGLE_1 (0xA5): angle + direction, no speed limit
                angle_centideg = int(value * 100)
                resp = await loop.run_in_executor(
                    None,
                    drv.send_single_loop_command_no_speed,
                    angle_centideg,
                    direction,
                )
            elif command_type == 5:
                # SINGLE_ANGLE_2 (0xA6): angle + direction + speed limit
                angle_centideg = int(value * 100)
                max_speed_dps = int(max_speed) if max_speed else 0
                resp = await loop.run_in_executor(
                    None,
                    drv.send_single_loop_command,
                    angle_centideg,
                    max_speed_dps,
                    direction,
                )
            elif command_type == 6:
                # INCREMENT_1 (0xA7): increment angle, no speed limit
                angle_centideg = int(value * 100)
                resp = await loop.run_in_executor(
                    None,
                    drv.send_increment_command_no_speed,
                    angle_centideg,
                )
            elif command_type == 7:
                # INCREMENT_2 (0xA8): increment angle + speed limit
                angle_centideg = int(value * 100)
                max_speed_dps = int(max_speed) if max_speed else 0
                resp = await loop.run_in_executor(
                    None,
                    drv.send_increment_command,
                    angle_centideg,
                    max_speed_dps,
                )
            else:
                return {
                    "success": False,
                    "error": f"Unknown command_type {command_type}",
                }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        if resp is None:
            return {
                "success": False,
                "error": "RS485 command got no response",
            }

        return {
            "success": True,
            "temperature": int(resp.get("temperature_c", 0)),
            "torque_current": int(resp.get("torque_current_a", 0)),
            "speed": int(resp.get("speed_dps", 0)),
            "encoder": int(resp.get("encoder_position", 0)),
            "error_message": "",
        }

    async def _rs485_motor_lifecycle(self, motor_id: int, action: int) -> dict:
        """Execute motor lifecycle command via RS485 serial."""
        id_err = self._rs485_motor_id_check(motor_id)
        if id_err:
            return id_err

        drv = self._rs485_driver
        loop = asyncio.get_event_loop()

        # action: 0=ON, 1=OFF, 2=STOP, 3=REBOOT, 4=SAVE_PID_ROM,
        #         5=SAVE_ZERO_ROM
        _ACTION_MAP = {
            0: drv.motor_on,
            1: drv.motor_off,
            2: drv.motor_stop,
        }

        func = _ACTION_MAP.get(action)
        if func is None:
            return {
                "success": False,
                "error": (
                    f"Lifecycle action {action} not supported " "via RS485 (only ON/OFF/STOP)"
                ),
                "error_message": (
                    f"Lifecycle action {action} not supported " "via RS485 (only ON/OFF/STOP)"
                ),
            }

        try:
            resp = await loop.run_in_executor(None, func)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        if resp is None:
            return {
                "success": False,
                "error": "RS485 lifecycle command got no response",
            }

        # Map action to motor state code
        state_map = {0: 1, 1: 0, 2: 2}  # ON->RUNNING, OFF->OFF, STOP->STOPPED
        new_state = state_map.get(action, 4)
        # Track lifecycle state so WebSocket poll includes it
        self._rs485_lifecycle_state[drv.motor_id] = new_state
        return {
            "success": True,
            "motor_state": new_state,
            "error_message": "",
        }

    async def _rs485_read_motor_limits(self, motor_id: int) -> dict:
        """Read motor limits via RS485 serial."""
        id_err = self._rs485_motor_id_check(motor_id)
        if id_err:
            return id_err

        drv = self._rs485_driver
        loop = asyncio.get_event_loop()

        try:
            max_torque = await loop.run_in_executor(None, drv.read_max_torque)
            accel = await loop.run_in_executor(None, drv.read_acceleration)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        if max_torque is None and accel is None:
            return {
                "success": False,
                "error": "RS485 read_motor_limits failed",
            }

        return {
            "success": True,
            "max_torque_ratio": int(max_torque) if max_torque is not None else 0,
            "acceleration_dps": float(accel) if accel is not None else 0.0,
            "error_message": "",
        }

    async def _rs485_write_motor_limits(
        self,
        motor_id: int,
        max_torque_ratio: int,
        acceleration_dps: float,
        set_max_torque: bool,
        set_acceleration: bool,
    ) -> dict:
        """Write motor limits via RS485 serial."""
        id_err = self._rs485_motor_id_check(motor_id)
        if id_err:
            return id_err

        drv = self._rs485_driver
        loop = asyncio.get_event_loop()

        try:
            if set_max_torque:
                resp = await loop.run_in_executor(None, drv.write_max_torque, max_torque_ratio)
                if resp is None:
                    return {
                        "success": False,
                        "error": "RS485 write_max_torque failed",
                    }
            if set_acceleration:
                resp = await loop.run_in_executor(
                    None, drv.write_acceleration, int(acceleration_dps)
                )
                if resp is None:
                    return {
                        "success": False,
                        "error": "RS485 write_acceleration failed",
                    }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        return {"success": True, "error_message": ""}

    async def _rs485_read_encoder(self, motor_id: int) -> dict:
        """Read encoder via RS485 serial."""
        id_err = self._rs485_motor_id_check(motor_id)
        if id_err:
            return id_err

        drv = self._rs485_driver
        loop = asyncio.get_event_loop()

        try:
            resp = await loop.run_in_executor(None, drv.read_encoder)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        if resp is None:
            return {
                "success": False,
                "error": "RS485 read_encoder failed",
            }

        return {
            "success": True,
            "raw_value": int(resp["raw_value"]),
            "offset": int(resp["offset"]),
            "original_value": int(resp["original_value"]),
            "error_message": "",
        }

    async def _rs485_write_encoder_zero(self, motor_id: int, mode: int, encoder_value: int) -> dict:
        """Write encoder zero via RS485 serial."""
        id_err = self._rs485_motor_id_check(motor_id)
        if id_err:
            return id_err

        drv = self._rs485_driver
        loop = asyncio.get_event_loop()

        try:
            # RS485 driver only supports set_encoder_zero (current pos)
            resp = await loop.run_in_executor(None, drv.set_encoder_zero)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        if resp is None:
            return {
                "success": False,
                "error": "RS485 set_encoder_zero failed",
            }

        return {"success": True, "error_message": ""}

    async def _rs485_read_motor_angles(self, motor_id: int) -> dict:
        """Read motor angles via RS485 serial."""
        id_err = self._rs485_motor_id_check(motor_id)
        if id_err:
            return id_err

        drv = self._rs485_driver
        loop = asyncio.get_event_loop()

        try:
            multi = await loop.run_in_executor(None, drv.read_multi_turn_angle)
            single = await loop.run_in_executor(None, drv.read_single_turn_angle)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        if multi is None and single is None:
            return {
                "success": False,
                "error": "RS485 read_motor_angles failed",
            }

        return {
            "success": True,
            "multi_turn_deg": float(multi) if multi is not None else 0.0,
            "single_turn_deg": float(single) if single is not None else 0.0,
            "error_message": "",
        }

    async def _rs485_clear_motor_errors(self, motor_id: int) -> dict:
        """Clear motor errors via RS485 serial."""
        id_err = self._rs485_motor_id_check(motor_id)
        if id_err:
            return id_err

        drv = self._rs485_driver
        loop = asyncio.get_event_loop()

        try:
            resp = await loop.run_in_executor(None, drv.clear_errors)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        if resp is None:
            return {
                "success": False,
                "error": "RS485 clear_errors failed",
            }

        error_byte = resp.get("error_byte", 0)
        return {
            "success": True,
            "error_flags_after": _decode_error_flags(error_byte),
            "error_message": "",
        }

    async def _rs485_read_motor_state(self, motor_id: int) -> dict:
        """Read comprehensive motor state via RS485 serial."""
        id_err = self._rs485_motor_id_check(motor_id)
        if id_err:
            return id_err

        drv = self._rs485_driver
        loop = asyncio.get_event_loop()

        try:
            s1 = await loop.run_in_executor(None, drv.read_status_1)
            s2 = await loop.run_in_executor(None, drv.read_status_2)
            s3 = await loop.run_in_executor(None, drv.read_status_3)
            multi = await loop.run_in_executor(None, drv.read_multi_turn_angle)
            single = await loop.run_in_executor(None, drv.read_single_turn_angle)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        if s1 is None and s2 is None:
            return {
                "success": False,
                "error": "RS485 read_motor_state failed",
            }

        temp = 0.0
        voltage = 0.0
        error_byte = 0
        if s1 is not None:
            temp = s1.get("temperature_c", 0.0)
            voltage = s1.get("voltage_v", 0.0)
            error_byte = s1.get("error_byte", 0)

        torque_current = 0.0
        speed = 0.0
        encoder_pos = 0
        if s2 is not None:
            temp = s2.get("temperature_c", temp)
            torque_current = s2.get("torque_current_a", 0.0)
            speed = s2.get("speed_dps", 0.0)
            encoder_pos = s2.get("encoder_position", 0)

        phase = [0.0, 0.0, 0.0]
        if s3 is not None:
            phase = s3.get("phase_current_a", [0.0, 0.0, 0.0])

        return {
            "success": True,
            "temperature_c": float(temp),
            "voltage_v": float(voltage),
            "torque_current_a": float(torque_current),
            "speed_dps": float(speed),
            "encoder_position": int(encoder_pos),
            "multi_turn_deg": float(multi) if multi is not None else 0.0,
            "single_turn_deg": float(single) if single is not None else 0.0,
            "phase_current_a": phase,
            "error_flags": _decode_error_flags(error_byte),
            "error_message": "",
        }


_bridge = MotorConfigBridge()


def initialize_motor_bridge(
    serial_port: Optional[str] = None,
    motor_id: Optional[int] = None,
) -> None:
    """Initialize the motor config bridge.

    Called at dashboard startup.  When *serial_port* is provided the bridge
    will create an :class:`RS485MotorDriver`, connect to the motor, and
    start background state polling so the WebSocket feeds live data even
    when ROS2 is not running.

    Parameters
    ----------
    serial_port:
        Serial device path (e.g. ``/dev/ttyUSB0``).  ``None`` disables RS485.
    motor_id:
        Motor ID on the RS485 bus (default ``1`` if omitted but serial_port
        is given).
    """
    try:
        _bridge.initialize()
        logger.info("Motor config bridge ready")
    except Exception:
        logger.exception("Failed to initialize motor config bridge")

    # --- RS485 fallback setup ---
    if serial_port and RS485_AVAILABLE:
        mid = motor_id if motor_id is not None else 1
        try:
            drv = RS485MotorDriver(port=serial_port, motor_id=mid)
            if drv.connect():
                _bridge.set_rs485_driver(drv)
                # NOTE: polling is NOT auto-started — the frontend
                # requests it via POST /api/motor/polling/start when
                # the user navigates to a tab that needs live data
                # (Test, PID Tuning).  This avoids continuous serial
                # traffic when viewing static tabs (Setting, Encoder,
                # Product).
                logger.info(
                    "RS485 fallback active (polling paused): port=%s motor_id=%d",
                    serial_port,
                    mid,
                )
            else:
                logger.warning("RS485 connect failed on %s", serial_port)
        except Exception:
            logger.exception("RS485 driver init failed for %s", serial_port)


# ===================================================================
# FastAPI Router
# ===================================================================

motor_router = APIRouter(prefix="/api/motor", tags=["Motor Config"])


# -------------------------------------------------------------------
# Task 5.12: GET /api/motor/validation_ranges
# -------------------------------------------------------------------


@motor_router.get("/validation_ranges")
async def get_validation_ranges() -> dict:
    """Return validation ranges for all motor command fields per motor type."""
    return {
        "mg6010": {
            "torque_current": {
                "min": -2000,
                "max": 2000,
                "unit": "mA",
            },
            "speed": {
                "min": -3600,
                "max": 3600,
                "unit": "dps",
            },
            "angle": {
                "min": -36000,
                "max": 36000,
                "unit": "degrees",
            },
            "max_speed": {
                "min": 0,
                "max": 3600,
                "unit": "dps",
            },
            "max_torque_current": {
                "min": 0,
                "max": 2000,
                "unit": "ratio",
            },
            "acceleration": {
                "min": 1,
                "max": 65535,
                "unit": "dps/s",
            },
            "encoder": {
                "min": 0,
                "max": 65535,
                "unit": "raw",
            },
            "pid_gains": {
                "min": 0,
                "max": 65535,
                "unit": "byte",
            },
        }
    }


# -------------------------------------------------------------------
# Task 5.3: POST /api/motor/{motor_id}/command
# -------------------------------------------------------------------


@motor_router.post(
    "/{motor_id}/command",
    response_model=MotorCommandResponse,
)
async def motor_command(motor_id: int, body: MotorCommandRequest) -> MotorCommandResponse:
    """Send a motor command (torque, speed, angle, or increment)."""
    _validate_motor_id(motor_id)

    # For angle-based commands (modes 2-7), the value is in degrees
    # from the API but the ROS2 service also expects degrees per the
    # .srv definition, so no conversion needed for the value itself.
    # max_speed is in dps and the service also expects dps.
    result = await _bridge.motor_command(
        motor_id=motor_id,
        command_type=body.mode,
        value=body.value,
        max_speed=body.max_speed,
        direction=body.direction,
    )

    if not result.get("success", False):
        error_msg = result.get("error", "Unknown error")
        if "timed out" in error_msg or "not available" in error_msg:
            raise HTTPException(status_code=504, detail=error_msg)
        raise HTTPException(status_code=502, detail=error_msg)

    return MotorCommandResponse(
        success=True,
        temperature=result.get("temperature", 0),
        torque_current=result.get("torque_current", 0),
        speed=result.get("speed", 0),
        encoder=result.get("encoder", 0),
        error_message="",
    )


# -------------------------------------------------------------------
# Task 5.4: POST /api/motor/{motor_id}/lifecycle
# -------------------------------------------------------------------

# Motor state name mapping for the response
_MOTOR_STATE_NAMES = {
    0: "OFF",
    1: "RUNNING",
    2: "STOPPED",
    3: "ERROR",
    4: "UNKNOWN",
}


@motor_router.post("/{motor_id}/lifecycle")
async def motor_lifecycle(motor_id: int, body: MotorLifecycleRequest) -> dict:
    """Control motor lifecycle (on, off, stop, reboot, save to ROM)."""
    _validate_motor_id(motor_id)

    # SAVE_ZERO_ROM requires confirmation token
    if body.action == 5:
        if body.confirmation_token != "CONFIRM_ENCODER_ZERO":
            raise HTTPException(
                status_code=400,
                detail=("SAVE_ZERO_ROM requires " "confirmation_token='CONFIRM_ENCODER_ZERO'"),
            )

    result = await _bridge.motor_lifecycle(motor_id=motor_id, action=body.action)

    if not result.get("success", False):
        error_msg = result.get("error_message", result.get("error", "Unknown error"))
        if "timed out" in error_msg or "not available" in error_msg:
            raise HTTPException(status_code=504, detail=error_msg)
        raise HTTPException(status_code=502, detail=error_msg)

    motor_state_code = result.get("motor_state", 4)
    return {
        "success": True,
        "motor_state": motor_state_code,
        "motor_state_name": _MOTOR_STATE_NAMES.get(motor_state_code, "UNKNOWN"),
    }


# -------------------------------------------------------------------
# Task 5.5: GET/PUT limits
# -------------------------------------------------------------------


@motor_router.get("/{motor_id}/limits", response_model=LimitsResponse)
async def read_motor_limits(
    motor_id: int,
) -> LimitsResponse:
    """Read current motor limits (max torque, acceleration)."""
    _validate_motor_id(motor_id)

    result = await _bridge.read_motor_limits(motor_id)

    if not result.get("success", False):
        error_msg = result.get("error", "Unknown error")
        # Return 200 with success=false so frontend doesn't see a hard error.
        # RS485 firmware may not support 0x40 ParamID commands for limits.
        return LimitsResponse(
            success=False,
            error_message=error_msg,
        )

    return LimitsResponse(
        success=True,
        max_torque_ratio=result.get("max_torque_ratio", 0),
        acceleration_dps=result.get("acceleration_dps", 0.0),
    )


@motor_router.put("/{motor_id}/limits/max_torque_current")
async def write_max_torque_current(motor_id: int, body: MaxTorqueCurrentRequest) -> dict:
    """Set the max torque current ratio (0-2000)."""
    _validate_motor_id(motor_id)

    result = await _bridge.write_motor_limits(
        motor_id=motor_id,
        max_torque_ratio=body.value,
        set_max_torque=True,
    )

    if not result.get("success", False):
        error_msg = result.get("error_message", result.get("error", "Unknown error"))
        if "timed out" in error_msg or "not available" in error_msg:
            raise HTTPException(status_code=504, detail=error_msg)
        raise HTTPException(status_code=502, detail=error_msg)

    return {"success": True, "max_torque_ratio": body.value}


@motor_router.put("/{motor_id}/limits/acceleration")
async def write_acceleration(motor_id: int, body: AccelerationRequest) -> dict:
    """Set the motor acceleration (dps/s)."""
    _validate_motor_id(motor_id)

    result = await _bridge.write_motor_limits(
        motor_id=motor_id,
        acceleration_dps=body.value,
        set_acceleration=True,
    )

    if not result.get("success", False):
        error_msg = result.get("error_message", result.get("error", "Unknown error"))
        if "timed out" in error_msg or "not available" in error_msg:
            raise HTTPException(status_code=504, detail=error_msg)
        raise HTTPException(status_code=502, detail=error_msg)

    return {"success": True, "acceleration_dps": body.value}


# -------------------------------------------------------------------
# Task 5.6: GET/POST encoder
# -------------------------------------------------------------------


@motor_router.get("/{motor_id}/encoder", response_model=EncoderResponse)
async def read_encoder(motor_id: int) -> EncoderResponse:
    """Read current encoder values."""
    _validate_motor_id(motor_id)

    result = await _bridge.read_encoder(motor_id)

    if not result.get("success", False):
        error_msg = result.get("error", "Unknown error")
        if "timed out" in error_msg or "not available" in error_msg:
            raise HTTPException(status_code=504, detail=error_msg)
        raise HTTPException(status_code=502, detail=error_msg)

    return EncoderResponse(
        success=True,
        raw_value=result.get("raw_value", 0),
        offset=result.get("offset", 0),
        original_value=result.get("original_value", 0),
    )


@motor_router.post("/{motor_id}/encoder/zero")
async def write_encoder_zero(motor_id: int, body: EncoderZeroRequest) -> dict:
    """Set encoder zero position. Requires confirmation token."""
    _validate_motor_id(motor_id)

    if body.confirmation_token != "CONFIRM_ENCODER_ZERO":
        raise HTTPException(
            status_code=400,
            detail=("Invalid confirmation_token. " "Must be 'CONFIRM_ENCODER_ZERO'."),
        )

    result = await _bridge.write_encoder_zero(
        motor_id=motor_id,
        mode=body.mode,
        encoder_value=body.encoder_value,
    )

    if not result.get("success", False):
        error_msg = result.get("error_message", result.get("error", "Unknown error"))
        if "timed out" in error_msg or "not available" in error_msg:
            raise HTTPException(status_code=504, detail=error_msg)
        raise HTTPException(status_code=502, detail=error_msg)

    return {"success": True, "mode": body.mode}


# -------------------------------------------------------------------
# Task 5.7: GET angles and state
# -------------------------------------------------------------------


@motor_router.get("/{motor_id}/angles", response_model=AnglesResponse)
async def read_motor_angles(motor_id: int) -> AnglesResponse:
    """Read multi-turn and single-turn motor angles (in degrees)."""
    _validate_motor_id(motor_id)

    result = await _bridge.read_motor_angles(motor_id)

    if not result.get("success", False):
        error_msg = result.get("error", "Unknown error")
        if "timed out" in error_msg or "not available" in error_msg:
            raise HTTPException(status_code=504, detail=error_msg)
        raise HTTPException(status_code=502, detail=error_msg)

    return AnglesResponse(
        success=True,
        multi_turn_deg=result.get("multi_turn_deg", 0.0),
        single_turn_deg=result.get("single_turn_deg", 0.0),
    )


@motor_router.get("/{motor_id}/angle/multi_turn")
async def read_multi_turn_angle(motor_id: int) -> dict:
    """Read multi-turn angle only (cmd 0x92)."""
    _validate_motor_id(motor_id)

    drv = _bridge._rs485_driver
    if drv is None:
        raise HTTPException(status_code=503, detail="RS485 driver not available")

    id_err = _bridge._rs485_motor_id_check(motor_id)
    if id_err:
        raise HTTPException(status_code=400, detail=id_err["error"])

    loop = asyncio.get_event_loop()
    try:
        deg = await loop.run_in_executor(None, drv.read_multi_turn_angle)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if deg is None:
        raise HTTPException(status_code=502, detail="Read multi-turn angle failed")

    return {"success": True, "multi_turn_deg": deg}


@motor_router.get("/{motor_id}/angle/single_turn")
async def read_single_turn_angle(motor_id: int) -> dict:
    """Read single-turn angle only (cmd 0x94)."""
    _validate_motor_id(motor_id)

    drv = _bridge._rs485_driver
    if drv is None:
        raise HTTPException(status_code=503, detail="RS485 driver not available")

    id_err = _bridge._rs485_motor_id_check(motor_id)
    if id_err:
        raise HTTPException(status_code=400, detail=id_err["error"])

    loop = asyncio.get_event_loop()
    try:
        deg = await loop.run_in_executor(None, drv.read_single_turn_angle)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if deg is None:
        raise HTTPException(status_code=502, detail="Read single-turn angle failed")

    return {"success": True, "single_turn_deg": deg}


@motor_router.get("/{motor_id}/state", response_model=MotorStateResponse)
async def read_motor_state(
    motor_id: int,
) -> MotorStateResponse:
    """Read comprehensive motor state."""
    _validate_motor_id(motor_id)

    result = await _bridge.read_motor_state(motor_id)

    if not result.get("success", False):
        error_msg = result.get("error", "Unknown error")
        if "timed out" in error_msg or "not available" in error_msg:
            raise HTTPException(status_code=504, detail=error_msg)
        raise HTTPException(status_code=502, detail=error_msg)

    return MotorStateResponse(
        success=True,
        temperature_c=result.get("temperature_c", 0.0),
        voltage_v=result.get("voltage_v", 0.0),
        torque_current_a=result.get("torque_current_a", 0.0),
        speed_dps=result.get("speed_dps", 0.0),
        encoder_position=result.get("encoder_position", 0),
        multi_turn_deg=result.get("multi_turn_deg", 0.0),
        single_turn_deg=result.get("single_turn_deg", 0.0),
        phase_current_a=result.get("phase_current_a", [0.0, 0.0, 0.0]),
        error_flags=result.get("error_flags", {}),
    )


# -------------------------------------------------------------------
# Task 5.8: POST errors/clear
# -------------------------------------------------------------------


@motor_router.post("/{motor_id}/errors/clear")
async def clear_motor_errors(motor_id: int) -> dict:
    """Clear motor error flags."""
    _validate_motor_id(motor_id)

    result = await _bridge.clear_motor_errors(motor_id)

    if not result.get("success", False):
        error_msg = result.get("error_message", result.get("error", "Unknown error"))
        if "timed out" in error_msg or "not available" in error_msg:
            raise HTTPException(status_code=504, detail=error_msg)
        raise HTTPException(status_code=502, detail=error_msg)

    return {
        "success": True,
        "error_flags_after": result.get("error_flags_after", {}),
    }


# -------------------------------------------------------------------
# Transport preference GET/PUT
# -------------------------------------------------------------------


@motor_router.get("/transport")
async def get_transport() -> dict:
    """Return current transport mode and preference."""
    return {
        "preference": _bridge.transport_preference,
        "active": _bridge.active_transport,
        "rs485_available": _bridge.has_rs485,
        "ros2_available": ROS2_AVAILABLE and _bridge._node is not None,
    }


@motor_router.put("/transport")
async def set_transport(body: dict) -> dict:
    """Set transport preference: 'auto', 'rs485', or 'ros2'."""
    pref = body.get("preference")
    if pref not in ("auto", "rs485", "ros2"):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid preference: {pref!r}. Must be 'auto', 'rs485', or 'ros2'.",
        )
    _bridge.set_transport_preference(pref)
    # Also update PID bridge if available
    try:
        from backend.pid_tuning_api import _bridge as _pid_bridge

        _pid_bridge.set_transport_preference(pref)
    except Exception:
        pass
    return {
        "preference": _bridge.transport_preference,
        "active": _bridge.active_transport,
    }


# -------------------------------------------------------------------
# Connection management: GET/PUT motor ID, connect/disconnect
# -------------------------------------------------------------------


@motor_router.get("/serial_ports")
async def list_serial_ports() -> dict:
    """List available serial ports on the system.

    Returns a list of {port, description, hwid} for each detected port,
    sorted with /dev/ttyUSB* first (most likely RS485 adapters).
    """
    try:
        from serial.tools.list_ports import comports

        ports = []
        for p in sorted(comports(), key=lambda x: x.device):
            ports.append(
                {
                    "port": p.device,
                    "description": p.description or "",
                    "hwid": p.hwid or "",
                }
            )

        # Sort: ttyUSB first, then ttyACM, then others
        def _sort_key(entry):
            d = entry["port"]
            if "/ttyUSB" in d:
                return (0, d)
            if "/ttyACM" in d:
                return (1, d)
            return (2, d)

        ports.sort(key=_sort_key)
        return {"ports": ports}
    except ImportError:
        return {"ports": [], "_warning": "pyserial not installed"}
    except Exception as exc:
        return {"ports": [], "_warning": str(exc)}


@motor_router.get("/connection")
async def get_connection() -> dict:
    """Return RS485 connection info: port, baudrate, motor_id, connected.

    Even when the RS485 driver has not been created (e.g. serial device
    missing), return the *configured* values from environment variables
    so the UI can display the intended port / motor-id.
    """
    drv = _bridge._rs485_driver
    if drv is None:
        # Fall back to env-var config so the UI shows intended settings
        cfg_port = os.environ.get("PRAGATI_MOTOR_SERIAL_PORT")
        cfg_id_str = os.environ.get("PRAGATI_MOTOR_ID")
        cfg_id = int(cfg_id_str) if cfg_id_str else 1
        return {
            "serial_port": cfg_port,
            "baudrate": 115200,
            "motor_id": cfg_id,
            "connected": False,
        }
    ser = getattr(drv, "_serial", None)
    return {
        "serial_port": getattr(drv, "port", None),
        "baudrate": getattr(drv, "baud", None),
        "motor_id": getattr(drv, "motor_id", None),
        "connected": ser is not None and getattr(ser, "is_open", False),
    }


@motor_router.put("/connection")
async def update_connection(body: dict) -> dict:
    """Update motor_id, baudrate, or serial_port at runtime.

    Changing motor_id takes effect immediately on the shared driver
    instance used by both MotorBridge and PIDTuningBridge.
    If baudrate or serial_port changes, the serial port is reopened.
    If no driver exists but serial_port is provided, a new RS485
    driver is created and injected.
    """
    drv = _bridge._rs485_driver
    new_port = body.get("serial_port")

    # --- Bootstrap a new driver if none exists yet ---
    if drv is None:
        if new_port and RS485_AVAILABLE:
            motor_id = int(body.get("motor_id", 1))
            baud = int(body.get("baudrate", 115200))
            drv = RS485MotorDriver(port=new_port, motor_id=motor_id, baud=baud)
            drv.connect()
            _bridge.set_rs485_driver(drv)
            # Polling not auto-started — frontend requests via /polling/start
            logger.info(
                "Created new RS485 driver on %s (id=%d, baud=%d)",
                new_port,
                motor_id,
                baud,
            )
            ser = getattr(drv, "_serial", None)
            return {
                "serial_port": drv.port,
                "baudrate": drv.baud,
                "motor_id": drv.motor_id,
                "connected": ser is not None and getattr(ser, "is_open", False),
            }
        raise HTTPException(status_code=400, detail="No RS485 driver configured")

    need_reconnect = False

    # --- serial_port ---
    if new_port is not None:
        if not isinstance(new_port, str) or not new_port.strip():
            raise HTTPException(
                status_code=422,
                detail="serial_port must be a non-empty string",
            )
        if new_port != drv.port:
            old_port = drv.port
            drv.port = new_port
            need_reconnect = True
            logger.info("Serial port changed: %s -> %s", old_port, new_port)

    # --- motor_id ---
    new_id = body.get("motor_id")
    if new_id is not None:
        new_id = int(new_id)
        if new_id < 1 or new_id > 32:
            raise HTTPException(
                status_code=422,
                detail=f"motor_id must be 1-32, got {new_id}",
            )
        old_id = drv.motor_id
        drv.motor_id = new_id
        logger.info("Motor ID changed: %d -> %d", old_id, new_id)

    # --- baudrate ---
    new_baud = body.get("baudrate")
    if new_baud is not None:
        new_baud = int(new_baud)
        if new_baud not in (9600, 19200, 38400, 57600, 115200, 230400, 460800, 500000):
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported baudrate: {new_baud}",
            )
        if new_baud != drv.baud:
            drv.baud = new_baud
            need_reconnect = True
            logger.info("Baudrate changed to %d", new_baud)

    # --- Reconnect if port or baud changed ---
    if need_reconnect:
        ser = getattr(drv, "_serial", None)
        was_open = ser is not None and getattr(ser, "is_open", False)
        if was_open:
            _bridge.stop_rs485_polling()
            drv.disconnect()
            ok = drv.connect()
            # Polling not auto-restarted — frontend requests when needed
            logger.info("Serial port reopened on %s at %d baud", drv.port, drv.baud)

    ser = getattr(drv, "_serial", None)
    return {
        "serial_port": drv.port,
        "baudrate": drv.baud,
        "motor_id": drv.motor_id,
        "connected": ser is not None and getattr(ser, "is_open", False),
    }


@motor_router.post("/connect")
async def connect_serial() -> dict:
    """Open the RS485 serial connection."""
    drv = _bridge._rs485_driver
    if drv is None:
        raise HTTPException(status_code=400, detail="No RS485 driver configured")

    ser = getattr(drv, "_serial", None)
    if ser is not None and getattr(ser, "is_open", False):
        return {"connected": True, "message": "Already connected"}

    ok = drv.connect()
    if not ok:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to open {drv.port} at {drv.baud} baud",
        )
    return {
        "connected": True,
        "message": f"Connected to {drv.port} at {drv.baud} baud (motor_id={drv.motor_id})",
    }


@motor_router.post("/disconnect")
async def disconnect_serial() -> dict:
    """Close the RS485 serial connection."""
    drv = _bridge._rs485_driver
    if drv is None:
        raise HTTPException(status_code=400, detail="No RS485 driver configured")

    _bridge.stop_rs485_polling()
    drv.disconnect()
    return {"connected": False, "message": "Disconnected"}


# -------------------------------------------------------------------
# RS485 state polling control
# -------------------------------------------------------------------


@motor_router.post("/polling/start")
async def start_polling() -> dict:
    """Start background RS485 state polling (10 Hz).

    Called by the frontend when the user navigates to a tab that needs
    live data (Test, PID Tuning).  Idempotent — calling when already
    running is a no-op.
    """
    if _bridge._rs485_driver is None:
        raise HTTPException(status_code=400, detail="No RS485 driver configured")
    _bridge.start_rs485_polling()
    return {"polling": True}


@motor_router.post("/polling/stop")
async def stop_polling() -> dict:
    """Stop background RS485 state polling.

    Called by the frontend when the user leaves live-data tabs.
    Idempotent — calling when already stopped is a no-op.
    """
    _bridge.stop_rs485_polling()
    return {"polling": False}


@motor_router.get("/polling")
async def get_polling_status() -> dict:
    """Return whether RS485 state polling is currently active."""
    return {"polling": _bridge._rs485_poll_thread is not None}


# -------------------------------------------------------------------
# Serial frame log (protocol debugging)
# -------------------------------------------------------------------


@motor_router.get("/serial_log")
async def get_serial_log(limit: int = 100) -> dict:
    """Get recent TX/RX serial frames for protocol debugging."""
    drv = _bridge._rs485_driver
    if drv is None:
        return {"frames": [], "comm_errors": 0}
    return {
        "frames": drv.get_frame_log(limit),
        "comm_errors": drv.get_comm_error_count(),
    }


@motor_router.delete("/serial_log")
async def clear_serial_log() -> dict:
    """Clear the serial frame log and reset error counter."""
    drv = _bridge._rs485_driver
    if drv is not None:
        drv.clear_frame_log()
    return {"success": True}


# -------------------------------------------------------------------
# Product info, brake, restore, clear multi-turn, set zero RAM
# -------------------------------------------------------------------


@motor_router.get("/{motor_id}/product_info")
async def get_product_info(motor_id: int) -> dict:
    """Read motor product info (cmd 0x12)."""
    _validate_motor_id(motor_id)

    drv = _bridge._rs485_driver
    if drv is None:
        raise HTTPException(status_code=503, detail="RS485 driver not available")

    id_err = _bridge._rs485_motor_id_check(motor_id)
    if id_err:
        raise HTTPException(status_code=400, detail=id_err["error"])

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, drv.read_product_info)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read product info: {exc}")

    if not result:
        raise HTTPException(status_code=500, detail="Failed to read product info")
    return result


@motor_router.post("/{motor_id}/brake")
async def brake_control(motor_id: int, action: int = Body(..., embed=True)) -> dict:
    """Control holding brake. action: 0=brake_on, 1=brake_release."""
    _validate_motor_id(motor_id)

    if action not in (0, 1):
        raise HTTPException(
            status_code=400,
            detail="action must be 0 (brake) or 1 (release)",
        )

    drv = _bridge._rs485_driver
    if drv is None:
        raise HTTPException(status_code=503, detail="RS485 driver not available")

    id_err = _bridge._rs485_motor_id_check(motor_id)
    if id_err:
        raise HTTPException(status_code=400, detail=id_err["error"])

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, drv.brake_control, action)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Brake command failed: {exc}")

    if not result:
        raise HTTPException(status_code=500, detail="Brake command failed")
    return result


@motor_router.get("/{motor_id}/brake")
async def get_brake_state(motor_id: int) -> dict:
    """Read holding brake state."""
    _validate_motor_id(motor_id)

    drv = _bridge._rs485_driver
    if drv is None:
        raise HTTPException(status_code=503, detail="RS485 driver not available")

    id_err = _bridge._rs485_motor_id_check(motor_id)
    if id_err:
        raise HTTPException(status_code=400, detail=id_err["error"])

    loop = asyncio.get_event_loop()
    try:
        # 0x10 = read state
        result = await loop.run_in_executor(None, drv.brake_control, 0x10)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read brake state: {exc}",
        )

    if not result:
        raise HTTPException(status_code=500, detail="Failed to read brake state")
    return result


@motor_router.post("/{motor_id}/restore")
async def motor_restore(motor_id: int) -> dict:
    """Restore motor to default state (cmd 0x89)."""
    _validate_motor_id(motor_id)

    drv = _bridge._rs485_driver
    if drv is None:
        raise HTTPException(status_code=503, detail="RS485 driver not available")

    id_err = _bridge._rs485_motor_id_check(motor_id)
    if id_err:
        raise HTTPException(status_code=400, detail=id_err["error"])

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, drv.motor_restore)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Motor restore failed: {exc}")

    return {"success": result is not None}


@motor_router.post("/{motor_id}/clear_multi_turn")
async def clear_multi_turn(motor_id: int) -> dict:
    """Clear multi-turn angle counter (cmd 0x93)."""
    _validate_motor_id(motor_id)

    drv = _bridge._rs485_driver
    if drv is None:
        raise HTTPException(status_code=503, detail="RS485 driver not available")

    id_err = _bridge._rs485_motor_id_check(motor_id)
    if id_err:
        raise HTTPException(status_code=400, detail=id_err["error"])

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, drv.clear_multi_turn_angle)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Clear multi-turn failed: {exc}",
        )

    return {"success": result is not None}


@motor_router.post("/{motor_id}/set_zero_ram")
async def set_zero_ram(motor_id: int) -> dict:
    """Set current position as motor zero in RAM (cmd 0x95)."""
    _validate_motor_id(motor_id)

    drv = _bridge._rs485_driver
    if drv is None:
        raise HTTPException(status_code=503, detail="RS485 driver not available")

    id_err = _bridge._rs485_motor_id_check(motor_id)
    if id_err:
        raise HTTPException(status_code=400, detail=id_err["error"])

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, drv.set_zero_position_ram)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Set zero RAM failed: {exc}",
        )

    return {"success": result is not None}


# -------------------------------------------------------------------
# Extended limits (ParamID-based)
# -------------------------------------------------------------------


@motor_router.get("/{motor_id}/ext_config")
async def get_ext_config(motor_id: int) -> dict:
    """Read extended config via undocumented 0x16 command.

    Returns basic settings, protection settings, and EEPROM info.
    Fields marked None are not yet reverse-engineered.
    Derives motor_poles and reduction_ratio from product info motor name.
    """
    _validate_motor_id(motor_id)

    drv = _bridge._rs485_driver
    if drv is None:
        raise HTTPException(status_code=503, detail="RS485 driver not available")

    id_err = _bridge._rs485_motor_id_check(motor_id)
    if id_err:
        raise HTTPException(status_code=400, detail=id_err["error"])

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, drv.read_product_info_ext)

    if result is None:
        raise HTTPException(status_code=500, detail="Failed to read extended config")

    # Derive motor_poles and reduction_ratio from product info
    if "encoder_setting" in result:
        try:
            pi = await loop.run_in_executor(None, drv.read_product_info)
            if pi:
                motor_name = pi.get("motor_name", "")
                poles = _lookup_motor_poles(motor_name)
                if poles is not None:
                    result["encoder_setting"]["motor_poles"] = poles
                ratio = _lookup_reduction_ratio(motor_name)
                if ratio is not None:
                    result["encoder_setting"]["reduction_ratio"] = ratio
        except Exception:
            pass  # Best-effort enrichment

    return result


@motor_router.get("/{motor_id}/extended_limits")
async def get_extended_limits(motor_id: int) -> dict:
    """Read all motor limits via ParamID system.

    Returns max speed, max angle, current ramp, speed ramp, and
    max torque current when available.
    """
    _validate_motor_id(motor_id)

    drv = _bridge._rs485_driver
    if drv is None:
        raise HTTPException(status_code=503, detail="RS485 driver not available")

    id_err = _bridge._rs485_motor_id_check(motor_id)
    if id_err:
        raise HTTPException(status_code=400, detail=id_err["error"])

    loop = asyncio.get_event_loop()
    result: dict = {}
    failed: list[str] = []

    max_speed = await loop.run_in_executor(None, drv.read_max_speed)
    if max_speed:
        result.update(max_speed)
    else:
        failed.append("max_speed")

    max_angle = await loop.run_in_executor(None, drv.read_max_angle)
    if max_angle:
        result.update(max_angle)
    else:
        failed.append("max_angle")

    current_ramp = await loop.run_in_executor(None, drv.read_current_ramp)
    if current_ramp:
        result.update(current_ramp)
    else:
        failed.append("current_ramp")

    speed_ramp = await loop.run_in_executor(None, drv.read_speed_ramp)
    if speed_ramp:
        result.update(speed_ramp)
    else:
        failed.append("speed_ramp")

    # Max torque current may already be available
    try:
        torque = await loop.run_in_executor(None, drv.read_max_torque)
        if torque:
            result["max_torque_current"] = torque.get(
                "max_torque", torque.get("max_torque_current")
            )
        else:
            failed.append("max_torque_current")
    except Exception:
        failed.append("max_torque_current")

    if failed:
        result["_warning"] = (
            f"Could not read: {', '.join(failed)}. "
            "Motor firmware may not support ParamID commands (0x40)."
        )
        result["_failed"] = failed
    result["_success"] = len(failed) == 0

    return result


@motor_router.put("/{motor_id}/extended_limits/{param}")
async def set_extended_limit(
    motor_id: int,
    param: str,
    value: float = Body(..., embed=True),
    to_rom: bool = Body(False, embed=True),
) -> dict:
    """Write a motor limit parameter.

    param: max_speed, max_angle, current_ramp
    """
    _validate_motor_id(motor_id)

    drv = _bridge._rs485_driver
    if drv is None:
        raise HTTPException(status_code=503, detail="RS485 driver not available")

    id_err = _bridge._rs485_motor_id_check(motor_id)
    if id_err:
        raise HTTPException(status_code=400, detail=id_err["error"])

    loop = asyncio.get_event_loop()

    if param == "max_speed":
        result = await loop.run_in_executor(None, drv.write_max_speed, int(value), to_rom)
    elif param == "max_angle":
        result = await loop.run_in_executor(None, drv.write_max_angle, int(value), to_rom)
    elif param == "current_ramp":
        result = await loop.run_in_executor(None, drv.write_current_ramp, int(value), to_rom)
    elif param == "speed_ramp":
        result = await loop.run_in_executor(None, drv.write_speed_ramp, int(value), to_rom)
    else:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown param: {param}. " "Valid: max_speed, max_angle, current_ramp, speed_ramp"
            ),
        )

    return {
        "success": result is not None,
        "param": param,
        "value": value,
        "to_rom": to_rom,
    }


# -------------------------------------------------------------------
# Protocol parity endpoints (CMD 0x1F, 0x14, 0x10, combined sequence)
# -------------------------------------------------------------------


@motor_router.get("/{motor_id}/firmware_version")
async def get_firmware_version(motor_id: int) -> dict:
    """Read firmware version via CMD 0x1F."""
    _validate_motor_id(motor_id)

    drv = _bridge._rs485_driver
    if drv is None:
        raise HTTPException(status_code=503, detail="RS485 driver not available")

    id_err = _bridge._rs485_motor_id_check(motor_id)
    if id_err:
        raise HTTPException(status_code=400, detail=id_err["error"])

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, drv.read_firmware_version)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read firmware version: {exc}",
        )

    if not result:
        raise HTTPException(
            status_code=500,
            detail="Failed to read firmware version (timeout)",
        )
    return result


@motor_router.get("/{motor_id}/full_config")
async def get_full_config(motor_id: int) -> dict:
    """Read full config via CMD 0x14 (104-byte response).

    Returns structured JSON with pid_setting, protection_setting,
    limits_setting, basic_setting, and trailer sections.
    """
    _validate_motor_id(motor_id)

    drv = _bridge._rs485_driver
    if drv is None:
        raise HTTPException(status_code=503, detail="RS485 driver not available")

    id_err = _bridge._rs485_motor_id_check(motor_id)
    if id_err:
        raise HTTPException(status_code=400, detail=id_err["error"])

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, drv.read_full_config)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read full config: {exc}",
        )

    if not result:
        raise HTTPException(
            status_code=500,
            detail="Failed to read full config (timeout)",
        )
    return result


@motor_router.get("/{motor_id}/heartbeat")
async def get_heartbeat(motor_id: int) -> dict:
    """Send heartbeat / system state (CMD 0x10).

    Returns alive status. Used to confirm motor communication.
    """
    _validate_motor_id(motor_id)

    drv = _bridge._rs485_driver
    if drv is None:
        raise HTTPException(status_code=503, detail="RS485 driver not available")

    id_err = _bridge._rs485_motor_id_check(motor_id)
    if id_err:
        raise HTTPException(status_code=400, detail=id_err["error"])

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, drv.read_system_state)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Heartbeat failed: {exc}",
        )

    if not result:
        raise HTTPException(
            status_code=500,
            detail="Heartbeat failed (timeout)",
        )
    return result


@motor_router.post("/{motor_id}/read_all_settings")
async def read_all_settings(motor_id: int) -> dict:
    """Run the full LK Motor Tool connect sequence.

    Sends commands in order: 0x1F -> 0x12 -> 0x16 -> 0x14 -> 0x10.
    Returns combined result from all commands. Individual failures
    are logged but do not abort the sequence.
    """
    _validate_motor_id(motor_id)

    drv = _bridge._rs485_driver
    if drv is None:
        raise HTTPException(status_code=503, detail="RS485 driver not available")

    id_err = _bridge._rs485_motor_id_check(motor_id)
    if id_err:
        raise HTTPException(status_code=400, detail=id_err["error"])

    loop = asyncio.get_event_loop()
    combined: dict = {}
    failed: list[str] = []

    # 1. Firmware version (CMD 0x1F)
    try:
        fw = await loop.run_in_executor(None, drv.read_firmware_version)
        if fw and "error" not in fw:
            combined["firmware_version"] = fw
        else:
            failed.append("firmware_version")
    except Exception:
        failed.append("firmware_version")

    # 2. Product info (CMD 0x12)
    try:
        pi = await loop.run_in_executor(None, drv.read_product_info)
        if pi and "error" not in pi:
            combined["product_info"] = pi
        else:
            failed.append("product_info")
    except Exception:
        failed.append("product_info")

    # 3. Extended product info / EEPROM (CMD 0x16)
    try:
        ext = await loop.run_in_executor(None, drv.read_product_info_ext)
        if ext and "error" not in ext:
            combined["ext_config"] = ext
        else:
            failed.append("ext_config")
    except Exception:
        failed.append("ext_config")

    # 4. Full config (CMD 0x14)
    try:
        cfg = await loop.run_in_executor(None, drv.read_full_config)
        if cfg and "error" not in cfg:
            combined["full_config"] = cfg
        else:
            failed.append("full_config")
    except Exception:
        failed.append("full_config")

    # 5. Heartbeat (CMD 0x10)
    try:
        hb = await loop.run_in_executor(None, drv.read_system_state)
        if hb:
            combined["heartbeat"] = hb
        else:
            failed.append("heartbeat")
    except Exception:
        failed.append("heartbeat")

    if failed:
        combined["_failed"] = failed
        combined["_warning"] = f"Some commands failed: {', '.join(failed)}"
    combined["_success"] = len(failed) == 0

    # Derive motor_poles and reduction_ratio from product_info
    # motor_name and inject into ext_config.encoder_setting for
    # frontend consumption.
    pi = combined.get("product_info")
    ext = combined.get("ext_config")
    if pi and ext and "encoder_setting" in ext:
        motor_name = pi.get("motor_name", "")
        poles = _lookup_motor_poles(motor_name)
        if poles is not None:
            ext["encoder_setting"]["motor_poles"] = poles
        ratio = _lookup_reduction_ratio(motor_name)
        if ratio is not None:
            ext["encoder_setting"]["reduction_ratio"] = ratio

    return combined


# -------------------------------------------------------------------
# Detailed state (all 3 status registers)
# -------------------------------------------------------------------


@motor_router.get("/{motor_id}/state_detailed")
async def get_state_detailed(motor_id: int) -> dict:
    """Read all 3 motor states.

    state1: temp/voltage/errors
    state2: current/speed/encoder
    state3: phase currents
    """
    _validate_motor_id(motor_id)

    drv = _bridge._rs485_driver
    if drv is None:
        raise HTTPException(status_code=503, detail="RS485 driver not available")

    id_err = _bridge._rs485_motor_id_check(motor_id)
    if id_err:
        raise HTTPException(status_code=400, detail=id_err["error"])

    loop = asyncio.get_event_loop()
    result: dict = {}

    state1 = await loop.run_in_executor(None, drv.read_status_1)
    if state1:
        result["state1"] = state1

    state2 = await loop.run_in_executor(None, drv.read_status_2)
    if state2:
        result["state2"] = state2

    state3 = await loop.run_in_executor(None, drv.read_status_3)
    if state3:
        result["state3"] = state3

    return result


@motor_router.get("/{motor_id}/state/{state_num}")
async def get_state_individual(motor_id: int, state_num: int) -> dict:
    """Read a single motor state (1, 2, or 3).

    state 1: temp/voltage/errors (cmd 0x9A)
    state 2: current/speed/encoder (cmd 0x9C)
    state 3: phase currents (cmd 0x9D)
    """
    _validate_motor_id(motor_id)

    if state_num not in (1, 2, 3):
        raise HTTPException(status_code=400, detail="state_num must be 1, 2, or 3")

    drv = _bridge._rs485_driver
    if drv is None:
        raise HTTPException(status_code=503, detail="RS485 driver not available")

    id_err = _bridge._rs485_motor_id_check(motor_id)
    if id_err:
        raise HTTPException(status_code=400, detail=id_err["error"])

    loop = asyncio.get_event_loop()
    read_fn = {1: drv.read_status_1, 2: drv.read_status_2, 3: drv.read_status_3}[state_num]
    data = await loop.run_in_executor(None, read_fn)

    key = f"state{state_num}"
    if data:
        return {key: data}
    return {key: None, "error": f"State {state_num} read failed"}


# -------------------------------------------------------------------
# Task 5.10: WebSocket /api/motor/ws/state
# -------------------------------------------------------------------

_ws_motor_state_clients: Set[WebSocket] = set()


@motor_router.websocket("/ws/state")
async def ws_motor_state(websocket: WebSocket) -> None:
    """Stream motor state updates to WebSocket clients at ~10 Hz.

    Clients can send ``{"motor_id": N}`` to filter updates.
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

                    await websocket.send_text(state_json)
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("WebSocket motor state disconnected")
    finally:
        _ws_motor_state_clients.discard(websocket)


# -------------------------------------------------------------------
# WebSocket /api/motor/ws/serial_log — real-time serial frame streaming
# -------------------------------------------------------------------


@motor_router.websocket("/ws/serial_log")
async def serial_log_ws(ws: WebSocket):
    """WebSocket for real-time serial frame streaming.

    The RS485 driver may not exist when this WebSocket first connects
    (e.g. user launches dashboard without ``--serial-port`` and later
    clicks CONNECT in the UI).  We re-check ``_bridge._rs485_driver``
    on every keepalive cycle so the listener is registered as soon as
    the driver becomes available.
    """
    await ws.accept()

    queue: asyncio.Queue = asyncio.Queue(maxsize=200)

    def on_frame(entry):
        """Callback from RS485 driver thread — put frame in async queue."""
        try:
            queue.put_nowait(entry)
        except asyncio.QueueFull:
            pass  # Drop frames if consumer is slow

    # Track which driver instance we registered on so we can detect
    # driver creation (None → driver) or replacement (old → new).
    registered_driver = None

    def _sync_listener():
        """Register/re-register frame listener when driver changes."""
        nonlocal registered_driver
        current = _bridge._rs485_driver
        if current is registered_driver:
            return  # No change
        # Unregister from old driver (if any)
        if registered_driver is not None:
            registered_driver.remove_frame_listener(on_frame)
        # Register on new driver (if any)
        if current is not None:
            current.add_frame_listener(on_frame)
        registered_driver = current

    _sync_listener()

    try:
        # Send any existing history first
        if registered_driver:
            history = registered_driver.get_frame_log(limit=50)
            for frame in history:
                await ws.send_json(frame)

        # Then stream new frames
        while True:
            try:
                entry = await asyncio.wait_for(queue.get(), timeout=30.0)
                await ws.send_json(entry)
            except asyncio.TimeoutError:
                # Re-check driver on each keepalive in case it was
                # created or replaced since we last checked.
                _sync_listener()
                await ws.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if registered_driver is not None:
            registered_driver.remove_frame_listener(on_frame)
