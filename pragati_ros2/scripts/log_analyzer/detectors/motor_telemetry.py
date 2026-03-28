"""
Motor telemetry analysis from arm-side motor_health events.

Tasks 9.2-9.8 of log-analyzer-enhancements:
  9.2 — Temperature trend analysis per motor
  9.3 — Battery voltage tracking and discharge rate
  9.4 — Position precision grouped by transmission ratio
  9.5 — Reach time trend analysis and degradation detection
  9.6 — Command supersede rate per motor
  9.7 — CAN bus health (tx_fail and timeout rates)
  9.8 — Unified entry point returning results dict + issues list
"""

from __future__ import annotations

import statistics
from typing import TYPE_CHECKING, Dict, List, Tuple

if TYPE_CHECKING:
    from ..models import EventStore

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# 9.2 Temperature
_TEMP_MEDIUM_C = 55.0
_TEMP_HIGH_C = 65.0
# Number of consecutive samples within ±1°C to count as "stabilised"
_TEMP_STABLE_WINDOW = 5
_TEMP_STABLE_DELTA = 1.0

# 9.3 Voltage
_VOLTAGE_MEDIUM_V = 48.0
_VOLTAGE_HIGH_V = 45.0

# 9.4 Transmission ratio groups
_RATIO_GROUPS: Dict[str, float] = {
    "1:1": 1.0,
    "12.7:1": 12.7,
}
_RATIO_TOLERANCE = 0.5  # ± tolerance for grouping

# 9.5 Reach time
_REACH_DEGRADATION_PCT = 30.0  # last-quarter >30% above first-quarter → Low

# 9.6 Supersede
_SUPERSEDE_RATE_LOW_PCT = 25.0

# 9.7 CAN bus — any non-zero failure is High
# (no numeric threshold; presence triggers)

# Minimum samples for meaningful analysis
_MIN_SAMPLES = 3


# ---------------------------------------------------------------------------
# 9.2 — Temperature trend analysis
# ---------------------------------------------------------------------------


def _analyze_temperature(
    events: "EventStore",
) -> Tuple[Dict[str, dict], List[dict]]:
    """Per-motor temperature trend: start, peak, end, stabilisation, direction.

    Returns (motor_temps dict, issues list).
    """
    by_motor: Dict[str, List[float]] = {}
    for ev in events.motor_health_arm:
        motors = ev.get("motors", [])
        if not isinstance(motors, list):
            continue
        for motor in motors:
            if not isinstance(motor, dict):
                continue
            mid = motor.get("joint") or motor.get("id", "unknown")
            temp = motor.get("temp_c")
            if temp is not None:
                by_motor.setdefault(mid, []).append(float(temp))

    results: Dict[str, dict] = {}
    issues: List[dict] = []

    for mid, temps in sorted(by_motor.items()):
        if len(temps) < _MIN_SAMPLES:
            continue

        start_temp = temps[0]
        peak_temp = max(temps)
        end_temp = temps[-1]

        # Stabilisation time: index of first window where all values within ±1°C
        stabilisation_idx = None
        for i in range(len(temps) - _TEMP_STABLE_WINDOW + 1):
            window = temps[i : i + _TEMP_STABLE_WINDOW]
            if max(window) - min(window) <= _TEMP_STABLE_DELTA:
                stabilisation_idx = i
                break

        # Trend direction: compare first-quarter mean vs last-quarter mean
        q = max(1, len(temps) // 4)
        early_mean = statistics.mean(temps[:q])
        late_mean = statistics.mean(temps[-q:])
        if late_mean > early_mean + _TEMP_STABLE_DELTA:
            direction = "rising"
        elif late_mean < early_mean - _TEMP_STABLE_DELTA:
            direction = "falling"
        else:
            direction = "stable"

        results[mid] = {
            "motor_id": mid,
            "sample_count": len(temps),
            "start_temp_c": round(start_temp, 1),
            "peak_temp_c": round(peak_temp, 1),
            "end_temp_c": round(end_temp, 1),
            "stabilisation_sample": stabilisation_idx,
            "trend_direction": direction,
        }

        # Severity thresholds
        if peak_temp >= _TEMP_HIGH_C:
            issues.append({
                "severity": "high",
                "category": "motor",
                "title": f"Motor temperature critical: {mid}",
                "description": (
                    f"Motor '{mid}' peak temperature {peak_temp:.1f}°C"
                    f" exceeds {_TEMP_HIGH_C}°C threshold."
                    f" Start={start_temp:.1f}°C, End={end_temp:.1f}°C."
                ),
                "node": "arm",
                "timestamp": 0,
                "message": (
                    f"Motor temp critical: {mid}"
                    f" peak={peak_temp:.1f}°C"
                ),
                "recommendation": (
                    "Reduce duty cycle or improve motor cooling."
                    " Check for mechanical binding increasing load."
                ),
            })
        elif peak_temp >= _TEMP_MEDIUM_C:
            issues.append({
                "severity": "medium",
                "category": "motor",
                "title": f"Motor temperature elevated: {mid}",
                "description": (
                    f"Motor '{mid}' peak temperature {peak_temp:.1f}°C"
                    f" exceeds {_TEMP_MEDIUM_C}°C threshold."
                    f" Start={start_temp:.1f}°C, End={end_temp:.1f}°C."
                ),
                "node": "arm",
                "timestamp": 0,
                "message": (
                    f"Motor temp elevated: {mid}"
                    f" peak={peak_temp:.1f}°C"
                ),
                "recommendation": (
                    "Monitor temperature trend. Consider reducing"
                    " continuous operation time."
                ),
            })

    return results, issues


# ---------------------------------------------------------------------------
# 9.3 — Battery voltage tracking
# ---------------------------------------------------------------------------


def _analyze_voltage(
    events: "EventStore",
) -> Tuple[dict, List[dict]]:
    """Session voltage tracking: start, end, min, discharge rate.

    Returns (voltage_stats dict, issues list).
    """
    voltages: List[float] = []
    timestamps: List[float] = []

    for ev in events.motor_health_arm:
        vbus = ev.get("vbus_v")
        if vbus is not None:
            voltages.append(float(vbus))
            ts = ev.get("_ts")
            timestamps.append(float(ts) if ts is not None else 0.0)

    if len(voltages) < _MIN_SAMPLES:
        return {}, []

    start_v = voltages[0]
    end_v = voltages[-1]
    min_v = min(voltages)

    # Discharge rate (V/hour) — only if we have valid timestamps
    discharge_rate_v_per_hour = None
    valid_ts = [t for t in timestamps if t > 0]
    if len(valid_ts) >= 2:
        duration_s = valid_ts[-1] - valid_ts[0]
        if duration_s > 0:
            discharge_rate_v_per_hour = round(
                (start_v - end_v) / (duration_s / 3600.0), 3
            )

    result = {
        "sample_count": len(voltages),
        "start_v": round(start_v, 2),
        "end_v": round(end_v, 2),
        "min_v": round(min_v, 2),
        "mean_v": round(statistics.mean(voltages), 2),
        "discharge_rate_v_per_hour": discharge_rate_v_per_hour,
    }

    issues: List[dict] = []
    if min_v < _VOLTAGE_HIGH_V:
        issues.append({
            "severity": "high",
            "category": "power",
            "title": "Battery voltage critically low",
            "description": (
                f"Minimum bus voltage {min_v:.2f}V dropped below"
                f" {_VOLTAGE_HIGH_V}V threshold."
                f" Start={start_v:.2f}V, End={end_v:.2f}V."
            ),
            "node": "arm",
            "timestamp": 0,
            "message": f"Vbus critically low: min={min_v:.2f}V",
            "recommendation": (
                "Charge or replace battery immediately."
                " Low voltage causes motor control instability."
            ),
        })
    elif min_v < _VOLTAGE_MEDIUM_V:
        issues.append({
            "severity": "medium",
            "category": "power",
            "title": "Battery voltage low",
            "description": (
                f"Minimum bus voltage {min_v:.2f}V dropped below"
                f" {_VOLTAGE_MEDIUM_V}V threshold."
                f" Start={start_v:.2f}V, End={end_v:.2f}V."
            ),
            "node": "arm",
            "timestamp": 0,
            "message": f"Vbus low: min={min_v:.2f}V",
            "recommendation": (
                "Plan battery swap soon. Monitor for further drop."
            ),
        })

    return result, issues


# ---------------------------------------------------------------------------
# 9.4 — Position precision by transmission ratio
# ---------------------------------------------------------------------------


def _classify_ratio_group(ratio: float) -> str:
    """Map a transmission_ratio value to a named group."""
    for name, ref in _RATIO_GROUPS.items():
        if abs(ratio - ref) <= _RATIO_TOLERANCE:
            return name
    return f"{ratio:.1f}:1"


def _analyze_position_precision(
    events: "EventStore",
) -> Tuple[Dict[str, dict], List[dict]]:
    """Group motors by transmission ratio, compute position error stats.

    Returns (ratio_groups dict, issues list).
    """
    # Collect (ratio_group, pos_error) pairs
    by_group: Dict[str, List[float]] = {}
    motor_ratios: Dict[str, float] = {}

    for ev in events.motor_health_arm:
        motors = ev.get("motors", [])
        if not isinstance(motors, list):
            continue
        for motor in motors:
            if not isinstance(motor, dict):
                continue
            mid = motor.get("joint") or motor.get("id", "unknown")
            pos_error = motor.get("pos_error")
            ratio = motor.get("transmission_ratio")
            if pos_error is not None:
                if ratio is not None:
                    motor_ratios[mid] = float(ratio)
                group = _classify_ratio_group(
                    motor_ratios.get(mid, 1.0)
                )
                by_group.setdefault(group, []).append(float(pos_error))

    results: Dict[str, dict] = {}
    issues: List[dict] = []

    for group, errors in sorted(by_group.items()):
        if len(errors) < _MIN_SAMPLES:
            continue
        abs_errors = [abs(e) for e in errors]
        results[group] = {
            "ratio_group": group,
            "sample_count": len(errors),
            "mean_error": round(statistics.mean(abs_errors), 4),
            "median_error": round(statistics.median(abs_errors), 4),
            "max_error": round(max(abs_errors), 4),
            "stddev_error": round(
                statistics.stdev(abs_errors) if len(abs_errors) >= 2 else 0.0,
                4,
            ),
        }

    return results, issues


# ---------------------------------------------------------------------------
# 9.5 — Reach time trend analysis
# ---------------------------------------------------------------------------


def _analyze_reach_time(
    events: "EventStore",
) -> Tuple[Dict[str, dict], List[dict]]:
    """Per-motor reach time stats and degradation detection.

    Returns (motor_reach dict, issues list).
    """
    by_motor: Dict[str, List[float]] = {}

    for ev in events.motor_health_arm:
        motors = ev.get("motors", [])
        if not isinstance(motors, list):
            continue
        for motor in motors:
            if not isinstance(motor, dict):
                continue
            mid = motor.get("joint") or motor.get("id", "unknown")
            rt = motor.get("reach_time_ms")
            if rt is not None:
                by_motor.setdefault(mid, []).append(float(rt))

    results: Dict[str, dict] = {}
    issues: List[dict] = []

    for mid, times in sorted(by_motor.items()):
        if len(times) < _MIN_SAMPLES:
            continue

        mean_rt = statistics.mean(times)
        sorted_times = sorted(times)
        p50 = statistics.median(sorted_times)
        # p95 via nearest-rank
        p95_idx = max(0, int(len(sorted_times) * 0.95) - 1)
        p95 = sorted_times[p95_idx]
        max_rt = max(times)

        # Degradation: last-quarter mean vs first-quarter mean
        q = max(1, len(times) // 4)
        first_q_mean = statistics.mean(times[:q])
        last_q_mean = statistics.mean(times[-q:])
        degraded = False
        if first_q_mean > 0:
            pct_increase = (
                (last_q_mean - first_q_mean) / first_q_mean * 100.0
            )
            if pct_increase > _REACH_DEGRADATION_PCT:
                degraded = True

        results[mid] = {
            "motor_id": mid,
            "sample_count": len(times),
            "mean_ms": round(mean_rt, 1),
            "p50_ms": round(p50, 1),
            "p95_ms": round(p95, 1),
            "max_ms": round(max_rt, 1),
            "first_quarter_mean_ms": round(first_q_mean, 1),
            "last_quarter_mean_ms": round(last_q_mean, 1),
            "degraded": degraded,
        }

        if degraded and first_q_mean > 0:
            pct = (last_q_mean - first_q_mean) / first_q_mean * 100.0
            issues.append({
                "severity": "low",
                "category": "motor",
                "title": f"Reach time degradation: {mid}",
                "description": (
                    f"Motor '{mid}' reach time increased {pct:.1f}%"
                    f" from first quarter ({first_q_mean:.1f}ms)"
                    f" to last quarter ({last_q_mean:.1f}ms)."
                    f" Threshold: {_REACH_DEGRADATION_PCT}%."
                ),
                "node": "arm",
                "timestamp": 0,
                "message": (
                    f"Reach time degradation: {mid}"
                    f" +{pct:.1f}% over session"
                ),
                "recommendation": (
                    "Check for increasing mechanical friction or"
                    " thermal effects on motor performance."
                ),
            })

    return results, issues


# ---------------------------------------------------------------------------
# 9.6 — Supersede rate
# ---------------------------------------------------------------------------


def _analyze_supersede_rate(
    events: "EventStore",
) -> Tuple[Dict[str, dict], List[dict]]:
    """Per-motor command supersede percentage.

    Returns (motor_supersede dict, issues list).
    """
    total_by_motor: Dict[str, int] = {}
    superseded_by_motor: Dict[str, int] = {}

    for ev in events.motor_health_arm:
        motors = ev.get("motors", [])
        if not isinstance(motors, list):
            continue
        for motor in motors:
            if not isinstance(motor, dict):
                continue
            mid = motor.get("joint") or motor.get("id", "unknown")
            superseded = motor.get("superseded")
            if superseded is not None:
                total_by_motor[mid] = total_by_motor.get(mid, 0) + 1
                if superseded:
                    superseded_by_motor[mid] = (
                        superseded_by_motor.get(mid, 0) + 1
                    )

    results: Dict[str, dict] = {}
    issues: List[dict] = []

    for mid in sorted(total_by_motor.keys()):
        total = total_by_motor[mid]
        if total < _MIN_SAMPLES:
            continue
        superseded = superseded_by_motor.get(mid, 0)
        rate = (superseded / total) * 100.0 if total > 0 else 0.0

        results[mid] = {
            "motor_id": mid,
            "total_commands": total,
            "superseded_commands": superseded,
            "supersede_rate_pct": round(rate, 1),
        }

        if rate > _SUPERSEDE_RATE_LOW_PCT:
            issues.append({
                "severity": "low",
                "category": "motor",
                "title": f"High command supersede rate: {mid}",
                "description": (
                    f"Motor '{mid}' has {rate:.1f}% command supersede"
                    f" rate ({superseded}/{total} commands)."
                    f" Threshold: {_SUPERSEDE_RATE_LOW_PCT}%."
                ),
                "node": "arm",
                "timestamp": 0,
                "message": (
                    f"Supersede rate: {mid}"
                    f" {rate:.1f}% ({superseded}/{total})"
                ),
                "recommendation": (
                    "Review motion planning to reduce rapid"
                    " command changes. High supersede rates"
                    " indicate target oscillation."
                ),
            })

    return results, issues


# ---------------------------------------------------------------------------
# 9.7 — CAN bus health
# ---------------------------------------------------------------------------


def _analyze_can_health(
    events: "EventStore",
) -> Tuple[Dict[str, dict], List[dict]]:
    """Per-motor CAN tx_fail and timeout rates.

    Returns (motor_can dict, issues list).
    """
    by_motor: Dict[str, Dict[str, int]] = {}

    for ev in events.motor_health_arm:
        motors = ev.get("motors", [])
        if not isinstance(motors, list):
            continue
        for motor in motors:
            if not isinstance(motor, dict):
                continue
            mid = motor.get("joint") or motor.get("id", "unknown")
            stats = by_motor.setdefault(
                mid, {"samples": 0, "tx_fail": 0, "timeout": 0}
            )
            stats["samples"] += 1
            tx_fail = motor.get("can_tx_fail")
            if tx_fail is not None:
                stats["tx_fail"] += int(tx_fail)
            can_timeout = motor.get("can_timeout")
            if can_timeout is not None:
                stats["timeout"] += int(can_timeout)

    results: Dict[str, dict] = {}
    issues: List[dict] = []

    for mid in sorted(by_motor.keys()):
        stats = by_motor[mid]
        samples = stats["samples"]
        if samples < _MIN_SAMPLES:
            continue
        tx_fail = stats["tx_fail"]
        timeout = stats["timeout"]
        tx_fail_rate = (tx_fail / samples) * 100.0 if samples > 0 else 0.0
        timeout_rate = (timeout / samples) * 100.0 if samples > 0 else 0.0

        results[mid] = {
            "motor_id": mid,
            "sample_count": samples,
            "tx_fail_count": tx_fail,
            "timeout_count": timeout,
            "tx_fail_rate_pct": round(tx_fail_rate, 2),
            "timeout_rate_pct": round(timeout_rate, 2),
        }

        if tx_fail > 0 or timeout > 0:
            failures = []
            if tx_fail > 0:
                failures.append(f"tx_fail={tx_fail}")
            if timeout > 0:
                failures.append(f"timeout={timeout}")
            fail_desc = ", ".join(failures)
            issues.append({
                "severity": "high",
                "category": "can_bus",
                "title": f"CAN bus failures: {mid}",
                "description": (
                    f"Motor '{mid}' has CAN bus failures:"
                    f" {fail_desc} over {samples} samples."
                ),
                "node": "arm",
                "timestamp": 0,
                "message": (
                    f"CAN failures: {mid} {fail_desc}"
                ),
                "recommendation": (
                    "Check CAN bus wiring, termination resistors,"
                    " and bus load. CAN failures cause motor"
                    " control loss."
                ),
            })

    return results, issues


# ---------------------------------------------------------------------------
# 9.8 — Unified entry point
# ---------------------------------------------------------------------------


def analyze_motor_telemetry(
    events: "EventStore",
) -> dict:
    """Analyse motor telemetry from motor_health_arm events.

    Combines temperature, voltage, position precision, reach time,
    supersede rate, and CAN bus health analyses.

    Args:
        events: EventStore containing motor_health_arm events.

    Returns:
        Dict with keys:
          - "temperature": per-motor temp trends
          - "voltage": session voltage stats
          - "position_precision": per-ratio-group error stats
          - "reach_time": per-motor reach time stats
          - "supersede_rate": per-motor supersede rates
          - "can_health": per-motor CAN bus stats
          - "issues": combined list of all issues
    """
    if not events.motor_health_arm:
        return {
            "temperature": {},
            "voltage": {},
            "position_precision": {},
            "reach_time": {},
            "supersede_rate": {},
            "can_health": {},
            "issues": [],
        }

    temp_results, temp_issues = _analyze_temperature(events)
    voltage_results, voltage_issues = _analyze_voltage(events)
    precision_results, precision_issues = _analyze_position_precision(events)
    reach_results, reach_issues = _analyze_reach_time(events)
    supersede_results, supersede_issues = _analyze_supersede_rate(events)
    can_results, can_issues = _analyze_can_health(events)

    all_issues = (
        temp_issues
        + voltage_issues
        + precision_issues
        + reach_issues
        + supersede_issues
        + can_issues
    )

    return {
        "temperature": temp_results,
        "voltage": voltage_results,
        "position_precision": precision_results,
        "reach_time": reach_results,
        "supersede_rate": supersede_results,
        "can_health": can_results,
        "issues": all_issues,
    }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
from .registry import register as _register

_register(
    "analyze_motor_telemetry", analyze_motor_telemetry,
    category="motor",
    description="Analyze motor telemetry (temperature, voltage, precision, CAN health).",
)
