"""FastAPI router for multi-arm MQTT coordination endpoints.

Provides REST endpoints for querying arm states, vehicle status, and
sending commands via the :class:`~backend.mqtt_status_service.MqttStatusService`.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level service / logger singletons (set by the dashboard server)
# ---------------------------------------------------------------------------
_mqtt_service: Any = None
_audit_logger: Any = None

VALID_COMMANDS = {"restart", "estop"}


def set_mqtt_service(service: Any) -> None:
    """Inject the MqttStatusService instance."""
    global _mqtt_service
    _mqtt_service = service


def set_audit_logger(audit: Any) -> None:
    """Inject an AuditLogger instance."""
    global _audit_logger
    _audit_logger = audit


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ArmCommandRequest(BaseModel):
    command: str


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
mqtt_router = APIRouter()


@mqtt_router.get("/api/arms")
def get_all_arms() -> Dict[str, Any]:
    """Return all tracked arm states."""
    if _mqtt_service is None:
        return {}
    return _mqtt_service.get_all_arms()


@mqtt_router.get("/api/mqtt/status")
def get_mqtt_status() -> Dict[str, Any]:
    """Return MQTT broker health, vehicle status, and arm counts.

    This is the unified health-check endpoint (tasks 1.4, 4.4).
    """
    if _mqtt_service is None:
        return {"connected": False, "broker": None, "vehicle": None}
    return _mqtt_service.get_status()


# Keep old path as alias for backward compatibility
@mqtt_router.get("/api/arms/mqtt/status")
def get_mqtt_status_legacy() -> Dict[str, Any]:
    """Legacy MQTT status endpoint — redirects to /api/mqtt/status."""
    return get_mqtt_status()


@mqtt_router.get("/api/arms/{arm_id}")
def get_arm(arm_id: str) -> Dict[str, Any]:
    """Return a single arm's state, or 404."""
    if _mqtt_service is None:
        raise HTTPException(status_code=404, detail="Arm not found")
    arm = _mqtt_service.get_arm(arm_id)
    if arm is None:
        raise HTTPException(status_code=404, detail="Arm not found")
    return arm


@mqtt_router.post("/api/arms/{arm_id}/command")
def send_arm_command(arm_id: str, body: ArmCommandRequest) -> Dict[str, Any]:
    """Send a command to an arm via MQTT."""
    if body.command not in VALID_COMMANDS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid command '{body.command}'. "
            f"Valid: {sorted(VALID_COMMANDS)}",
        )
    if _mqtt_service is None:
        raise HTTPException(
            status_code=503, detail="MQTT service unavailable"
        )

    try:
        _mqtt_service.send_command(arm_id, body.command)
    except ConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    if _audit_logger is not None:
        _audit_logger.log(
            "arm_command",
            {"arm_id": arm_id, "command": body.command},
            "sent",
        )

    return {"status": "sent", "arm_id": arm_id, "command": body.command}
