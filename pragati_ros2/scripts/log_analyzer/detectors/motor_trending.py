"""
Motor position trending analysis.

Phase 4 of log-analyzer-enhancements:
  4.1 — Per-joint homing statistics (mean, max, stddev of position_error)
  4.3 — Threshold-based issue flagging
  4.15 — Per-joint error tolerance (Joint3=0.050, others=0.010)
"""

from __future__ import annotations

import statistics
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from ..models import EventStore

# Default threshold for mean position error (rotations)
DEFAULT_MEAN_ERROR_THRESHOLD = 0.01

# Per-joint default thresholds (task 4.15)
# Joint3 has 10x larger tolerance due to mechanical characteristics
DEFAULT_JOINT_TOLERANCES: Dict[str, float] = {
    "Joint3": 0.050,
}
# Fallback for joints not in the above dict
DEFAULT_JOINT_TOLERANCE_FALLBACK = 0.010


def _linear_slope(values: List[float]) -> float:
    """Compute least-squares linear regression slope.

    Uses simple linear regression: slope = sum((x-x_mean)(y-y_mean)) / sum((x-x_mean)^2)
    where x is the 0-based index. Returns 0.0 for fewer than 2 values.
    """
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    num = sum(
        (i - x_mean) * (y - y_mean) for i, y in enumerate(values)
    )
    den = sum((i - x_mean) ** 2 for i in range(n))
    if den == 0.0:
        return 0.0
    return num / den


def _trend_direction(slope: float, threshold: float = 1e-6) -> str:
    """Classify slope into trend direction.

    Returns "improving" (negative slope = errors decreasing),
    "degrading" (positive slope = errors increasing),
    or "stable" (near zero).
    """
    if abs(slope) < threshold:
        return "stable"
    return "degrading" if slope > 0 else "improving"


def analyze_motor_trending(
    events: "EventStore",
    mean_error_threshold: float = DEFAULT_MEAN_ERROR_THRESHOLD,
    joint_tolerances: Optional[Dict[str, float]] = None,
) -> Dict:
    """Analyze homing events for per-joint position error statistics.

    Args:
        events: EventStore containing homing_events.
        mean_error_threshold: Flat threshold for mean error flagging
            (default 0.01 rot). Used as fallback when joint_tolerances
            is not provided.
        joint_tolerances: Optional dict mapping joint name to threshold.
            Overrides per-joint defaults when provided. Falls back to
            DEFAULT_JOINT_TOLERANCES then DEFAULT_JOINT_TOLERANCE_FALLBACK.

    Returns:
        Dict with keys:
          - "joints": dict mapping joint_id -> stats dict
          - "issues": list of issue dicts for joints exceeding threshold
    """
    homing = events.homing_events
    if not homing:
        return {"joints": {}, "issues": []}

    # Build effective tolerance map
    effective_tolerances: Dict[str, float] = {}
    effective_tolerances.update(DEFAULT_JOINT_TOLERANCES)
    if joint_tolerances:
        effective_tolerances.update(joint_tolerances)

    # Group position_error values by joint
    by_joint: Dict[str, List[float]] = {}
    for ev in homing:
        joint = ev.get("joint") or ev.get("id", "unknown")
        pos_err = ev.get("position_error")
        if pos_err is not None:
            by_joint.setdefault(joint, []).append(float(pos_err))

    joints: Dict[str, dict] = {}
    issues: List[dict] = []

    for joint_id, errors in sorted(by_joint.items()):
        n = len(errors)
        if n < 2:
            continue  # need at least 2 events for trending

        mean_err = statistics.mean(errors)
        max_err = max(errors)
        stddev = statistics.stdev(errors) if n >= 2 else 0.0
        slope = _linear_slope(errors)
        trend = _trend_direction(slope)

        joints[joint_id] = {
            "joint_id": joint_id,
            "event_count": n,
            "mean_error": round(mean_err, 6),
            "max_error": round(max_err, 6),
            "stddev": round(stddev, 6),
            "trend_direction": trend,
            "slope": round(slope, 8),
        }

        # Task 4.15 — per-joint threshold lookup
        threshold = effective_tolerances.get(
            joint_id, DEFAULT_JOINT_TOLERANCE_FALLBACK
        )

        # Task 4.3 — flag joints with mean error exceeding threshold
        if mean_err > threshold:
            issues.append({
                "severity": "medium",
                "category": "motor",
                "title": "Motor Position Error Trending High",
                "description": (
                    f"Joint '{joint_id}' has mean homing"
                    f" position error of {mean_err:.4f} rot"
                    f" (threshold: {threshold} rot)"
                    f" across {n} homing events."
                    f" Trend: {trend}."
                ),
                "node": "arm",
                "timestamp": 0,
                "message": (
                    f"High position error: {joint_id}"
                    f" mean={mean_err:.4f} rot ({trend})"
                ),
                "recommendation": (
                    "Inspect joint mechanical alignment and"
                    " encoder calibration. Degrading trend"
                    " indicates progressive wear."
                ),
            })

    return {"joints": joints, "issues": issues}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
from .registry import register as _register

_register(
    "analyze_motor_trending", analyze_motor_trending,
    category="motor",
    description="Analyze per-joint homing position error trends over time.",
)
