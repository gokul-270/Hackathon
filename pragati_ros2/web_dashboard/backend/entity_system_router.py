"""Entity System Router — entity-scoped system management API routes.

Provides per-entity endpoints for systemd service management and
system lifecycle (reboot/shutdown). Remote entities proxy to the
RPi agent. Local entity dispatches to existing systemd_api logic
or subprocess calls.

Phase 4, Tasks 4.1–4.5 of dashboard-system-management.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .entity_manager import AGENT_PORT, get_entity_manager
from .entity_model import Entity
from .systemd_api import (
    ALLOWED_SERVICES,
    _get_service_status,
    _run_systemctl,
    _validate_service_name,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

entity_system_router = APIRouter(prefix="/api/entities", tags=["entity-system"])

# Timeout for agent proxy requests (seconds)
_PROXY_TIMEOUT_S = 20

# Valid service actions
_VALID_ACTIONS = {"start", "stop", "restart", "enable", "disable"}

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


class RebootRequest(BaseModel):
    token: str = ""


class ShutdownRequest(BaseModel):
    token: str = ""


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
        return JSONResponse(
            status_code=resp.status_code,
            content=(
                resp.json()
                if resp.headers.get("content-type", "").startswith("application/json")
                else {
                    "error": "agent_error",
                    "message": (f"Agent returned status {resp.status_code}"),
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
                    "message": (f"Agent returned status {resp.status_code}"),
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
# Endpoints: List services
# ---------------------------------------------------------------------------


@entity_system_router.get("/{entity_id}/system/services")
async def list_entity_services(entity_id: str):
    """List systemd service status for an entity."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        services = []
        for name in ALLOWED_SERVICES:
            try:
                status = await _get_service_status(name)
                services.append(status)
            except Exception as exc:
                services.append(
                    {
                        "name": name,
                        "active_state": "unknown",
                        "sub_state": "unknown",
                        "enabled": False,
                        "error": str(exc),
                    }
                )
        return _wrap_response(entity_id, "local", {"services": services})

    # Remote: proxy to agent
    data = await _proxy_get(entity, "/systemd/services")
    if isinstance(data, JSONResponse):
        return data
    return _wrap_response(entity_id, "remote", data)


# ---------------------------------------------------------------------------
# Endpoints: Service actions (start/stop/restart/enable/disable)
# ---------------------------------------------------------------------------


@entity_system_router.post("/{entity_id}/system/services/{name}/{action}")
async def entity_service_action(entity_id: str, name: str, action: str):
    """Perform a service action on an entity."""
    entity = _get_entity_or_404(entity_id)

    # Validate service name (403 for disallowed)
    _validate_service_name(name)

    # Validate action
    if action not in _VALID_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid action '{action}'. " f"Allowed: {sorted(_VALID_ACTIONS)}"
            ),
        )

    if entity.source == "local":
        stdout, stderr, rc = await _run_systemctl(action, f"{name}.service")
        if rc != 0:
            raise HTTPException(
                status_code=502,
                detail=f"systemctl {action} failed: {stderr.strip()}",
            )
        return _wrap_response(
            entity_id,
            "local",
            {"success": True, "service": name, "action": action},
        )

    # Remote: proxy to agent
    data = await _proxy_post(entity, f"/systemd/services/{name}/{action}", None)
    if isinstance(data, JSONResponse):
        return data
    return _wrap_response(entity_id, "remote", data)


# ---------------------------------------------------------------------------
# Endpoints: Service logs
# ---------------------------------------------------------------------------


@entity_system_router.get("/{entity_id}/system/services/{name}/logs")
async def get_entity_service_logs(
    entity_id: str,
    name: str,
    lines: int = Query(200, ge=1, le=10000),
):
    """Fetch journal log lines for a service on an entity."""
    entity = _get_entity_or_404(entity_id)

    # Validate service name (403 for disallowed)
    _validate_service_name(name)

    if entity.source == "local":
        proc = await asyncio.create_subprocess_exec(
            "journalctl",
            "-u",
            f"{name}.service",
            "--no-pager",
            "-n",
            str(lines),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _stderr = await proc.communicate()

        output = stdout.decode("utf-8", errors="replace")
        log_lines = [line for line in output.splitlines() if line.strip()]

        return _wrap_response(
            entity_id,
            "local",
            {
                "service": name,
                "lines": log_lines,
                "count": len(log_lines),
            },
        )

    # Remote: proxy to agent
    data = await _proxy_get(
        entity,
        f"/systemd/services/{name}/logs?lines={lines}",
    )
    if isinstance(data, JSONResponse):
        return data
    return _wrap_response(entity_id, "remote", data)


# ---------------------------------------------------------------------------
# Endpoints: Reboot
# ---------------------------------------------------------------------------


@entity_system_router.post("/{entity_id}/system/reboot")
async def entity_reboot(entity_id: str, body: RebootRequest):
    """Reboot an entity. Requires token: REBOOT."""
    entity = _get_entity_or_404(entity_id)

    if body.token != "REBOOT":
        raise HTTPException(
            status_code=403,
            detail="Reboot requires token: REBOOT",
        )

    if entity.source == "local":
        try:
            subprocess.Popen(
                ["sudo", "reboot"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            logger.exception("Failed to initiate local reboot")
        return _wrap_response(
            entity_id,
            "local",
            {"status": "reboot_initiated"},
        )

    # Remote: proxy to agent
    data = await _proxy_post(
        entity,
        "/system/reboot",
        json_body={"token": "REBOOT"},
    )
    if isinstance(data, JSONResponse):
        return data
    return _wrap_response(entity_id, "remote", data)


# ---------------------------------------------------------------------------
# Endpoints: Shutdown
# ---------------------------------------------------------------------------


@entity_system_router.post("/{entity_id}/system/shutdown")
async def entity_shutdown(entity_id: str, body: ShutdownRequest):
    """Shutdown an entity. Requires token: SHUTDOWN."""
    entity = _get_entity_or_404(entity_id)

    if body.token != "SHUTDOWN":
        raise HTTPException(
            status_code=403,
            detail="Shutdown requires token: SHUTDOWN",
        )

    if entity.source == "local":
        try:
            subprocess.Popen(
                ["sudo", "shutdown", "-h", "now"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            logger.exception("Failed to initiate local shutdown")
        return _wrap_response(
            entity_id,
            "local",
            {"status": "shutdown_initiated"},
        )

    # Remote: proxy to agent
    data = await _proxy_post(
        entity,
        "/system/shutdown",
        json_body={"token": "SHUTDOWN"},
    )
    if isinstance(data, JSONResponse):
        return data
    return _wrap_response(entity_id, "remote", data)
