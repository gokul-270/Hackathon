"""
Health — Startup health registry, /health endpoint, and status/capabilities routes.
"""

import logging
import os
import platform
import time
from typing import Any

from fastapi import APIRouter

try:
    import psutil

    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False

from backend.ros2_monitor import filter_dashboard_internals
from backend.version import get_version

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

# ---------------------------------------------------------------------------
# Health registry
# ---------------------------------------------------------------------------
_startup_time: float = 0.0
_modules_loaded: list[str] = []
_modules_failed: list[dict[str, str]] = []


def init_health_registry():
    """Initialize the health registry at startup."""
    global _startup_time
    _startup_time = time.time()
    _modules_loaded.clear()
    _modules_failed.clear()


def register_module_ok(name: str):
    """Register a module that loaded successfully."""
    _modules_loaded.append(name)
    logger.info(
        '{"event": "module_loaded", "module": "%s", "status": "ok"}',
        name,
    )


def register_module_failed(name: str, error: str):
    """Register a module that failed to load."""
    _modules_failed.append({"name": name, "error": error})
    logger.error(
        '{"event": "module_load_failed", "module": "%s", "error": "%s"}',
        name,
        error,
    )


# ---------------------------------------------------------------------------
# Dependencies injected at startup (status / capabilities / system-info)
# ---------------------------------------------------------------------------
_system_state = None
_capabilities_manager = None
_message_envelope = None
_server_start_time: float = 0.0


def init_status_deps(
    system_state, capabilities_manager, message_envelope, server_start_time
):
    """Inject shared dependencies used by the status endpoints."""
    global _system_state, _capabilities_manager, _message_envelope, _server_start_time
    _system_state = system_state
    _capabilities_manager = capabilities_manager
    _message_envelope = message_envelope
    _server_start_time = server_start_time


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """Return startup health status with optional system metrics."""
    status = "healthy" if not _modules_failed else "degraded"
    uptime = time.time() - _startup_time if _startup_time else 0.0
    result: dict[str, Any] = {
        "status": status,
        "modules_loaded": list(_modules_loaded),
        "modules_failed": list(_modules_failed),
        "uptime_seconds": round(uptime, 2),
    }
    if _PSUTIL_AVAILABLE:
        result["cpu_percent"] = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        result["memory_percent"] = round(mem.percent, 1)
    return result


@router.get("/api/status")
async def get_system_status():
    """Get complete system status."""
    filtered_state = _system_state.copy()
    filtered_state["nodes"] = filter_dashboard_internals(_system_state["nodes"])
    filtered_state["topics"] = filter_dashboard_internals(_system_state["topics"])
    filtered_state["services"] = filter_dashboard_internals(_system_state["services"])

    if _capabilities_manager and _message_envelope:
        return _message_envelope.create_envelope("system_status", filtered_state)
    return {"data": filtered_state}


@router.get("/api/capabilities")
async def get_capabilities():
    """Get enabled capabilities."""
    version = get_version()
    if _capabilities_manager:
        return {
            "enabled": _capabilities_manager.get_enabled_capabilities(),
            "all_capabilities": list(_capabilities_manager.capabilities.keys()),
            "server_version": version,
        }
    return {
        "enabled": [],
        "all_capabilities": [],
        "server_version": version,
    }


@router.get("/api/system/info")
async def get_system_info():
    """Return system identity information for the settings panel."""
    ros_distro = os.environ.get("ROS_DISTRO", "unknown")
    server_version = get_version()
    return {
        "dashboard_version": server_version,
        "ros_distro": ros_distro,
        "hostname": platform.node(),
        "platform": f"{platform.system()} {platform.release()}",
        "python_version": platform.python_version(),
        "uptime_seconds": int(time.time() - _server_start_time),
    }
