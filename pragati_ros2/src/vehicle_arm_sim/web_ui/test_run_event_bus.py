"""Tests for RunEventBus — thread-safe event bus for run observability."""
import threading
import time

import pytest


def test_run_event_bus_emit_and_subscribe_delivers_event():
    """An emitted event must be delivered to a waiting subscriber."""
    from run_event_bus import RunEventBus
    bus = RunEventBus()
    received = []

    def consume():
        for evt in bus.subscribe():
            received.append(evt)
            break  # consume one then stop

    t = threading.Thread(target=consume)
    t.start()
    time.sleep(0.01)  # let subscriber block
    bus.emit({"type": "test", "value": 42})
    t.join(timeout=1.0)
    assert received == [{"type": "test", "value": 42}]


def test_run_event_bus_close_unblocks_subscriber():
    """Calling close() must cause subscribe() to stop yielding."""
    from run_event_bus import RunEventBus
    bus = RunEventBus()
    received = []

    def consume():
        for evt in bus.subscribe():
            received.append(evt)

    t = threading.Thread(target=consume)
    t.start()
    time.sleep(0.01)
    bus.close()
    t.join(timeout=1.0)
    assert not t.is_alive(), "subscribe() did not stop after close()"


def test_run_event_bus_emit_multiple_events_in_order():
    """Multiple emitted events must be delivered in emission order."""
    from run_event_bus import RunEventBus
    bus = RunEventBus()
    received = []

    def consume():
        for evt in bus.subscribe():
            received.append(evt["n"])
            if evt["n"] == 2:
                break

    t = threading.Thread(target=consume)
    t.start()
    time.sleep(0.01)
    bus.emit({"type": "x", "n": 0})
    bus.emit({"type": "x", "n": 1})
    bus.emit({"type": "x", "n": 2})
    t.join(timeout=1.0)
    assert received == [0, 1, 2]


def test_run_event_bus_reset_clears_state_and_allows_new_subscriptions():
    """After reset(), a new subscribe() must work normally."""
    from run_event_bus import RunEventBus
    bus = RunEventBus()
    bus.emit({"type": "old"})
    bus.close()
    bus.reset()

    received = []

    def consume():
        for evt in bus.subscribe():
            received.append(evt)
            break

    t = threading.Thread(target=consume)
    t.start()
    time.sleep(0.01)
    bus.emit({"type": "new"})
    t.join(timeout=1.0)
    assert received == [{"type": "new"}]


def test_subscribe_after_close_returns_immediately():
    """subscribe() on a closed bus must return immediately without blocking."""
    from run_event_bus import RunEventBus
    bus = RunEventBus()
    bus.close()

    done = threading.Event()

    def consume():
        list(bus.subscribe())  # must drain and return
        done.set()

    t = threading.Thread(target=consume)
    t.start()
    t.join(timeout=1.0)
    assert done.is_set(), "subscribe() on a closed bus did not return promptly"


def test_subscribe_after_reset_blocks_until_emit():
    """After close() then reset(), subscribe() must block until an event is emitted."""
    from run_event_bus import RunEventBus
    bus = RunEventBus()
    bus.close()
    bus.reset()

    received = []
    subscriber_started = threading.Event()

    def consume():
        gen = bus.subscribe()
        subscriber_started.set()
        received.append(next(gen))

    t = threading.Thread(target=consume)
    t.start()
    subscriber_started.wait(timeout=1.0)
    time.sleep(0.02)  # subscriber should now be blocked (bus is open but empty)
    assert not received, "subscribe() returned prematurely on a reset bus"
    bus.emit({"type": "after_reset"})
    t.join(timeout=1.0)
    assert received == [{"type": "after_reset"}], (
        "subscribe() on a reset bus did not receive emitted event"
    )


def test_sse_stream_closes_after_run_complete():
    """subscribe() must drain and return after emit(run_complete) + close()."""
    from run_event_bus import RunEventBus
    bus = RunEventBus()

    events = []

    def consume():
        for evt in bus.subscribe():
            events.append(evt)

    t = threading.Thread(target=consume)
    t.start()
    time.sleep(0.01)
    bus.emit({"type": "run_complete", "run_id": "x"})
    bus.close()
    t.join(timeout=1.0)
    assert not t.is_alive(), "subscribe() did not stop after run_complete + close()"
    assert events[0]["type"] == "run_complete"


def test_run_event_bus_is_thread_safe_under_concurrent_emitters():
    """100 concurrent emitters must all deliver without data loss."""
    from run_event_bus import RunEventBus
    bus = RunEventBus()
    received = []
    stop = threading.Event()

    def consume():
        for evt in bus.subscribe():
            received.append(evt)
            if stop.is_set() and len(received) >= 100:
                break

    t = threading.Thread(target=consume)
    t.start()
    time.sleep(0.01)

    emitters = []
    for i in range(100):
        e = threading.Thread(target=bus.emit, args=({"type": "x", "n": i},))
        emitters.append(e)
    for e in emitters:
        e.start()
    for e in emitters:
        e.join()

    stop.set()
    bus.close()
    t.join(timeout=2.0)
    assert len(received) == 100


def test_run_active_flag_set_after_reset_and_cleared_after_close():
    """reset() must mark the bus as active; close() must mark it inactive."""
    from run_event_bus import RunEventBus
    bus = RunEventBus()

    assert not bus.run_active, "bus must not be active before first reset()"
    bus.reset()
    assert bus.run_active, "bus must be active after reset()"
    bus.close()
    assert not bus.run_active, "bus must not be active after close()"


def test_reset_while_run_active_does_not_clear_queue():
    """Calling reset() on an active bus (run in progress) must not wipe queued events."""
    from run_event_bus import RunEventBus
    bus = RunEventBus()
    bus.reset()  # marks active — simulates run_start calling reset()
    bus.emit({"type": "step_start", "step_id": 0})
    bus.emit({"type": "cotton_reached", "arm_id": "arm1"})

    # Simulate mid-run SSE reconnect calling reset() — must be a no-op
    bus.reset()

    # The queue must still have both events
    events = list(bus._queue)
    assert len(events) == 2, (
        f"reset() on active bus wiped the queue; remaining events: {events}"
    )
    assert events[0]["type"] == "step_start"
    assert events[1]["type"] == "cotton_reached"
