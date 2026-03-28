"""Tests for shared proxy helpers — entity_proxy_helpers.py.

Covers:
  - Task 1.4: network error handling, 502 responses, timeout behavior
  - Task 2.5: retry logic — GET retry on timeout, exhausted retries, no retry on HTTP 404,
              POST retry on connection refused, POST no retry on HTTP 500, SSE no retry.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException

MODULE = "backend.entity_proxy_helpers"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entity(ip: str = "192.168.1.10") -> MagicMock:
    entity = MagicMock()
    entity.ip = ip
    entity.agent_base_url.return_value = f"http://{ip}:8765"
    return entity


def _mock_httpx_200(json_data: dict):
    """Return a mock httpx context manager that yields a 200 response."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = json_data

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.put = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


def _mock_httpx_status(status: int):
    """Return a mock httpx context manager that yields an error status response."""
    mock_resp = MagicMock()
    mock_resp.status_code = status
    mock_resp.json.return_value = {}

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.put = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# ---------------------------------------------------------------------------
# _proxy_get tests
# ---------------------------------------------------------------------------


class TestProxyGet:
    pytestmark = pytest.mark.asyncio

    async def test_success_returns_json(self):
        from backend.entity_proxy_helpers import _proxy_get

        entity = _make_entity()
        payload = {"nodes": ["/foo"]}

        with patch(f"{MODULE}.httpx") as mock_httpx:
            mock_httpx.Timeout = httpx.Timeout
            mock_httpx.ConnectTimeout = httpx.ConnectTimeout
            mock_httpx.ReadTimeout = httpx.ReadTimeout
            mock_httpx.ConnectError = httpx.ConnectError
            mock_httpx.RemoteProtocolError = httpx.RemoteProtocolError
            mock_client = _mock_httpx_200(payload)
            mock_httpx.AsyncClient.return_value = mock_client

            result = await _proxy_get(entity, "/ros2/nodes")

        assert result == payload

    @pytest.mark.asyncio
    async def test_http_error_raises_502(self):
        from backend.entity_proxy_helpers import _proxy_get

        entity = _make_entity()

        with patch(f"{MODULE}.httpx") as mock_httpx:
            mock_httpx.Timeout = httpx.Timeout
            mock_httpx.ConnectTimeout = httpx.ConnectTimeout
            mock_httpx.ReadTimeout = httpx.ReadTimeout
            mock_httpx.ConnectError = httpx.ConnectError
            mock_httpx.RemoteProtocolError = httpx.RemoteProtocolError
            mock_client = _mock_httpx_status(500)
            mock_httpx.AsyncClient.return_value = mock_client

            with pytest.raises(HTTPException) as exc_info:
                await _proxy_get(entity, "/ros2/nodes")

        assert exc_info.value.status_code == 502

    @pytest.mark.asyncio
    async def test_no_retry_on_http_404(self):
        """HTTP 404 from agent should raise 502 immediately — no retry."""
        from backend.entity_proxy_helpers import _proxy_get

        entity = _make_entity()

        with patch(f"{MODULE}.httpx") as mock_httpx, patch(
            f"{MODULE}.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            mock_httpx.Timeout = httpx.Timeout
            mock_httpx.ConnectTimeout = httpx.ConnectTimeout
            mock_httpx.ReadTimeout = httpx.ReadTimeout
            mock_httpx.ConnectError = httpx.ConnectError
            mock_httpx.RemoteProtocolError = httpx.RemoteProtocolError
            mock_client = _mock_httpx_status(404)
            mock_httpx.AsyncClient.return_value = mock_client

            with pytest.raises(HTTPException) as exc_info:
                await _proxy_get(entity, "/ros2/nodes")

        assert exc_info.value.status_code == 502
        # sleep should NOT have been called — no retry on HTTP error
        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_retry_on_timeout_succeeds(self):
        """GET should retry once on ConnectTimeout and succeed on second attempt."""
        from backend.entity_proxy_helpers import _proxy_get

        entity = _make_entity()
        payload = {"nodes": ["/bar"]}

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = payload

        client_fail = AsyncMock()
        client_fail.get = AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))
        client_fail.__aenter__ = AsyncMock(return_value=client_fail)
        client_fail.__aexit__ = AsyncMock(return_value=False)

        client_ok = AsyncMock()
        client_ok.get = AsyncMock(return_value=mock_resp)
        client_ok.__aenter__ = AsyncMock(return_value=client_ok)
        client_ok.__aexit__ = AsyncMock(return_value=False)

        with patch(f"{MODULE}.httpx") as mock_httpx, patch(
            f"{MODULE}.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            mock_httpx.Timeout = httpx.Timeout
            mock_httpx.ConnectTimeout = httpx.ConnectTimeout
            mock_httpx.ReadTimeout = httpx.ReadTimeout
            mock_httpx.ConnectError = httpx.ConnectError
            mock_httpx.RemoteProtocolError = httpx.RemoteProtocolError
            mock_httpx.AsyncClient.side_effect = [client_fail, client_ok]

            result = await _proxy_get(entity, "/ros2/nodes")

        assert result == payload
        mock_sleep.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_exhausted_returns_502(self):
        """GET should return 502 after all retry attempts are exhausted."""
        from backend.entity_proxy_helpers import _proxy_get

        entity = _make_entity()

        client_fail = AsyncMock()
        client_fail.get = AsyncMock(side_effect=httpx.ReadTimeout("timeout"))
        client_fail.__aenter__ = AsyncMock(return_value=client_fail)
        client_fail.__aexit__ = AsyncMock(return_value=False)

        with patch(f"{MODULE}.httpx") as mock_httpx, patch(
            f"{MODULE}.asyncio.sleep", new_callable=AsyncMock
        ):
            mock_httpx.Timeout = httpx.Timeout
            mock_httpx.ConnectTimeout = httpx.ConnectTimeout
            mock_httpx.ReadTimeout = httpx.ReadTimeout
            mock_httpx.ConnectError = httpx.ConnectError
            mock_httpx.RemoteProtocolError = httpx.RemoteProtocolError
            # Both attempts fail
            mock_httpx.AsyncClient.side_effect = [client_fail, client_fail]

            with pytest.raises(HTTPException) as exc_info:
                await _proxy_get(entity, "/ros2/nodes")

        assert exc_info.value.status_code == 502
        assert "unreachable" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_connect_error_triggers_retry(self):
        """ConnectError should trigger GET retry."""
        from backend.entity_proxy_helpers import _proxy_get

        entity = _make_entity()
        payload = {"ok": True}

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = payload

        client_fail = AsyncMock()
        client_fail.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        client_fail.__aenter__ = AsyncMock(return_value=client_fail)
        client_fail.__aexit__ = AsyncMock(return_value=False)

        client_ok = AsyncMock()
        client_ok.get = AsyncMock(return_value=mock_resp)
        client_ok.__aenter__ = AsyncMock(return_value=client_ok)
        client_ok.__aexit__ = AsyncMock(return_value=False)

        with patch(f"{MODULE}.httpx") as mock_httpx, patch(
            f"{MODULE}.asyncio.sleep", new_callable=AsyncMock
        ):
            mock_httpx.Timeout = httpx.Timeout
            mock_httpx.ConnectTimeout = httpx.ConnectTimeout
            mock_httpx.ReadTimeout = httpx.ReadTimeout
            mock_httpx.ConnectError = httpx.ConnectError
            mock_httpx.RemoteProtocolError = httpx.RemoteProtocolError
            mock_httpx.AsyncClient.side_effect = [client_fail, client_ok]

            result = await _proxy_get(entity, "/health")

        assert result == payload


# ---------------------------------------------------------------------------
# _proxy_post tests
# ---------------------------------------------------------------------------


class TestProxyPost:
    pytestmark = pytest.mark.asyncio

    async def test_success_returns_json(self):
        from backend.entity_proxy_helpers import _proxy_post

        entity = _make_entity()
        payload = {"status": "ok"}

        with patch(f"{MODULE}.httpx") as mock_httpx:
            mock_httpx.Timeout = httpx.Timeout
            mock_httpx.ConnectTimeout = httpx.ConnectTimeout
            mock_httpx.ReadTimeout = httpx.ReadTimeout
            mock_httpx.ConnectError = httpx.ConnectError
            mock_httpx.RemoteProtocolError = httpx.RemoteProtocolError
            mock_client = _mock_httpx_200(payload)
            mock_httpx.AsyncClient.return_value = mock_client

            result = await _proxy_post(entity, "/command", {"cmd": "start"})

        assert result == payload

    @pytest.mark.asyncio
    async def test_no_retry_on_http_500(self):
        """HTTP 500 from agent should raise 502 immediately — no retry for POST."""
        from backend.entity_proxy_helpers import _proxy_post

        entity = _make_entity()

        with patch(f"{MODULE}.httpx") as mock_httpx, patch(
            f"{MODULE}.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            mock_httpx.Timeout = httpx.Timeout
            mock_httpx.ConnectTimeout = httpx.ConnectTimeout
            mock_httpx.ReadTimeout = httpx.ReadTimeout
            mock_httpx.ConnectError = httpx.ConnectError
            mock_httpx.RemoteProtocolError = httpx.RemoteProtocolError
            mock_client = _mock_httpx_status(500)
            mock_httpx.AsyncClient.return_value = mock_client

            with pytest.raises(HTTPException) as exc_info:
                await _proxy_post(entity, "/command")

        assert exc_info.value.status_code == 502
        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_retry_on_connection_refused(self):
        """POST should retry once on ConnectError (connection refused)."""
        from backend.entity_proxy_helpers import _proxy_post

        entity = _make_entity()
        payload = {"status": "ok"}

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = payload

        client_fail = AsyncMock()
        client_fail.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        client_fail.__aenter__ = AsyncMock(return_value=client_fail)
        client_fail.__aexit__ = AsyncMock(return_value=False)

        client_ok = AsyncMock()
        client_ok.post = AsyncMock(return_value=mock_resp)
        client_ok.__aenter__ = AsyncMock(return_value=client_ok)
        client_ok.__aexit__ = AsyncMock(return_value=False)

        with patch(f"{MODULE}.httpx") as mock_httpx, patch(
            f"{MODULE}.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            mock_httpx.Timeout = httpx.Timeout
            mock_httpx.ConnectTimeout = httpx.ConnectTimeout
            mock_httpx.ReadTimeout = httpx.ReadTimeout
            mock_httpx.ConnectError = httpx.ConnectError
            mock_httpx.RemoteProtocolError = httpx.RemoteProtocolError
            mock_httpx.AsyncClient.side_effect = [client_fail, client_ok]

            result = await _proxy_post(entity, "/command")

        assert result == payload
        mock_sleep.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_retry_on_read_timeout(self):
        """POST should NOT retry on ReadTimeout (only connection errors are safe to retry)."""
        from backend.entity_proxy_helpers import _proxy_post

        entity = _make_entity()

        client_fail = AsyncMock()
        client_fail.post = AsyncMock(side_effect=httpx.ReadTimeout("timed out"))
        client_fail.__aenter__ = AsyncMock(return_value=client_fail)
        client_fail.__aexit__ = AsyncMock(return_value=False)

        with patch(f"{MODULE}.httpx") as mock_httpx, patch(
            f"{MODULE}.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            mock_httpx.Timeout = httpx.Timeout
            mock_httpx.ConnectTimeout = httpx.ConnectTimeout
            mock_httpx.ReadTimeout = httpx.ReadTimeout
            mock_httpx.ConnectError = httpx.ConnectError
            mock_httpx.RemoteProtocolError = httpx.RemoteProtocolError
            mock_httpx.AsyncClient.return_value = client_fail

            with pytest.raises(HTTPException) as exc_info:
                await _proxy_post(entity, "/command")

        assert exc_info.value.status_code == 502
        # No retry sleep for ReadTimeout on POST
        mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# _proxy_put tests
# ---------------------------------------------------------------------------


class TestProxyPut:
    pytestmark = pytest.mark.asyncio

    async def test_success_returns_json(self):
        from backend.entity_proxy_helpers import _proxy_put

        entity = _make_entity()
        payload = {"status": "updated"}

        with patch(f"{MODULE}.httpx") as mock_httpx:
            mock_httpx.Timeout = httpx.Timeout
            mock_httpx.ConnectTimeout = httpx.ConnectTimeout
            mock_httpx.ReadTimeout = httpx.ReadTimeout
            mock_httpx.ConnectError = httpx.ConnectError
            mock_httpx.RemoteProtocolError = httpx.RemoteProtocolError
            mock_client = _mock_httpx_200(payload)
            mock_httpx.AsyncClient.return_value = mock_client

            result = await _proxy_put(entity, "/config", {"speed": 50})

        assert result == payload

    @pytest.mark.asyncio
    async def test_retry_on_connect_timeout(self):
        """PUT retries once on ConnectTimeout."""
        from backend.entity_proxy_helpers import _proxy_put

        entity = _make_entity()
        payload = {"status": "updated"}

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = payload

        client_fail = AsyncMock()
        client_fail.put = AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))
        client_fail.__aenter__ = AsyncMock(return_value=client_fail)
        client_fail.__aexit__ = AsyncMock(return_value=False)

        client_ok = AsyncMock()
        client_ok.put = AsyncMock(return_value=mock_resp)
        client_ok.__aenter__ = AsyncMock(return_value=client_ok)
        client_ok.__aexit__ = AsyncMock(return_value=False)

        with patch(f"{MODULE}.httpx") as mock_httpx, patch(
            f"{MODULE}.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            mock_httpx.Timeout = httpx.Timeout
            mock_httpx.ConnectTimeout = httpx.ConnectTimeout
            mock_httpx.ReadTimeout = httpx.ReadTimeout
            mock_httpx.ConnectError = httpx.ConnectError
            mock_httpx.RemoteProtocolError = httpx.RemoteProtocolError
            mock_httpx.AsyncClient.side_effect = [client_fail, client_ok]

            result = await _proxy_put(entity, "/config")

        assert result == payload
        mock_sleep.assert_called_once()

    @pytest.mark.asyncio
    async def test_http_error_raises_502(self):
        from backend.entity_proxy_helpers import _proxy_put

        entity = _make_entity()

        with patch(f"{MODULE}.httpx") as mock_httpx:
            mock_httpx.Timeout = httpx.Timeout
            mock_httpx.ConnectTimeout = httpx.ConnectTimeout
            mock_httpx.ReadTimeout = httpx.ReadTimeout
            mock_httpx.ConnectError = httpx.ConnectError
            mock_httpx.RemoteProtocolError = httpx.RemoteProtocolError
            mock_client = _mock_httpx_status(422)
            mock_httpx.AsyncClient.return_value = mock_client

            with pytest.raises(HTTPException) as exc_info:
                await _proxy_put(entity, "/config")

        assert exc_info.value.status_code == 502


# ---------------------------------------------------------------------------
# _proxy_sse tests
# ---------------------------------------------------------------------------


class TestProxySse:
    pytestmark = pytest.mark.asyncio

    async def test_sse_returns_streaming_response(self):
        """SSE proxy returns a StreamingResponse with correct headers."""
        from backend.entity_proxy_helpers import _proxy_sse
        from fastapi.responses import StreamingResponse

        entity = _make_entity()

        async def _fake_aiter_lines():
            yield "data: hello"
            yield "data: world"

        mock_stream_resp = AsyncMock()
        mock_stream_resp.status_code = 200
        mock_stream_resp.aiter_lines = _fake_aiter_lines
        mock_stream_resp.__aenter__ = AsyncMock(return_value=mock_stream_resp)
        mock_stream_resp.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_stream_resp)

        with patch(f"{MODULE}.httpx") as mock_httpx:
            mock_httpx.Timeout = httpx.Timeout
            mock_httpx.AsyncClient.return_value = mock_client

            response = await _proxy_sse(entity, "/logs/stream")

        assert isinstance(response, StreamingResponse)
        assert response.media_type == "text/event-stream"

    async def test_sse_single_client_call_on_error(self):
        """SSE proxy returns a StreamingResponse — generator is lazy, no eager retry."""
        from backend.entity_proxy_helpers import _proxy_sse

        entity = _make_entity()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(side_effect=Exception("connection refused"))

        with patch(f"{MODULE}.httpx") as mock_httpx:
            mock_httpx.Timeout = httpx.Timeout
            mock_httpx.AsyncClient.return_value = mock_client

            # _proxy_sse just builds the StreamingResponse — generator is lazy
            response = await _proxy_sse(entity, "/logs/stream")

        # The response should be a streaming response with correct media type
        assert response.media_type == "text/event-stream"
        # AsyncClient not yet called — generator runs lazily when body is consumed
        assert mock_httpx.AsyncClient.call_count == 0


# ---------------------------------------------------------------------------
# Entity lookup helpers
# ---------------------------------------------------------------------------


class TestEntityLookupHelpers:
    def test_get_mgr_or_503_raises_when_no_manager(self):
        from backend.entity_proxy_helpers import _get_mgr_or_503

        with patch(f"{MODULE}.get_entity_manager", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                _get_mgr_or_503()

        assert exc_info.value.status_code == 503

    def test_get_entity_or_404_raises_when_not_found(self):
        from backend.entity_proxy_helpers import _get_entity_or_404

        mock_mgr = MagicMock()
        mock_mgr.get_entity.return_value = None

        with patch(f"{MODULE}.get_entity_manager", return_value=mock_mgr):
            with pytest.raises(HTTPException) as exc_info:
                _get_entity_or_404("arm99")

        assert exc_info.value.status_code == 404
        assert "arm99" in exc_info.value.detail

    def test_get_entity_or_404_returns_entity(self):
        from backend.entity_proxy_helpers import _get_entity_or_404

        entity = _make_entity()
        mock_mgr = MagicMock()
        mock_mgr.get_entity.return_value = entity

        with patch(f"{MODULE}.get_entity_manager", return_value=mock_mgr):
            result = _get_entity_or_404("arm1")

        assert result is entity

    def test_wrap_response(self):
        from backend.entity_proxy_helpers import _wrap_response

        result = _wrap_response("arm1", "remote", {"nodes": []})
        assert result["entity_id"] == "arm1"
        assert result["source"] == "remote"
        assert result["data"] == {"nodes": []}
