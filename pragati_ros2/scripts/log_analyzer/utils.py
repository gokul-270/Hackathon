"""
Shared utility functions for the log_analyzer package.
"""

import sys
import time
from typing import Iterator, Optional, TypeVar

T = TypeVar("T")


def format_duration(seconds: float) -> str:
    """Convert raw seconds to human-readable ``Xh Ym Zs`` format.

    Rules:
    - Fractional seconds are truncated (not rounded).
    - Zero components are omitted (e.g. ``5m`` not ``5m 0s``).
    - ``0`` seconds returns ``"0s"``.

    Examples::

        >>> format_duration(0)
        '0s'
        >>> format_duration(45.2)
        '45s'
        >>> format_duration(300.0)
        '5m'
        >>> format_duration(672.3)
        '11m 12s'
        >>> format_duration(3600.0)
        '1h'
        >>> format_duration(3930.0)
        '1h 5m 30s'
    """
    total = int(seconds)  # truncate fractional part
    if total <= 0:
        return "0s"

    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60

    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs:
        parts.append(f"{secs}s")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Progress indication (task 6.3)
# ---------------------------------------------------------------------------


class ProgressTracker:
    """Lightweight file-processing progress indicator.

    Prints ``[3/10] 30%  elapsed 5s`` style updates to stderr.

    Suppression rules:
    - Single file: no output.
    - Non-TTY stderr: no output.
    - Total elapsed < 2s: no output (deferred until threshold crossed).

    When *tqdm* is available it is preferred over raw carriage-return updates.
    Updates are throttled to 4 Hz max (250 ms minimum interval).
    """

    _MIN_INTERVAL_S: float = 0.25  # 4 Hz throttle

    def __init__(self, total: int) -> None:
        self._total = total
        self._current = 0
        self._start = time.monotonic()
        self._last_update = 0.0
        self._tqdm_bar: Optional[object] = None
        self._use_tqdm = False
        self._suppressed = total <= 1 or not _stderr_is_tty()

        if self._suppressed:
            return

        try:
            import tqdm as _tqdm_mod  # type: ignore[import-untyped]

            self._tqdm_bar = _tqdm_mod.tqdm(
                total=total,
                desc="Analyzing",
                unit="file",
                file=sys.stderr,
                leave=False,
                dynamic_ncols=True,
            )
            self._use_tqdm = True
        except ImportError:
            pass

    def update(self, n: int = 1) -> None:
        """Advance the counter by *n* and maybe print a status line."""
        self._current += n
        if self._suppressed:
            return

        now = time.monotonic()
        elapsed = now - self._start

        # Suppress until 2s have passed
        if elapsed < 2.0:
            return

        # Throttle to 4 Hz
        if now - self._last_update < self._MIN_INTERVAL_S:
            return

        self._last_update = now

        if self._use_tqdm and self._tqdm_bar is not None:
            self._tqdm_bar.update(n)  # type: ignore[union-attr]
        else:
            pct = (
                100 * self._current // self._total
                if self._total
                else 0
            )
            elapsed_str = format_duration(elapsed)
            msg = (
                f"\r  [{self._current}/{self._total}]"
                f" {pct}%  elapsed {elapsed_str}"
            )
            sys.stderr.write(msg)
            sys.stderr.flush()

    def finish(self) -> None:
        """Clear / close the progress line."""
        if self._suppressed:
            return
        if self._use_tqdm and self._tqdm_bar is not None:
            self._tqdm_bar.close()  # type: ignore[union-attr]
        else:
            elapsed = time.monotonic() - self._start
            if elapsed >= 2.0:
                # Clear the line
                sys.stderr.write("\r" + " " * 60 + "\r")
                sys.stderr.flush()


def _stderr_is_tty() -> bool:
    """Return True when stderr is connected to a terminal."""
    try:
        return hasattr(sys.stderr, "isatty") and sys.stderr.isatty()
    except Exception:
        return False

