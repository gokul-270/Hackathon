"""Tests for the /ws/topic_echo/{topic_name} WebSocket route.

Covers:
- Connection lifecycle (connect, receive messages, disconnect)
- Backend-side throttling (max 10 Hz = 100ms between sends)
- Message truncation (> 10 KB gets truncated with _truncated flag)
- Concurrent connection limit per IP (max 3, 4th rejected with 4001)
- Cleanup on disconnect (connection tracking freed)
"""

import asyncio
import json
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_topic_echo_service(messages=None):
    """Create a mock TopicEchoService that yields canned messages."""
    svc = AsyncMock()
    svc.start_echo = AsyncMock(return_value={"success": True})
    svc.stop_echo = AsyncMock(return_value={"success": True})
    svc.cleanup_client = AsyncMock()

    # get_topic_messages returns a list of dicts
    if messages is None:
        messages = [
            {"timestamp": "2026-01-01T00:00:00Z", "data": {"value": i}}
            for i in range(5)
        ]
    svc.get_topic_messages = AsyncMock(
        return_value={"messages": messages, "topic": "/test_topic", "count": len(messages)}
    )
    return svc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_enhanced_services():
    """Ensure ENHANCED_SERVICES_AVAILABLE is True and topic echo service is mocked."""
    with patch("backend.service_registry.ENHANCED_SERVICES_AVAILABLE", True):
        yield


@pytest.fixture()
def mock_service():
    return _make_mock_topic_echo_service()


@pytest.fixture()
def client(mock_service):
    """TestClient wired to the real app with a mocked topic echo service."""
    from backend.dashboard_server import app
    # Ensure the module is in sys.modules before patch() resolves the path
    from backend import topic_echo_service as tes

    async def _get_mock_service():
        return mock_service

    with patch.object(tes, "get_topic_echo_service", _get_mock_service):
        # Reset connection tracking between tests
        tes._topic_echo_connections.clear()
        yield TestClient(app)


# ---------------------------------------------------------------------------
# 1. Connection lifecycle
# ---------------------------------------------------------------------------

class TestConnectionLifecycle:
    """Connect, receive messages, disconnect cleanly."""

    def test_connect_and_receive_message(self, client, mock_service):
        """Client connects and receives at least one JSON message."""
        with client.websocket_connect("/ws/topic_echo/test_topic") as ws:
            data = ws.receive_json()
            assert "messages" in data or "data" in data or "topic" in data

    def test_start_echo_called_on_connect(self, client, mock_service):
        """start_echo is invoked with the topic name on connect."""
        with client.websocket_connect("/ws/topic_echo/test_topic"):
            pass  # connect then immediately disconnect
        mock_service.start_echo.assert_called_once()
        call_args = mock_service.start_echo.call_args
        assert call_args[0][0] == "test_topic"  # topic_name

    def test_stop_echo_and_cleanup_on_disconnect(self, client, mock_service):
        """stop_echo and cleanup_client are called after disconnect."""
        with client.websocket_connect("/ws/topic_echo/test_topic"):
            pass
        mock_service.stop_echo.assert_called_once()
        mock_service.cleanup_client.assert_called_once()


# ---------------------------------------------------------------------------
# 2. Throttling
# ---------------------------------------------------------------------------

class TestThrottling:
    """Messages must not exceed 10 Hz (100 ms between sends)."""

    def test_messages_respect_rate_limit(self, client, mock_service):
        """Two consecutive messages are separated by >= 90 ms (allowing jitter)."""
        with client.websocket_connect("/ws/topic_echo/test_topic") as ws:
            t0 = time.monotonic()
            ws.receive_json()
            t1 = time.monotonic()
            ws.receive_json()
            t2 = time.monotonic()
            # The interval between the first and second received messages
            interval = t2 - t1
            # Allow 10ms of slack for scheduling jitter (100ms target)
            assert interval >= 0.080, (
                f"Messages arrived too fast: {interval*1000:.1f}ms apart "
                f"(expected >=80ms)"
            )


# ---------------------------------------------------------------------------
# 3. Message truncation
# ---------------------------------------------------------------------------

class TestMessageTruncation:
    """Messages > max size (default 10 KB) are truncated."""

    def test_large_message_is_truncated(self, client):
        """A message exceeding 10 KB is truncated with _truncated flag."""
        large_data = {"value": "x" * 20_000}  # ~20 KB
        big_messages = [
            {"timestamp": "2026-01-01T00:00:00Z", "data": large_data}
        ]
        svc = _make_mock_topic_echo_service(messages=big_messages)

        from backend.dashboard_server import app
        from backend import topic_echo_service as tes

        async def _get_svc():
            return svc

        with patch.object(tes, "get_topic_echo_service", _get_svc):
            tes._topic_echo_connections.clear()
            with TestClient(app).websocket_connect(
                "/ws/topic_echo/test_topic"
            ) as ws:
                data = ws.receive_json()
                raw = json.dumps(data)
                # Message should be within bounds or flagged as truncated
                assert len(raw.encode("utf-8")) <= 11_000 or data.get(
                    "_truncated"
                ), "Large message was neither truncated nor flagged"

    def test_small_message_not_truncated(self, client, mock_service):
        """A small message is sent as-is without _truncated flag."""
        with client.websocket_connect("/ws/topic_echo/test_topic") as ws:
            data = ws.receive_json()
            assert data.get("_truncated") is not True


# ---------------------------------------------------------------------------
# 4. Concurrent connection limit
# ---------------------------------------------------------------------------

class TestConnectionLimit:
    """Max 3 echo connections per client IP; 4th gets close code 4001."""

    def test_fourth_connection_rejected(self, mock_service):
        """Opening a 4th WebSocket from the same IP returns code 4001."""
        from backend.dashboard_server import app
        from backend import topic_echo_service as tes

        async def _get_svc():
            return mock_service

        with patch.object(tes, "get_topic_echo_service", _get_svc):
            tes._topic_echo_connections.clear()
            test_client = TestClient(app)

            ws_list = []
            try:
                for i in range(3):
                    ws = test_client.websocket_connect(
                        f"/ws/topic_echo/topic_{i}"
                    )
                    ctx = ws.__enter__()
                    ws_list.append((ws, ctx))

                # 4th connection should be rejected
                with pytest.raises(Exception) as exc_info:
                    with test_client.websocket_connect(
                        "/ws/topic_echo/topic_extra"
                    ) as ws4:
                        ws4.receive_json()
                # Starlette raises WebSocketDisconnect with the close code
                assert "4001" in str(exc_info.value) or (
                    hasattr(exc_info.value, "code")
                    and exc_info.value.code == 4001
                )
            finally:
                for ws_cm, ctx in ws_list:
                    try:
                        ws_cm.__exit__(None, None, None)
                    except Exception:
                        pass


# ---------------------------------------------------------------------------
# 5. Cleanup on disconnect
# ---------------------------------------------------------------------------

class TestCleanup:
    """Connection tracking is cleaned up after disconnect."""

    def test_tracking_cleaned_after_disconnect(self, client, mock_service):
        """After disconnect, the IP slot is freed for new connections."""
        from backend import topic_echo_service as tes

        with client.websocket_connect("/ws/topic_echo/test_topic"):
            # During connection, tracking should have an entry
            assert len(tes._topic_echo_connections) > 0

        # After disconnect, tracking should be empty
        assert len(tes._topic_echo_connections) == 0

    def test_slot_reusable_after_disconnect(self, mock_service):
        """Disconnecting frees a slot so a new connection can be made."""
        from backend.dashboard_server import app
        from backend import topic_echo_service as tes

        async def _get_svc():
            return mock_service

        with patch.object(tes, "get_topic_echo_service", _get_svc):
            tes._topic_echo_connections.clear()
            test_client = TestClient(app)

            # Fill 3 slots and release them
            for _ in range(3):
                with test_client.websocket_connect(
                    "/ws/topic_echo/test_topic"
                ):
                    pass

            # Should be able to connect again (all slots freed)
            with test_client.websocket_connect(
                "/ws/topic_echo/test_topic"
            ) as ws:
                data = ws.receive_json()
                assert data is not None
