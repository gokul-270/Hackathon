"""
Trend detection functions for field summary reports.

Groups 17 and 24.7 of the vehicle-log-analyzer change.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Dict, List, Tuple

from ._helpers import _hour_bucket

if TYPE_CHECKING:
    from ..analyzer import ROS2LogAnalyzer
    from ..models import FieldSummary


def detect_trends(analyzer: "ROS2LogAnalyzer", summary: "FieldSummary") -> None:
    """
    task 17.1 — Detect performance trends across the session.
    """
    session_start = analyzer.start_time or 0.0
    alerts: List[dict] = []

    _trend_pick_cycle_time(analyzer, session_start, alerts)
    _trend_arm_motor_temperature(analyzer, session_start, alerts)
    _trend_vehicle_health_score(analyzer, session_start, alerts)
    _trend_detection_latency(analyzer, session_start, alerts)
    _trend_arm_motor_failures(analyzer, session_start, alerts)
    _trend_camera_reconnections(analyzer, session_start, alerts)
    _trend_mqtt_disconnects(analyzer, session_start, alerts)

    summary.trend_alerts = alerts


def _linear_slope(xs: List[float], ys: List[float]) -> float:
    """Return slope of simple linear regression."""
    n = len(xs)
    if n < 2:
        return 0.0
    sx = sum(xs)
    sy = sum(ys)
    sxy = sum(x * y for x, y in zip(xs, ys))
    sxx = sum(x * x for x in xs)
    denom = n * sxx - sx * sx
    if denom == 0:
        return 0.0
    return (n * sxy - sx * sy) / denom


def _per_hour_averages(
    items: List[dict],
    value_key: str,
    ts_key: str,
    session_start: float,
) -> Tuple[List[int], List[float]]:
    """Group items by hour bucket and return (hours, avg_values)."""
    buckets: Dict[int, List[float]] = defaultdict(list)
    for item in items:
        val = item.get(value_key)
        ts = item.get(ts_key)
        if val is not None and ts is not None:
            h = _hour_bucket(ts, session_start)
            buckets[h].append(float(val))
    hours = sorted(buckets)
    avgs = [sum(buckets[h]) / len(buckets[h]) for h in hours]
    return hours, avgs


def _trend_pick_cycle_time(
    analyzer: "ROS2LogAnalyzer",
    session_start: float,
    alerts: list,
) -> None:
    """task 17.2 — Pick cycle time degradation.

    Filters out instant IK rejections (total_ms <= 1) before computing
    the trend.  Without this filter, natural fluctuation in the ratio of
    instant rejections to real picks causes a spurious degradation alert
    (e.g. the 21.8%/hour false alarm in February 2026 field data).
    """
    # Exclude instant IK rejections (0-1ms) and recovery-only rejections
    # that never executed a real motor cycle.
    real_picks = [p for p in analyzer.events.picks if (p.get("total_ms") or 0) > 1]
    hours, avgs = _per_hour_averages(real_picks, "total_ms", "_ts", session_start)
    if len(hours) < 2:
        return
    slope = _linear_slope([float(h) for h in hours], avgs)
    baseline = avgs[0] if avgs[0] != 0 else 1.0
    slope_pct_per_hour = 100.0 * slope / baseline
    if slope_pct_per_hour > 10.0:
        alerts.append(
            {
                "type": "pick_cycle_time_degradation",
                "slope_pct_per_hour": round(slope_pct_per_hour, 1),
                "description": (
                    f"Pick cycle time increasing by"
                    f" {slope_pct_per_hour:.1f}%/hour "
                    f"(from {avgs[0]:.0f}ms to {avgs[-1]:.0f}ms)"
                ),
            }
        )


def _trend_arm_motor_temperature(
    analyzer: "ROS2LogAnalyzer",
    session_start: float,
    alerts: list,
) -> None:
    """task 17.3 — Arm motor temperature rising (arm-side only, uses temp_c).

    task 5.4 — Keys on (arm_id, joint_name) composite to avoid mixing
    temperature readings from arm_1 and arm_2 into spurious trend alerts.
    """
    # Collect per (arm_id, joint) per-hour temperature
    joint_hour_temps: Dict[tuple, Dict[int, List[float]]] = defaultdict(lambda: defaultdict(list))
    for mh in analyzer.events.motor_health_arm:
        ts = mh.get("_ts")
        arm_id = mh.get("arm_id")
        for m in mh.get("motors") or []:
            joint = str(m.get("joint") or m.get("id") or "?")
            temp = m.get("temp_c")
            if temp is not None and ts is not None:
                h = _hour_bucket(ts, session_start)
                composite_key = (arm_id, joint)
                joint_hour_temps[composite_key][h].append(float(temp))

    for (arm_id, joint), hour_data in joint_hour_temps.items():
        hours = sorted(hour_data)
        if len(hours) < 2:
            continue
        avgs = [sum(hour_data[h]) / len(hour_data[h]) for h in hours]
        rise = avgs[-1] - avgs[0]
        if rise > 5.0:
            label = f"Joint {joint}" if arm_id is None else f"Arm {arm_id} Joint {joint}"
            alerts.append(
                {
                    "type": "arm_motor_temperature_rising",
                    "arm_id": arm_id,
                    "joint": joint,
                    "temp_rise_c": round(rise, 1),
                    "description": (
                        f"{label} temperature rose {rise:.1f}\u00b0C "
                        f"(from {avgs[0]:.1f}\u00b0C"
                        f" to {avgs[-1]:.1f}\u00b0C)"
                    ),
                }
            )


def _trend_vehicle_health_score(
    analyzer: "ROS2LogAnalyzer",
    session_start: float,
    alerts: list,
) -> None:
    """task 17.4 — Vehicle health score declining."""
    hours, avgs = _per_hour_averages(
        analyzer.events.motor_health_vehicle,
        "health_score",
        "_ts",
        session_start,
    )
    if not avgs:
        return
    if min(avgs) < 80:
        alerts.append(
            {
                "type": "vehicle_health_score_low",
                "min_score": round(min(avgs), 1),
                "description": (
                    f"Vehicle health score dropped to {min(avgs):.0f} " f"(threshold: 80)"
                ),
            }
        )


def _trend_detection_latency(
    analyzer: "ROS2LogAnalyzer",
    session_start: float,
    alerts: list,
) -> None:
    """task 17.5 — Detection latency increasing."""
    # Use picks as proxy (they have detection_age_ms)
    hours, avgs = _per_hour_averages(
        analyzer.events.picks,
        "detection_age_ms",
        "_ts",
        session_start,
    )
    if len(hours) < 2:
        return
    slope = _linear_slope([float(h) for h in hours], avgs)
    if slope > 50:  # >50ms/hour increase
        alerts.append(
            {
                "type": "detection_latency_increasing",
                "slope_ms_per_hour": round(slope, 1),
                "description": (
                    f"Detection age increasing by {slope:.0f}ms/hour "
                    f"(from {avgs[0]:.0f}ms to {avgs[-1]:.0f}ms)"
                ),
            }
        )


def _trend_arm_motor_failures(
    analyzer: "ROS2LogAnalyzer",
    session_start: float,
    alerts: list,
) -> None:
    """task 24.7 — Arm motor failure rate per hour."""
    buckets: Dict[int, int] = defaultdict(int)
    for f in analyzer.events.motor_failure_details:
        ts = f.get("_ts")
        if ts is not None:
            h = _hour_bucket(ts, session_start)
            buckets[h] += 1

    hours = sorted(buckets)
    if len(hours) < 2:
        return
    counts = [buckets[h] for h in hours]
    # If last hour has 2x or more failures vs first hour
    if counts[0] > 0 and counts[-1] >= counts[0] * 2:
        alerts.append(
            {
                "type": "arm_motor_failure_rate_increasing",
                "first_hour": counts[0],
                "last_hour": counts[-1],
                "description": (
                    f"Arm motor failure rate doubled:"
                    f" {counts[0]} \u2192 {counts[-1]} failures/hour"
                ),
            }
        )


def _trend_camera_reconnections(
    analyzer: "ROS2LogAnalyzer",
    session_start: float,
    alerts: list,
) -> None:
    """task 24.7 — Camera reconnection rate per hour."""
    buckets: Dict[int, int] = defaultdict(int)
    for r in analyzer.events.camera_reconnections:
        ts = r.get("_ts")
        if ts is not None:
            h = _hour_bucket(ts, session_start)
            buckets[h] += 1

    total_reconnects = len(analyzer.events.camera_reconnections)
    if total_reconnects >= 5:
        hours_with_data = len(buckets) or 1
        rate_per_hour = total_reconnects / hours_with_data
        alerts.append(
            {
                "type": "frequent_camera_reconnections",
                "total": total_reconnects,
                "rate_per_hour": round(rate_per_hour, 1),
                "description": (
                    f"Frequent camera reconnections:"
                    f" {total_reconnects} total "
                    f"({rate_per_hour:.1f}/hour)"
                ),
            }
        )


def _trend_mqtt_disconnects(
    analyzer: "ROS2LogAnalyzer",
    session_start: float,
    alerts: list,
) -> None:
    """task 24.7 — MQTT disconnect rate per hour."""
    buckets: Dict[int, int] = defaultdict(int)
    for d in analyzer.mqtt.disconnects:
        ts = d.get("_ts")
        if ts is not None:
            h = _hour_bucket(ts, session_start)
            buckets[h] += 1

    total = sum(buckets.values())
    hours_count = len(buckets) or 1
    rate_per_hour = total / hours_count
    if rate_per_hour > 3:
        alerts.append(
            {
                "type": "frequent_mqtt_disconnects",
                "rate_per_hour": round(rate_per_hour, 1),
                "description": (
                    f"Frequent MQTT disconnects: {total} total "
                    f"({rate_per_hour:.1f}/hour, threshold 3/hour)"
                ),
            }
        )
