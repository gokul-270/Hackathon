"""Entity System Stats Router — proxy system stats to RPi agents or local.

Provides per-entity endpoints for system resource monitoring:
  GET /api/entities/{entity_id}/system/stats
  GET /api/entities/{entity_id}/system/processes

Remote entities proxy to the RPi agent (port 8091).
Local entity collects directly via psutil.

Part of dashboard-system-stats change.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx
import psutil
from fastapi import APIRouter, HTTPException

from .entity_manager import AGENT_PORT, get_entity_manager
from .entity_model import Entity

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

entity_system_stats_router = APIRouter(
    prefix="/api/entities", tags=["entity-system-stats"]
)

# Timeout for agent proxy requests (seconds)
_PROXY_TIMEOUT_S = 20

# Network errors that indicate agent unreachable
_PROXY_NETWORK_ERRORS = (
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
    OSError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_entity_or_404(entity_id: str) -> Entity:
    """Look up an entity by ID or raise 404."""
    mgr = get_entity_manager()
    if mgr is None:
        raise HTTPException(status_code=503, detail="EntityManager not initialized")
    entity = mgr.get_entity(entity_id)
    if entity is None:
        raise HTTPException(
            status_code=404,
            detail=f"Entity '{entity_id}' not found",
        )
    return entity


async def _proxy_get(entity: Entity, path: str) -> dict[str, Any]:
    """Proxy a GET request to a remote entity's agent."""
    url = f"{entity.agent_base_url(AGENT_PORT)}{path}"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(_PROXY_TIMEOUT_S)) as client:
            resp = await client.get(url)
        if resp.status_code == 200:
            return resp.json()
        raise HTTPException(
            status_code=502,
            detail=f"Agent at {entity.ip} returned status {resp.status_code}",
        )
    except _PROXY_NETWORK_ERRORS as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Agent at {entity.ip} unreachable: {exc}",
        )


def _wrap_response(entity_id: str, source: str, data: Any) -> dict[str, Any]:
    """Standard envelope for proxy responses."""
    return {
        "entity_id": entity_id,
        "source": source,
        "data": data,
    }


def _collect_local_stats() -> dict:
    """Collect system stats locally via psutil (for local entity)."""
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    temps = psutil.sensors_temperatures()
    cpu_temp: Optional[float] = None
    if temps:
        first_sensor = next(iter(temps.values()))
        if first_sensor:
            cpu_temp = first_sensor[0].current

    return {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "memory_used": mem.used,
        "memory_total": mem.total,
        "disk_used": disk.used,
        "disk_total": disk.total,
        "cpu_temp": cpu_temp,
    }


def _collect_local_processes() -> list[dict]:
    """Collect top 15 processes locally via psutil (for local entity)."""
    procs = []
    for proc in psutil.process_iter(
        ["pid", "name", "cpu_percent", "memory_info", "status"]
    ):
        try:
            info = proc.info
            procs.append(
                {
                    "pid": info["pid"],
                    "name": info["name"] or "",
                    "cpu_percent": info["cpu_percent"] or 0.0,
                    "memory_mb": round(
                        (
                            (info["memory_info"].rss / (1024 * 1024))
                            if info["memory_info"]
                            else 0.0
                        ),
                        1,
                    ),
                    "status": info["status"] or "unknown",
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    procs.sort(key=lambda p: p["cpu_percent"], reverse=True)
    return procs[:15]


# ---------------------------------------------------------------------------
# GET /api/entities/{entity_id}/system/stats
# ---------------------------------------------------------------------------


@entity_system_stats_router.get("/{entity_id}/system/stats")
async def get_entity_system_stats(entity_id: str):
    """Get system stats (CPU, RAM, disk, temp) for an entity."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        data = _collect_local_stats()
        return _wrap_response(entity_id, "local", data)

    data = await _proxy_get(entity, "/system/stats")
    return _wrap_response(entity_id, "remote", data)


# ---------------------------------------------------------------------------
# GET /api/entities/{entity_id}/system/processes
# ---------------------------------------------------------------------------


@entity_system_stats_router.get("/{entity_id}/system/processes")
async def get_entity_system_processes(entity_id: str):
    """Get top 15 processes by CPU for an entity."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        data = _collect_local_processes()
        return _wrap_response(entity_id, "local", data)

    data = await _proxy_get(entity, "/system/processes")
    return _wrap_response(entity_id, "remote", data)
