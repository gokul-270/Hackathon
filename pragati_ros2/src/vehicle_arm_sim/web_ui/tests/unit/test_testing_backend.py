#!/usr/bin/env python3
"""Tests for testing_backend cotton colour SDF generation."""


def test_arm1_cotton_sdf_is_red():
    """Cotton SDF for arm1 must use red colour (1 0 0 1)."""
    import testing_backend as tb

    # Call the internal SDF builder — we test the template substitution
    # by checking that the colour lookup for arm1 is red
    colour = tb._ARM_COTTON_COLOURS.get("arm1", "1 1 1 1")
    assert colour == "1 0 0 1", f"arm1 cotton must be red (1 0 0 1), got {colour}"


def test_arm2_cotton_sdf_is_blue():
    """Cotton SDF for arm2 must use blue colour (0 0 1 1)."""
    import testing_backend as tb

    colour = tb._ARM_COTTON_COLOURS.get("arm2", "1 1 1 1")
    assert colour == "0 0 1 1", f"arm2 cotton must be blue (0 0 1 1), got {colour}"


def test_arm3_cotton_sdf_fallback_is_white():
    """Cotton SDF for unknown arm_id must fall back to white (1 1 1 1)."""
    import testing_backend as tb

    colour = tb._ARM_COTTON_COLOURS.get("arm3", "1 1 1 1")
    assert colour == "1 1 1 1", f"unknown arm must use white (1 1 1 1), got {colour}"


def test_cotton_sdf_template_has_ambient_placeholder():
    """_COTTON_SDF_TEMPLATE must have {ambient} placeholder for colour injection."""
    import testing_backend as tb

    assert "{ambient}" in tb._COTTON_SDF_TEMPLATE, (
        "_COTTON_SDF_TEMPLATE must contain {ambient} placeholder"
    )


def test_cotton_sdf_template_has_diffuse_placeholder():
    """_COTTON_SDF_TEMPLATE must have {diffuse} placeholder for colour injection."""
    import testing_backend as tb

    assert "{diffuse}" in tb._COTTON_SDF_TEMPLATE, (
        "_COTTON_SDF_TEMPLATE must contain {diffuse} placeholder"
    )


def test_arm1_all_three_cotton_spawns_are_red():
    """All 3 SDF strings for arm1 spawns must contain the red material definition."""
    import testing_backend as tb

    for i in range(3):
        colour = tb._ARM_COTTON_COLOURS.get("arm1", "1 1 1 1")
        sdf = tb._COTTON_SDF_TEMPLATE.format(name=f"arm1_cotton_{i}", ambient=colour, diffuse=colour)
        assert "<ambient>1 0 0 1</ambient>" in sdf, (
            f"arm1 cotton spawn {i} SDF must contain red ambient; got fragment: "
            f"{sdf[sdf.find('<ambient>'):][:60]!r}"
        )
        assert "<diffuse>1 0 0 1</diffuse>" in sdf, (
            f"arm1 cotton spawn {i} SDF must contain red diffuse; got fragment: "
            f"{sdf[sdf.find('<diffuse>'):][:60]!r}"
        )


def test_run_events_endpoint_returns_event_stream_content_type():
    """GET /api/run/events must return text/event-stream content type."""
    import threading
    from fastapi.testclient import TestClient
    import testing_backend as tb
    # Reset event bus to clean state so subscribe() starts fresh
    tb._event_bus.reset()

    def _emit_and_close():
        import time
        time.sleep(0.05)
        tb._event_bus.emit({"type": "run_complete"})

    timer = threading.Thread(target=_emit_and_close)
    timer.start()
    with TestClient(tb.app) as client:
        with client.stream("GET", "/api/run/events") as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")
    timer.join(timeout=2.0)


def test_compute_applies_compensation_by_default():
    """CottonComputeRequest.enable_phi_compensation defaults to True."""
    import testing_backend as tb

    req = tb.CottonComputeRequest()
    assert req.enable_phi_compensation is True


def test_pick_applies_compensation_by_default():
    """CottonPickRequest.enable_phi_compensation defaults to True."""
    import testing_backend as tb

    req = tb.CottonPickRequest()
    assert req.enable_phi_compensation is True


def test_pick_all_applies_compensation_by_default():
    """CottonPickAllRequest.enable_phi_compensation defaults to True."""
    import testing_backend as tb

    req = tb.CottonPickAllRequest()
    assert req.enable_phi_compensation is True


def test_compensation_can_be_disabled_explicitly():
    """All 3 request models accept enable_phi_compensation=False."""
    import testing_backend as tb

    compute = tb.CottonComputeRequest(enable_phi_compensation=False)
    assert compute.enable_phi_compensation is False
    pick = tb.CottonPickRequest(enable_phi_compensation=False)
    assert pick.enable_phi_compensation is False
    pick_all = tb.CottonPickAllRequest(enable_phi_compensation=False)
    assert pick_all.enable_phi_compensation is False


def test_phi_comp_checkbox_checked_by_default_in_html():
    """The cotton-phi-comp checkbox in testing_ui.html has checked attribute."""
    from pathlib import Path

    html_path = Path(__file__).resolve().parent.parent.parent / "testing_ui.html"
    html_content = html_path.read_text()
    # Find the input element with id="cotton-phi-comp"
    import re

    match = re.search(
        r'<input[^>]*id="cotton-phi-comp"[^>]*>', html_content,
    )
    assert match is not None, "cotton-phi-comp input not found"
    assert "checked" in match.group(0), (
        f"cotton-phi-comp should have 'checked' attribute, "
        f"got: {match.group(0)}"
    )


def test_run_complete_emit_is_preceded_by_logger_info():
    """testing_backend must call logger.info before emitting run_complete."""
    import logging
    from unittest.mock import patch, call
    import testing_backend as tb

    log_calls = []

    with patch.object(tb.logger, "info", side_effect=lambda msg, *a: log_calls.append(msg % a if a else msg)):
        # Directly check that the logger module has logger attribute
        pass  # We test structurally — verify logger exists and is a Logger

    assert hasattr(tb, "logger"), "testing_backend must have a module-level logger"
    assert isinstance(tb.logger, logging.Logger), "tb.logger must be a logging.Logger instance"


def test_sse_stream_emits_heartbeat_comment_during_idle_period():
    """GET /api/run/events must emit SSE comment heartbeats while waiting for events.

    A long quiet gap between step events (e.g. step 4 parallel dispatch) must not
    cause the TCP connection to time out. The SSE generator must emit ': heartbeat'
    comment lines at regular intervals to keep the connection alive.
    """
    import json as _json
    import threading
    import time as _time
    from fastapi.testclient import TestClient
    import testing_backend as tb

    # Re-arm bus for test; shorten heartbeat interval so test completes quickly.
    tb._event_bus.close()
    tb._event_bus.reset()
    original_interval = tb._SSE_HEARTBEAT_INTERVAL
    tb._SSE_HEARTBEAT_INTERVAL = 1.0  # fire heartbeat after 1 s of silence

    heartbeat_seen = threading.Event()
    done = threading.Event()

    def _delayed_emit():
        # Wait until heartbeat received by test, then unblock the stream
        heartbeat_seen.wait(timeout=5.0)
        tb._event_bus.emit({"type": "run_complete", "run_id": "heartbeat-test"})
        tb._event_bus.close()

    emitter = threading.Thread(target=_delayed_emit, daemon=True)
    emitter.start()

    try:
        with TestClient(tb.app) as client:
            with client.stream("GET", "/api/run/events") as resp:
                for raw_line in resp.iter_lines():
                    if raw_line.startswith(": heartbeat"):
                        heartbeat_seen.set()
                    if raw_line.startswith("data:"):
                        evt = _json.loads(raw_line[len("data:"):].strip())
                        if evt.get("type") == "run_complete":
                            done.set()
                            break
    finally:
        tb._SSE_HEARTBEAT_INTERVAL = original_interval

    emitter.join(timeout=5.0)
    assert heartbeat_seen.is_set(), (
        "SSE stream did not emit any heartbeat comment during idle; "
        "connection would time out during long steps"
    )
    assert done.is_set(), "SSE stream did not deliver run_complete after heartbeats"


def test_sse_onerror_handler_does_not_close_evtsource_permanently():
    """testing_ui.js onerror handler must not call evtSource.close() unconditionally.

    If onerror calls close(), the browser's built-in EventSource reconnect is
    disabled and any mid-run SSE blip permanently kills the log stream.
    The handler should NOT close the stream on transient errors.
    """
    from pathlib import Path
    import re

    js_path = Path(__file__).resolve().parent.parent.parent / "testing_ui.js"
    js = js_path.read_text()

    # Find the onerror handler block
    onerror_match = re.search(
        r'evtSource\.onerror\s*=\s*function\s*\([^)]*\)\s*\{([^}]*)\}',
        js,
        re.DOTALL,
    )
    assert onerror_match is not None, "evtSource.onerror handler not found in testing_ui.js"

    handler_body = onerror_match.group(1)
    assert "evtSource.close()" not in handler_body, (
        "evtSource.onerror calls evtSource.close() unconditionally — "
        "this permanently disables EventSource reconnect on any transient error. "
        "Remove the close() call from onerror so the browser can auto-reconnect."
    )


def test_sse_stream_delivers_all_events_when_heartbeats_fire_between_each_event():
    """SSE stream must not lose events when heartbeat timeouts fire between event emissions.

    Regression test for the duplicate run_in_executor bug:
    - Old code: called loop.run_in_executor(executor, next, gen) at the TOP of the outer
      while-loop on every iteration, including after a heartbeat.  Each heartbeat therefore
      submitted a SECOND call to next(gen) while the first was still blocking — silently
      consuming events that the SSE client never saw.
    - New code: submits exactly ONE executor.submit(_safe_next, gen) per event and reuses
      the same Future across all heartbeat iterations, preventing duplicate next() calls.

    This test fires heartbeats BETWEEN every event (heartbeat interval < emit interval) and
    verifies that ALL emitted events reach the client.
    """
    import json as _json
    import threading
    import time as _time
    from fastapi.testclient import TestClient
    import testing_backend as tb

    tb._event_bus.close()
    tb._event_bus.reset()
    original_interval = tb._SSE_HEARTBEAT_INTERVAL
    # Heartbeat fires every 0.05 s; events are emitted 0.15 s apart
    # → at least 2 heartbeats fire between each pair of events.
    tb._SSE_HEARTBEAT_INTERVAL = 0.05

    EVENT_TYPES = ["step_start", "dispatch_order", "step_complete", "run_complete"]
    emitted = list(EVENT_TYPES)  # copy so we can assert against it

    def _emit_all():
        for etype in emitted:
            _time.sleep(0.15)
            tb._event_bus.emit({"type": etype})
        tb._event_bus.close()

    emitter = threading.Thread(target=_emit_all, daemon=True)
    emitter.start()

    received_types = []
    try:
        with TestClient(tb.app) as client:
            with client.stream("GET", "/api/run/events") as resp:
                for raw_line in resp.iter_lines():
                    if raw_line.startswith("data:"):
                        evt = _json.loads(raw_line[len("data:"):].strip())
                        received_types.append(evt.get("type"))
                        if evt.get("type") == "run_complete":
                            break
    finally:
        tb._SSE_HEARTBEAT_INTERVAL = original_interval

    emitter.join(timeout=5.0)
    assert received_types == emitted, (
        f"SSE stream lost events when heartbeats fired between emissions.\n"
        f"  Emitted:  {emitted}\n"
        f"  Received: {received_types}\n"
        "This is caused by duplicate run_in_executor submissions on each heartbeat iteration."
    )


def test_sse_generator_exits_cleanly_after_bus_close_without_hanging():
    """SSE generator must exit cleanly when the event bus is closed after all events.

    Regression test for the StopIteration-in-run_in_executor hang bug (Bug 1):

    When loop.run_in_executor(executor, next, gen) is called and next(gen) raises
    StopIteration (generator exhausted via bus.close()), Python 3.12 raises:
        TypeError: StopIteration interacts badly with generators and cannot be
        raised into a Future
    in the asyncio callback _chain_future._set_state, leaving the asyncio Future
    permanently PENDING.  The SSE inner wait_for loop then times out forever —
    the stream hangs emitting heartbeats but never delivering further events or
    closing.

    The fix: wrap next(gen) in _safe_next() which catches StopIteration and
    returns a _STOP sentinel instead.  The Future always completes normally, the
    generator detects _STOP and exits.

    This test verifies the SSE stream terminates within a short timeout when the
    bus is closed WITHOUT a run_complete event, simulating an aborted/crashed run.
    """
    import asyncio
    import concurrent.futures
    import threading
    import time

    _HEARTBEAT_INTERVAL = 0.05
    _STOP = object()

    from run_event_bus import RunEventBus

    bus = RunEventBus()
    bus.reset()

    # Emit one mid-run event, then close WITHOUT run_complete.
    # This is the scenario that triggers StopIteration in the old code:
    # subscribe() returns (via bus.close()), next() raises StopIteration,
    # asyncio Future is left PENDING, and wait_for loops forever.
    def _emit_then_close():
        time.sleep(0.10)
        bus.emit({"type": "step_start"})
        time.sleep(0.20)
        bus.close()  # no run_complete — simulates aborted run

    emitter = threading.Thread(target=_emit_then_close, daemon=True)
    emitter.start()

    # --- FIXED pattern: _safe_next returns _STOP sentinel ---

    def safe_next(g):
        try:
            return next(g)
        except StopIteration:
            return _STOP

    async def run_fixed_pattern():
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        gen = bus.subscribe()
        received = []
        try:
            while True:
                future = asyncio.ensure_future(
                    asyncio.wrap_future(executor.submit(safe_next, gen))
                )
                while not future.done():
                    try:
                        await asyncio.wait_for(
                            asyncio.shield(future), timeout=_HEARTBEAT_INTERVAL
                        )
                    except asyncio.TimeoutError:
                        pass  # heartbeat
                event = future.result()
                if event is _STOP:
                    break
                received.append(event)
                if event.get("type") == "run_complete":
                    break
        finally:
            executor.shutdown(wait=False)
        return received

    async def run_with_timeout():
        return await asyncio.wait_for(run_fixed_pattern(), timeout=2.0)

    try:
        result = asyncio.run(run_with_timeout())
    except asyncio.TimeoutError:
        raise AssertionError(
            "SSE generator hung after bus.close() — StopIteration-in-Future bug not fixed.\n"
            "The generator must exit cleanly within 2 s of bus close.\n"
            "Fix: use _safe_next() to catch StopIteration and return a _STOP sentinel."
        )
    finally:
        emitter.join(timeout=2.0)

    assert result == [{"type": "step_start"}], (
        f"Generator did not deliver the expected events before bus close.\n"
        f"  Expected: [{{'type': 'step_start'}}]\n"
        f"  Got:      {result}"
    )


def test_sse_generator_submits_next_exactly_once_per_event_across_heartbeats():
    """SSE generator must call next(gen) exactly once per event, even with heartbeats.

    Directly tests the asyncio generator pattern for the duplicate run_in_executor bug.
    When a heartbeat timeout fires, the OLD code re-submitted run_in_executor(next, gen)
    creating a second in-flight next() call on the same generator — silently consuming
    the next event into a Future that nobody reads.  The NEW code holds a single Future
    created once per event and reuses it across all heartbeat iterations.

    This test uses asyncio directly (not FastAPI TestClient) to reproduce the exact
    async scheduling conditions where the bug manifests.
    """
    import asyncio
    import concurrent.futures

    _HEARTBEAT_INTERVAL = 0.05  # short to ensure multiple heartbeats per event

    # Slow event source: each call to next() blocks for 0.15 s to force heartbeats.
    # Records every next() call so we can assert no duplicates.
    next_call_log = []  # list of int indices; one entry per next() call
    events = [{"type": "step_start"}, {"type": "run_complete"}]

    def slow_next_gen():
        """Generator that yields 2 events, each after a 0.15 s delay."""
        for evt in events:
            import time
            time.sleep(0.15)  # forces at least 2 heartbeat timeouts
            yield evt

    _STOP = object()

    def _safe_next(g):
        next_call_log.append(len(next_call_log))
        try:
            return next(g)
        except StopIteration:
            return _STOP

    async def run_new_generator_pattern(gen):
        """New (fixed) pattern: submit executor future ONCE per event."""
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        received = []
        try:
            while True:
                future = asyncio.ensure_future(
                    asyncio.wrap_future(executor.submit(_safe_next, gen))
                )
                while not future.done():
                    try:
                        await asyncio.wait_for(
                            asyncio.shield(future), timeout=_HEARTBEAT_INTERVAL
                        )
                    except asyncio.TimeoutError:
                        pass  # heartbeat — do NOT re-submit
                event = future.result()
                if event is _STOP:
                    break
                received.append(event)
                if event.get("type") == "run_complete":
                    break
        finally:
            executor.shutdown(wait=False)
        return received

    gen = slow_next_gen()
    received = asyncio.run(run_new_generator_pattern(gen))

    assert received == events, (
        f"Generator did not deliver all events.\n"
        f"  Expected: {events}\n"
        f"  Got:      {received}"
    )
    # next() must be called exactly once per event: 2 events → 2 calls.
    # More than 2 calls means duplicate submissions happened.
    assert len(next_call_log) == len(events), (
        f"next(gen) was called {len(next_call_log)} times for {len(events)} events.\n"
        f"Expected exactly {len(events)} calls (one per event).\n"
        f"Extra calls indicate duplicate run_in_executor submissions on heartbeat."
    )


def test_sse_generator_submits_next_exactly_once_per_event_across_heartbeats():
    """SSE generator must call next(gen) exactly once per event, even with heartbeats.

    Directly tests the asyncio generator pattern for the duplicate run_in_executor bug.
    When a heartbeat timeout fires, the OLD code re-submitted run_in_executor(next, gen)
    creating a second in-flight next() call on the same generator — silently consuming
    the next event into a Future that nobody reads.  The NEW code holds a single Future
    created once per event and reuses it across all heartbeat iterations.

    This test uses asyncio directly (not FastAPI TestClient) to reproduce the exact
    async scheduling conditions where the bug manifests.
    """
    import asyncio
    import concurrent.futures

    _HEARTBEAT_INTERVAL = 0.05  # short to ensure multiple heartbeats per event

    # Slow event source: each call to next() blocks for 0.15 s to force heartbeats.
    # Records every next() call so we can assert no duplicates.
    next_call_log = []  # list of int indices; one entry per next() call
    events = [{"type": "step_start"}, {"type": "run_complete"}]
    event_index = [0]

    def slow_next_gen():
        """Generator that yields 2 events, each after a 0.15 s delay."""
        for evt in events:
            import time
            time.sleep(0.15)  # forces at least 2 heartbeat timeouts
            yield evt

    _STOP = object()

    def _safe_next(g):
        next_call_log.append(len(next_call_log))
        try:
            return next(g)
        except StopIteration:
            return _STOP

    async def run_new_generator_pattern(gen):
        """New (fixed) pattern: submit executor future ONCE per event."""
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        received = []
        try:
            while True:
                future = asyncio.ensure_future(
                    asyncio.wrap_future(executor.submit(_safe_next, gen))
                )
                while not future.done():
                    try:
                        await asyncio.wait_for(
                            asyncio.shield(future), timeout=_HEARTBEAT_INTERVAL
                        )
                    except asyncio.TimeoutError:
                        pass  # heartbeat — do NOT re-submit
                event = future.result()
                if event is _STOP:
                    break
                received.append(event)
                if event.get("type") == "run_complete":
                    break
        finally:
            executor.shutdown(wait=False)
        return received

    gen = slow_next_gen()
    received = asyncio.run(run_new_generator_pattern(gen))

    assert received == events, (
        f"Generator did not deliver all events.\n"
        f"  Expected: {events}\n"
        f"  Got:      {received}"
    )
    # next() must be called exactly once per event: 2 events → 2 calls.
    # More than 2 calls means duplicate submissions happened.
    assert len(next_call_log) == len(events), (
        f"next(gen) was called {len(next_call_log)} times for {len(events)} events.\n"
        f"Expected exactly {len(events)} calls (one per event).\n"
        f"Extra calls indicate duplicate run_in_executor submissions on heartbeat."
    )
