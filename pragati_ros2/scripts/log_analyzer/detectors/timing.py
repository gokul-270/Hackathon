"""
Pick cycle timing analysis and bottleneck detection.

Tasks 5.1-5.6 of timing/bottleneck detector:
  5.1 — Pick phase timing analysis (per-phase stats)
  5.2 — Bottleneck identification (>40% of cycle time)
  5.3 — Cycle time outlier detection (>2x session median)
  5.4 — TF lookup latency detection (p95 >50ms)
  5.5 — Retrigger delay detection (mean >3s after failure)
  5.6 — slowMotorsAvailable warning detection (>5 occurrences)
"""

from __future__ import annotations

import statistics
from typing import TYPE_CHECKING, Callable, Dict, List, Optional

if TYPE_CHECKING:
    from ..models import EventStore

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# Task 5.2: phase is a bottleneck if it accounts for >40% of total cycle time
_BOTTLENECK_PCT_THRESHOLD = 40.0

# Task 5.3: a pick is an outlier if total_ms > 2x session median
_OUTLIER_MULTIPLIER = 2.0

# Task 5.4: TF lookup p95 latency threshold in milliseconds
_TF_LATENCY_P95_THRESHOLD_MS = 50.0

# Task 5.5: mean retrigger delay threshold in seconds
_RETRIGGER_DELAY_THRESHOLD_S = 3.0

# Task 5.6: slow motors warning count threshold
_SLOW_MOTORS_THRESHOLD = 5

# Minimum picks required for meaningful statistics
_MIN_PICKS_FOR_STATS = 3


def _safe_median(values: List[float]) -> float:
    """Compute median, returning 0.0 for empty lists."""
    return statistics.median(values) if values else 0.0


def _safe_mean(values: List[float]) -> float:
    """Compute mean, returning 0.0 for empty lists."""
    return statistics.mean(values) if values else 0.0


def _percentile(values: List[float], pct: float) -> float:
    """Compute a percentile from a sorted list of values.

    Uses nearest-rank method.  Returns 0.0 for empty lists.
    """
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = int(len(sorted_vals) * pct / 100.0)
    k = min(k, len(sorted_vals) - 1)
    return sorted_vals[k]


def _phase_stats(values: List[float]) -> dict:
    """Compute mean, p50 (median), p95, and max for a list of durations."""
    if not values:
        return {
            "mean": 0.0,
            "p50": 0.0,
            "p95": 0.0,
            "max": 0.0,
            "count": 0,
        }
    return {
        "mean": round(_safe_mean(values), 1),
        "p50": round(_safe_median(values), 1),
        "p95": round(_percentile(values, 95), 1),
        "max": round(max(values), 1),
        "count": len(values),
    }


# ---------------------------------------------------------------------------
# Phase name mapping: pick_complete event fields → phase names
# ---------------------------------------------------------------------------

# Each pick_complete record has timing fields for these phases.
# "detection" is approximated by detection_age_ms (time from detection to
# pick start).  The phases map to the cotton-picking arm cycle:
#   detection → detection_age_ms
#   approach  → approach_ms
#   grasp     → capture_ms (EE capture / grasp phase)
#   retract   → retreat_ms
#   deposit   → delay_ms  (inter-pick delay, includes deposit)

_PHASE_FIELDS = {
    "detection": "detection_age_ms",
    "approach": "approach_ms",
    "grasp": "capture_ms",
    "retract": "retreat_ms",
    "deposit": "delay_ms",
}


def analyze_timing(
    report: dict,
    issues_callback: Optional[Callable[[dict], None]] = None,
) -> dict:
    """Analyze pick cycle timing and detect bottlenecks.

    Args:
        report: Dict-like object that must contain an ``events`` attribute
            (an EventStore instance) with ``picks``, ``pick_failures``,
            ``detection_quality_events``, and ``entries`` data.
            Alternatively, a plain dict with those keys works too.
        issues_callback: Optional callable invoked with each issue dict.
            If None, issues are collected internally and returned.

    Returns:
        Dict with keys:
          - ``phase_stats``: per-phase statistics (mean, p50, p95, max)
          - ``bottlenecks``: list of phase names flagged as bottlenecks
          - ``outliers``: list of outlier pick dicts
          - ``tf_lookup``: TF lookup latency stats (or empty dict)
          - ``retrigger``: retrigger delay stats (or empty dict)
          - ``slow_motors``: slow motor warning stats (or empty dict)
          - ``issues``: list of all generated issue dicts
    """
    issues: List[dict] = []

    def _emit(issue: dict) -> None:
        issues.append(issue)
        if issues_callback is not None:
            issues_callback(issue)

    # -----------------------------------------------------------------------
    # Extract event data — support both EventStore attribute and plain dict
    # -----------------------------------------------------------------------
    if hasattr(report, "events"):
        events = report.events
        picks = list(events.picks)
        pick_failures = list(events.pick_failures)
        entries = getattr(report, "entries", [])
        detection_summaries = list(events.detection_summaries)
    else:
        events = report
        picks = list(report.get("picks", []))
        pick_failures = list(report.get("pick_failures", []))
        entries = list(report.get("entries", []))
        detection_summaries = list(report.get("detection_summaries", []))

    result: dict = {
        "phase_stats": {},
        "bottlenecks": [],
        "outliers": [],
        "tf_lookup": {},
        "retrigger": {},
        "slow_motors": {},
        "issues": issues,
    }

    # ===================================================================
    # Task 5.1: Pick phase timing analysis
    # ===================================================================

    # Collect per-phase durations from pick_complete events
    phase_durations: Dict[str, List[float]] = {
        phase: [] for phase in _PHASE_FIELDS
    }
    total_durations: List[float] = []
    # Keep per-pick phase values for outlier analysis (task 5.3)
    per_pick_phases: List[dict] = []

    for pick in picks:
        total_ms = pick.get("total_ms")
        if total_ms is None:
            continue
        total_ms = float(total_ms)
        if total_ms <= 0:
            continue

        total_durations.append(total_ms)
        pick_phases: dict = {"_ts": pick.get("_ts"), "total_ms": total_ms}

        for phase_name, field_name in _PHASE_FIELDS.items():
            val = pick.get(field_name)
            if val is not None:
                val = float(val)
                phase_durations[phase_name].append(val)
                pick_phases[phase_name] = val

        per_pick_phases.append(pick_phases)

    # Compute per-phase statistics
    phase_stats: Dict[str, dict] = {}
    for phase_name, durations in phase_durations.items():
        phase_stats[phase_name] = _phase_stats(durations)

    result["phase_stats"] = phase_stats

    # ===================================================================
    # Task 5.2: Bottleneck identification
    # ===================================================================

    if len(total_durations) >= _MIN_PICKS_FOR_STATS:
        mean_total = _safe_mean(total_durations)

        if mean_total > 0:
            for phase_name, durations in phase_durations.items():
                if not durations:
                    continue
                mean_phase = _safe_mean(durations)
                pct = (mean_phase / mean_total) * 100.0

                if pct > _BOTTLENECK_PCT_THRESHOLD:
                    result["bottlenecks"].append(phase_name)
                    stats = phase_stats[phase_name]
                    _emit({
                        "severity": "medium",
                        "category": "timing",
                        "title": f"Bottleneck: {phase_name} phase",
                        "description": (
                            f"The '{phase_name}' phase accounts for"
                            f" {pct:.1f}% of total cycle time"
                            f" (mean: {mean_phase:.0f}ms,"
                            f" p95: {stats['p95']:.0f}ms)."
                            f" Threshold: {_BOTTLENECK_PCT_THRESHOLD}%."
                        ),
                        "node": "arm",
                        "timestamp": 0,
                        "message": (
                            f"Bottleneck: {phase_name}"
                            f" {pct:.1f}% of cycle"
                            f" (mean={mean_phase:.0f}ms,"
                            f" p95={stats['p95']:.0f}ms)"
                        ),
                        "recommendation": (
                            f"Investigate {phase_name} phase for"
                            f" optimization opportunities. Profile"
                            f" motion planning and motor response"
                            f" during this phase."
                        ),
                    })

    # ===================================================================
    # Task 5.3: Cycle time outlier detection
    # ===================================================================

    if len(total_durations) >= _MIN_PICKS_FOR_STATS:
        session_median = _safe_median(total_durations)
        outlier_threshold = session_median * _OUTLIER_MULTIPLIER

        # Compute per-phase medians for deviation analysis
        phase_medians: Dict[str, float] = {}
        for phase_name, durations in phase_durations.items():
            phase_medians[phase_name] = _safe_median(durations)

        for pick_data in per_pick_phases:
            pick_total = pick_data["total_ms"]
            if pick_total <= outlier_threshold:
                continue

            # Find which phase caused the largest deviation
            max_deviation = 0.0
            worst_phase = "unknown"
            for phase_name in _PHASE_FIELDS:
                val = pick_data.get(phase_name)
                if val is None:
                    continue
                median = phase_medians.get(phase_name, 0.0)
                if median > 0:
                    deviation = val - median
                else:
                    deviation = val
                if deviation > max_deviation:
                    max_deviation = deviation
                    worst_phase = phase_name

            outlier_info = {
                "total_ms": pick_total,
                "session_median_ms": round(session_median, 1),
                "worst_phase": worst_phase,
                "worst_phase_deviation_ms": round(max_deviation, 1),
                "_ts": pick_data.get("_ts"),
            }
            result["outliers"].append(outlier_info)

        if result["outliers"]:
            count = len(result["outliers"])
            _emit({
                "severity": "low",
                "category": "timing",
                "title": "Cycle time outliers detected",
                "description": (
                    f"{count} pick(s) exceeded 2x session median"
                    f" ({session_median:.0f}ms)."
                    f" Most common worst phase:"
                    f" {_most_common_phase(result['outliers'])}."
                ),
                "node": "arm",
                "timestamp": 0,
                "message": (
                    f"Cycle outliers: {count} picks"
                    f" >2x median ({session_median:.0f}ms)"
                ),
                "recommendation": (
                    "Review outlier picks for mechanical issues,"
                    " detection delays, or environmental factors."
                ),
            })

    # ===================================================================
    # Task 5.4: TF lookup latency detection
    # ===================================================================

    tf_durations: List[float] = []
    for entry in entries:
        msg = getattr(entry, "message", "") if hasattr(entry, "message") else str(entry)
        tf_val = _extract_tf_lookup_ms(msg)
        if tf_val is not None:
            tf_durations.append(tf_val)

    if tf_durations:
        tf_stats = _phase_stats(tf_durations)
        result["tf_lookup"] = tf_stats

        if tf_stats["p95"] > _TF_LATENCY_P95_THRESHOLD_MS:
            _emit({
                "severity": "medium",
                "category": "timing",
                "title": "High TF lookup latency",
                "description": (
                    f"TF lookup p95 latency is {tf_stats['p95']:.1f}ms"
                    f" (threshold: {_TF_LATENCY_P95_THRESHOLD_MS}ms)."
                    f" Mean: {tf_stats['mean']:.1f}ms,"
                    f" Max: {tf_stats['max']:.1f}ms"
                    f" across {tf_stats['count']} lookups."
                ),
                "node": "arm",
                "timestamp": 0,
                "message": (
                    f"TF lookup p95={tf_stats['p95']:.1f}ms"
                    f" >{_TF_LATENCY_P95_THRESHOLD_MS}ms"
                ),
                "recommendation": (
                    "Check TF publisher rates, clock synchronization,"
                    " and TF buffer size. Consider increasing TF"
                    " cache duration or publishing frequency."
                ),
            })

    # ===================================================================
    # Task 5.5: Retrigger delay detection
    # ===================================================================

    retrigger_delays: List[float] = _compute_retrigger_delays(
        pick_failures, picks,
    )

    if retrigger_delays:
        mean_delay_s = _safe_mean(retrigger_delays)
        retrigger_stats = {
            "mean_s": round(mean_delay_s, 2),
            "p50_s": round(_safe_median(retrigger_delays), 2),
            "p95_s": round(_percentile(retrigger_delays, 95), 2),
            "max_s": round(max(retrigger_delays), 2),
            "count": len(retrigger_delays),
        }
        result["retrigger"] = retrigger_stats

        if mean_delay_s > _RETRIGGER_DELAY_THRESHOLD_S:
            _emit({
                "severity": "low",
                "category": "timing",
                "title": "Slow retrigger after pick failure",
                "description": (
                    f"Mean delay between failed pick and next"
                    f" detection cycle is {mean_delay_s:.1f}s"
                    f" (threshold: {_RETRIGGER_DELAY_THRESHOLD_S}s)."
                    f" p95: {retrigger_stats['p95_s']:.1f}s,"
                    f" max: {retrigger_stats['max_s']:.1f}s."
                ),
                "node": "arm",
                "timestamp": 0,
                "message": (
                    f"Retrigger delay mean={mean_delay_s:.1f}s"
                    f" >{_RETRIGGER_DELAY_THRESHOLD_S}s"
                ),
                "recommendation": (
                    "Review failure recovery logic and detection"
                    " restart timing. Consider reducing cooldown"
                    " period after pick failures."
                ),
            })

    # ===================================================================
    # Task 5.6: slowMotorsAvailable warning detection
    # ===================================================================

    slow_motor_events = _find_slow_motor_warnings(entries)

    if slow_motor_events:
        count = len(slow_motor_events)
        first_ts = slow_motor_events[0]
        last_ts = slow_motor_events[-1]
        result["slow_motors"] = {
            "count": count,
            "first_ts": first_ts,
            "last_ts": last_ts,
        }

        if count > _SLOW_MOTORS_THRESHOLD:
            _emit({
                "severity": "medium",
                "category": "timing",
                "title": "Frequent slowMotorsAvailable warnings",
                "description": (
                    f"{count} slowMotorsAvailable warnings detected"
                    f" (threshold: {_SLOW_MOTORS_THRESHOLD})."
                    f" First: {_format_ts(first_ts)},"
                    f" Last: {_format_ts(last_ts)}."
                ),
                "node": "arm",
                "timestamp": first_ts if isinstance(first_ts, (int, float)) else 0,
                "message": (
                    f"slowMotorsAvailable: {count} warnings"
                    f" >{_SLOW_MOTORS_THRESHOLD}"
                ),
                "recommendation": (
                    "Motors are reporting slow response. Check"
                    " CAN bus load, motor driver health, and"
                    " power supply stability."
                ),
            })

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _most_common_phase(outliers: List[dict]) -> str:
    """Return the most frequently occurring worst_phase among outliers."""
    counts: Dict[str, int] = {}
    for o in outliers:
        phase = o.get("worst_phase", "unknown")
        counts[phase] = counts.get(phase, 0) + 1
    if not counts:
        return "unknown"
    return max(counts, key=lambda k: counts[k])


def _extract_tf_lookup_ms(message: str) -> Optional[float]:
    """Extract TF lookup duration in ms from a log message.

    Looks for patterns like:
      - "TF lookup: 12.3ms"
      - "tf_lookup_duration=15ms"
      - "lookupTransform took 8.5 ms"
      - "TF lookup duration: 20ms"
    """
    import re
    patterns = [
        re.compile(r"(?:TF|tf)\s*lookup(?:\s*duration)?[:\s=]*(\d+\.?\d*)\s*ms", re.IGNORECASE),
        re.compile(r"lookupTransform\s+took\s+(\d+\.?\d*)\s*ms", re.IGNORECASE),
        re.compile(r"tf_lookup_duration\s*=\s*(\d+\.?\d*)", re.IGNORECASE),
    ]
    for pat in patterns:
        m = pat.search(message)
        if m:
            return float(m.group(1))
    return None


def _compute_retrigger_delays(
    pick_failures: List[dict],
    picks: List[dict],
) -> List[float]:
    """Compute delay (in seconds) between a failed pick and the next pick start.

    Uses timestamps from pick_failures and subsequent pick_complete events
    to measure how long the system takes to begin a new detection/pick cycle
    after a failure.
    """
    if not pick_failures or not picks:
        return []

    # Build sorted list of pick start timestamps (from pick_complete events)
    pick_timestamps = sorted(
        float(p["_ts"])
        for p in picks
        if p.get("_ts") is not None
    )

    if not pick_timestamps:
        return []

    delays: List[float] = []
    for failure in pick_failures:
        fail_ts = failure.get("_ts")
        if fail_ts is None:
            continue
        fail_ts = float(fail_ts)

        # Find next pick after this failure (binary search)
        next_pick_ts = _find_next_after(pick_timestamps, fail_ts)
        if next_pick_ts is not None:
            delay_s = next_pick_ts - fail_ts
            # Only count reasonable delays (0-60s; ignore cross-session gaps)
            if 0 < delay_s <= 60.0:
                delays.append(delay_s)

    return delays


def _find_next_after(sorted_timestamps: List[float], target: float) -> Optional[float]:
    """Binary search for the first timestamp strictly after target."""
    import bisect
    idx = bisect.bisect_right(sorted_timestamps, target)
    if idx < len(sorted_timestamps):
        return sorted_timestamps[idx]
    return None


def _find_slow_motor_warnings(entries) -> List[float]:
    """Find all slowMotorsAvailable warnings and return their timestamps."""
    timestamps: List[float] = []
    for entry in entries:
        msg = getattr(entry, "message", "") if hasattr(entry, "message") else str(entry)
        if "slowMotorsAvailable" in msg:
            ts = getattr(entry, "timestamp", None) if hasattr(entry, "timestamp") else 0
            timestamps.append(ts if ts is not None else 0)
    return timestamps


def _format_ts(ts) -> str:
    """Format a timestamp for display in issue descriptions."""
    if ts is None or ts == 0:
        return "N/A"
    try:
        from datetime import datetime
        dt = datetime.fromtimestamp(float(ts))
        epoch_frac = float(ts) % 1
        return dt.strftime("%H:%M:%S") + f".{int(epoch_frac * 1000):03d}"
    except (ValueError, OSError, OverflowError, TypeError):
        return str(ts)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
from .registry import register as _register

_register(
    "analyze_timing", analyze_timing,
    category="analysis",
    description="Analyze pick cycle timing phases and detect bottlenecks.",
)
