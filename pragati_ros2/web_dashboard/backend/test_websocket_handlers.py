"""Tests for WebSocket handlers -- ping/pong, refresh, change detection, error logging.

Covers handle_main_websocket from backend.websocket_handlers:
1. Ping/pong: server replies {'type':'pong'} to {'type':'ping'}
2. Refresh: server sends system_state, performance, health, alerts envelopes
3. Change detection: duplicate state is not re-sent
4. Exception logging: WebSocket errors are logged at warning level
"""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

from backend.websocket_handlers import (
    handle_main_websocket,
    websocket_connections,
)

import pytest

# ---------------------------------------------------------------------------
# Sentinel to break the handler loop from outside
# ---------------------------------------------------------------------------


class _StopLoop(BaseException):
    """Raised to terminate the handler loop in tests.

    Inherits from BaseException (not Exception) so it propagates through
    the handler's ``except Exception`` blocks.
    """


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ws_mock(messages, *, extra_loops=1):
    """Create a mock WebSocket that delivers *messages* then terminates.

    The ``_fake_wait_for`` helper in ``_run_handler`` calls
    ``receive_json`` directly (bypassing real asyncio.wait_for).

    Strategy for termination:
    - Deliver each message via ``receive_json`` in order.
    - After messages, raise ``asyncio.TimeoutError`` for ``extra_loops``
      iterations (simulating 'no client message').
    - After that, raise ``_StopLoop`` (a BaseException) which propagates
      past both ``except Exception`` blocks and terminates the handler.

    Returns a mock with a ``._send_log`` list of all sent payloads.
    """
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.close = AsyncMock()

    msg_iter = iter(messages)
    recv_call = 0
    timeouts_remaining = extra_loops

    async def _receive():
        nonlocal recv_call, timeouts_remaining
        recv_call += 1
        try:
            return next(msg_iter)
        except StopIteration:
            if timeouts_remaining > 0:
                timeouts_remaining -= 1
                raise asyncio.TimeoutError
            raise _StopLoop("test done")

    ws.receive_json = AsyncMock(side_effect=_receive)

    send_log = []

    async def _send(data):
        send_log.append(data)

    ws.send_json = AsyncMock(side_effect=_send)
    ws._send_log = send_log
    return ws


def _make_envelope_mock():
    """Mock message_envelope with create_envelope / create_handshake."""
    envelope = MagicMock()
    envelope.create_handshake.return_value = {
        "status": "connected",
        "capabilities": ["basic"],
    }
    envelope.create_envelope.side_effect = lambda msg_type, data: {
        "type": msg_type,
        "data": data,
    }
    return envelope


def _make_capabilities_mock(rate_hz=1000.0):
    """Return a mock capabilities_manager with configurable rate."""
    mgr = MagicMock()
    mgr.get_server_config.return_value = rate_hz
    mgr.is_enabled.return_value = False
    return mgr


def _make_perf_monitor(summary=None):
    """Return a mock performance monitor."""
    mon = MagicMock()
    mon.get_summary.return_value = summary or {"cpu": 42}
    return mon


def _make_health_monitor(health=None):
    """Return a mock health monitor."""
    mon = MagicMock()
    mon.get_system_health.return_value = health or {"status": "ok"}
    return mon


def _make_alert_engine(alerts=None):
    """Return a mock alert engine."""
    eng = MagicMock()
    eng.get_active_alerts.return_value = alerts or []
    return eng


async def _run_handler(
    ws,
    system_state=None,
    capabilities_manager=None,
    message_envelope=None,
    enhanced_services=False,
    perf_monitor=None,
    health_monitor=None,
    alert_engine=None,
    safety_manager=None,
):
    """Run handle_main_websocket with sensible defaults.

    Patches ``asyncio.sleep`` (no-op) and ``asyncio.wait_for`` (direct
    await, bypassing real timeout) so the mock's ``receive_json``
    side-effect controls the loop.

    The ``_StopLoop`` sentinel (BaseException) terminates the handler.
    """
    if system_state is None:
        system_state = {"ros_connected": True}
    if capabilities_manager is None:
        capabilities_manager = _make_capabilities_mock()
    if message_envelope is None:
        message_envelope = _make_envelope_mock()

    _perf = perf_monitor or _make_perf_monitor()
    _health = health_monitor or _make_health_monitor()
    _alert = alert_engine or _make_alert_engine()

    async def _fake_wait_for(coro, *, timeout):
        return await coro

    with (
        patch("backend.websocket_handlers.asyncio.sleep", new=AsyncMock()),
        patch(
            "backend.websocket_handlers.asyncio.wait_for",
            new=_fake_wait_for,
        ),
    ):
        try:
            await handle_main_websocket(
                websocket=ws,
                system_state=system_state,
                capabilities_manager=capabilities_manager,
                message_envelope=message_envelope,
                reload_capabilities=None,
                get_topic_echo_service=None,
                get_performance_monitor=lambda: _perf,
                get_health_monitor=lambda: _health,
                get_alert_engine=lambda: _alert,
                enhanced_services_available=enhanced_services,
                safety_manager=safety_manager,
            )
        except _StopLoop:
            pass  # expected -- test-controlled termination


def _sent_payloads(ws):
    """Return all payloads passed to send_json."""
    return list(ws._send_log)


def _sent_types(ws):
    """Extract 'type' values from all send_json calls."""
    return [
        m.get("type") for m in _sent_payloads(ws) if isinstance(m, dict) and "type" in m
    ]


# ---------------------------------------------------------------------------
# 1. Ping / Pong
# ---------------------------------------------------------------------------


class TestPingPong:
    """Server replies pong to a ping message."""

    @pytest.mark.asyncio
    async def test_ping_returns_pong(self):
        """Server sends pong in response to ping."""
        ws = _make_ws_mock([{"type": "ping"}])
        await _run_handler(ws)

        types = _sent_types(ws)
        assert "pong" in types, f"Expected pong in sent types: {types}"

        pong_msgs = [m for m in _sent_payloads(ws) if m.get("type") == "pong"]
        assert pong_msgs[0] == {"type": "pong"}

    @pytest.mark.asyncio
    async def test_two_pings_get_two_pongs(self):
        """Each ping gets exactly one pong -- no duplicates, no drops."""
        ws = _make_ws_mock([{"type": "ping"}, {"type": "ping"}])
        await _run_handler(ws)

        pong_count = sum(1 for t in _sent_types(ws) if t == "pong")
        assert pong_count == 2, f"Expected 2 pongs for 2 pings, got {pong_count}"


# ---------------------------------------------------------------------------
# 2. Refresh
# ---------------------------------------------------------------------------


class TestRefresh:
    """Refresh sends system_state, performance, health, and alerts."""

    @pytest.mark.asyncio
    async def test_refresh_sends_all_categories(self):
        """Refresh triggers sends for all 4 data categories."""
        ws = _make_ws_mock([{"type": "refresh"}], extra_loops=1)
        await _run_handler(ws, enhanced_services=True)

        types = _sent_types(ws)
        assert "system_update" in types, f"Missing system_update in {types}"
        assert "performance_update" in types, f"Missing performance_update in {types}"
        assert "health_update" in types, f"Missing health_update in {types}"
        assert "alerts_update" in types, f"Missing alerts_update in {types}"

    @pytest.mark.asyncio
    async def test_refresh_uses_envelope_format(self):
        """Refresh messages use envelope format with type and data."""
        ws = _make_ws_mock([{"type": "refresh"}], extra_loops=1)
        envelope = _make_envelope_mock()
        await _run_handler(ws, message_envelope=envelope, enhanced_services=True)

        envelope_calls = [
            c
            for c in envelope.create_envelope.call_args_list
            if c.args[0] == "system_update"
        ]
        assert (
            len(envelope_calls) >= 1
        ), "create_envelope should be called for system_update on refresh"

    @pytest.mark.asyncio
    async def test_refresh_without_enhanced_sends_only_system(self):
        """Without enhanced services, refresh sends only system state."""
        ws = _make_ws_mock([{"type": "refresh"}], extra_loops=1)
        await _run_handler(ws, enhanced_services=False)

        types = _sent_types(ws)
        assert "system_update" in types

        refresh_enhanced = [
            t
            for t in types
            if t in ("performance_update", "health_update", "alerts_update")
        ]
        assert len(refresh_enhanced) == 0, (
            f"Enhanced types should not appear without enhanced services: "
            f"{refresh_enhanced}"
        )

    @pytest.mark.asyncio
    async def test_refresh_with_failing_perf_still_sends_health_and_alerts(
        self,
    ):
        """If performance monitor raises, health and alerts still go out."""
        ws = _make_ws_mock([{"type": "refresh"}], extra_loops=1)
        bad_perf = MagicMock()
        bad_perf.get_summary.side_effect = RuntimeError("perf exploded")

        await _run_handler(
            ws,
            enhanced_services=True,
            perf_monitor=bad_perf,
        )

        types = _sent_types(ws)
        assert (
            "health_update" in types
        ), "health_update should still be sent despite perf failure"
        assert (
            "alerts_update" in types
        ), "alerts_update should still be sent despite perf failure"


# ---------------------------------------------------------------------------
# 3. Change detection
# ---------------------------------------------------------------------------


class TestChangeDetection:
    """Duplicate data is not re-sent (hash-based dedup)."""

    @pytest.mark.asyncio
    async def test_identical_state_not_sent_twice(self):
        """Unchanged system_state is sent only once across loops."""
        ws = _make_ws_mock([], extra_loops=3)

        state = {"ros_connected": True, "nodes": []}
        await _run_handler(ws, system_state=state, enhanced_services=False)

        system_sends = [
            m
            for m in _sent_payloads(ws)
            if isinstance(m, dict) and m.get("type") == "system_update"
        ]

        assert len(system_sends) == 1, (
            f"Expected 1 system_update (dedup should skip repeats), "
            f"got {len(system_sends)}"
        )

    @pytest.mark.asyncio
    async def test_changed_state_is_sent_again(self):
        """When system_state mutates between loops, both sends go through."""
        state = {"ros_connected": True, "counter": 0}
        recv_call = 0
        timeouts_remaining = 3

        async def _receive():
            nonlocal recv_call, timeouts_remaining
            recv_call += 1
            if recv_call == 2:
                state["counter"] = 1
            if timeouts_remaining > 0:
                timeouts_remaining -= 1
                raise asyncio.TimeoutError
            raise _StopLoop("test done")

        send_log = []

        async def _send(data):
            send_log.append(data)

        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.close = AsyncMock()
        ws.receive_json = AsyncMock(side_effect=_receive)
        ws.send_json = AsyncMock(side_effect=_send)
        ws._send_log = send_log

        await _run_handler(ws, system_state=state, enhanced_services=False)

        system_sends = [
            m
            for m in send_log
            if isinstance(m, dict) and m.get("type") == "system_update"
        ]

        assert len(system_sends) == 2, (
            f"Expected 2 system_update sends (state changed), "
            f"got {len(system_sends)}"
        )

    @pytest.mark.asyncio
    async def test_enhanced_dedup_skips_identical_perf(self):
        """Identical performance data is not re-sent on second loop."""
        ws = _make_ws_mock([], extra_loops=3)
        perf = _make_perf_monitor({"cpu": 42})

        await _run_handler(
            ws,
            system_state={"s": 1},
            enhanced_services=True,
            perf_monitor=perf,
        )

        perf_sends = [
            m
            for m in _sent_payloads(ws)
            if isinstance(m, dict) and m.get("type") == "performance_update"
        ]

        assert (
            len(perf_sends) == 1
        ), f"Expected 1 performance_update (dedup), got {len(perf_sends)}"


# ---------------------------------------------------------------------------
# 4. Exception logging
# ---------------------------------------------------------------------------


class TestExceptionLogging:
    """Errors in the WebSocket handler are logged at warning level."""

    @pytest.mark.asyncio
    async def test_runtime_error_breaks_loop_cleanly(self, caplog):
        """RuntimeError (disconnect) exits loop without logging spam."""
        recv_call = 0

        async def _receive():
            nonlocal recv_call
            recv_call += 1
            if recv_call == 1:
                raise RuntimeError("Cannot call 'receive' once a disconnect")
            raise _StopLoop("should not reach here")

        send_log = []

        async def _send(data):
            send_log.append(data)

        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.close = AsyncMock()
        ws.receive_json = AsyncMock(side_effect=_receive)
        ws.send_json = AsyncMock(side_effect=_send)
        ws._send_log = send_log

        logger = logging.getLogger("backend.websocket_handlers")
        logger.propagate = True
        with caplog.at_level(logging.WARNING):
            await _run_handler(ws, enhanced_services=False)

        # RuntimeError should NOT produce a warning log (it's a clean exit)
        warning_msgs = [
            r.message
            for r in caplog.records
            if r.levelno == logging.WARNING and "error receiving" in r.message.lower()
        ]
        assert (
            warning_msgs == []
        ), f"RuntimeError should break silently, got warnings: {warning_msgs}"
        # Loop should have broken after first receive (recv_call == 1)
        assert recv_call == 1

    @pytest.mark.asyncio
    async def test_outer_exception_logged_and_client_cleaned_up(self, caplog):
        """Unrecoverable error logs a warning and cleans up client."""
        send_log = []

        async def _send(data):
            send_log.append(data)
            raise ConnectionError("gone")

        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.close = AsyncMock()
        ws.receive_json = AsyncMock(side_effect=asyncio.TimeoutError)
        ws.send_json = AsyncMock(side_effect=_send)
        ws._send_log = send_log

        initial_count = len(websocket_connections)

        logger = logging.getLogger("backend.websocket_handlers")
        logger.propagate = True
        with caplog.at_level(logging.WARNING):
            await _run_handler(ws, enhanced_services=False)

        assert (
            len(websocket_connections) == initial_count
        ), "Client should be removed from websocket_connections after error"

        warning_msgs = [
            r.message for r in caplog.records if r.levelno == logging.WARNING
        ]
        assert (
            len(warning_msgs) >= 1
        ), "Expected at least one warning for the connection error"

    @pytest.mark.asyncio
    async def test_error_not_silently_swallowed(self, caplog):
        """Errors must produce log output -- never silently lost."""
        send_log = []

        async def _send(data):
            send_log.append(data)
            raise ValueError("corrupt")

        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.close = AsyncMock()
        ws.receive_json = AsyncMock(side_effect=asyncio.TimeoutError)
        ws.send_json = AsyncMock(side_effect=_send)
        ws._send_log = send_log

        logger = logging.getLogger("backend.websocket_handlers")
        logger.propagate = True
        with caplog.at_level(logging.DEBUG):
            await _run_handler(ws, enhanced_services=False)

        warning_or_above = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warning_or_above) >= 1, (
            "Errors in WebSocket handler must be logged, not swallowed. "
            f"Log records: {[r.message for r in caplog.records]}"
        )
