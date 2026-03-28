"""Shared proxy helpers — extracted from entity_ros2_router and entity_proxy.

Contains all shared helper functions and constants used by entity-scoped
proxy routes. Both entity_ros2_router.py and entity_proxy.py import from
here to avoid code duplication.

Capability: proxy-request-retry (dashboard-reliability-hardening)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
import json

from .entity_manager import AGENT_PORT, get_entity_manager
from .entity_model import Entity

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

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

# Connection-only errors: safe to retry for POST/PUT (idempotent at transport level)
_PROXY_CONNECTION_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
)

# Retry configuration
_PROXY_RETRY_COUNT = 1
_PROXY_RETRY_DELAY_S = 2.0


# ---------------------------------------------------------------------------
# Entity lookup helpers
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


# ---------------------------------------------------------------------------
# Response helper
# ---------------------------------------------------------------------------


def _wrap_response(entity_id: str, source: str, data: Any) -> dict[str, Any]:
    """Standard envelope for proxy responses."""
    return {
        "entity_id": entity_id,
        "source": source,
        "data": data,
    }


# ---------------------------------------------------------------------------
# Proxy helpers with retry
# ---------------------------------------------------------------------------


async def _proxy_get(entity: Entity, path: str) -> Any:
    """Proxy a GET request to a remote entity's agent.

    Retries once on network errors (_PROXY_NETWORK_ERRORS) after a 2s delay.
    HTTP error responses (4xx/5xx) are NOT retried.
    """
    url = f"{entity.agent_base_url(AGENT_PORT)}{path}"
    last_exc: Exception | None = None

    for attempt in range(_PROXY_RETRY_COUNT + 1):
        if attempt > 0:
            logger.info(
                "Retrying GET %s (attempt %d/%d) after network error: %s",
                url,
                attempt + 1,
                _PROXY_RETRY_COUNT + 1,
                last_exc,
            )
            await asyncio.sleep(_PROXY_RETRY_DELAY_S)
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(_PROXY_TIMEOUT_S)) as client:
                resp = await client.get(url)
            if resp.status_code == 200:
                return resp.json()
            # HTTP error — do not retry
            raise HTTPException(
                status_code=502,
                detail=f"Agent at {url} returned status {resp.status_code}",
            )
        except HTTPException:
            raise
        except _PROXY_NETWORK_ERRORS as exc:
            last_exc = exc
            continue

    raise HTTPException(
        status_code=502,
        detail=f"Agent at {url} unreachable after {_PROXY_RETRY_COUNT + 1} attempts: {last_exc}",
    )


async def _proxy_post(entity: Entity, path: str, json_body: dict | None = None) -> Any:
    """Proxy a POST request to a remote entity's agent.

    Retries once only on connection errors (refused/reset). Does NOT retry
    on HTTP errors or read timeouts (POST may not be idempotent).
    """
    url = f"{entity.agent_base_url(AGENT_PORT)}{path}"
    last_exc: Exception | None = None

    for attempt in range(_PROXY_RETRY_COUNT + 1):
        if attempt > 0:
            logger.info(
                "Retrying POST %s (attempt %d/%d) after connection error: %s",
                url,
                attempt + 1,
                _PROXY_RETRY_COUNT + 1,
                last_exc,
            )
            await asyncio.sleep(_PROXY_RETRY_DELAY_S)
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(_PROXY_TIMEOUT_S)) as client:
                resp = await client.post(url, json=json_body)
            if resp.status_code == 200:
                return resp.json()
            # HTTP error — do not retry
            raise HTTPException(
                status_code=502,
                detail=f"Agent at {url} returned status {resp.status_code}",
            )
        except HTTPException:
            raise
        except _PROXY_CONNECTION_ERRORS as exc:
            # Only retry connection errors for POST (not read timeouts)
            last_exc = exc
            continue
        except _PROXY_NETWORK_ERRORS as exc:
            # Non-connection network errors: raise immediately (no retry for POST)
            raise HTTPException(
                status_code=502,
                detail=f"Agent at {url} unreachable: {exc}",
            )

    raise HTTPException(
        status_code=502,
        detail=f"Agent at {url} unreachable after {_PROXY_RETRY_COUNT + 1} attempts: {last_exc}",
    )


async def _proxy_put(entity: Entity, path: str, json_body: dict | None = None) -> Any:
    """Proxy a PUT request to a remote entity's agent.

    Same retry policy as POST: retries once on connection errors only.
    """
    url = f"{entity.agent_base_url(AGENT_PORT)}{path}"
    last_exc: Exception | None = None

    for attempt in range(_PROXY_RETRY_COUNT + 1):
        if attempt > 0:
            logger.info(
                "Retrying PUT %s (attempt %d/%d) after connection error: %s",
                url,
                attempt + 1,
                _PROXY_RETRY_COUNT + 1,
                last_exc,
            )
            await asyncio.sleep(_PROXY_RETRY_DELAY_S)
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(_PROXY_TIMEOUT_S)) as client:
                resp = await client.put(url, json=json_body)
            if resp.status_code == 200:
                return resp.json()
            # HTTP error — do not retry
            raise HTTPException(
                status_code=502,
                detail=f"Agent at {url} returned status {resp.status_code}",
            )
        except HTTPException:
            raise
        except _PROXY_CONNECTION_ERRORS as exc:
            last_exc = exc
            continue
        except _PROXY_NETWORK_ERRORS as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Agent at {url} unreachable: {exc}",
            )

    raise HTTPException(
        status_code=502,
        detail=f"Agent at {url} unreachable after {_PROXY_RETRY_COUNT + 1} attempts: {last_exc}",
    )


async def _proxy_sse(entity: Entity, path: str, query_string: str = "") -> StreamingResponse:
    """Proxy an SSE stream from a remote agent.

    No retry — SSE reconnect is handled by the frontend ReconnectingEventSource.
    """
    url = f"{entity.agent_base_url(AGENT_PORT)}{path}"
    if query_string:
        url += ("&" if "?" in url else "?") + query_string

    async def generate():
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(None)) as client:
                async with client.stream("GET", url) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        err = body.decode("utf-8", errors="replace")
                        yield f"data: {{\"error\": \"agent returned {resp.status_code}\", \"detail\": {json.dumps(err)}}}\n\n"
                        return
                    async for line in resp.aiter_lines():
                        if line:
                            yield f"{line}\n\n"
        except Exception as e:
            # Catch broad exceptions for SSE robustness
            logger.debug("SSE proxy error: %s", e)
            yield 'data: {"error": "agent_unreachable", "detail": "Cannot connect to agent"}\n\n'

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
