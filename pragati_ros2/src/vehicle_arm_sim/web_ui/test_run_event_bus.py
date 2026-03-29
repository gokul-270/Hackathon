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
