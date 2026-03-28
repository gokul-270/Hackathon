"""Safety Controls API for Pragati dashboard.

Provides FastAPI router with endpoints for:
- E-stop activation (POST /api/estop)
- E-stop reset (POST /api/estop/reset)
- Safety status (GET /api/safety/status)
- Emergency shutdown (POST /api/emergency-shutdown)

CAN bus communication uses python-can (optional dependency).
ProcessManager and AuditLogger are injected via module-level setters.
"""

import logging
import subprocess
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# CAN bus import (optional -- python-can may not be installed)
# -------------------------------------------------------------------
try:
    import can

    CAN_AVAILABLE = True
except ImportError:
    CAN_AVAILABLE = False
    logger.warning("python-can not available -- CAN commands will be mocked")


# -------------------------------------------------------------------
# Module-level dependencies (injected at startup)
# -------------------------------------------------------------------
_process_manager = None  # Optional[ProcessManager]
_audit_logger = None  # Optional[AuditLogger]


def set_process_manager(pm) -> None:
    """Set the ProcessManager instance for E-stop process termination."""
    global _process_manager
    _process_manager = pm


def set_audit_logger(al) -> None:
    """Set the AuditLogger instance for action logging."""
    global _audit_logger
    _audit_logger = al


# -------------------------------------------------------------------
# SafetyManager (Task 2.2)
# -------------------------------------------------------------------


class SafetyManager:
    """Track E-stop state and system safety status.

    Attributes:
        estop_active: Whether E-stop is currently engaged.
        estop_timestamp: ISO 8601 timestamp of last E-stop activation.
        active_arms: Number of active arms (placeholder, default 1).
    """

    def __init__(self) -> None:
        self.estop_active: bool = False
        self.estop_timestamp: Optional[str] = None
        self.active_arms: int = 1

    @property
    def can_connected(self) -> bool:
        """Check if CAN bus interface is available."""
        return CAN_AVAILABLE

    def activate_estop(self) -> None:
        """Set E-stop state to active with current timestamp."""
        self.estop_active = True
        self.estop_timestamp = datetime.now(timezone.utc).isoformat()

    def clear_estop(self) -> None:
        """Clear E-stop state."""
        self.estop_active = False

    def get_status(self) -> dict:
        """Return safety status as a dict."""
        return {
            "estop_active": self.estop_active,
            "active_arms": self.active_arms,
            "can_connected": self.can_connected,
            "last_estop": self.estop_timestamp,
        }


# Module-level SafetyManager instance
_safety_manager = SafetyManager()


# -------------------------------------------------------------------
# CAN helper
# -------------------------------------------------------------------


def _send_can_estop() -> bool:
    """Send CAN emergency stop frame (ID 0x00, data [0x01]).

    Returns True if sent successfully, False otherwise.
    """
    if not CAN_AVAILABLE:
        logger.warning("CAN not available -- E-stop CAN frame not sent")
        return False

    try:
        bus = can.Bus(interface="socketcan", channel="can0")
        msg = can.Message(
            arbitration_id=0x00,
            data=[0x01],
            is_extended_id=False,
        )
        bus.send(msg)
        bus.shutdown()
        return True
    except Exception:
        logger.exception("Failed to send CAN E-stop frame")
        return False


# -------------------------------------------------------------------
# Shutdown helper
# -------------------------------------------------------------------


def _schedule_shutdown() -> None:
    """Schedule system shutdown via sudo shutdown -h now."""
    try:
        subprocess.Popen(
            ["sudo", "shutdown", "-h", "now"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        logger.exception("Failed to schedule system shutdown")


# -------------------------------------------------------------------
# Pydantic request models
# -------------------------------------------------------------------


class EstopResetRequest(BaseModel):
    """Request body for E-stop reset."""

    confirm: bool = False


class EmergencyShutdownRequest(BaseModel):
    """Request body for emergency shutdown."""

    token: str = ""


# -------------------------------------------------------------------
# FastAPI Router
# -------------------------------------------------------------------

safety_router = APIRouter(tags=["Safety"])


@safety_router.post("/api/estop")
async def activate_estop() -> dict:
    """Activate emergency stop.

    Sends CAN E-stop frame, stops all managed processes, and updates state.
    No confirmation required -- fire and forget.
    """
    # Send CAN E-stop frame
    can_sent = _send_can_estop()

    # Stop all managed processes
    processes_stopped = 0
    if _process_manager is not None:
        # Count running processes before stopping
        registry = getattr(_process_manager, "_registry", {})
        processes_stopped = sum(
            1
            for entry in registry.values()
            if entry.get("status") == "running"
        )
        await _process_manager.stop_all()

    # Update safety state
    _safety_manager.activate_estop()

    # Log action
    if _audit_logger is not None:
        _audit_logger.log(
            "estop",
            {"can_sent": can_sent, "processes_stopped": processes_stopped},
            "estop_activated",
        )

    return {
        "status": "estop_activated",
        "can_sent": can_sent,
        "processes_stopped": processes_stopped,
    }


@safety_router.post("/api/estop/reset")
async def reset_estop(body: EstopResetRequest) -> dict:
    """Reset E-stop state.

    Requires ``{"confirm": true}`` in request body.
    """
    if not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="E-stop reset requires confirm: true",
        )

    _safety_manager.clear_estop()

    # Log action
    if _audit_logger is not None:
        _audit_logger.log("estop_reset", {}, "estop_cleared")

    return {"status": "estop_cleared"}


@safety_router.get("/api/safety/status")
async def get_safety_status() -> dict:
    """Return current safety system status."""
    return _safety_manager.get_status()


@safety_router.post("/api/emergency-shutdown")
async def emergency_shutdown(body: EmergencyShutdownRequest) -> dict:
    """Initiate emergency shutdown.

    Requires ``{"token": "SHUTDOWN"}`` in request body.
    Activates E-stop first, then schedules system shutdown.
    """
    if body.token != "SHUTDOWN":
        raise HTTPException(
            status_code=400,
            detail="Emergency shutdown requires token: SHUTDOWN",
        )

    # Activate E-stop first
    can_sent = _send_can_estop()

    processes_stopped = 0
    if _process_manager is not None:
        registry = getattr(_process_manager, "_registry", {})
        processes_stopped = sum(
            1
            for entry in registry.values()
            if entry.get("status") == "running"
        )
        await _process_manager.stop_all()

    _safety_manager.activate_estop()

    if _audit_logger is not None:
        _audit_logger.log(
            "estop",
            {"can_sent": can_sent, "processes_stopped": processes_stopped},
            "estop_activated",
        )

    # Schedule system shutdown
    _schedule_shutdown()

    # Log shutdown action
    if _audit_logger is not None:
        _audit_logger.log(
            "emergency_shutdown",
            {"token_provided": True},
            "shutdown_initiated",
        )

    return {"status": "shutdown_initiated"}
