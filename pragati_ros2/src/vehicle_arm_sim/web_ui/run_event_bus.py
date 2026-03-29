"""Thread-safe event bus for streaming run observability events."""
import collections
import threading
from typing import Generator


class RunEventBus:
    """Thread-safe in-memory event bus for per-step run events.

    Producers call emit(). Consumers iterate subscribe() which blocks until
    new events arrive or close() is called.
    """

    def __init__(self) -> None:
        self._lock = threading.Condition(threading.Lock())
        self._queue: collections.deque = collections.deque()
        self._closed = False

    def emit(self, event: dict) -> None:
        """Append an event and notify all waiting subscribers."""
        with self._lock:
            self._queue.append(event)
            self._lock.notify_all()

    def subscribe(self) -> Generator[dict, None, None]:
        """Yield events as they arrive. Returns when close() is called."""
        cursor = 0
        while True:
            with self._lock:
                while cursor >= len(self._queue) and not self._closed:
                    self._lock.wait()
                while cursor < len(self._queue):
                    yield self._queue[cursor]
                    cursor += 1
                if self._closed:
                    return

    def close(self) -> None:
        """Signal all subscribers to stop. Idempotent."""
        with self._lock:
            self._closed = True
            self._lock.notify_all()

    def reset(self) -> None:
        """Clear all events and re-arm for the next run."""
        with self._lock:
            self._queue.clear()
            self._closed = False
