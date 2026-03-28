"""Entity Rosbag Router — entity-scoped rosbag API routes.

Provides per-entity endpoints for bag listing, recording start/stop/status,
downloading, and playback start/stop.
Remote entities proxy to the RPi agent. Local entity dispatches to
existing bag_api logic.

Phase 3b, Tasks 4.1–4.3 of dashboard-motor-rosbag.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from .entity_manager import AGENT_PORT, get_entity_manager
from .entity_model import Entity

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

entity_rosbag_router = APIRouter(prefix="/api/entities", tags=["entity-rosbag"])

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
# Pydantic models
# ---------------------------------------------------------------------------


class RecordStartRequest(BaseModel):
    profile: str = "default"


class PlayStartRequest(BaseModel):
    bag_name: str


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


async def _proxy_get(entity: Entity, path: str, timeout: float = _PROXY_TIMEOUT_S) -> Any:
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


async def _proxy_stream(entity: Entity, path: str) -> StreamingResponse:
    """Proxy a GET request as a streaming response (for large downloads)."""
    url = f"{entity.agent_base_url(AGENT_PORT)}{path}"
    client = httpx.AsyncClient(timeout=httpx.Timeout(300.0))
    try:
        req = client.build_request("GET", url)
        resp = await client.send(req, stream=True)
    except _PROXY_NETWORK_ERRORS as exc:
        await client.aclose()
        raise HTTPException(
            status_code=502,
            detail=f"Agent at {entity.ip} unreachable: {exc}",
        )

    if resp.status_code != 200:
        body = await resp.aread()
        await resp.aclose()
        await client.aclose()
        raise HTTPException(
            resp.status_code,
            detail=f"Agent error: {resp.status_code}",
        )

    async def _stream_gen():
        try:
            async for chunk in resp.aiter_bytes(chunk_size=65536):
                yield chunk
        finally:
            await resp.aclose()
            await client.aclose()

    content_disp = resp.headers.get(
        "content-disposition",
        f'attachment; filename="{path.split("/")[-1]}.tar.gz"',
    )
    return StreamingResponse(
        _stream_gen(),
        media_type=resp.headers.get("content-type", "application/gzip"),
        headers={"Content-Disposition": content_disp},
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
# Local rosbag logic helpers (delegate to existing bag_api)
# ---------------------------------------------------------------------------

# Module-level playback state (local entity only)
_playback_state: dict | None = None


async def _local_list_bags() -> list[dict]:
    """List bags using local bag_api logic."""
    try:
        from . import bag_api

        bags: list[dict] = []
        bags_dir = bag_api.BAGS_DIR
        if not bags_dir.exists():
            return []
        entries = sorted(
            bags_dir.iterdir(),
            key=lambda p: bag_api._safe_mtime(p),
            reverse=True,
        )
        for entry in entries:
            if entry.is_dir() or (entry.is_file() and entry.suffix == ".mcap"):
                meta = await bag_api._get_bag_metadata(entry)
                bags.append(meta)
        return bags
    except Exception as exc:
        logger.error("Local list_bags failed: %s", exc)
        return []


async def _local_record_start(profile: str) -> dict:
    """Start recording using local bag_api logic."""
    from . import bag_api

    body = bag_api.RecordStartRequest(profile=profile)
    return await bag_api.record_start(body)


async def _local_record_stop() -> dict:
    """Stop recording using local bag_api logic."""
    from . import bag_api

    return await bag_api.record_stop()


async def _local_record_status() -> dict:
    """Get recording status using local bag_api logic."""
    from . import bag_api

    return await bag_api.record_status()


async def _local_download(name: str) -> StreamingResponse:
    """Download a bag using local bag_api logic."""
    from . import bag_api

    bag_path = bag_api._resolve_bag_path(name)
    if bag_path is None:
        raise HTTPException(
            status_code=404,
            detail=f"Bag '{name}' not found",
        )

    if bag_path.is_file():
        return StreamingResponse(
            bag_api._stream_file(bag_path),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": (f'attachment; filename="{name}.mcap"'),
            },
        )

    # Directory — stream as tar.gz
    return StreamingResponse(
        bag_api._stream_tar_gz(bag_path),
        media_type="application/gzip",
        headers={
            "Content-Disposition": (f'attachment; filename="{name}.tar.gz"'),
        },
    )


async def _local_play_start(bag_name: str) -> dict:
    """Start rosbag playback for a local entity."""
    from . import bag_api

    global _playback_state

    # Cannot play while recording
    if bag_api._recording_state is not None:
        proc = bag_api._recording_state["process"]
        if proc.returncode is None:
            raise HTTPException(
                status_code=409,
                detail="Cannot play while recording is active",
            )

    if _playback_state is not None:
        proc = _playback_state["process"]
        if proc.returncode is None:
            raise HTTPException(
                status_code=409,
                detail="Playback already active",
            )
        # Process exited — clean up stale state
        _playback_state = None

    bag_path = bag_api._resolve_bag_path(bag_name)
    if bag_path is None:
        raise HTTPException(
            status_code=404,
            detail=f"Bag '{bag_name}' not found",
        )

    try:
        proc = await asyncio.create_subprocess_exec(
            "ros2",
            "bag",
            "play",
            str(bag_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except Exception as exc:
        logger.exception("Failed to start ros2 bag play")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start playback: {exc}",
        ) from exc

    _playback_state = {
        "process": proc,
        "bag_name": bag_name,
        "start_time": time.time(),
        "pid": proc.pid,
    }
    logger.info("Started playback: bag=%s pid=%d", bag_name, proc.pid)
    return {"playing": True, "bag_name": bag_name, "pid": proc.pid}


async def _local_play_stop() -> dict:
    """Stop rosbag playback for a local entity."""
    import signal

    global _playback_state

    if _playback_state is None:
        raise HTTPException(
            status_code=409,
            detail="No active playback",
        )

    proc = _playback_state["process"]
    bag_name = _playback_state["bag_name"]

    # Graceful stop via SIGINT
    try:
        proc.send_signal(signal.SIGINT)
    except ProcessLookupError:
        logger.warning("Playback process already exited (pid=%d)", proc.pid)

    # Wait up to 10 seconds, then SIGKILL
    try:
        await asyncio.wait_for(proc.wait(), timeout=10.0)
    except asyncio.TimeoutError:
        logger.warning(
            "Playback did not stop within 10s, sending SIGKILL (pid=%d)",
            proc.pid,
        )
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        await proc.wait()

    logger.info("Stopped playback: bag=%s", bag_name)
    _playback_state = None
    return {"playing": False, "bag_name": bag_name}


# ---------------------------------------------------------------------------
# Endpoints: List bags
# ---------------------------------------------------------------------------


@entity_rosbag_router.get("/{entity_id}/rosbag/list")
async def get_entity_rosbag_list(entity_id: str):
    """List recorded bags for an entity."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        data = await _local_list_bags()
        return _wrap_response(entity_id, "local", data)

    data = await _proxy_get(entity, "/rosbag/list")
    if isinstance(data, JSONResponse):
        return data
    return _wrap_response(entity_id, "remote", data)


# ---------------------------------------------------------------------------
# Endpoints: Record start / stop / status
# ---------------------------------------------------------------------------


@entity_rosbag_router.post("/{entity_id}/rosbag/record/start")
async def post_entity_rosbag_record_start(entity_id: str, body: RecordStartRequest):
    """Start rosbag recording on an entity."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        data = await _local_record_start(body.profile)
        return _wrap_response(entity_id, "local", data)

    data = await _proxy_post(
        entity,
        "/rosbag/record/start",
        json_body=body.model_dump(),
    )
    if isinstance(data, JSONResponse):
        return data
    return _wrap_response(entity_id, "remote", data)


@entity_rosbag_router.post("/{entity_id}/rosbag/record/stop")
async def post_entity_rosbag_record_stop(entity_id: str):
    """Stop rosbag recording on an entity."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        data = await _local_record_stop()
        return _wrap_response(entity_id, "local", data)

    data = await _proxy_post(entity, "/rosbag/record/stop")
    if isinstance(data, JSONResponse):
        return data
    return _wrap_response(entity_id, "remote", data)


@entity_rosbag_router.get("/{entity_id}/rosbag/record/status")
async def get_entity_rosbag_record_status(entity_id: str):
    """Get recording status for an entity."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        data = await _local_record_status()
        return _wrap_response(entity_id, "local", data)

    data = await _proxy_get(entity, "/rosbag/record/status")
    if isinstance(data, JSONResponse):
        return data
    return _wrap_response(entity_id, "remote", data)


# ---------------------------------------------------------------------------
# Endpoints: Download bag
# ---------------------------------------------------------------------------


@entity_rosbag_router.get("/{entity_id}/rosbag/download/{name}")
async def get_entity_rosbag_download(entity_id: str, name: str):
    """Download a recorded bag from an entity."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        return await _local_download(name)

    # Stream proxy from agent — don't buffer in memory
    return await _proxy_stream(entity, f"/rosbag/download/{name}")


# ---------------------------------------------------------------------------
# Endpoints: Playback start / stop
# ---------------------------------------------------------------------------


@entity_rosbag_router.post("/{entity_id}/rosbag/play/start")
async def post_entity_rosbag_play_start(entity_id: str, body: PlayStartRequest):
    """Start rosbag playback on an entity."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        data = await _local_play_start(body.bag_name)
        return _wrap_response(entity_id, "local", data)

    data = await _proxy_post(
        entity,
        "/rosbag/play/start",
        json_body=body.model_dump(),
    )
    if isinstance(data, JSONResponse):
        return data
    return _wrap_response(entity_id, "remote", data)


@entity_rosbag_router.post("/{entity_id}/rosbag/play/stop")
async def post_entity_rosbag_play_stop(entity_id: str):
    """Stop rosbag playback on an entity."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        data = await _local_play_stop()
        return _wrap_response(entity_id, "local", data)

    data = await _proxy_post(entity, "/rosbag/play/stop")
    if isinstance(data, JSONResponse):
        return data
    return _wrap_response(entity_id, "remote", data)
