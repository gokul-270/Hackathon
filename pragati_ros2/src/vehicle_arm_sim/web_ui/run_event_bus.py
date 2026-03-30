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
        self._run_active = False

    @property
    def run_active(self) -> bool:
        """True while a run is in progress (between reset() and close())."""
        with self._lock:
            return self._run_active

    def emit(self, event: dict) -> None:
        """Append an event and notify all waiting subscribers."""
        with self._lock:
            self._queue.append(event)
            self._lock.notify_all()

    def subscribe(self) -> Generator[dict, None, None]:
        """Yield events as they arrive. Returns when close() is called.

        The lock is released before each yield so that producers (emit/close)
        are never blocked by a suspended consumer.  Without this, calling
        emit() from the asyncio event-loop thread while the SSE generator is
        suspended mid-yield causes a deadlock: the event loop cannot re-enter
        next(gen) to release the lock, and emit() cannot acquire it.
        """
        cursor = 0
        while True:
            # Collect the next batch of available events under the lock,
            # then yield them outside the lock so producers can proceed.
            with self._lock:
                while cursor >= len(self._queue) and not self._closed:
                    self._lock.wait()
                pending = list(self._queue)[cursor:]
                cursor += len(pending)
                closed = self._closed

            for event in pending:
                yield event

            if closed:
                return

    def close(self) -> None:
        """Signal all subscribers to stop. Idempotent."""
        with self._lock:
            self._closed = True
            self._run_active = False
            self._lock.notify_all()

    def reset(self) -> None:
        """Clear all events and re-arm for the next run.

        No-op if the bus is already active (run in progress). This prevents
        a mid-run SSE reconnect from wiping the event queue of an active run.
        Only the first caller (POST /api/run/start) transitions idle→active.
        """
        with self._lock:
            if self._run_active:
                return  # mid-run reconnect: do NOT wipe the active queue
            self._queue.clear()
            self._closed = False
            self._run_active = True
