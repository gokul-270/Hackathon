"""PID gain safety validation: clamps, rate limiters, and sanity checks before writing to motor.

This module provides pure-Python safety enforcement for PID tuning operations:
- Gain limit enforcement per motor type (configurable via YAML)
- Gain ramping for large parameter changes
- Oscillation detection with automatic rollback signaling
- Session locking to prevent concurrent writes to the same motor
- Session logging for audit trail and post-analysis
"""

from __future__ import annotations

import json
import logging
import math
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Gain parameter keys used throughout the module
# ---------------------------------------------------------------------------
GAIN_KEYS = [
    "position_kp",
    "position_ki",
    "speed_kp",
    "speed_ki",
    "torque_kp",
    "torque_ki",
]

# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """Result of a gain validation check."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    clamped_values: dict | None = None


@dataclass
class OscillationResult:
    """Result of an oscillation detection check."""

    detected: bool
    severity: str  # 'none', 'transient', 'sustained'
    crossings: int
    amplitude: float
    message: str


# ---------------------------------------------------------------------------
# GainLimits dataclass
# ---------------------------------------------------------------------------


@dataclass
class GainLimits:
    """Per-motor-type min/max bounds for each PID gain parameter.

    Each field is a (min, max) tuple of integers.
    """

    position_kp: tuple[int, int] = (0, 200)
    position_ki: tuple[int, int] = (0, 100)
    speed_kp: tuple[int, int] = (0, 200)
    speed_ki: tuple[int, int] = (0, 100)
    torque_kp: tuple[int, int] = (0, 150)
    torque_ki: tuple[int, int] = (0, 80)

    def as_dict(self) -> dict[str, tuple[int, int]]:
        """Return limits as a dict keyed by gain name."""
        return {k: getattr(self, k) for k in GAIN_KEYS}


# ---------------------------------------------------------------------------
# GainLimitEnforcer
# ---------------------------------------------------------------------------


class GainLimitEnforcer:
    """Validates and clamps PID gains against per-motor-type limits.

    Loads limits from YAML config files if available, otherwise falls back to
    hardcoded defaults for known motor types.
    """

    # Hardcoded defaults per motor type
    _DEFAULTS: dict[str, GainLimits] = {
        "MG6010": GainLimits(
            position_kp=(0, 200),
            position_ki=(0, 100),
            speed_kp=(0, 200),
            speed_ki=(0, 100),
            torque_kp=(0, 150),
            torque_ki=(0, 80),
        ),
        "MG6012": GainLimits(
            position_kp=(0, 200),
            position_ki=(0, 100),
            speed_kp=(0, 200),
            speed_ki=(0, 100),
            torque_kp=(0, 150),
            torque_ki=(0, 80),
        ),
    }

    # Override range when operator explicitly acknowledges expanded limits
    _OVERRIDE_RANGE: tuple[int, int] = (0, 255)

    def __init__(self, config_dir: str = "configs/pid_safety") -> None:
        self._config_dir = Path(config_dir)
        self._cache: dict[str, GainLimits] = {}

    def load_limits(self, motor_type: str) -> GainLimits:
        """Load gain limits for *motor_type*.

        Resolution order:
        1. YAML file at ``<config_dir>/<motor_type>.yaml``
        2. Hardcoded defaults for known motor types
        3. Generic MG6010 defaults as ultimate fallback
        """
        if motor_type in self._cache:
            return self._cache[motor_type]

        limits = self._load_from_yaml(motor_type)
        if limits is None:
            limits = self._DEFAULTS.get(motor_type, self._DEFAULTS["MG6010"])
            if motor_type not in self._DEFAULTS:
                logger.warning(
                    "No config or defaults for motor type '%s'; "
                    "using MG6010 defaults",
                    motor_type,
                )

        self._cache[motor_type] = limits
        return limits

    def validate_gains(
        self,
        motor_type: str,
        gains: dict,
        override: bool = False,
    ) -> ValidationResult:
        """Validate *gains* against limits for *motor_type*.

        Args:
            motor_type: Motor model identifier (e.g. ``'MG6010'``).
            gains: Dict mapping gain key names to integer values.
            override: If ``True``, expand allowed range to 0-255 for all
                parameters (operator must explicitly acknowledge).

        Returns:
            :class:`ValidationResult` with ``valid=True`` if all gains are
            within limits, or ``valid=False`` with per-field error messages.
        """
        limits = self.load_limits(motor_type)
        errors: list[str] = []

        for key in GAIN_KEYS:
            if key not in gains:
                continue
            value = gains[key]

            if override:
                lo, hi = self._OVERRIDE_RANGE
            else:
                lo, hi = getattr(limits, key)

            if not isinstance(value, (int, float)):
                errors.append(f"{key}: value must be numeric, got {type(value).__name__}")
                continue

            value = int(value)
            if value < lo or value > hi:
                errors.append(f"{key}: {value} out of range [{lo}, {hi}]")

        return ValidationResult(valid=len(errors) == 0, errors=errors)

    def clamp_gains(self, motor_type: str, gains: dict) -> dict:
        """Clamp each gain in *gains* to the limits for *motor_type*.

        Returns a new dict with clamped values.  Keys not in :data:`GAIN_KEYS`
        are passed through unchanged.
        """
        limits = self.load_limits(motor_type)
        clamped: dict[str, Any] = {}

        for key, value in gains.items():
            if key in GAIN_KEYS:
                lo, hi = getattr(limits, key)
                clamped[key] = max(lo, min(hi, int(value)))
            else:
                clamped[key] = value

        return clamped

    # -- internal helpers ---------------------------------------------------

    def _load_from_yaml(self, motor_type: str) -> GainLimits | None:
        """Attempt to load limits from a YAML config file."""
        path = self._config_dir / f"{motor_type}.yaml"
        if not path.is_file():
            return None

        try:
            with open(path, "r") as fh:
                data = yaml.safe_load(fh)

            if not isinstance(data, dict):
                logger.warning("Invalid YAML structure in %s", path)
                return None

            kwargs: dict[str, tuple[int, int]] = {}
            for key in GAIN_KEYS:
                if key in data:
                    entry = data[key]
                    if isinstance(entry, dict):
                        kwargs[key] = (int(entry.get("min", 0)), int(entry.get("max", 255)))
                    elif isinstance(entry, (list, tuple)) and len(entry) == 2:
                        kwargs[key] = (int(entry[0]), int(entry[1]))

            return GainLimits(**kwargs) if kwargs else None
        except Exception:
            logger.exception("Failed to load YAML config from %s", path)
            return None


# ---------------------------------------------------------------------------
# GainRamper
# ---------------------------------------------------------------------------


class GainRamper:
    """Computes intermediate gain steps when a parameter change is large.

    When the delta between current and target exceeds *max_step* for any
    parameter, the change is broken into multiple steps of at most *max_step*
    per parameter per step.
    """

    def __init__(self, max_step: int = 20, delay_ms: int = 100) -> None:
        self.max_step = max_step
        self.delay_ms = delay_ms

    def needs_ramping(self, current: dict, target: dict) -> bool:
        """Return ``True`` if any parameter delta exceeds *max_step*."""
        for key in GAIN_KEYS:
            if key in current and key in target:
                if abs(int(target[key]) - int(current[key])) > self.max_step:
                    return True
        return False

    def compute_ramp_steps(self, current: dict, target: dict) -> list[dict]:
        """Compute intermediate gain dicts from *current* to *target*.

        Each returned dict represents a full set of gain values to apply.
        The final entry in the list equals *target* (for the keys present in
        both *current* and *target*).

        Parameters not present in both dicts are taken from *target* in every
        step.
        """
        # Determine the number of steps needed (driven by largest delta)
        max_delta = 0
        active_keys: list[str] = []
        for key in GAIN_KEYS:
            if key in current and key in target:
                active_keys.append(key)
                delta = abs(int(target[key]) - int(current[key]))
                if delta > max_delta:
                    max_delta = delta

        if max_delta == 0:
            return [dict(target)]

        num_steps = math.ceil(max_delta / self.max_step)

        steps: list[dict] = []
        for i in range(1, num_steps + 1):
            step: dict[str, int] = {}
            for key in active_keys:
                cur = int(current[key])
                tgt = int(target[key])
                # Linear interpolation, snapping to target on last step
                if i == num_steps:
                    step[key] = tgt
                else:
                    step[key] = cur + round((tgt - cur) * i / num_steps)
            # Include keys only in target (not being ramped)
            for key in target:
                if key not in step:
                    step[key] = target[key]
            steps.append(step)

        return steps


# ---------------------------------------------------------------------------
# OscillationDetector
# ---------------------------------------------------------------------------


class OscillationDetector:
    """Detects oscillation in position error using zero-crossing analysis.

    Oscillation is flagged when more than *min_crossings* zero-crossings occur
    within *window_seconds* and the peak-to-peak amplitude exceeds
    *amplitude_factor* times the steady-state error band.
    """

    # Duration below which oscillation is considered transient
    _TRANSIENT_THRESHOLD_S: float = 0.5

    def __init__(
        self,
        window_seconds: float = 2.0,
        min_crossings: int = 3,
        amplitude_factor: float = 2.0,
    ) -> None:
        self.window_seconds = window_seconds
        self.min_crossings = min_crossings
        self.amplitude_factor = amplitude_factor

        # Internal state
        self._history: list[tuple[float, float]] = []  # (timestamp, error)
        self._steady_state_band: float = 1.0  # default error band

    @property
    def steady_state_band(self) -> float:
        """Current steady-state error band used as baseline."""
        return self._steady_state_band

    @steady_state_band.setter
    def steady_state_band(self, value: float) -> None:
        self._steady_state_band = max(value, 0.01)  # prevent zero-division

    def update(self, timestamp: float, position_error: float) -> None:
        """Feed a new data point into the detector."""
        self._history.append((timestamp, position_error))
        self._prune(timestamp)

    def check(self) -> OscillationResult:
        """Analyse the current window for oscillation.

        Returns:
            :class:`OscillationResult` describing detection state.
        """
        if len(self._history) < 2:
            return OscillationResult(
                detected=False,
                severity="none",
                crossings=0,
                amplitude=0.0,
                message="Insufficient data",
            )

        # Count zero-crossings and compute amplitude within window
        crossings = 0
        min_err = float("inf")
        max_err = float("-inf")
        first_crossing_ts: float | None = None
        last_crossing_ts: float | None = None

        for i in range(1, len(self._history)):
            _, prev_err = self._history[i - 1]
            ts, cur_err = self._history[i]

            min_err = min(min_err, cur_err)
            max_err = max(max_err, cur_err)

            # Zero-crossing: sign change (treat exact zero as crossing)
            if (prev_err > 0 and cur_err <= 0) or (prev_err < 0 and cur_err >= 0):
                crossings += 1
                if first_crossing_ts is None:
                    first_crossing_ts = ts
                last_crossing_ts = ts

        # Also include the first sample in amplitude
        min_err = min(min_err, self._history[0][1])
        max_err = max(max_err, self._history[0][1])

        amplitude = max_err - min_err
        amplitude_threshold = self.amplitude_factor * self._steady_state_band

        if crossings > self.min_crossings and amplitude > amplitude_threshold:
            # Determine duration of oscillation
            if (
                first_crossing_ts is not None
                and last_crossing_ts is not None
                and (last_crossing_ts - first_crossing_ts) < self._TRANSIENT_THRESHOLD_S
            ):
                return OscillationResult(
                    detected=True,
                    severity="transient",
                    crossings=crossings,
                    amplitude=amplitude,
                    message=(
                        f"Transient oscillation: {crossings} crossings, "
                        f"amplitude {amplitude:.2f} (< {self._TRANSIENT_THRESHOLD_S}s)"
                    ),
                )
            return OscillationResult(
                detected=True,
                severity="sustained",
                crossings=crossings,
                amplitude=amplitude,
                message=(
                    f"Sustained oscillation detected: {crossings} crossings, "
                    f"amplitude {amplitude:.2f}"
                ),
            )

        return OscillationResult(
            detected=False,
            severity="none",
            crossings=crossings,
            amplitude=amplitude,
            message="No oscillation detected",
        )

    def reset(self) -> None:
        """Clear history (call after gain rollback)."""
        self._history.clear()

    def _prune(self, now: float) -> None:
        """Remove samples outside the sliding window."""
        cutoff = now - self.window_seconds
        while self._history and self._history[0][0] < cutoff:
            self._history.pop(0)


# ---------------------------------------------------------------------------
# TuningSessionLock
# ---------------------------------------------------------------------------


class TuningSessionLock:
    """Ensures only one tuning session can write to a given motor at a time.

    Thread-safe.  Supports inactivity timeout to automatically release stale
    locks.
    """

    def __init__(self, timeout_seconds: float = 300.0) -> None:
        self._timeout = timeout_seconds
        self._lock = threading.Lock()
        # motor_id -> (session_id, last_activity_timestamp)
        self._locks: dict[int, tuple[str, float]] = {}

    def acquire(self, motor_id: int, session_id: str) -> bool:
        """Try to lock *motor_id* for *session_id*.

        Returns ``True`` if the lock was acquired (or already held by the same
        session).  Returns ``False`` if a different session holds the lock.
        """
        with self._lock:
            self._cleanup_expired_internal()

            if motor_id in self._locks:
                held_session, _ = self._locks[motor_id]
                if held_session == session_id:
                    # Same session — refresh timestamp
                    self._locks[motor_id] = (session_id, time.monotonic())
                    return True
                return False

            self._locks[motor_id] = (session_id, time.monotonic())
            return True

    def release(self, motor_id: int, session_id: str) -> bool:
        """Release lock on *motor_id* if held by *session_id*.

        Returns ``True`` if the lock was released, ``False`` otherwise.
        """
        with self._lock:
            if motor_id in self._locks:
                held_session, _ = self._locks[motor_id]
                if held_session == session_id:
                    del self._locks[motor_id]
                    return True
            return False

    def is_locked(self, motor_id: int) -> tuple[bool, str | None]:
        """Check if *motor_id* is locked.

        Returns a tuple of ``(is_locked, session_id_or_None)``.
        """
        with self._lock:
            self._cleanup_expired_internal()
            if motor_id in self._locks:
                session_id, _ = self._locks[motor_id]
                return True, session_id
            return False, None

    def touch(self, motor_id: int, session_id: str) -> None:
        """Update the activity timestamp for a lock held by *session_id*."""
        with self._lock:
            if motor_id in self._locks:
                held_session, _ = self._locks[motor_id]
                if held_session == session_id:
                    self._locks[motor_id] = (session_id, time.monotonic())

    def cleanup_expired(self) -> None:
        """Release all locks that have exceeded the inactivity timeout."""
        with self._lock:
            self._cleanup_expired_internal()

    def _cleanup_expired_internal(self) -> None:
        """Internal cleanup — caller must hold ``self._lock``."""
        now = time.monotonic()
        expired = [
            mid
            for mid, (_, ts) in self._locks.items()
            if (now - ts) > self._timeout
        ]
        for mid in expired:
            logger.info("Session lock expired for motor %d", mid)
            del self._locks[mid]


# ---------------------------------------------------------------------------
# TuningSessionLogger
# ---------------------------------------------------------------------------


class TuningSessionLogger:
    """Logs all PID tuning operations to per-session JSON files.

    Each session creates a JSON file at
    ``<session_dir>/<timestamp>_<motor_id>.json`` containing a list of
    timestamped events.
    """

    # Recognised event types
    VALID_EVENT_TYPES = frozenset(
        {
            "pid_read",
            "pid_write",
            "pid_write_rom",
            "step_test_start",
            "step_test_end",
            "oscillation_detected",
            "gain_rollback",
            "limit_override",
            "safety_event",
        }
    )

    def __init__(self, session_dir: str = "data/pid_sessions") -> None:
        self._session_dir = Path(session_dir)
        self._lock = threading.Lock()
        # session_id -> {"path": Path, "motor_id": int, "motor_type": str,
        #                "events": list, "active": bool}
        self._sessions: dict[str, dict[str, Any]] = {}

    def start_session(self, motor_id: int, motor_type: str) -> str:
        """Create a new session log file and return the session ID."""
        session_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc)
        timestamp_str = now.strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp_str}_{motor_id}.json"

        self._session_dir.mkdir(parents=True, exist_ok=True)
        filepath = self._session_dir / filename

        session_record: dict[str, Any] = {
            "path": filepath,
            "motor_id": motor_id,
            "motor_type": motor_type,
            "events": [],
            "active": True,
            "started_at": now.isoformat(),
        }

        with self._lock:
            self._sessions[session_id] = session_record

        # Write initial header
        self._flush(session_id)
        logger.info(
            "Started tuning session %s for motor %d (%s)",
            session_id,
            motor_id,
            motor_type,
        )
        return session_id

    def log_event(self, session_id: str, event_type: str, data: dict) -> None:
        """Append an event to the session log.

        Args:
            session_id: ID returned by :meth:`start_session`.
            event_type: One of :attr:`VALID_EVENT_TYPES`.
            data: Arbitrary event payload.

        Raises:
            ValueError: If *session_id* is unknown or *event_type* is invalid.
        """
        if event_type not in self.VALID_EVENT_TYPES:
            raise ValueError(
                f"Invalid event type '{event_type}'; "
                f"valid types: {sorted(self.VALID_EVENT_TYPES)}"
            )

        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise ValueError(f"Unknown session ID: {session_id}")

            event = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_type": event_type,
                "data": data,
            }
            session["events"].append(event)

        self._flush(session_id)

    def end_session(self, session_id: str) -> None:
        """Finalize a session log.

        Marks the session as inactive and writes the final JSON file.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise ValueError(f"Unknown session ID: {session_id}")
            session["active"] = False
            session["ended_at"] = datetime.now(timezone.utc).isoformat()

        self._flush(session_id)
        logger.info("Ended tuning session %s", session_id)

    def get_session_log(self, session_id: str) -> list[dict]:
        """Read back all events for a session.

        If the session is still in-memory, returns the in-memory events.
        Otherwise, reads from the JSON file on disk.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                return list(session["events"])

        # Fallback: scan session dir for the file (not typical in normal flow)
        raise ValueError(f"Unknown session ID: {session_id}")

    # -- internal helpers ---------------------------------------------------

    def _flush(self, session_id: str) -> None:
        """Write the current session state to disk as JSON."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return

            payload = {
                "session_id": session_id,
                "motor_id": session["motor_id"],
                "motor_type": session["motor_type"],
                "started_at": session["started_at"],
                "ended_at": session.get("ended_at"),
                "active": session["active"],
                "events": session["events"],
            }
            filepath: Path = session["path"]

        # Write outside of lock to avoid holding it during I/O
        try:
            with open(filepath, "w") as fh:
                json.dump(payload, fh, indent=2)
        except OSError:
            logger.exception("Failed to write session log to %s", filepath)
