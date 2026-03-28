"""Entity Motor Router — entity-scoped motor API routes.

Provides per-entity endpoints for motor status, commands, PID tuning,
encoder calibration, motor limits, and step response testing.
Remote entities proxy to the RPi agent. Local entity dispatches to
existing motor_api / pid_tuning_api logic.

Phase 3b, Tasks 3.1–3.4 of dashboard-motor-rosbag.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .entity_manager import AGENT_PORT, get_entity_manager
from .entity_model import Entity

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

entity_motor_router = APIRouter(prefix="/api/entities", tags=["entity-motors"])

# Timeout for agent proxy requests (seconds)
_PROXY_TIMEOUT_S = 20
# Longer timeout for step response (test can take up to 30s)
_STEP_RESPONSE_TIMEOUT_S = 35

# Network errors that indicate agent unreachable
_PROXY_NETWORK_ERRORS = (
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
    OSError,
)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class MotorCommandRequest(BaseModel):
    motor_id: int | None = None
    mode: str
    params: dict = {}


class PIDWriteRequest(BaseModel):
    motor_id: int
    angle_kp: int
    angle_ki: int
    speed_kp: int
    speed_ki: int
    current_kp: int
    current_ki: int


class CalibrateZeroRequest(BaseModel):
    motor_id: int


class MotorLimitsWriteRequest(BaseModel):
    motor_id: int
    min_angle_deg: float
    max_angle_deg: float
    max_speed_dps: float
    max_current_a: float


class StepResponseRequest(BaseModel):
    motor_id: int
    target_angle_deg: float
    duration_s: float = 5.0
    sample_rate_hz: int = 50


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_mgr_or_503():
    """Return the EntityManager or raise 503."""
    mgr = get_entity_manager()
    if mgr is None:
        raise HTTPException(status_code=503, detail="EntityManager not initialized")
    return mgr


def _get_entity_or_404(entity_id: str) -> Entity:
    """Look up an entity by ID or raise 404."""
    mgr = _get_mgr_or_503()
    entity = mgr.get_entity(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=404,
            detail=f"Entity '{entity_id}' not found",
        )
    return entity


async def _proxy_get(
    entity: Entity, path: str, timeout: float = _PROXY_TIMEOUT_S
) -> Any:
    """Proxy a GET request to a remote entity's agent."""
    url = f"{entity.agent_base_url(AGENT_PORT)}{path}"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
            resp = await client.get(url)
        if resp.status_code == 200:
            return resp.json()
        # Forward non-200 status from agent
        return JSONResponse(
            status_code=resp.status_code,
            content=(
                resp.json()
                if resp.headers.get("content-type", "").startswith("application/json")
                else {
                    "error": "agent_error",
                    "message": f"Agent returned status {resp.status_code}",
                }
            ),
        )
    except _PROXY_NETWORK_ERRORS as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Agent at {entity.ip} unreachable: {exc}",
        )


async def _proxy_post(
    entity: Entity,
    path: str,
    json_body: dict | None = None,
    timeout: float = _PROXY_TIMEOUT_S,
) -> Any:
    """Proxy a POST request to a remote entity's agent."""
    url = f"{entity.agent_base_url(AGENT_PORT)}{path}"
    api_key = _get_agent_api_key()
    headers = {"X-API-Key": api_key} if api_key else {}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
            resp = await client.post(url, json=json_body, headers=headers)
        if resp.status_code == 200:
            return resp.json()
        return JSONResponse(
            status_code=resp.status_code,
            content=(
                resp.json()
                if resp.headers.get("content-type", "").startswith("application/json")
                else {
                    "error": "agent_error",
                    "message": f"Agent returned status {resp.status_code}",
                }
            ),
        )
    except _PROXY_NETWORK_ERRORS as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Agent at {entity.ip} unreachable: {exc}",
        )


async def _proxy_put(
    entity: Entity,
    path: str,
    json_body: dict | None = None,
    timeout: float = _PROXY_TIMEOUT_S,
) -> Any:
    """Proxy a PUT request to a remote entity's agent."""
    url = f"{entity.agent_base_url(AGENT_PORT)}{path}"
    api_key = _get_agent_api_key()
    headers = {"X-API-Key": api_key} if api_key else {}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
            resp = await client.put(url, json=json_body, headers=headers)
        if resp.status_code == 200:
            return resp.json()
        return JSONResponse(
            status_code=resp.status_code,
            content=(
                resp.json()
                if resp.headers.get("content-type", "").startswith("application/json")
                else {
                    "error": "agent_error",
                    "message": f"Agent returned status {resp.status_code}",
                }
            ),
        )
    except _PROXY_NETWORK_ERRORS as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Agent at {entity.ip} unreachable: {exc}",
        )


def _get_agent_api_key() -> str:
    """Get the API key used to authenticate with RPi agents."""
    import os

    return os.environ.get("PRAGATI_AGENT_API_KEY", "")


def _wrap_response(entity_id: str, source: str, data: Any) -> dict[str, Any]:
    """Standard envelope for proxy responses."""
    return {
        "entity_id": entity_id,
        "source": source,
        "data": data,
    }


# ---------------------------------------------------------------------------
# Local motor logic helpers (delegate to existing motor_api / pid_tuning_api)
# ---------------------------------------------------------------------------


def _get_motor_bridge():
    """Get the MotorConfigBridge singleton (lazy import)."""
    try:
        from .motor_api import _bridge

        return _bridge
    except (ImportError, AttributeError):
        return None


def _get_pid_bridge():
    """Get the PIDTuningBridge singleton (lazy import)."""
    try:
        from .pid_tuning_api import _bridge

        return _bridge
    except (ImportError, AttributeError):
        return None


def _local_motor_status(motor_id: int | None = None) -> list[dict]:
    """Read motor state from local ROS2 bridge."""
    bridge = _get_motor_bridge()
    if bridge is None:
        return [
            {
                "motor_id": mid,
                "angle_deg": None,
                "speed_dps": None,
                "current_a": None,
                "temperature_c": None,
                "online": False,
            }
            for mid in ([motor_id] if motor_id is not None else [1, 2, 3, 4, 5, 6])
        ]
    # Use bridge's cached state if available
    if hasattr(bridge, "motor_states") and bridge.motor_states:
        ids = [motor_id] if motor_id is not None else list(bridge.motor_states.keys())
        results = []
        for mid in ids:
            state = bridge.motor_states.get(mid, {})
            results.append(
                {
                    "motor_id": mid,
                    "angle_deg": state.get("angle", None),
                    "speed_dps": state.get("speed", None),
                    "current_a": state.get("current", None),
                    "temperature_c": state.get("temperature", None),
                    "online": bool(state),
                }
            )
        return results
    return []


async def _local_motor_command(motor_id: int | None, mode: str, params: dict) -> dict:
    """Send motor command via local ROS2 bridge."""
    bridge = _get_motor_bridge()
    if bridge is None:
        raise HTTPException(
            status_code=503,
            detail="Motor bridge not available",
        )
    # Delegate to bridge — it handles CAN command construction
    try:
        if mode in ("stop", "0x81"):
            # Emergency stop
            if hasattr(bridge, "send_stop_all"):
                bridge.send_stop_all()
                return {"success": True, "motor_id": motor_id}
        if hasattr(bridge, "send_command"):
            bridge.send_command(motor_id, mode, params)
            return {"success": True, "motor_id": motor_id}
        raise HTTPException(
            status_code=503, detail="Motor bridge send_command not available"
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


async def _local_pid_read(motor_id: int) -> dict:
    """Read PID gains from local ROS2 bridge."""
    bridge = _get_pid_bridge()
    if bridge is None:
        raise HTTPException(
            status_code=503,
            detail="PID bridge not available",
        )
    try:
        if hasattr(bridge, "read_gains"):
            gains = bridge.read_gains(motor_id)
            return {
                "motor_id": motor_id,
                "angle_kp": gains.get("angle_kp", 0),
                "angle_ki": gains.get("angle_ki", 0),
                "speed_kp": gains.get("speed_kp", 0),
                "speed_ki": gains.get("speed_ki", 0),
                "current_kp": gains.get("current_kp", 0),
                "current_ki": gains.get("current_ki", 0),
            }
        raise HTTPException(
            status_code=503, detail="PID bridge read_gains not available"
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


async def _local_pid_write(motor_id: int, gains: dict) -> dict:
    """Write PID gains via local ROS2 bridge."""
    bridge = _get_pid_bridge()
    if bridge is None:
        raise HTTPException(status_code=503, detail="PID bridge not available")
    try:
        if hasattr(bridge, "write_gains"):
            bridge.write_gains(motor_id, gains)
            return {"success": True}
        raise HTTPException(
            status_code=503, detail="PID bridge write_gains not available"
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Endpoints: Motor status
# ---------------------------------------------------------------------------


@entity_motor_router.get("/{entity_id}/motors/status")
async def get_entity_motor_status(
    entity_id: str,
    motor_id: int | None = Query(default=None),
):
    """Get motor state for an entity."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        data = _local_motor_status(motor_id)
        if motor_id is not None:
            return _wrap_response(entity_id, "local", data[0] if data else {})
        return _wrap_response(entity_id, "local", data)

    path = "/motors/status"
    if motor_id is not None:
        path += f"?motor_id={motor_id}"
    data = await _proxy_get(entity, path)
    if isinstance(data, JSONResponse):
        return data
    return _wrap_response(entity_id, "remote", data)


# ---------------------------------------------------------------------------
# Endpoints: Motor commands
# ---------------------------------------------------------------------------


@entity_motor_router.post("/{entity_id}/motors/command")
async def post_entity_motor_command(entity_id: str, body: MotorCommandRequest):
    """Send a motor command to an entity."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        data = await _local_motor_command(body.motor_id, body.mode, body.params)
        return _wrap_response(entity_id, "local", data)

    data = await _proxy_post(
        entity,
        "/motors/command",
        json_body=body.model_dump(),
    )
    if isinstance(data, JSONResponse):
        return data
    return _wrap_response(entity_id, "remote", data)


# ---------------------------------------------------------------------------
# Endpoints: PID read/write
# ---------------------------------------------------------------------------


@entity_motor_router.get("/{entity_id}/motors/pid/read")
async def get_entity_pid_read(entity_id: str, motor_id: int = Query()):
    """Read PID gains for a motor on an entity."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        data = await _local_pid_read(motor_id)
        return _wrap_response(entity_id, "local", data)

    data = await _proxy_get(entity, f"/motors/pid/read?motor_id={motor_id}")
    if isinstance(data, JSONResponse):
        return data
    return _wrap_response(entity_id, "remote", data)


@entity_motor_router.post("/{entity_id}/motors/pid/write")
async def post_entity_pid_write(entity_id: str, body: PIDWriteRequest):
    """Write PID gains to a motor on an entity."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        gains = {
            "angle_kp": body.angle_kp,
            "angle_ki": body.angle_ki,
            "speed_kp": body.speed_kp,
            "speed_ki": body.speed_ki,
            "current_kp": body.current_kp,
            "current_ki": body.current_ki,
        }
        data = await _local_pid_write(body.motor_id, gains)
        return _wrap_response(entity_id, "local", data)

    data = await _proxy_post(
        entity,
        "/motors/pid/write",
        json_body=body.model_dump(),
    )
    if isinstance(data, JSONResponse):
        return data
    return _wrap_response(entity_id, "remote", data)


# ---------------------------------------------------------------------------
# Endpoints: Encoder calibration
# ---------------------------------------------------------------------------


@entity_motor_router.get("/{entity_id}/motors/calibrate/read")
async def get_entity_calibrate_read(entity_id: str, motor_id: int = Query()):
    """Read encoder calibration data for a motor."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        # Local: use motor bridge encoder read
        bridge = _get_motor_bridge()
        if bridge and hasattr(bridge, "read_encoder"):
            try:
                enc = bridge.read_encoder(motor_id)
                return _wrap_response(entity_id, "local", enc)
            except Exception as exc:
                raise HTTPException(status_code=500, detail=str(exc))
        raise HTTPException(status_code=503, detail="Motor bridge not available")

    data = await _proxy_get(entity, f"/motors/calibrate/read?motor_id={motor_id}")
    if isinstance(data, JSONResponse):
        return data
    return _wrap_response(entity_id, "remote", data)


@entity_motor_router.post("/{entity_id}/motors/calibrate/zero")
async def post_entity_calibrate_zero(entity_id: str, body: CalibrateZeroRequest):
    """Zero-set encoder for a motor on an entity."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        bridge = _get_motor_bridge()
        if bridge and hasattr(bridge, "write_encoder_zero"):
            try:
                bridge.write_encoder_zero(body.motor_id)
                return _wrap_response(
                    entity_id,
                    "local",
                    {"success": True, "motor_id": body.motor_id},
                )
            except Exception as exc:
                raise HTTPException(status_code=500, detail=str(exc))
        raise HTTPException(status_code=503, detail="Motor bridge not available")

    data = await _proxy_post(
        entity,
        "/motors/calibrate/zero",
        json_body=body.model_dump(),
    )
    if isinstance(data, JSONResponse):
        return data
    return _wrap_response(entity_id, "remote", data)


# ---------------------------------------------------------------------------
# Endpoints: Motor limits
# ---------------------------------------------------------------------------


@entity_motor_router.get("/{entity_id}/motors/limits")
async def get_entity_motor_limits(entity_id: str, motor_id: int = Query()):
    """Read motor limits for an entity."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        bridge = _get_motor_bridge()
        if bridge and hasattr(bridge, "read_limits"):
            try:
                limits = bridge.read_limits(motor_id)
                return _wrap_response(entity_id, "local", limits)
            except Exception as exc:
                raise HTTPException(status_code=500, detail=str(exc))
        # Fallback: return defaults
        return _wrap_response(
            entity_id,
            "local",
            {
                "motor_id": motor_id,
                "min_angle_deg": -180.0,
                "max_angle_deg": 180.0,
                "max_speed_dps": 360.0,
                "max_current_a": 10.0,
            },
        )

    data = await _proxy_get(entity, f"/motors/limits?motor_id={motor_id}")
    if isinstance(data, JSONResponse):
        return data
    return _wrap_response(entity_id, "remote", data)


@entity_motor_router.put("/{entity_id}/motors/limits")
async def put_entity_motor_limits(entity_id: str, body: MotorLimitsWriteRequest):
    """Write motor limits for an entity."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        bridge = _get_motor_bridge()
        if bridge and hasattr(bridge, "write_limits"):
            try:
                bridge.write_limits(body.motor_id, body.model_dump())
                return _wrap_response(
                    entity_id,
                    "local",
                    {"success": True, "motor_id": body.motor_id},
                )
            except Exception as exc:
                raise HTTPException(status_code=500, detail=str(exc))
        raise HTTPException(status_code=503, detail="Motor bridge not available")

    data = await _proxy_put(
        entity,
        "/motors/limits",
        json_body=body.model_dump(),
    )
    if isinstance(data, JSONResponse):
        return data
    return _wrap_response(entity_id, "remote", data)


# ---------------------------------------------------------------------------
# Endpoints: Step response
# ---------------------------------------------------------------------------


@entity_motor_router.post("/{entity_id}/motors/step-response")
async def post_entity_step_response(entity_id: str, body: StepResponseRequest):
    """Execute step response test on an entity."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        # Local: delegate to PID bridge step test
        bridge = _get_pid_bridge()
        if bridge and hasattr(bridge, "run_step_test"):
            try:
                result = bridge.run_step_test(
                    motor_id=body.motor_id,
                    target_angle_deg=body.target_angle_deg,
                    duration_s=body.duration_s,
                    sample_rate_hz=body.sample_rate_hz,
                )
                return _wrap_response(entity_id, "local", result)
            except Exception as exc:
                raise HTTPException(status_code=500, detail=str(exc))
        raise HTTPException(status_code=503, detail="PID bridge not available")

    # Remote: agent runs the test entirely locally
    data = await _proxy_post(
        entity,
        "/motors/step-response",
        json_body=body.model_dump(),
        timeout=_STEP_RESPONSE_TIMEOUT_S,
    )
    if isinstance(data, JSONResponse):
        return data
    return _wrap_response(entity_id, "remote", data)
