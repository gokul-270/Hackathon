"""Step response metrics computation.

Computes rise time, settling time, overshoot, steady-state error, and integral
error metrics (IAE, ISE, ITSE) for a recorded step response.  All calculations
are pure NumPy — no scipy or ROS2 dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np


# ---------------------------------------------------------------------------
# Default performance targets (from spec / PRD)
# ---------------------------------------------------------------------------

DEFAULT_TARGETS: Dict[str, float] = {
    "rise_time": 0.5,         # seconds
    "settling_time": 1.0,     # seconds
    "overshoot_percent": 10.0,  # %
    "steady_state_error": 0.5,  # degrees
}


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class StepMetrics:
    """Performance metrics extracted from a step response.

    Attributes:
        rise_time: Time from 10 % to 90 % of the step (seconds).
        settling_time: Time to remain within 2 % of final value (seconds).
        overshoot_percent: (peak - setpoint) / step_size * 100.
        steady_state_error: |final_average - setpoint| in degrees.
        iae: Integral of Absolute Error.
        ise: Integral of Squared Error.
        itse: Integral of Time-weighted Squared Error.
        data_points: Number of samples in the response.
        confidence: 'high' / 'medium' / 'low'.
    """

    rise_time: float = float("nan")
    settling_time: float = float("nan")
    overshoot_percent: float = float("nan")
    steady_state_error: float = float("nan")
    iae: float = float("nan")
    ise: float = float("nan")
    itse: float = float("nan")
    data_points: int = 0
    confidence: str = "low"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_step_metrics(
    timestamps: np.ndarray,
    positions: np.ndarray,
    setpoint: float,
    step_size: float,
) -> StepMetrics:
    """Compute standard step-response metrics.

    Args:
        timestamps: 1-D monotonic time array in seconds.
        positions: 1-D measured position array (same length as timestamps).
        setpoint: Target position (after the step command).
        step_size: Magnitude of the step input (positive, in degrees).

    Returns:
        StepMetrics populated with the computed values.
    """
    ts = np.asarray(timestamps, dtype=np.float64)
    pos = np.asarray(positions, dtype=np.float64)
    metrics = StepMetrics(data_points=ts.size)

    if ts.size < 2 or pos.size < 2 or ts.size != pos.size:
        metrics.confidence = "low"
        return metrics

    if step_size == 0.0:
        metrics.confidence = "low"
        return metrics

    metrics.confidence = assess_confidence(ts, pos)

    initial_value = float(pos[0])
    abs_step = abs(step_size)

    # Use the sign of step_size to determine direction.
    sign = 1.0 if step_size > 0 else -1.0

    # Normalised response: 0 at start, 1 at setpoint.
    normalised = (pos - initial_value) * sign / abs_step

    # --- Rise time (10 % → 90 %) ---
    t10 = _first_crossing(ts, normalised, 0.10)
    t90 = _first_crossing(ts, normalised, 0.90)
    if t10 is not None and t90 is not None and t90 > t10:
        metrics.rise_time = t90 - t10

    # --- Overshoot ---
    if sign > 0:
        peak = float(np.max(pos))
    else:
        peak = float(np.min(pos))
    overshoot_abs = (peak - setpoint) * sign
    if overshoot_abs > 0:
        metrics.overshoot_percent = overshoot_abs / abs_step * 100.0
    else:
        metrics.overshoot_percent = 0.0

    # --- Steady-state error (average of last 20 % of data) ---
    tail_start = max(1, int(0.8 * ts.size))
    final_avg = float(np.mean(pos[tail_start:]))
    metrics.steady_state_error = abs(final_avg - setpoint)

    # --- Settling time (2 % band of final value) ---
    band = 0.02 * abs_step
    within_band = np.abs(pos - final_avg) <= band
    # Find the last index that is NOT within the band; settling time is the
    # timestamp just after that.
    outside_indices = np.where(~within_band)[0]
    if outside_indices.size > 0:
        last_outside = int(outside_indices[-1])
        if last_outside + 1 < ts.size:
            metrics.settling_time = float(
                ts[last_outside + 1] - ts[0]
            )
        else:
            # Never fully settled within the recording.
            metrics.settling_time = float(ts[-1] - ts[0])
    else:
        # Was always within the band (e.g. perfect step).
        metrics.settling_time = 0.0

    # --- Integral error metrics ---
    error = pos - setpoint
    dt = np.diff(ts)
    # Use midpoint values for trapezoidal-ish integration.
    error_mid = 0.5 * (error[:-1] + error[1:])
    t_mid = 0.5 * (ts[:-1] + ts[1:]) - ts[0]

    abs_error_mid = np.abs(error_mid)
    metrics.iae = float(np.sum(abs_error_mid * dt))
    metrics.ise = float(np.sum(error_mid ** 2 * dt))
    metrics.itse = float(np.sum(t_mid * error_mid ** 2 * dt))

    return metrics


def assess_confidence(
    timestamps: np.ndarray,
    positions: np.ndarray,
) -> str:
    """Assess data quality confidence level.

    Args:
        timestamps: 1-D time array.
        positions: 1-D position array.

    Returns:
        'high', 'medium', or 'low'.
    """
    ts = np.asarray(timestamps, dtype=np.float64)
    pos = np.asarray(positions, dtype=np.float64)

    n = min(ts.size, pos.size)
    if n < 10:
        return "low"

    # Estimate noise by comparing the raw signal to a smoothed version.
    # A moving-average filter removes high-frequency noise; the residual
    # standard deviation relative to the signal range gives a noise ratio.
    signal_range = float(np.ptp(pos[:n]))
    if signal_range <= 0:
        return "low"

    # Smoothing window: ~5% of data but at least 3, at most 51.
    win = max(3, min(51, n // 20 | 1))  # ensure odd
    if win >= n:
        win = n if n % 2 == 1 else n - 1
    if win < 3:
        return "low"

    kernel = np.ones(win) / win
    smoothed = np.convolve(pos[:n], kernel, mode="same")
    # Trim edges where convolution padding introduces artefacts.
    trim = win // 2
    interior = slice(trim, n - trim) if n > 2 * trim else slice(None)
    residual_std = float(np.std(pos[interior] - smoothed[interior]))
    noise_ratio = residual_std / signal_range

    if n > 20 and noise_ratio < 0.03:
        return "high"
    if n >= 10 and noise_ratio < 0.10:
        return "medium"
    return "low"

    kernel = np.ones(win) / win
    smoothed = np.convolve(pos[:n], kernel, mode="same")
    residual_std = float(np.std(pos[:n] - smoothed))
    noise_ratio = residual_std / signal_range

    if n > 20 and noise_ratio < 0.02:
        return "high"
    if n >= 10 and noise_ratio < 0.10:
        return "medium"
    return "low"


def check_targets(
    metrics: StepMetrics,
    targets: Optional[Dict[str, float]] = None,
) -> Dict[str, bool]:
    """Check whether metrics meet performance targets.

    Args:
        metrics: Computed step-response metrics.
        targets: Dict mapping metric names to threshold values.
            Defaults to ``DEFAULT_TARGETS``.

    Returns:
        Dict mapping each target name to True (pass) or False (fail).
    """
    if targets is None:
        targets = DEFAULT_TARGETS

    results: Dict[str, bool] = {}

    for name, threshold in targets.items():
        value = getattr(metrics, name, None)
        if value is None or (isinstance(value, float) and np.isnan(value)):
            results[name] = False
        else:
            results[name] = float(value) <= threshold

    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _first_crossing(
    ts: np.ndarray,
    normalised: np.ndarray,
    level: float,
) -> Optional[float]:
    """Find the first time the normalised response crosses *level*.

    Uses linear interpolation between samples for sub-sample accuracy.

    Returns:
        Time of crossing, or None if never crossed.
    """
    for i in range(len(normalised) - 1):
        if normalised[i] <= level <= normalised[i + 1]:
            # Linear interpolation.
            denom = normalised[i + 1] - normalised[i]
            if abs(denom) < 1e-15:
                return float(ts[i])
            frac = (level - normalised[i]) / denom
            return float(ts[i] + frac * (ts[i + 1] - ts[i]))
        # Also handle descending crossings (for negative step).
        if normalised[i] >= level >= normalised[i + 1]:
            denom = normalised[i + 1] - normalised[i]
            if abs(denom) < 1e-15:
                return float(ts[i])
            frac = (level - normalised[i]) / denom
            return float(ts[i] + frac * (ts[i + 1] - ts[i]))
    return None
