"""
Camera thermal trending and confidence threshold discrepancy detection.

Phase 4 of log-analyzer-enhancements:
  4.12 — OAK-D camera thermal trending from detection_summary events
  4.14 — Confidence threshold discrepancy detection
"""

from __future__ import annotations

import re
import statistics
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from ..analyzer import ROS2LogAnalyzer
    from ..models import EventStore

# Temperature thresholds for the trending detector
_WARN_TEMP_C = 70.0
_CRITICAL_TEMP_C = 85.0

# Regex patterns for confidence threshold extraction
_RE_CONFIDENCE_THRESHOLD = re.compile(
    r"confidence_threshold:\s*([\d.]+)"
)
_RE_NN_CONFIDENCE = re.compile(
    r"nn_confidence:\s*([\d.]+)"
)


def analyze_camera_thermal(
    events: "EventStore",
) -> dict:
    """Analyze OAK-D camera temperature from detection_summary events.

    Extracts camera_temp_c from detection summaries, computes
    min/max/mean over session, rate of rise (deg C/min), and flags
    thermal warnings/critical issues.

    Args:
        events: EventStore containing detection_summaries.

    Returns:
        Dict with keys:
          - "thermal": dict of temperature stats (or empty if no data)
          - "issues": list of issue dicts for temperature exceedances
    """
    summaries = events.detection_summaries
    if not summaries:
        return {"thermal": {}, "issues": []}

    # Extract temperature readings with timestamps
    temps: List[float] = []
    temp_ts: List[float] = []
    for ev in summaries:
        temp = ev.get("camera_temp_c")
        if temp is not None:
            temps.append(float(temp))
            ts = ev.get("_ts", 0.0)
            temp_ts.append(float(ts))

    if not temps:
        return {"thermal": {}, "issues": []}

    start_temp = temps[0]
    end_temp = temps[-1]
    max_temp = max(temps)
    min_temp = min(temps)
    mean_temp = round(statistics.mean(temps), 1)

    # Compute rate of rise (deg C / min)
    rate_of_rise = 0.0
    if len(temp_ts) >= 2:
        time_span_s = temp_ts[-1] - temp_ts[0]
        if time_span_s > 0:
            temp_delta = end_temp - start_temp
            rate_of_rise = round(
                temp_delta / (time_span_s / 60.0), 2
            )

    # Compute time to threshold at current rate (minutes)
    time_to_threshold = None
    if rate_of_rise > 0 and end_temp < _CRITICAL_TEMP_C:
        remaining_deg = _CRITICAL_TEMP_C - end_temp
        time_to_threshold = round(remaining_deg / rate_of_rise, 1)

    thermal = {
        "has_data": True,
        "start_temp": round(start_temp, 1),
        "end_temp": round(end_temp, 1),
        "max_temp": round(max_temp, 1),
        "min_temp": round(min_temp, 1),
        "mean_temp": mean_temp,
        "sample_count": len(temps),
        "rate_of_rise": rate_of_rise,
        "time_to_threshold": time_to_threshold,
    }

    issues: List[dict] = []

    # Flag temperature exceedances
    if max_temp >= _CRITICAL_TEMP_C:
        issues.append({
            "severity": "high",
            "category": "thermal",
            "title": "Camera Critical Temperature",
            "description": (
                f"OAK-D camera reached {max_temp:.1f}\u00b0C"
                f" (critical threshold: {_CRITICAL_TEMP_C}\u00b0C)."
                f" Rate of rise: {rate_of_rise}\u00b0C/min."
            ),
            "node": "detection",
            "timestamp": 0,
            "message": (
                f"Camera critical temp: {max_temp:.1f}\u00b0C"
                f" (limit: {_CRITICAL_TEMP_C}\u00b0C)"
            ),
            "recommendation": (
                "Improve camera ventilation or add cooling."
                " OAK-D Lite thermal limit is 105\u00b0C;"
                " sustained operation above 85\u00b0C"
                " degrades image quality."
            ),
        })
    elif max_temp >= _WARN_TEMP_C:
        issues.append({
            "severity": "medium",
            "category": "thermal",
            "title": "Camera Temperature Warning",
            "description": (
                f"OAK-D camera reached {max_temp:.1f}\u00b0C"
                f" (warning threshold: {_WARN_TEMP_C}\u00b0C)."
                f" Rate of rise: {rate_of_rise}\u00b0C/min."
                + (
                    f" At current rate, critical threshold"
                    f" ({_CRITICAL_TEMP_C}\u00b0C) in"
                    f" {time_to_threshold:.0f} min."
                    if time_to_threshold
                    else ""
                )
            ),
            "node": "detection",
            "timestamp": 0,
            "message": (
                f"Camera temp warning: {max_temp:.1f}\u00b0C"
                f" (threshold: {_WARN_TEMP_C}\u00b0C)"
            ),
            "recommendation": (
                "Monitor camera temperature trend."
                " Consider adding passive heatsink"
                " or improving airflow."
            ),
        })

    return {"thermal": thermal, "issues": issues}


def detect_confidence_discrepancy(
    analyzer: "ROS2LogAnalyzer",
) -> List[dict]:
    """Detect confidence threshold discrepancy between app and NN.

    Scans log entries for application-level confidence_threshold
    (from ARM_client) and NN pipeline nn_confidence (from detection
    node config). Flags when they differ.

    Args:
        analyzer: ROS2LogAnalyzer with parsed entries.

    Returns:
        List of issue dicts (informational severity).
    """
    app_thresholds: set = set()
    nn_thresholds: set = set()

    for entry in analyzer.entries:
        msg = entry.message
        m = _RE_CONFIDENCE_THRESHOLD.search(msg)
        if m:
            app_thresholds.add(float(m.group(1)))
        m = _RE_NN_CONFIDENCE.search(msg)
        if m:
            nn_thresholds.add(float(m.group(1)))

    issues: List[dict] = []

    if app_thresholds and nn_thresholds:
        # Compare each app threshold with each NN threshold
        for app_t in app_thresholds:
            for nn_t in nn_thresholds:
                if abs(app_t - nn_t) > 0.001:
                    issues.append({
                        "severity": "low",
                        "category": "configuration",
                        "title": "Confidence Threshold Discrepancy",
                        "description": (
                            f"Application confidence threshold"
                            f" ({app_t:.2f}) differs from NN"
                            f" pipeline confidence ({nn_t:.2f})."
                            f" Pre-filter (NN) and post-filter"
                            f" (app) thresholds serve different"
                            f" purposes, but large gaps may"
                            f" indicate misconfiguration."
                        ),
                        "node": "detection",
                        "timestamp": 0,
                        "message": (
                            f"Confidence gap: app={app_t:.2f}"
                            f" vs NN={nn_t:.2f}"
                        ),
                        "recommendation": (
                            "Review whether the gap between"
                            " NN pre-filter and application"
                            " post-filter thresholds is"
                            " intentional."
                        ),
                    })

    return issues


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
from .registry import register as _register

_register(
    "analyze_camera_thermal", analyze_camera_thermal,
    category="camera",
    description="Analyze OAK-D camera temperature trends from detection_summary events.",
)
_register(
    "detect_confidence_discrepancy", detect_confidence_discrepancy,
    category="camera",
    description="Detect mismatch between NN confidence threshold and application filter.",
)
