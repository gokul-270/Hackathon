"""Tests for Multi-Arm WebSocket handler fix.

Validates that when MQTT service is unavailable, the WebSocket handler
sends an empty fleet state snapshot instead of closing with code 4003.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_sends_empty_fleet_when_no_mqtt():
    """Handler sends snapshot with empty arms when MQTT service is None."""
    from backend.websocket_handlers import handle_arms_status

    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()

    get_service = MagicMock(return_value=None)

    # Run the handler but cancel after a short time (it loops forever)
    task = asyncio.create_task(handle_arms_status(ws, get_service))
    await asyncio.sleep(0.1)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    ws.accept.assert_called_once()
    # Should have sent at least one snapshot
    assert ws.send_json.call_count >= 1
    first_msg = ws.send_json.call_args_list[0][0][0]
    assert first_msg["type"] == "snapshot"
    assert first_msg["arms"] == {}
    assert first_msg["broker_connected"] is False


@pytest.mark.asyncio
async def test_does_not_close_with_4003_when_no_mqtt():
    """Handler does NOT close WebSocket with code 4003 when MQTT unavailable."""
    from backend.websocket_handlers import handle_arms_status

    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()

    get_service = MagicMock(return_value=None)

    task = asyncio.create_task(handle_arms_status(ws, get_service))
    await asyncio.sleep(0.1)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # close should NOT have been called
    ws.close.assert_not_called()


@pytest.mark.asyncio
async def test_keeps_connection_open_with_heartbeat():
    """Handler keeps connection alive with periodic heartbeats when no MQTT."""
    from backend.websocket_handlers import handle_arms_status

    ws = AsyncMock()
    ws.accept = AsyncMock()
    call_count = 0

    async def track_send(data):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise Exception("stop test")

    ws.send_json = AsyncMock(side_effect=track_send)

    get_service = MagicMock(return_value=None)

    # Patch asyncio.sleep to speed up the test (heartbeat is every 10s)
    with patch("backend.websocket_handlers.asyncio.sleep", new_callable=AsyncMock):
        await handle_arms_status(ws, get_service)

    # Should have sent multiple snapshots (initial + heartbeats)
    assert call_count >= 2


@pytest.mark.asyncio
async def test_normal_mqtt_sends_initial_snapshot():
    """Handler sends full snapshot when MQTT service IS available."""
    from backend.websocket_handlers import handle_arms_status

    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()

    mock_mqtt = MagicMock()
    mock_mqtt.get_all_arms = MagicMock(return_value={"arm1": {"status": "active"}})
    mock_mqtt.subscribe_changes = MagicMock()

    get_service = MagicMock(return_value=mock_mqtt)

    # The handler will block on queue.get(), so cancel after initial snapshot
    task = asyncio.create_task(handle_arms_status(ws, get_service))
    await asyncio.sleep(0.1)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    ws.accept.assert_called_once()
    assert ws.send_json.call_count >= 1
    first_msg = ws.send_json.call_args_list[0][0][0]
    assert first_msg["type"] == "snapshot"
    assert "arm1" in first_msg["arms"]
