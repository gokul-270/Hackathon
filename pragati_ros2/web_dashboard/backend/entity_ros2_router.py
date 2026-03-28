"""Entity ROS2 Router — entity-scoped ROS2 introspection & logs proxy routes.

Provides per-entity endpoints for ROS2 topics, services, nodes, parameters,
and log access. Remote entities proxy to the lightweight RPi agent
(port 8091). Local entity uses ros2_monitor functions directly.

Phase 2, Tasks 2.1–2.8, 2.10 of dashboard-ros2-subtabs.
Proxy helpers consolidated: dashboard-reliability-hardening task 1.2.
"""

from __future__ import annotations

import asyncio
import logging
import os
import pathlib
import re
from datetime import datetime, timezone
from typing import Any

import httpx
import yaml
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from .entity_manager import AGENT_PORT
from .entity_model import Entity
from .entity_proxy_helpers import (
    _PROXY_NETWORK_ERRORS,
    _PROXY_TIMEOUT_S,
    _get_entity_or_404,
    _get_mgr_or_503,
    _proxy_get,
    _proxy_post,
    _proxy_put,
    _proxy_sse,
    _wrap_response,
)
from .ros2_monitor import (
    call_service,
    get_node_detail,
    get_nodes,
    get_parameters,
    get_services,
    get_topics,
    lifecycle_transition,
    set_parameter,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

entity_ros2_router = APIRouter(prefix="/api/entities", tags=["entity-ros2"])


# ---------------------------------------------------------------------------
# Pydantic models for request bodies
# ---------------------------------------------------------------------------


class ServiceCallRequest(BaseModel):
    """Request body for POST .../services/{name}/call."""

    service_type: str
    request: dict = {}


class SetParametersRequest(BaseModel):
    """Request body for PUT .../parameters/{node}."""

    params: list[dict]


def _get_publishable_topics() -> list[dict]:
    """Return the publishable topics allowlist from dashboard config."""
    try:
        config_path = pathlib.Path(__file__).resolve().parent.parent / "config" / "dashboard.yaml"
        if not config_path.exists():
            return []
        with open(config_path) as fh:
            config = yaml.safe_load(fh) or {}
        pragati = config.get("pragati") or {}
        return pragati.get("publishable_topics") or []
    except Exception:
        return []


def _get_log_dirs() -> list[str]:
    """Return the list of log directories to scan (shared by list + tail)."""
    env_dirs = os.environ.get("PRAGATI_LOG_DIRS", "")
    if env_dirs:
        return [d for d in env_dirs.split(":") if d]
    return [
        os.path.expanduser("~/pragati_ros2/log"),
        os.path.expanduser("~/.ros/log"),
    ]


def _list_local_logs() -> list[dict]:
    """List local log files from configured log directories."""
    log_dirs = _get_log_dirs()

    files: list[dict] = []
    for d in log_dirs:
        if not os.path.isdir(d):
            continue
        for root, _, filenames in os.walk(d):
            for f in filenames:
                fp = os.path.join(root, f)
                try:
                    stat = os.stat(fp)
                    files.append(
                        {
                            "name": f,
                            "path": os.path.relpath(fp, d),
                            "size_bytes": stat.st_size,
                            "modified": datetime.fromtimestamp(
                                stat.st_mtime, tz=timezone.utc
                            ).isoformat(),
                        }
                    )
                except OSError:
                    continue

    # Add journald special entry
    files.append(
        {
            "name": "System Journal (pragati-*)",
            "path": "__journald__",
            "size_bytes": 0,
            "modified": None,
        }
    )
    return files


# ---------------------------------------------------------------------------
# GET /api/entities/{entity_id}/ros2/topics  (Task 2.1)
# ---------------------------------------------------------------------------


@entity_ros2_router.get("/{entity_id}/ros2/topics")
async def get_entity_ros2_topics(entity_id: str):
    """Get ROS2 topics for an entity."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        data = get_topics()
        return _wrap_response(entity_id, "local", data)

    data = await _proxy_get(entity, "/ros2/topics")
    return _wrap_response(entity_id, "remote", data)


# ---------------------------------------------------------------------------
# GET /api/entities/{entity_id}/ros2/topics/{topic_name}/echo  (Task 2.2)
# ---------------------------------------------------------------------------


@entity_ros2_router.get("/{entity_id}/ros2/topics/{topic_name:path}/echo")
async def get_entity_ros2_topic_echo(entity_id: str, topic_name: str):
    """SSE stream of topic messages for an entity."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        raise HTTPException(
            status_code=501,
            detail="Local topic echo via SSE not yet implemented; use WebSocket",
        )

    # Remote: proxy SSE stream from agent
    return await _proxy_sse(entity, f"/ros2/topics/{topic_name}/echo")


# ---------------------------------------------------------------------------
# GET /api/entities/{entity_id}/ros2/services  (Task 2.3)
# ---------------------------------------------------------------------------


@entity_ros2_router.get("/{entity_id}/ros2/services")
async def get_entity_ros2_services(entity_id: str):
    """Get ROS2 services for an entity."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        data = get_services()
        return _wrap_response(entity_id, "local", data)

    data = await _proxy_get(entity, "/ros2/services")
    return _wrap_response(entity_id, "remote", data)


# ---------------------------------------------------------------------------
# POST /api/entities/{entity_id}/ros2/services/{service_name}/call  (Task 2.4)
# ---------------------------------------------------------------------------


@entity_ros2_router.post("/{entity_id}/ros2/services/{service_name:path}/call")
async def post_entity_ros2_service_call(
    entity_id: str, service_name: str, body: ServiceCallRequest
):
    """Call a ROS2 service on an entity."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        try:
            result = call_service(
                service_name=f"/{service_name}",
                service_type=body.service_type,
                request=body.request,
            )
            return _wrap_response(entity_id, "local", result)
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    data = await _proxy_post(
        entity,
        f"/ros2/services/{service_name}/call",
        json_body={"service_type": body.service_type, "request": body.request},
    )
    return _wrap_response(entity_id, "remote", data)


# ---------------------------------------------------------------------------
# POST /api/entities/{entity_id}/ros2/topics/{topic_name}/publish  (Task 5.3)
# ---------------------------------------------------------------------------


@entity_ros2_router.post("/{entity_id}/ros2/topics/{topic_name:path}/publish")
async def publish_ros2_topic(entity_id: str, topic_name: str, request: Request):
    """Proxy a topic publish request to the entity agent, after allowlist check."""
    from urllib.parse import unquote

    decoded_topic = unquote(topic_name)
    if not decoded_topic.startswith("/"):
        decoded_topic = "/" + decoded_topic

    # Validate against allowlist
    allowed = _get_publishable_topics()
    allowed_names = {entry.get("name") for entry in allowed if isinstance(entry, dict)}
    if decoded_topic not in allowed_names:
        return JSONResponse(
            status_code=403,
            content={"error": "Topic not in publishable allowlist"},
        )

    entity = _get_entity_or_404(entity_id)
    json_body: dict | None = None
    try:
        json_body = await request.json()
    except Exception:
        json_body = None

    proxy_path = f"/ros2/topics/{topic_name}/publish"
    data = await _proxy_post(entity, proxy_path, json_body=json_body)
    return _wrap_response(entity_id, "remote", data)


# ---------------------------------------------------------------------------
# GET /api/entities/{entity_id}/ros2/nodes  (Task 2.5)
# ---------------------------------------------------------------------------


@entity_ros2_router.get("/{entity_id}/ros2/nodes")
async def get_entity_ros2_nodes(entity_id: str):
    """Get ROS2 nodes for an entity."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        data = get_nodes()
        return _wrap_response(entity_id, "local", data)

    data = await _proxy_get(entity, "/ros2/nodes")
    return _wrap_response(entity_id, "remote", data)


# ---------------------------------------------------------------------------
# GET /api/entities/{entity_id}/ros2/nodes/{node_name}  (Task 2.6)
# ---------------------------------------------------------------------------


@entity_ros2_router.get("/{entity_id}/ros2/nodes/{node_name}")
async def get_entity_ros2_node_detail(entity_id: str, node_name: str):
    """Get detailed info for a single ROS2 node on an entity."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        detail = get_node_detail(node_name)
        if detail is None:
            raise HTTPException(
                status_code=404,
                detail=f"Node '{node_name}' not found",
            )
        return _wrap_response(entity_id, "local", detail)

    data = await _proxy_get(entity, f"/ros2/nodes/{node_name}")
    return _wrap_response(entity_id, "remote", data)


# ---------------------------------------------------------------------------
# POST /api/entities/{id}/ros2/nodes/{name}/lifecycle/{transition}  (Task 2.7)
# ---------------------------------------------------------------------------


@entity_ros2_router.post("/{entity_id}/ros2/nodes/{node_name}/lifecycle/{transition}")
async def post_entity_ros2_lifecycle(entity_id: str, node_name: str, transition: str):
    """Send a lifecycle transition to a managed ROS2 node."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        try:
            result = lifecycle_transition(
                node_name=f"/{node_name}",
                transition=transition,
            )
            return _wrap_response(entity_id, "local", result)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    data = await _proxy_post(entity, f"/ros2/nodes/{node_name}/lifecycle/{transition}")
    return _wrap_response(entity_id, "remote", data)


# ---------------------------------------------------------------------------
# GET /api/entities/{entity_id}/ros2/parameters  (Task 2.8)
# ---------------------------------------------------------------------------


# Longer timeout for per-node parameter dump (runs ros2 param dump in thread).
_PARAMS_TIMEOUT_S = 30


@entity_ros2_router.get("/{entity_id}/ros2/parameters")
async def get_entity_ros2_parameters(entity_id: str):
    """Get ROS2 node list (lightweight — parameters are loaded per-node on demand)."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        data = get_parameters()
        return _wrap_response(entity_id, "local", data)

    data = await _proxy_get(entity, "/ros2/parameters")
    return _wrap_response(entity_id, "remote", data)


@entity_ros2_router.get("/{entity_id}/ros2/parameters/{node_name:path}")
async def get_entity_ros2_node_parameters(entity_id: str, node_name: str):
    """Get parameters for a single ROS2 node (on-demand, per-node)."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        # Local: use ros2_monitor helper
        from .ros2_monitor import get_parameters as _get_params

        all_params = _get_params()
        nodes = all_params.get("nodes", []) if isinstance(all_params, dict) else []
        for node in nodes:
            if node.get("name") == f"/{node_name}" or node.get("name") == node_name:
                return _wrap_response(entity_id, "local", node)
        return _wrap_response(entity_id, "local", {"name": node_name, "parameters": []})

    # Remote: proxy with extended timeout
    url = f"{entity.agent_base_url(AGENT_PORT)}/ros2/parameters/{node_name}"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(_PARAMS_TIMEOUT_S)) as client:
            resp = await client.get(url)
        if resp.status_code == 200:
            return _wrap_response(entity_id, "remote", resp.json())
        raise HTTPException(
            status_code=502,
            detail=f"Agent at {entity.ip} returned status {resp.status_code}",
        )
    except _PROXY_NETWORK_ERRORS as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Agent at {entity.ip} unreachable: {exc}",
        )


# ---------------------------------------------------------------------------
# PUT /api/entities/{entity_id}/ros2/parameters/{node_name}  (Task 2.8)
# ---------------------------------------------------------------------------


@entity_ros2_router.put("/{entity_id}/ros2/parameters/{node_name}")
async def put_entity_ros2_parameters(entity_id: str, node_name: str, body: SetParametersRequest):
    """Set parameters on a ROS2 node for an entity."""
    entity = _get_entity_or_404(entity_id)

    # Normalize: strip leading slashes so local gets exactly one '/' prefix
    # and remote proxy path never has a double-slash.
    bare_name = node_name.lstrip("/") or node_name

    if entity.source == "local":
        try:
            results = []
            for param in body.params:
                result = set_parameter(
                    node_name=f"/{bare_name}",
                    param_name=param["name"],
                    value=param["value"],
                )
                results.append(result)
            return _wrap_response(entity_id, "local", {"results": results})
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    data = await _proxy_put(
        entity,
        f"/ros2/parameters/{bare_name}",
        json_body={"params": body.params},
    )
    return _wrap_response(entity_id, "remote", data)


# ---------------------------------------------------------------------------
# GET /api/entities/{entity_id}/logs  (Task 2.10)
# ---------------------------------------------------------------------------


@entity_ros2_router.get("/{entity_id}/logs")
async def get_entity_logs(entity_id: str):
    """List available log files for an entity."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        data = _list_local_logs()
        return _wrap_response(entity_id, "local", data)

    data = await _proxy_get(entity, "/logs")
    return _wrap_response(entity_id, "remote", data)


# ---------------------------------------------------------------------------
# GET /api/entities/{entity_id}/logs/{log_name}/tail  (Task 2.10)
# ---------------------------------------------------------------------------


@entity_ros2_router.get("/{entity_id}/logs/{log_name:path}/tail")
async def get_entity_log_tail(entity_id: str, log_name: str):
    """SSE stream of log tail for an entity."""
    entity = _get_entity_or_404(entity_id)

    if entity.source == "local":
        # Sanitize: reject path traversal
        if ".." in log_name or log_name.startswith("/"):
            raise HTTPException(
                status_code=400,
                detail="Invalid log name — path traversal not allowed",
            )

        # Search all configured log directories (same as _list_local_logs)
        log_path: pathlib.Path | None = None
        for d in _get_log_dirs():
            dir_path = pathlib.Path(d).resolve()
            candidate = (dir_path / log_name).resolve()
            # Ensure resolved path is still under this log dir
            if str(candidate).startswith(str(dir_path)) and candidate.is_file():
                log_path = candidate
                break

        if log_path is None:
            raise HTTPException(
                status_code=404,
                detail=f"Log file not found: {log_name}",
            )

        async def _tail_local_log():
            proc = await asyncio.create_subprocess_exec(
                "tail",
                "-f",
                "-n",
                "100",
                str(log_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                async for line in proc.stdout:
                    text = line.decode("utf-8", errors="replace").rstrip("\n")
                    yield f"data: {text}\n\n"
            finally:
                proc.kill()
                await proc.wait()

        return StreamingResponse(
            _tail_local_log(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # Remote: proxy SSE stream from agent
    return await _proxy_sse(entity, f"/logs/{log_name}/tail")


# ---------------------------------------------------------------------------
# GET /api/entities/{entity_id}/logs/journal/{unit}
# ---------------------------------------------------------------------------


@entity_ros2_router.get("/{entity_id}/logs/journal/{unit}")
async def get_entity_journal_stream(
    entity_id: str,
    unit: str,
    since: str | None = None,
    until: str | None = None,
):
    """SSE stream of journalctl output for a specific systemd unit.

    Optional query params ``since`` and ``until`` (ISO 8601 local timestamps)
    are forwarded as ``--since`` / ``--until`` flags to journalctl.  When
    either is present the stream runs in historical (non-follow) mode;
    otherwise it follows live output.
    """
    entity = _get_entity_or_404(entity_id)

    # Sanitize since/until: reject shell metacharacters
    _SAFE_TIME_RE = re.compile(r"^[\d\-T: .+]+$")
    if since and not _SAFE_TIME_RE.match(since):
        raise HTTPException(status_code=400, detail="Invalid 'since' value")
    if until and not _SAFE_TIME_RE.match(until):
        raise HTTPException(status_code=400, detail="Invalid 'until' value")

    if entity.source == "local":
        # Sanitize unit name: allow only alphanumerics, hyphens, underscores,
        # dots, and @ (for template instances like foo@bar.service).
        if not re.fullmatch(r"[a-zA-Z0-9@._\-]+", unit):
            raise HTTPException(
                status_code=400,
                detail="Invalid systemd unit name",
            )

        has_time_filter = bool(since or until)

        async def _stream_journal():
            cmd = ["journalctl", "-u", unit, "--no-pager", "-o", "json"]
            if since:
                cmd += ["--since", since]
            if until:
                cmd += ["--until", until]
            if has_time_filter:
                # Historical query: emit all matching lines then exit
                cmd += ["--no-tail"]
            else:
                # Live tail: follow new output
                cmd += ["-f", "-n", "200"]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                async for line in proc.stdout:
                    text = line.decode("utf-8", errors="replace").rstrip("\n")
                    if text:
                        yield f"data: {text}\n\n"
            finally:
                proc.kill()
                await proc.wait()

        return StreamingResponse(
            _stream_journal(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # Remote: proxy SSE stream from agent's /logs/journal/{unit}
    # Forward since/until as query params
    qs_parts = []
    if since:
        qs_parts.append(f"since={since}")
    if until:
        qs_parts.append(f"until={until}")
    return await _proxy_sse(entity, f"/logs/journal/{unit}", query_string="&".join(qs_parts))
