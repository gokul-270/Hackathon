"""Entity Proxy — entity-scoped API routes that proxy to RPi agents or local.

Provides per-entity endpoints for health, ROS2 introspection, systemd
services, and emergency stop. Remote entities proxy to the lightweight
RPi agent (port 8091). Local entity uses psutil / local system_state.

Phase 3, Tasks 3.2 and 3.7 of dashboard-entity-core.
Proxy helpers consolidated: dashboard-reliability-hardening task 1.3.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone


import httpx
import psutil
from fastapi import APIRouter, HTTPException, Request

from .entity_manager import AGENT_PORT
from .entity_model import Entity
from .entity_proxy_helpers import (
    _PROXY_NETWORK_ERRORS,
    _PROXY_TIMEOUT_S,
    _get_entity_or_404,
    _get_mgr_or_503,
    _proxy_get,
    _proxy_post,
    _wrap_response,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

entity_proxy_router = APIRouter(prefix="/api/entities", tags=["entity-proxy"])


# ---------------------------------------------------------------------------
# Helpers (local to this module)
# ---------------------------------------------------------------------------


def _get_local_system_state() -> dict:
    """Return the shared system_state dict from ros2_monitor.

    Isolated in a function so tests can mock it easily.
    """
    try:
        from .ros2_monitor import system_state

        return system_state
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# GET /api/entities/{entity_id}/images  — list detection images
# GET /api/entities/{entity_id}/images/{image_type}/{filename} — serve image
# ---------------------------------------------------------------------------


@entity_proxy_router.get("/{entity_id}/images")
async def get_entity_images(entity_id: str):
    """List detection images on an entity."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        # Local: list from local data dirs
        import os
        from pathlib import Path

        home = Path.home()
        image_dirs = {
            "input": home / "pragati_ros2" / "data" / "inputs",
            "output": home / "pragati_ros2" / "data" / "outputs",
        }
        files = []
        for img_type, img_dir in image_dirs.items():
            if not img_dir.is_dir():
                continue
            for fpath in img_dir.iterdir():
                if not fpath.is_file():
                    continue
                if fpath.suffix.lower() not in (".jpg", ".jpeg", ".png"):
                    continue
                stat = fpath.stat()
                files.append(
                    {
                        "name": fpath.name,
                        "type": img_type,
                        "size_bytes": stat.st_size,
                        "modified": datetime.fromtimestamp(
                            stat.st_mtime, tz=timezone.utc
                        ).isoformat(),
                    }
                )
        files.sort(key=lambda f: f["modified"] or "", reverse=True)
        return _wrap_response(entity_id, "local", {"images": files[:100]})

    data = await _proxy_get(entity, "/images")
    return _wrap_response(entity_id, "remote", data)


@entity_proxy_router.get("/{entity_id}/images/{image_type}/{filename}")
async def get_entity_image_file(entity_id: str, image_type: str, filename: str):
    """Serve a detection image from an entity."""
    entity = _get_entity_or_404(entity_id)

    # Validate image_type
    if image_type not in ("input", "output"):
        raise HTTPException(status_code=400, detail="Type must be 'input' or 'output'")
    # Path traversal check
    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    if entity.source == "local":
        from pathlib import Path
        from starlette.responses import FileResponse

        home = Path.home()
        dirs = {
            "input": home / "pragati_ros2" / "data" / "inputs",
            "output": home / "pragati_ros2" / "data" / "outputs",
        }
        fpath = dirs[image_type] / filename
        if not fpath.is_file():
            raise HTTPException(status_code=404, detail="Image not found")
        media = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
        return FileResponse(str(fpath), media_type=media)

    # Remote: stream image bytes from agent
    url = f"{entity.agent_base_url(AGENT_PORT)}/images/{image_type}/{filename}"
    try:
        client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        req = client.build_request("GET", url)
        resp = await client.send(req, stream=True)
    except _PROXY_NETWORK_ERRORS as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Agent at {entity.ip} unreachable: {exc}",
        )

    if resp.status_code != 200:
        await resp.aclose()
        await client.aclose()
        raise HTTPException(status_code=resp.status_code, detail="Agent error")

    from starlette.responses import StreamingResponse as _SR

    async def _stream():
        try:
            async for chunk in resp.aiter_bytes(chunk_size=65536):
                yield chunk
        finally:
            await resp.aclose()
            await client.aclose()

    return _SR(
        _stream(),
        media_type=resp.headers.get("content-type", "image/jpeg"),
        headers={"Cache-Control": "public, max-age=3600"},
    )


@entity_proxy_router.delete("/{entity_id}/images/{image_type}/{filename}")
async def delete_entity_image(entity_id: str, image_type: str, filename: str):
    """Delete a single detection image on an entity."""
    entity = _get_entity_or_404(entity_id)

    if image_type not in ("input", "output"):
        raise HTTPException(status_code=400, detail="Type must be 'input' or 'output'")
    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    if entity.source == "local":
        from pathlib import Path

        home = Path.home()
        dirs = {
            "input": home / "pragati_ros2" / "data" / "inputs",
            "output": home / "pragati_ros2" / "data" / "outputs",
        }
        fpath = dirs[image_type] / filename
        if not fpath.is_file():
            raise HTTPException(status_code=404, detail="Image not found")
        fpath.unlink()
        return _wrap_response(entity_id, "local", {"deleted": 1, "files": [filename]})

    data = await _proxy_post(
        entity, f"/images/delete", {"filenames": [filename], "image_type": image_type}
    )
    return _wrap_response(entity_id, "remote", data)


@entity_proxy_router.post("/{entity_id}/images/delete")
async def bulk_delete_entity_images(entity_id: str, request: Request):
    """Bulk-delete detection images on an entity."""
    entity = _get_entity_or_404(entity_id)
    body = await request.json()

    if entity.source == "local":
        from pathlib import Path

        home = Path.home()
        dirs = {
            "input": home / "pragati_ros2" / "data" / "inputs",
            "output": home / "pragati_ros2" / "data" / "outputs",
        }
        deleted = []
        image_type = body.get("image_type", "all")
        scan_dirs = dirs.items() if image_type == "all" else [(image_type, dirs.get(image_type))]

        if body.get("filenames"):
            for fname in body["filenames"]:
                if ".." in fname or "/" in fname:
                    continue
                for _, d in scan_dirs:
                    if d is None:
                        continue
                    fpath = d / fname
                    if fpath.is_file():
                        fpath.unlink()
                        deleted.append(fname)
                        break
        elif body.get("before"):
            cutoff = datetime.fromisoformat(body["before"])
            for _, d in scan_dirs:
                if d is None or not d.is_dir():
                    continue
                for fpath in d.iterdir():
                    if not fpath.is_file():
                        continue
                    if fpath.suffix.lower() not in (".jpg", ".jpeg", ".png"):
                        continue
                    mtime = datetime.fromtimestamp(fpath.stat().st_mtime, tz=timezone.utc)
                    if mtime < cutoff:
                        fpath.unlink()
                        deleted.append(fpath.name)

        return _wrap_response(entity_id, "local", {"deleted": len(deleted), "files": deleted})

    data = await _proxy_post(entity, "/images/delete", body)
    return _wrap_response(entity_id, "remote", data)


# ---------------------------------------------------------------------------
# GET /api/entities/{entity_id}/health  (Task 3.2)
# ---------------------------------------------------------------------------


@entity_proxy_router.get("/{entity_id}/health")
async def get_entity_health(entity_id: str):
    """Get health metrics for an entity."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        data = {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage("/").percent,
        }
        return _wrap_response(entity_id, "local", data)

    # Remote: proxy to agent
    data = await _proxy_get(entity, "/health")
    return _wrap_response(entity_id, "remote", data)


# ---------------------------------------------------------------------------
# GET /api/entities/{entity_id}/ros2/nodes
# NOTE: These endpoints are now handled by entity_ros2_router with full type info
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# GET /api/entities/{entity_id}/ros2/topics
# NOTE: This endpoint is now handled by entity_ros2_router with full type info
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# GET /api/entities/{entity_id}/ros2/services
# NOTE: This endpoint is now handled by entity_ros2_router with full type info
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# GET /api/entities/{entity_id}/systemd/services  (Task 3.2)
# ---------------------------------------------------------------------------


@entity_proxy_router.get("/{entity_id}/systemd/services")
async def get_entity_systemd_services(entity_id: str):
    """Get systemd services for an entity."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        # Local dev machine: no RPi systemd services to report
        return _wrap_response(entity_id, "local", {"services": []})

    data = await _proxy_get(entity, "/systemd/services")
    return _wrap_response(entity_id, "remote", data)


# ---------------------------------------------------------------------------
# POST /api/entities/{entity_id}/systemd/services/{name}/restart
# ---------------------------------------------------------------------------


@entity_proxy_router.post("/{entity_id}/systemd/services/{service_name}/restart")
async def restart_entity_systemd_service(entity_id: str, service_name: str):
    """Restart a systemd service on an entity."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        raise HTTPException(
            status_code=400,
            detail="Systemd service restart not supported on local entity",
        )

    data = await _proxy_post(entity, f"/systemd/services/{service_name}/restart")
    return _wrap_response(entity_id, "remote", data)


# ---------------------------------------------------------------------------
# POST /api/entities/{entity_id}/estop  (Task 3.7)
# ---------------------------------------------------------------------------


def _local_emergency_stop() -> tuple[bool, str | None]:
    """Attempt a local emergency stop via ROS2 service call.

    Returns (success, error_message).
    """
    try:
        import subprocess

        result = subprocess.run(
            [
                "ros2",
                "service",
                "call",
                "/emergency_stop",
                "std_srvs/srv/Trigger",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return (True, None)
        return (False, f"ros2 service call failed: {result.stderr}")
    except Exception as exc:
        return (False, str(exc))


@entity_proxy_router.post("/{entity_id}/estop")
async def entity_estop(entity_id: str):
    """Emergency stop for an entity.

    For remote entities: forwards to agent's pragati-arm restart endpoint.
    For local entity: calls local ROS2 emergency stop service.

    Always returns per-entity result tracking:
    {entity_id, success, error}
    """
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        success, error = _local_emergency_stop()
        return {
            "entity_id": entity_id,
            "success": success,
            "error": error,
        }

    # Remote: try agent estop endpoint, fall back to systemd restart
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(_PROXY_TIMEOUT_S)) as client:
            # Try dedicated estop endpoint first
            url = f"{entity.agent_base_url(AGENT_PORT)}" f"/systemd/services/pragati-arm/restart"
            resp = await client.post(url)

        if resp.status_code == 200:
            return {
                "entity_id": entity_id,
                "success": True,
                "error": None,
            }
        return {
            "entity_id": entity_id,
            "success": False,
            "error": f"Agent returned status {resp.status_code}",
        }
    except _PROXY_NETWORK_ERRORS as exc:
        return {
            "entity_id": entity_id,
            "success": False,
            "error": f"Agent unreachable: {exc}",
        }
    except Exception as exc:
        return {
            "entity_id": entity_id,
            "success": False,
            "error": str(exc),
        }
