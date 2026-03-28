"""
Motor current draw tracking and anomaly detection.

Phase 4 of log-analyzer-enhancements:
  4.17 — Extract current_a from motor status messages, compute per-joint
         statistics, flag spikes and gradual increases.
"""

from __future__ import annotations

import statistics
from typing import TYPE_CHECKING, Dict, List

if TYPE_CHECKING:
    from ..models import EventStore

# Spike threshold: flag if current exceeds this multiplier of rolling mean
_SPIKE_MULTIPLIER = 2.5

# Gradual increase threshold: flag if late-session mean exceeds early by this
_GRADUAL_INCREASE_PCT = 30.0

# Rolling window size for spike detection
_ROLLING_WINDOW = 10

# Minimum samples per joint to include in report
MIN_SAMPLES_PER_JOINT = 10


def analyze_motor_current(
    events: "EventStore",
) -> dict:
    """Analyze motor current draw from motor_health_arm events.

    Extracts current_a from the motors list in each motor_health_arm
    event, computes per-joint statistics, detects spikes and gradual
    increases.

    Args:
        events: EventStore containing motor_health_arm events.

    Returns:
        Dict with keys:
          - "joints": dict mapping joint_id -> stats dict
          - "issues": list of issue dicts for anomalies
    """
    health_events = events.motor_health_arm
    if not health_events:
        return {"joints": {}, "issues": []}

    # Collect current readings per joint (in order)
    by_joint: Dict[str, List[float]] = {}
    transmission_ratios: Dict[str, float] = {}

    for ev in health_events:
        motors = ev.get("motors", [])
        if not isinstance(motors, list):
            continue
        for motor in motors:
            if not isinstance(motor, dict):
                continue
            joint_id = motor.get("joint") or motor.get(
                "id", "unknown"
            )
            current = motor.get("current_a")
            if current is not None:
                by_joint.setdefault(joint_id, []).append(
                    float(current)
                )
            tr = motor.get("transmission_ratio")
            if tr is not None:
                transmission_ratios[joint_id] = float(tr)

    if not by_joint:
        return {"joints": {}, "issues": []}

    joints: Dict[str, dict] = {}
    issues: List[dict] = []

    for joint_id, currents in sorted(by_joint.items()):
        n = len(currents)
        if n < MIN_SAMPLES_PER_JOINT:
            continue

        mean_a = statistics.mean(currents)
        max_a = max(currents)
        min_a = min(currents)
        stddev_a = (
            statistics.stdev(currents) if n >= 2 else 0.0
        )
        tr = transmission_ratios.get(joint_id, 0.0)

        # Spike detection: count samples > 2.5x rolling mean
        # Track the worst spike ratio for proportional severity
        spike_count = 0
        worst_spike_ratio = 0.0
        worst_spike_current = 0.0
        for i in range(len(currents)):
            window_start = max(0, i - _ROLLING_WINDOW)
            window = currents[window_start:i] if i > 0 else [mean_a]
            if not window:
                window = [mean_a]
            rolling_mean = statistics.mean(window)
            if (
                rolling_mean > 0
                and currents[i] > _SPIKE_MULTIPLIER * rolling_mean
            ):
                spike_count += 1
                ratio = currents[i] / rolling_mean
                if ratio > worst_spike_ratio:
                    worst_spike_ratio = ratio
                    worst_spike_current = currents[i]

        # Gradual increase: compare early vs late session
        split = n // 2
        early_mean = statistics.mean(currents[:split])
        late_mean = statistics.mean(currents[split:])
        gradual_increase = False
        if early_mean > 0:
            pct_change = (
                (late_mean - early_mean) / early_mean * 100.0
            )
            if pct_change > _GRADUAL_INCREASE_PCT:
                gradual_increase = True

        # Health indicator
        if spike_count > 0:
            health = "ALERT"
        elif gradual_increase:
            health = "WATCH"
        else:
            health = "OK"

        joints[joint_id] = {
            "joint_id": joint_id,
            "sample_count": n,
            "mean_a": round(mean_a, 3),
            "max_a": round(max_a, 3),
            "min_a": round(min_a, 3),
            "stddev_a": round(stddev_a, 3),
            "transmission_ratio": round(tr, 3),
            "spike_count": spike_count,
            "health_indicator": health,
        }

        # Issue: spikes — proportional severity
        if spike_count > 0:
            # Determine severity based on absolute current and
            # spike ratio relative to rolling mean:
            #   abs(current) < 0.5A → low (within motor rating)
            #   ratio 2.5x-4x      → medium
            #   ratio 4x+           → high
            if worst_spike_current < 0.5:
                spike_severity = "low"
            elif worst_spike_ratio >= 4.0:
                spike_severity = "high"
            else:
                spike_severity = "medium"
            issues.append({
                "severity": spike_severity,
                "category": "motor",
                "title": "Motor Current Spike Detected",
                "description": (
                    f"Joint '{joint_id}' had {spike_count}"
                    f" current spike(s) exceeding"
                    f" {_SPIKE_MULTIPLIER}x rolling mean"
                    f" (worst: {worst_spike_ratio:.1f}x"
                    f" at {worst_spike_current:.3f}A)."
                    f" Mean: {mean_a:.3f}A,"
                    f" Max: {max_a:.3f}A."
                ),
                "node": "arm",
                "timestamp": 0,
                "message": (
                    f"Current spikes: {joint_id}"
                    f" {spike_count}x >{_SPIKE_MULTIPLIER}x"
                    f" mean ({mean_a:.3f}A)"
                ),
                "recommendation": (
                    "Check for mechanical binding, loose"
                    " connections, or damaged motor windings."
                ),
            })

        # Issue: gradual increase
        if gradual_increase and early_mean > 0:
            pct = (late_mean - early_mean) / early_mean * 100.0
            issues.append({
                "severity": "low",
                "category": "motor",
                "title": "Motor Current Gradual Increase",
                "description": (
                    f"Joint '{joint_id}' current draw"
                    f" increased {pct:.1f}% from early"
                    f" session ({early_mean:.3f}A) to late"
                    f" session ({late_mean:.3f}A)."
                    f" Threshold: {_GRADUAL_INCREASE_PCT}%."
                ),
                "node": "arm",
                "timestamp": 0,
                "message": (
                    f"Current increase: {joint_id}"
                    f" +{pct:.1f}% over session"
                ),
                "recommendation": (
                    "Monitor for progressive mechanical"
                    " degradation or thermal effects."
                ),
            })

    return {"joints": joints, "issues": issues}


# Known transmission ratio groups for cross-joint comparison.
# Joints with the same ratio share similar mechanical loads and
# should draw comparable current.
_TRANSMISSION_RATIO_GROUPS: Dict[str, float] = {
    "joint3": 1.0,     # 1:1 direct drive
    "joint4": 12.7,    # 12.7:1 geared
    "joint5": 12.7,    # 12.7:1 geared
}

# Sigma threshold for flagging outlier joints within a ratio group
_CROSS_JOINT_SIGMA = 2.0


def detect_cross_joint_current_anomalies(
    report: dict,
) -> List[dict]:
    """Compare mean current across joints with the same transmission ratio.

    Groups joints by known transmission ratio. For each group with 2+
    joints, computes group mean and stddev of per-joint average current.
    Flags any joint whose mean current deviates by more than 2 sigma
    from its group peers.

    Args:
        report: The dict returned by ``analyze_motor_current()``, with
            a ``"joints"`` key mapping joint_id to stats dicts that
            include ``"mean_a"``.

    Returns:
        List of issue dicts (may be empty).
    """
    joints_data = report.get("joints", {})
    if not joints_data:
        return []

    # Build ratio groups: ratio_value -> [(joint_id, mean_a), ...]
    ratio_groups: Dict[float, List[tuple]] = {}
    for joint_id, stats in joints_data.items():
        ratio = _TRANSMISSION_RATIO_GROUPS.get(joint_id)
        if ratio is None:
            continue
        mean_a = stats.get("mean_a")
        if mean_a is None:
            continue
        ratio_groups.setdefault(ratio, []).append(
            (joint_id, float(mean_a))
        )

    issues: List[dict] = []

    for ratio, members in sorted(ratio_groups.items()):
        if len(members) < 2:
            continue  # skip groups with only one joint

        means = [m for _, m in members]
        group_mean = statistics.mean(means)
        group_stdev = statistics.stdev(means)

        if group_stdev == 0:
            continue  # all identical — no outliers

        for joint_id, joint_mean in members:
            deviation = abs(joint_mean - group_mean)
            if deviation > _CROSS_JOINT_SIGMA * group_stdev:
                issues.append({
                    "severity": "medium",
                    "category": "motor",
                    "title": "Cross-Joint Current Anomaly",
                    "description": (
                        f"Joint '{joint_id}' mean current"
                        f" ({joint_mean:.3f}A) deviates"
                        f" {deviation / group_stdev:.1f} sigma"
                        f" from its {ratio}:1 ratio group"
                        f" peers (group mean: {group_mean:.3f}A,"
                        f" stdev: {group_stdev:.3f}A)."
                    ),
                    "node": "arm",
                    "timestamp": 0,
                    "message": (
                        f"Current outlier: {joint_id}"
                        f" {joint_mean:.3f}A vs group"
                        f" {group_mean:.3f}A"
                        f" ({deviation / group_stdev:.1f}σ)"
                    ),
                    "recommendation": (
                        "Compare mechanical load and wiring"
                        " between same-ratio joints. Uneven"
                        " current may indicate binding,"
                         " friction, or wiring issues on"
                        f" {joint_id}."
                    ),
                })

    return issues


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
from .registry import register as _register

_register(
    "analyze_motor_current", analyze_motor_current,
    category="motor",
    description="Track per-joint motor current draw and flag spikes or gradual increases.",
)
_register(
    "detect_cross_joint_current_anomalies", detect_cross_joint_current_anomalies,
    category="motor",
    description="Compare current draw across same-ratio joints to find outliers.",
)
