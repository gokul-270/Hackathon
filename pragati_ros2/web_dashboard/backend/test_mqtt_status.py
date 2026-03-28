"""Unit tests for MQTT Multi-Arm Coordination (Tasks 7.1-7.5).

Tests cover:
- 7.1: Lifecycle (start/stop, connect/disconnect, offline mode)
- 7.2: WebSocket bridge queue (enqueue, overflow, serialization, bridge loop)
- 7.3: Heartbeat state machine (connected/stale/offline transitions, recovery)
- 7.4: Vehicle hub status (vehicle dict, broker flags, arm counts, get_status)
- 7.5: Star topology model (arm isolation, no cross-arm refs, vehicle separation)

API endpoint tests:
- GET /api/arms, GET /api/arms/{arm_id}, POST /api/arms/{arm_id}/command
- GET /api/mqtt/status, GET /api/arms/mqtt/status (legacy alias)

paho-mqtt is fully mocked — no real broker needed.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Mock paho-mqtt BEFORE importing implementation modules
# ---------------------------------------------------------------------------
_mock_paho = MagicMock()
_mock_paho_client = MagicMock()
_mock_paho.Client = MagicMock(return_value=_mock_paho_client)

import sys

sys.modules["paho"] = MagicMock()
sys.modules["paho.mqtt"] = MagicMock()
sys.modules["paho.mqtt.client"] = _mock_paho

from backend.mqtt_status_service import (  # noqa: E402
    CONN_CONNECTED,
    CONN_OFFLINE,
    CONN_STALE,
    MqttStatusService,
)
from backend.mqtt_api import (  # noqa: E402
    mqtt_router,
    set_audit_logger,
    set_mqtt_service,
)
from backend.websocket_handlers import (  # noqa: E402
    broadcast_to_arms_ws,
    mqtt_ws_bridge_loop,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service(
    heartbeat_timeout: float = 5.0,
) -> MqttStatusService:
    """Create a service with mocked MQTT client, not started."""
    svc = MqttStatusService(
        broker_host="localhost",
        broker_port=1883,
        heartbeat_timeout=heartbeat_timeout,
    )
    return svc


def _drain_queue(queue: asyncio.Queue) -> list:
    """Drain all items from an asyncio queue synchronously."""
    items = []
    while not queue.empty():
        try:
            items.append(queue.get_nowait())
        except asyncio.QueueEmpty:
            break
    return items


# ===================================================================
# Task 7.1 — Lifecycle tests
# ===================================================================


class TestLifecycleStart:
    """Test .start() connects and starts the MQTT loop."""

    def test_start_calls_connect_and_loop_start(self):
        svc = _make_service()
        mock_client = MagicMock()
        svc._mqtt_client = mock_client

        svc.start()

        mock_client.connect.assert_called_once_with("localhost", 1883)
        mock_client.loop_start.assert_called_once()

    def test_start_sets_running_flag(self):
        svc = _make_service()
        mock_client = MagicMock()
        svc._mqtt_client = mock_client

        svc.start()

        assert svc._running is True

    def test_start_with_no_client_returns_without_error(self):
        """Offline mode: _mqtt_client is None, start() is a no-op."""
        svc = _make_service()
        svc._mqtt_client = None

        # Should not raise
        svc.start()
        assert svc._running is False

    def test_on_connect_subscribes_to_armstatus_wildcard(self):
        svc = _make_service()
        mock_client = MagicMock()

        svc._on_connect(mock_client, None, None, 0)

        mock_client.subscribe.assert_any_call("topic/+")


class TestLifecycleStop:
    """Test .stop() disconnects and cleans up."""

    def test_stop_calls_loop_stop_and_disconnect(self):
        svc = _make_service()
        mock_client = MagicMock()
        svc._mqtt_client = mock_client
        svc._connected = True
        svc._running = True

        svc.stop()

        mock_client.loop_stop.assert_called_once()
        mock_client.disconnect.assert_called_once()

    def test_stop_sets_connected_false(self):
        svc = _make_service()
        mock_client = MagicMock()
        svc._mqtt_client = mock_client
        svc._connected = True

        svc.stop()

        assert svc._connected is False

    def test_stop_clears_connect_time(self):
        svc = _make_service()
        mock_client = MagicMock()
        svc._mqtt_client = mock_client
        svc._connect_time = 12345.0

        svc.stop()

        assert svc._connect_time is None

    def test_stop_enqueues_mqtt_status_disconnection_event(self):
        svc = _make_service()
        mock_client = MagicMock()
        svc._mqtt_client = mock_client
        svc._connected = True

        svc.stop()

        events = _drain_queue(svc._ws_queue)
        mqtt_events = [e for e in events if e.get("type") == "mqtt_status"]
        assert len(mqtt_events) == 1
        assert mqtt_events[0]["mqtt_connected"] is False

    def test_stop_sets_running_false(self):
        svc = _make_service()
        mock_client = MagicMock()
        svc._mqtt_client = mock_client
        svc._running = True

        svc.stop()

        assert svc._running is False

    def test_stop_cancels_heartbeat_task(self):
        svc = _make_service()
        svc._mqtt_client = MagicMock()
        mock_task = MagicMock()
        svc._heartbeat_task = mock_task

        svc.stop()

        mock_task.cancel.assert_called_once()
        assert svc._heartbeat_task is None


class TestIsConnectedLifecycle:
    """Test is_connected reflects MQTT connection state."""

    def test_initially_disconnected(self):
        svc = _make_service()
        assert svc.is_connected() is False

    def test_connected_after_on_connect(self):
        svc = _make_service()
        svc._on_connect(None, None, None, 0)
        assert svc.is_connected() is True

    def test_disconnected_after_on_disconnect(self):
        svc = _make_service()
        svc._on_connect(None, None, None, 0)
        svc._on_disconnect(None, None, 0)
        assert svc.is_connected() is False

    def test_reconnect_toggles_state(self):
        svc = _make_service()
        svc._on_connect(None, None, None, 0)
        assert svc.is_connected() is True
        svc._on_disconnect(None, None, 0)
        assert svc.is_connected() is False
        svc._on_connect(None, None, None, 0)
        assert svc.is_connected() is True


# ===================================================================
# Task 7.2 — WebSocket bridge queue tests
# ===================================================================


class TestEnqueueWsEvent:
    """Test _enqueue_ws_event puts events on the WS queue."""

    def test_enqueue_single_event(self):
        svc = _make_service()
        event = {"type": "test", "data": "hello"}

        svc._enqueue_ws_event(event)

        item = svc._ws_queue.get_nowait()
        assert item == event

    def test_enqueue_multiple_events_preserves_order(self):
        svc = _make_service()

        for i in range(5):
            svc._enqueue_ws_event({"type": "test", "seq": i})

        items = _drain_queue(svc._ws_queue)
        assert [it["seq"] for it in items] == [0, 1, 2, 3, 4]


class TestWsEventSerialization:
    """Test arm status messages create proper dict events."""

    def test_arm_status_event_has_correct_type(self):
        svc = _make_service()
        svc._on_status_message("arm-01", '{"state": "picking"}')

        events = _drain_queue(svc._ws_queue)
        arm_events = [e for e in events if e.get("type") == "arm_status"]
        assert len(arm_events) >= 1
        assert arm_events[0]["arm_id"] == "arm-01"

    def test_arm_status_event_contains_state_and_connectivity(self):
        svc = _make_service()
        svc._on_status_message("arm-01", '{"state": "idle", "cotton_count": 5}')

        events = _drain_queue(svc._ws_queue)
        arm_events = [e for e in events if e.get("type") == "arm_status"]
        assert len(arm_events) >= 1
        ev = arm_events[0]
        assert ev["state"] == "idle"
        assert ev["connectivity"] == CONN_CONNECTED
        assert ev["connected"] is True
        assert ev["cotton_count"] == 5

    def test_plain_string_payload_ready_maps_to_active_ready(self):
        svc = _make_service()

        svc._on_message(
            None,
            None,
            MagicMock(topic="topic/ArmStatus_arm1", payload=b"ready"),
        )

        arm = svc.get_arm("arm1")
        assert arm["connectivity"] == CONN_CONNECTED
        assert arm["state"] == "ready"

    def test_topic_suffix_extracts_entity_id(self):
        svc = _make_service()

        svc._on_message(
            None,
            None,
            MagicMock(topic="topic/ArmStatus_arm1", payload=b"busy"),
        )

        assert svc.get_arm("arm1") is not None

    def test_empty_payload_is_ignored(self):
        svc = _make_service()

        svc._on_message(
            None,
            None,
            MagicMock(topic="topic/ArmStatus_arm1", payload=b""),
        )

        assert svc.get_arm("arm1") is None

    def test_lwt_offline_payload_sets_offline_state(self):
        svc = _make_service()

        svc._on_message(
            None,
            None,
            MagicMock(topic="topic/ArmStatus_arm1", payload=b"offline"),
        )

        arm = svc.get_arm("arm1")
        assert arm["connectivity"] == CONN_OFFLINE
        assert arm["state"] == "offline"


class TestWsQueueOverflow:
    """Test queue overflow: fill to 100, oldest is dropped."""

    def test_overflow_drops_oldest_and_adds_newest(self):
        svc = _make_service()

        # Fill queue to capacity (100)
        for i in range(100):
            svc._enqueue_ws_event({"seq": i})

        assert svc._ws_queue.full()

        # Enqueue one more — oldest (seq=0) should be dropped
        svc._enqueue_ws_event({"seq": 100})

        items = _drain_queue(svc._ws_queue)
        sequences = [it["seq"] for it in items]

        # The queue should have 100 items: seq 1..100
        assert len(sequences) == 100
        assert sequences[0] == 1  # oldest surviving
        assert sequences[-1] == 100  # newest

    def test_overflow_multiple_times(self):
        svc = _make_service()

        # Fill to capacity
        for i in range(100):
            svc._enqueue_ws_event({"seq": i})

        # Overflow 3 more times
        for i in range(100, 103):
            svc._enqueue_ws_event({"seq": i})

        items = _drain_queue(svc._ws_queue)
        sequences = [it["seq"] for it in items]
        assert len(sequences) == 100
        assert sequences[0] == 3
        assert sequences[-1] == 102


class TestMqttWsBridgeLoop:
    """Test mqtt_ws_bridge_loop drains queue and calls broadcast."""

    @pytest.mark.asyncio
    async def test_bridge_loop_drains_queue_and_broadcasts(self):
        svc = _make_service()
        event = {"type": "arm_status", "arm_id": "arm-01", "state": "idle"}
        svc._enqueue_ws_event(event)

        broadcast_calls = []

        with patch(
            "backend.websocket_handlers.broadcast_to_arms_ws",
            new_callable=AsyncMock,
        ) as mock_broadcast:
            mock_broadcast.side_effect = lambda e: broadcast_calls.append(e)

            # Run bridge loop in a task with a short timeout
            getter = lambda: svc  # noqa: E731

            async def run_bridge_briefly():
                task = asyncio.create_task(mqtt_ws_bridge_loop(getter))
                # Give it time to drain one event
                await asyncio.sleep(0.05)
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            await run_bridge_briefly()

        assert len(broadcast_calls) == 1
        assert broadcast_calls[0]["arm_id"] == "arm-01"

    @pytest.mark.asyncio
    async def test_bridge_loop_waits_when_no_service(self):
        """When getter returns None, loop sleeps without crashing."""
        getter = lambda: None  # noqa: E731
        task = asyncio.create_task(mqtt_ws_bridge_loop(getter))
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        # No exception means success


# ===================================================================
# Task 7.3 — Heartbeat state machine tests
# ===================================================================


class TestHeartbeatInitialState:
    """Test arm starts as connected on first message."""

    def test_first_status_message_sets_connected(self):
        svc = _make_service()
        svc._on_status_message("arm-01", '{"state": "idle"}')

        arm = svc.get_arm("arm-01")
        assert arm["connectivity"] == CONN_CONNECTED
        assert arm["connected"] is True

    def test_first_heartbeat_sets_connected(self):
        svc = _make_service()
        svc._on_heartbeat("arm-01")

        arm = svc.get_arm("arm-01")
        assert arm["connectivity"] == CONN_CONNECTED
        assert arm["connected"] is True


class TestHeartbeatConnectedToStale:
    """Test connected -> stale transition when age > timeout."""

    def test_stale_when_age_exceeds_timeout(self):
        svc = _make_service(heartbeat_timeout=10.0)
        base_time = 1000.0

        with patch("time.monotonic", return_value=base_time):
            svc._on_status_message("arm-01", '{"state": "idle"}')

        # Advance time past timeout (10s) but under 2*timeout (20s)
        with patch("time.monotonic", return_value=base_time + 15.0):
            svc.check_heartbeat_timeouts()

        arm = svc.get_arm("arm-01")
        assert arm["connectivity"] == CONN_STALE
        assert arm["connected"] is False

    def test_stays_connected_within_timeout(self):
        svc = _make_service(heartbeat_timeout=10.0)
        base_time = 1000.0

        with patch("time.monotonic", return_value=base_time):
            svc._on_status_message("arm-01", '{"state": "idle"}')

        # Still within timeout
        with patch("time.monotonic", return_value=base_time + 5.0):
            svc.check_heartbeat_timeouts()

        arm = svc.get_arm("arm-01")
        assert arm["connectivity"] == CONN_CONNECTED
        assert arm["connected"] is True

    def test_stale_when_age_exceeds_seven_point_five_seconds(self):
        svc = _make_service(heartbeat_timeout=7.5)
        base_time = 1000.0

        with patch("time.monotonic", return_value=base_time):
            svc._on_message(
                None,
                None,
                MagicMock(topic="topic/ArmStatus_arm1", payload=b"ready"),
            )

        with patch("time.monotonic", return_value=base_time + 8.0):
            svc.check_heartbeat_timeouts()

        arm = svc.get_arm("arm1")
        assert arm["connectivity"] == CONN_STALE


class TestHeartbeatStaleToOffline:
    """Test stale -> offline transition when age > 2*timeout."""

    def test_offline_when_age_exceeds_double_timeout(self):
        svc = _make_service(heartbeat_timeout=10.0)
        base_time = 1000.0

        with patch("time.monotonic", return_value=base_time):
            svc._on_status_message("arm-01", '{"state": "idle"}')

        # Advance past 2*timeout (20s)
        with patch("time.monotonic", return_value=base_time + 25.0):
            svc.check_heartbeat_timeouts()

        arm = svc.get_arm("arm-01")
        assert arm["connectivity"] == CONN_OFFLINE
        assert arm["connected"] is False

    def test_stale_then_offline_sequential(self):
        """Two-step: first stale, then offline on next check."""
        svc = _make_service(heartbeat_timeout=10.0)
        base_time = 1000.0

        with patch("time.monotonic", return_value=base_time):
            svc._on_status_message("arm-01", '{"state": "idle"}')

        # Step 1: stale (age=15, timeout=10, 2*timeout=20)
        with patch("time.monotonic", return_value=base_time + 15.0):
            svc.check_heartbeat_timeouts()
        arm = svc.get_arm("arm-01")
        assert arm["connectivity"] == CONN_STALE

        # Step 2: offline (age=25)
        with patch("time.monotonic", return_value=base_time + 25.0):
            svc.check_heartbeat_timeouts()
        arm = svc.get_arm("arm-01")
        assert arm["connectivity"] == CONN_OFFLINE


class TestHeartbeatRecovery:
    """Test recovery: offline -> connected when new heartbeat received."""

    def test_recovery_from_offline_via_heartbeat(self):
        svc = _make_service(heartbeat_timeout=10.0)
        base_time = 1000.0

        with patch("time.monotonic", return_value=base_time):
            svc._on_status_message("arm-01", '{"state": "idle"}')

        # Go offline
        with patch("time.monotonic", return_value=base_time + 25.0):
            svc.check_heartbeat_timeouts()
        arm = svc.get_arm("arm-01")
        assert arm["connectivity"] == CONN_OFFLINE

        # New heartbeat arrives — recovery
        with patch("time.monotonic", return_value=base_time + 26.0):
            svc._on_heartbeat("arm-01")
        arm = svc.get_arm("arm-01")
        assert arm["connectivity"] == CONN_CONNECTED
        assert arm["connected"] is True

    def test_recovery_from_stale_via_status_message(self):
        svc = _make_service(heartbeat_timeout=10.0)
        base_time = 1000.0

        with patch("time.monotonic", return_value=base_time):
            svc._on_status_message("arm-01", '{"state": "idle"}')

        # Go stale
        with patch("time.monotonic", return_value=base_time + 15.0):
            svc.check_heartbeat_timeouts()
        arm = svc.get_arm("arm-01")
        assert arm["connectivity"] == CONN_STALE

        # Status message recovers the arm
        with patch("time.monotonic", return_value=base_time + 16.0):
            svc._on_status_message("arm-01", '{"state": "picking"}')
        arm = svc.get_arm("arm-01")
        assert arm["connectivity"] == CONN_CONNECTED
        assert arm["connected"] is True


class TestHeartbeatConfigurableTimeout:
    """Test different heartbeat_timeout values."""

    def test_short_timeout_triggers_stale_quickly(self):
        svc = _make_service(heartbeat_timeout=2.0)
        base_time = 1000.0

        with patch("time.monotonic", return_value=base_time):
            svc._on_status_message("arm-01", '{"state": "idle"}')

        # age=3 > timeout=2 => stale
        with patch("time.monotonic", return_value=base_time + 3.0):
            svc.check_heartbeat_timeouts()

        arm = svc.get_arm("arm-01")
        assert arm["connectivity"] == CONN_STALE

    def test_long_timeout_stays_connected_longer(self):
        svc = _make_service(heartbeat_timeout=60.0)
        base_time = 1000.0

        with patch("time.monotonic", return_value=base_time):
            svc._on_status_message("arm-01", '{"state": "idle"}')

        # age=30 < timeout=60 => still connected
        with patch("time.monotonic", return_value=base_time + 30.0):
            svc.check_heartbeat_timeouts()

        arm = svc.get_arm("arm-01")
        assert arm["connectivity"] == CONN_CONNECTED

    def test_exact_timeout_boundary_stays_connected(self):
        """At exactly the timeout boundary, age is not > timeout."""
        svc = _make_service(heartbeat_timeout=10.0)
        base_time = 1000.0

        with patch("time.monotonic", return_value=base_time):
            svc._on_status_message("arm-01", '{"state": "idle"}')

        # age == timeout exactly => not > timeout => connected
        with patch("time.monotonic", return_value=base_time + 10.0):
            svc.check_heartbeat_timeouts()

        arm = svc.get_arm("arm-01")
        assert arm["connectivity"] == CONN_CONNECTED


class TestHeartbeatTransitionBroadcastsWs:
    """Test stale/offline transitions broadcast via WS queue."""

    def test_stale_transition_enqueues_ws_event(self):
        svc = _make_service(heartbeat_timeout=10.0)
        base_time = 1000.0

        with patch("time.monotonic", return_value=base_time):
            svc._on_status_message("arm-01", '{"state": "idle"}')

        # Drain initial events from status message
        _drain_queue(svc._ws_queue)

        # Trigger stale
        with patch("time.monotonic", return_value=base_time + 15.0):
            svc.check_heartbeat_timeouts()

        events = _drain_queue(svc._ws_queue)
        arm_events = [
            e for e in events if e.get("type") == "arm_status" and e.get("arm_id") == "arm-01"
        ]
        assert len(arm_events) == 1
        assert arm_events[0]["connectivity"] == CONN_STALE

    def test_offline_transition_enqueues_ws_event(self):
        svc = _make_service(heartbeat_timeout=10.0)
        base_time = 1000.0

        with patch("time.monotonic", return_value=base_time):
            svc._on_status_message("arm-01", '{"state": "idle"}')

        # Go stale first
        with patch("time.monotonic", return_value=base_time + 15.0):
            svc.check_heartbeat_timeouts()

        # Drain all events so far
        _drain_queue(svc._ws_queue)

        # Go offline
        with patch("time.monotonic", return_value=base_time + 25.0):
            svc.check_heartbeat_timeouts()

        events = _drain_queue(svc._ws_queue)
        arm_events = [
            e for e in events if e.get("type") == "arm_status" and e.get("arm_id") == "arm-01"
        ]
        assert len(arm_events) == 1
        assert arm_events[0]["connectivity"] == CONN_OFFLINE

    def test_no_ws_event_when_no_transition(self):
        svc = _make_service(heartbeat_timeout=10.0)
        base_time = 1000.0

        with patch("time.monotonic", return_value=base_time):
            svc._on_status_message("arm-01", '{"state": "idle"}')

        _drain_queue(svc._ws_queue)

        # Still connected — no transition
        with patch("time.monotonic", return_value=base_time + 5.0):
            svc.check_heartbeat_timeouts()

        events = _drain_queue(svc._ws_queue)
        assert len(events) == 0


class TestHeartbeatNotifiesSubscribers:
    """Test heartbeat transitions notify change subscribers."""

    def test_timeout_notifies_subscribers(self):
        svc = _make_service(heartbeat_timeout=10.0)
        base_time = 1000.0
        changes = []
        svc.subscribe_changes(lambda arm_id, data: changes.append((arm_id, data)))

        with patch("time.monotonic", return_value=base_time):
            svc._on_status_message("arm-01", '{"state": "idle"}')

        changes.clear()

        with patch("time.monotonic", return_value=base_time + 15.0):
            svc.check_heartbeat_timeouts()

        assert len(changes) == 1
        assert changes[0][0] == "arm-01"
        assert changes[0][1]["connected"] is False
        assert changes[0][1]["connectivity"] == CONN_STALE


# ===================================================================
# Task 7.4 — Vehicle hub status tests
# ===================================================================


class TestVehicleStatus:
    """Test _on_vehicle_status updates _vehicle dict."""

    def test_vehicle_status_updates_fields(self):
        svc = _make_service()
        payload = json.dumps(
            {
                "state": "moving",
                "mode": "autonomous",
                "uptime": 3600,
                "error": None,
            }
        )
        svc._on_vehicle_status(payload)

        vehicle = svc.get_vehicle()
        assert vehicle["state"] == "moving"
        assert vehicle["mode"] == "autonomous"
        assert vehicle["uptime"] == 3600
        assert vehicle["error"] is None

    def test_vehicle_status_stores_last_status(self):
        svc = _make_service()
        data = {"state": "idle", "mode": "manual", "uptime": 100}
        svc._on_vehicle_status(json.dumps(data))

        vehicle = svc.get_vehicle()
        assert vehicle["last_status"] == data

    def test_vehicle_status_ignores_invalid_json(self):
        svc = _make_service()
        # Should not raise
        svc._on_vehicle_status("not json {{{")
        vehicle = svc.get_vehicle()
        assert vehicle["state"] == "unknown"


class TestVehicleBrokerConnection:
    """Test _on_connect/_on_disconnect set vehicle broker_connected."""

    def test_on_connect_sets_broker_connected_true(self):
        svc = _make_service()
        svc._on_connect(None, None, None, 0)

        vehicle = svc.get_vehicle()
        assert vehicle["broker_connected"] is True

    def test_on_disconnect_sets_broker_connected_false(self):
        svc = _make_service()
        svc._on_connect(None, None, None, 0)
        svc._on_disconnect(None, None, 0)

        vehicle = svc.get_vehicle()
        assert vehicle["broker_connected"] is False

    def test_initial_broker_connected_is_false(self):
        svc = _make_service()
        vehicle = svc.get_vehicle()
        assert vehicle["broker_connected"] is False


class TestUpdateArmCount:
    """Test _update_arm_count correctly calculates connected/total."""

    def test_single_connected_arm(self):
        svc = _make_service()
        svc._on_status_message("arm-01", '{"state": "idle"}')

        vehicle = svc.get_vehicle()
        assert vehicle["connected_arm_count"] == 1
        assert vehicle["total_arm_count"] == 1

    def test_multiple_arms_all_connected(self):
        svc = _make_service()
        svc._on_status_message("arm-01", '{"state": "idle"}')
        svc._on_status_message("arm-02", '{"state": "picking"}')
        svc._on_status_message("arm-03", '{"state": "idle"}')

        vehicle = svc.get_vehicle()
        assert vehicle["connected_arm_count"] == 3
        assert vehicle["total_arm_count"] == 3

    def test_some_arms_offline_reduces_connected_count(self):
        svc = _make_service(heartbeat_timeout=10.0)
        base_time = 1000.0

        with patch("time.monotonic", return_value=base_time):
            svc._on_status_message("arm-01", '{"state": "idle"}')
            svc._on_status_message("arm-02", '{"state": "idle"}')

        # Only arm-02 gets a fresh heartbeat
        with patch("time.monotonic", return_value=base_time + 15.0):
            svc._on_heartbeat("arm-02")

        # Now check timeouts — arm-01 goes stale
        with patch("time.monotonic", return_value=base_time + 15.0):
            svc.check_heartbeat_timeouts()

        # Re-check counts: _update_arm_count is now called during
        # check_heartbeat_timeouts when transitions occur.
        vehicle = svc.get_vehicle()
        # arm-01 is stale (not connected), arm-02 is connected
        assert vehicle["connected_arm_count"] == 1
        assert vehicle["total_arm_count"] == 2
        arm1 = svc.get_arm("arm-01")
        arm2 = svc.get_arm("arm-02")
        assert arm1["connectivity"] == CONN_STALE
        assert arm2["connectivity"] == CONN_CONNECTED

    def test_no_arms_shows_zero_counts(self):
        svc = _make_service()
        vehicle = svc.get_vehicle()
        assert vehicle["connected_arm_count"] == 0
        assert vehicle["total_arm_count"] == 0


class TestGetStatus:
    """Test get_status returns comprehensive MQTT status."""

    def test_disconnected_status(self):
        svc = _make_service()
        status = svc.get_status()

        assert status["connected"] is False
        assert status["broker"] == "localhost"
        assert "vehicle" in status
        assert "uptime_s" not in status

    def test_connected_status_includes_uptime(self):
        svc = _make_service()
        base_time = 1000.0

        with patch("time.monotonic", return_value=base_time):
            svc._on_connect(None, None, None, 0)

        with patch("time.monotonic", return_value=base_time + 60.0):
            status = svc.get_status()

        assert status["connected"] is True
        assert status["broker"] == "localhost"
        assert status["uptime_s"] == 60.0
        assert "vehicle" in status

    def test_disconnected_after_connection_shows_last_connected(self):
        svc = _make_service()
        fake_iso = "2026-03-08T12:00:00+00:00"

        with (
            patch("time.monotonic", return_value=1000.0),
            patch("backend.mqtt_status_service.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.isoformat.return_value = fake_iso
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            svc._on_connect(None, None, None, 0)

        svc._on_disconnect(None, None, 0)
        status = svc.get_status()

        assert status["connected"] is False
        assert "last_connected" in status
        assert status["last_connected"] == fake_iso

    def test_status_vehicle_includes_arm_counts(self):
        svc = _make_service()
        svc._on_status_message("arm-01", '{"state": "idle"}')
        svc._on_status_message("arm-02", '{"state": "picking"}')

        status = svc.get_status()
        vehicle = status["vehicle"]
        assert vehicle["total_arm_count"] == 2
        assert vehicle["connected_arm_count"] == 2


class TestVehicleStatusWsQueue:
    """Test vehicle status enqueued to WS queue."""

    def test_vehicle_status_enqueues_ws_event(self):
        svc = _make_service()
        payload = json.dumps({"state": "moving", "mode": "auto"})

        svc._on_vehicle_status(payload)

        events = _drain_queue(svc._ws_queue)
        vehicle_events = [e for e in events if e.get("type") == "vehicle_status"]
        assert len(vehicle_events) == 1
        assert vehicle_events[0]["state"] == "moving"
        assert vehicle_events[0]["mode"] == "auto"

    def test_on_connect_enqueues_mqtt_status_event(self):
        svc = _make_service()
        svc._on_connect(None, None, None, 0)

        events = _drain_queue(svc._ws_queue)
        mqtt_events = [e for e in events if e.get("type") == "mqtt_status"]
        assert len(mqtt_events) == 1
        assert mqtt_events[0]["mqtt_connected"] is True

    def test_on_disconnect_enqueues_mqtt_status_event(self):
        svc = _make_service()
        svc._on_disconnect(None, None, 0)

        events = _drain_queue(svc._ws_queue)
        mqtt_events = [e for e in events if e.get("type") == "mqtt_status"]
        assert len(mqtt_events) == 1
        assert mqtt_events[0]["mqtt_connected"] is False


# ===================================================================
# Task 7.5 — Star topology model tests
# ===================================================================


class TestStarTopologyArmIsolation:
    """Test _arms dict is separate from _vehicle dict."""

    def test_arms_dict_separate_from_vehicle(self):
        svc = _make_service()
        svc._on_status_message("arm-01", '{"state": "idle"}')

        # _arms should not contain vehicle entry
        assert "vehicle" not in svc._arms
        # _vehicle should not contain arm entries
        assert "arm-01" not in svc._vehicle

    def test_status_message_only_updates_target_arm(self):
        svc = _make_service()
        svc._on_status_message("arm-01", '{"state": "idle"}')
        svc._on_status_message("arm-02", '{"state": "picking"}')

        # Update arm-01 only
        svc._on_status_message("arm-01", '{"state": "moving"}')

        arm1 = svc.get_arm("arm-01")
        arm2 = svc.get_arm("arm-02")
        assert arm1["state"] == "moving"
        assert arm2["state"] == "picking"  # unchanged

    def test_no_cross_arm_references(self):
        """No arm entry should reference another arm's ID."""
        svc = _make_service()
        svc._on_status_message("arm-01", '{"state": "idle"}')
        svc._on_status_message("arm-02", '{"state": "picking"}')
        svc._on_status_message("arm-03", '{"state": "error"}')

        arms = svc.get_all_arms()
        for arm_id, arm_data in arms.items():
            # Check that no arm references other arm IDs in its keys
            other_ids = [aid for aid in arms.keys() if aid != arm_id]
            for key in arm_data.keys():
                for other_id in other_ids:
                    assert other_id not in key, (
                        f"arm {arm_id} has key '{key}' " f"referencing {other_id}"
                    )


class TestStarTopologyVehicleEntry:
    """Test vehicle entry structure."""

    def test_vehicle_has_required_keys(self):
        svc = _make_service()
        vehicle = svc.get_vehicle()

        assert "broker_connected" in vehicle
        assert "connected_arm_count" in vehicle
        assert "total_arm_count" in vehicle

    def test_vehicle_initial_state(self):
        svc = _make_service()
        vehicle = svc.get_vehicle()

        assert vehicle["state"] == "unknown"
        assert vehicle["broker_connected"] is False
        assert vehicle["connected_arm_count"] == 0
        assert vehicle["total_arm_count"] == 0


class TestStarTopologyGetAllArms:
    """Test get_all_arms returns only arm entries, no vehicle."""

    def test_get_all_arms_excludes_vehicle(self):
        svc = _make_service()
        svc._on_status_message("arm-01", '{"state": "idle"}')
        svc._on_vehicle_status(json.dumps({"state": "moving"}))

        arms = svc.get_all_arms()
        assert "vehicle" not in arms
        assert "arm-01" in arms

    def test_get_all_arms_returns_only_arms(self):
        svc = _make_service()
        svc._on_status_message("arm-01", '{"state": "idle"}')
        svc._on_status_message("arm-02", '{"state": "picking"}')

        arms = svc.get_all_arms()
        assert set(arms.keys()) == {"arm-01", "arm-02"}

    def test_get_all_arms_returns_deep_copy(self):
        svc = _make_service()
        svc._on_status_message("arm-01", '{"state": "idle"}')

        arms = svc.get_all_arms()
        arms["arm-01"]["state"] = "tampered"
        assert svc.get_arm("arm-01")["state"] == "idle"


# ===================================================================
# Additional service tests (existing coverage, updated)
# ===================================================================


class TestSendCommand:
    """Test send_command publishes MQTT message with action key."""

    def test_publishes_action_payload(self):
        svc = _make_service()
        mock_client = MagicMock()
        svc._mqtt_client = mock_client
        svc._connected = True

        svc.send_command("arm-01", "estop")

        mock_client.publish.assert_called_once()
        call_args = mock_client.publish.call_args
        assert call_args[0][0] == "pragati/arm/arm-01/command"
        payload = json.loads(call_args[0][1])
        assert payload["action"] == "estop"

    def test_send_command_when_disconnected_raises(self):
        svc = _make_service()
        svc._connected = False

        with pytest.raises(ConnectionError):
            svc.send_command("arm-01", "restart")

    def test_send_command_restart(self):
        svc = _make_service()
        mock_client = MagicMock()
        svc._mqtt_client = mock_client
        svc._connected = True

        svc.send_command("arm-02", "restart")

        call_args = mock_client.publish.call_args
        payload = json.loads(call_args[0][1])
        assert payload["action"] == "restart"
        assert "pragati/arm/arm-02/command" == call_args[0][0]


class TestSubscribeChanges:
    """Test subscribe/unsubscribe for change notifications."""

    def test_subscribe_receives_status_updates(self):
        svc = _make_service()
        changes = []
        svc.subscribe_changes(lambda arm_id, data: changes.append((arm_id, data)))

        svc._on_status_message("arm-01", '{"state": "picking"}')

        assert len(changes) == 1
        assert changes[0][0] == "arm-01"

    def test_unsubscribe_stops_notifications(self):
        svc = _make_service()
        changes = []
        cb = lambda arm_id, data: changes.append((arm_id, data))  # noqa: E731
        svc.subscribe_changes(cb)
        svc.unsubscribe_changes(cb)

        svc._on_status_message("arm-01", '{"state": "idle"}')

        assert len(changes) == 0


class TestReconnectionBackoff:
    """Test reconnection backoff calculation."""

    def test_initial_backoff_is_1s(self):
        svc = _make_service()
        assert svc._calculate_backoff(0) == 1.0

    def test_second_backoff_is_2s(self):
        svc = _make_service()
        assert svc._calculate_backoff(1) == 2.0

    def test_third_backoff_is_4s(self):
        svc = _make_service()
        assert svc._calculate_backoff(2) == 4.0

    def test_backoff_caps_at_30s(self):
        svc = _make_service()
        assert svc._calculate_backoff(10) == 30.0
        assert svc._calculate_backoff(100) == 30.0


class TestCottonCountHandler:
    """Test _on_cotton_count updates arm cotton_count field."""

    def test_cotton_count_updates_arm(self):
        svc = _make_service()
        svc._on_status_message("arm-01", '{"state": "idle"}')
        svc._on_cotton_count("arm-01", '{"count": 42}')

        arm = svc.get_arm("arm-01")
        assert arm["cotton_count"] == 42

    def test_cotton_count_unknown_arm_ignored(self):
        svc = _make_service()
        # Should not raise for unknown arm
        svc._on_cotton_count("unknown", '{"count": 5}')
        assert svc.get_arm("unknown") is None


class TestArmErrorHandler:
    """Test _on_arm_error updates arm error state."""

    def test_arm_error_sets_error_state(self):
        svc = _make_service()
        svc._on_status_message("arm-01", '{"state": "idle"}')
        svc._on_arm_error("arm-01", '{"code": "E001", "msg": "motor fault"}')

        arm = svc.get_arm("arm-01")
        assert arm["state"] == "error"
        assert arm["last_error"]["code"] == "E001"


# ===================================================================
# API endpoint tests (mqtt_api.py)
# ===================================================================


@pytest.fixture()
def mock_mqtt_service():
    """Create a mock MqttStatusService and inject it into mqtt_api."""
    svc = MagicMock(spec=MqttStatusService)
    svc.is_connected.return_value = True
    svc._broker_host = "test-broker"
    svc.get_all_arms.return_value = {
        "arm-01": {
            "state": "idle",
            "connected": True,
            "connectivity": CONN_CONNECTED,
            "last_heartbeat": "2025-01-01T00:00:00Z",
            "last_status": {"battery": 90},
        },
        "arm-02": {
            "state": "picking",
            "connected": True,
            "connectivity": CONN_CONNECTED,
            "last_heartbeat": "2025-01-01T00:00:01Z",
            "last_status": {"battery": 75},
        },
    }
    svc.get_arm.side_effect = lambda arm_id: {
        "arm-01": {
            "state": "idle",
            "connected": True,
            "connectivity": CONN_CONNECTED,
            "last_heartbeat": "2025-01-01T00:00:00Z",
            "last_status": {"battery": 90},
        },
    }.get(arm_id)
    svc.get_status.return_value = {
        "connected": True,
        "broker": "test-broker",
        "uptime_s": 120.0,
        "vehicle": {
            "state": "idle",
            "broker_connected": True,
            "connected_arm_count": 2,
            "total_arm_count": 2,
        },
    }
    set_mqtt_service(svc)
    yield svc
    set_mqtt_service(None)


@pytest.fixture()
def mock_audit():
    """Inject a mock audit logger."""
    logger = MagicMock()
    set_audit_logger(logger)
    yield logger
    set_audit_logger(None)


@pytest.fixture()
def api_client(mock_mqtt_service, mock_audit):
    """Create a TestClient with the mqtt_router mounted."""
    app = FastAPI()
    app.include_router(mqtt_router)
    return TestClient(app)


class TestApiGetArms:
    """Test GET /api/arms endpoint."""

    def test_returns_all_arms(self, api_client, mock_mqtt_service):
        resp = api_client.get("/api/arms")
        assert resp.status_code == 200

        data = resp.json()
        assert "arm-01" in data
        assert "arm-02" in data
        assert data["arm-01"]["state"] == "idle"

    def test_returns_empty_when_no_arms(self, api_client, mock_mqtt_service):
        mock_mqtt_service.get_all_arms.return_value = {}
        resp = api_client.get("/api/arms")
        assert resp.status_code == 200
        assert resp.json() == {}


class TestApiGetSingleArm:
    """Test GET /api/arms/{arm_id} endpoint."""

    def test_known_arm_returns_200(self, api_client, mock_mqtt_service):
        resp = api_client.get("/api/arms/arm-01")
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "idle"

    def test_unknown_arm_returns_404(self, api_client, mock_mqtt_service):
        resp = api_client.get("/api/arms/nonexistent")
        assert resp.status_code == 404


class TestApiCommandEndpoint:
    """Test POST /api/arms/{arm_id}/command endpoint."""

    def test_valid_command_returns_sent(self, api_client, mock_mqtt_service):
        resp = api_client.post(
            "/api/arms/arm-01/command",
            json={"command": "restart"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "sent"
        assert data["arm_id"] == "arm-01"
        assert data["command"] == "restart"
        mock_mqtt_service.send_command.assert_called_once_with("arm-01", "restart")

    def test_estop_command_works(self, api_client, mock_mqtt_service):
        resp = api_client.post(
            "/api/arms/arm-01/command",
            json={"command": "estop"},
        )
        assert resp.status_code == 200
        assert resp.json()["command"] == "estop"

    def test_invalid_command_returns_400(self, api_client, mock_mqtt_service):
        resp = api_client.post(
            "/api/arms/arm-01/command",
            json={"command": "hack"},
        )
        assert resp.status_code == 400

    def test_command_logs_audit(self, api_client, mock_mqtt_service, mock_audit):
        api_client.post(
            "/api/arms/arm-01/command",
            json={"command": "estop"},
        )
        mock_audit.log.assert_called_once()
        call_args = mock_audit.log.call_args
        assert call_args[0][0] == "arm_command"

    def test_command_when_disconnected_returns_503(self, api_client, mock_mqtt_service):
        mock_mqtt_service.send_command.side_effect = ConnectionError("Not connected")
        resp = api_client.post(
            "/api/arms/arm-01/command",
            json={"command": "restart"},
        )
        assert resp.status_code == 503


class TestApiMqttStatus:
    """Test GET /api/mqtt/status endpoint (unified health-check)."""

    def test_returns_status_from_get_status(self, api_client, mock_mqtt_service):
        resp = api_client.get("/api/mqtt/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is True
        assert data["broker"] == "test-broker"
        assert data["uptime_s"] == 120.0
        assert "vehicle" in data
        mock_mqtt_service.get_status.assert_called()

    def test_includes_vehicle_data(self, api_client, mock_mqtt_service):
        resp = api_client.get("/api/mqtt/status")
        data = resp.json()
        vehicle = data["vehicle"]
        assert vehicle["connected_arm_count"] == 2
        assert vehicle["total_arm_count"] == 2
        assert vehicle["broker_connected"] is True


class TestApiMqttStatusLegacy:
    """Test GET /api/arms/mqtt/status legacy alias endpoint."""

    def test_legacy_endpoint_returns_same_data(self, api_client, mock_mqtt_service):
        resp = api_client.get("/api/arms/mqtt/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is True
        assert data["broker"] == "test-broker"
        mock_mqtt_service.get_status.assert_called()

    def test_legacy_no_service_returns_disconnected(self, api_client, mock_mqtt_service):
        set_mqtt_service(None)
        resp = api_client.get("/api/arms/mqtt/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is False
