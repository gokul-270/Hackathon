"""
Camera health monitoring: thermal trends, memory leaks, reconnection
timeline, stereo depth failures, and detection filtering statistics.

Tasks 10.1–10.5 of log-analyzer camera health enhancement.
"""

from __future__ import annotations

import statistics
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from ..models import EventStore

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# 10.1 — Temperature severity thresholds (degrees C)
_TEMP_WARN_C = 70.0
_TEMP_HIGH_C = 80.0

# Stabilisation: temperature delta under this value over the window
_STABILIZE_DELTA_C = 1.0
_STABILIZE_WINDOW = 5  # consecutive samples within delta

# 10.2 — Memory leak thresholds
_MEMORY_RECONNECT_INCREASE_PCT = 20.0
_MEMORY_GRADUAL_INCREASE_PCT = 50.0

# 10.3 — Reconnection thresholds
_RECONNECT_HIGH_THRESHOLD = 2
_LATENCY_SPIKE_MULTIPLIER = 5.0

# 10.4 — Stereo depth failure threshold (fraction of raw detections)
_DEPTH_FAILURE_RATE_THRESHOLD = 0.05


def analyze_camera_health(
    events: "EventStore",
) -> dict:
    """Analyze camera health from detection_summary and related events.

    Covers:
      10.1 — OAK-D temperature trend extraction
      10.2 — Camera memory leak detection
      10.3 — Camera reconnection timeline
      10.4 — Stereo depth failure detection
      10.5 — Detection filtering statistics

    Args:
        events: EventStore containing detection_summaries, camera_reconnections,
                detection_frames_summary, and detection_quality_events.

    Returns:
        Dict with keys:
          - "temperature": dict of temperature trend stats
          - "memory": dict of memory analysis
          - "reconnections": dict of reconnection timeline
          - "depth_failures": dict of stereo depth failure stats
          - "filtering": dict of detection filtering statistics
          - "issues": list of issue dicts for anomalies
    """
    issues: List[dict] = []

    temperature = _analyze_temperature(events, issues)
    memory = _analyze_memory(events, issues)
    reconnections = _analyze_reconnections(events, issues)
    depth_failures = _analyze_depth_failures(events, issues)
    filtering = _analyze_filtering_stats(events)

    return {
        "temperature": temperature,
        "memory": memory,
        "reconnections": reconnections,
        "depth_failures": depth_failures,
        "filtering": filtering,
        "issues": issues,
    }


# ---------------------------------------------------------------------------
# 10.1 — OAK-D temperature trend extraction
# ---------------------------------------------------------------------------


def _analyze_temperature(
    events: "EventStore",
    issues: List[dict],
) -> dict:
    """Parse camera.temp_c from detection_summary events.

    Computes start/peak/end temperatures and time to stabilisation.
    Raises Medium at >70C, High at >80C.
    """
    summaries = events.detection_summaries
    if not summaries:
        return {}

    temps: List[float] = []
    temp_ts: List[float] = []
    for ev in summaries:
        temp = ev.get("camera_temp_c")
        if temp is not None:
            temps.append(float(temp))
            ts = ev.get("_ts", 0.0)
            temp_ts.append(float(ts))

    if not temps:
        return {}

    start_temp = temps[0]
    peak_temp = max(temps)
    end_temp = temps[-1]
    mean_temp = round(statistics.mean(temps), 1)

    # Time to stabilisation: first index where _STABILIZE_WINDOW
    # consecutive readings are within _STABILIZE_DELTA_C of each other
    stabilize_time_s: Optional[float] = None
    if len(temps) >= _STABILIZE_WINDOW:
        for i in range(len(temps) - _STABILIZE_WINDOW + 1):
            window = temps[i : i + _STABILIZE_WINDOW]
            if max(window) - min(window) <= _STABILIZE_DELTA_C:
                if len(temp_ts) > i and temp_ts[0] > 0:
                    stabilize_time_s = round(
                        temp_ts[i] - temp_ts[0], 1
                    )
                break

    result = {
        "has_data": True,
        "start_temp_c": round(start_temp, 1),
        "peak_temp_c": round(peak_temp, 1),
        "end_temp_c": round(end_temp, 1),
        "mean_temp_c": mean_temp,
        "sample_count": len(temps),
        "stabilize_time_s": stabilize_time_s,
    }

    # Issue detection
    if peak_temp > _TEMP_HIGH_C:
        issues.append({
            "severity": "high",
            "category": "thermal",
            "title": "Camera Temperature Exceeds 80\u00b0C",
            "description": (
                f"OAK-D camera reached {peak_temp:.1f}\u00b0C"
                f" (high threshold: {_TEMP_HIGH_C}\u00b0C)."
                f" Start: {start_temp:.1f}\u00b0C,"
                f" End: {end_temp:.1f}\u00b0C."
            ),
            "node": "detection",
            "timestamp": 0,
            "message": (
                f"Camera peak temp: {peak_temp:.1f}\u00b0C"
                f" > {_TEMP_HIGH_C}\u00b0C"
            ),
            "recommendation": (
                "Add active cooling or improve ventilation."
                " Sustained high temperature degrades"
                " image quality and accelerates hardware wear."
            ),
        })
    elif peak_temp > _TEMP_WARN_C:
        issues.append({
            "severity": "medium",
            "category": "thermal",
            "title": "Camera Temperature Exceeds 70\u00b0C",
            "description": (
                f"OAK-D camera reached {peak_temp:.1f}\u00b0C"
                f" (warning threshold: {_TEMP_WARN_C}\u00b0C)."
                f" Start: {start_temp:.1f}\u00b0C,"
                f" End: {end_temp:.1f}\u00b0C."
            ),
            "node": "detection",
            "timestamp": 0,
            "message": (
                f"Camera peak temp: {peak_temp:.1f}\u00b0C"
                f" > {_TEMP_WARN_C}\u00b0C"
            ),
            "recommendation": (
                "Monitor temperature trend. Consider adding"
                " a passive heatsink or improving airflow."
            ),
        })

    return result


# ---------------------------------------------------------------------------
# 10.2 — Camera memory leak detection
# ---------------------------------------------------------------------------


def _analyze_memory(
    events: "EventStore",
    issues: List[dict],
) -> dict:
    """Compare host.memory_mb before/after camera reconnection.

    Raises Medium when memory increases >20% post-reconnection and
    stays elevated, or when gradual growth >50% without reconnection.
    """
    summaries = events.detection_summaries
    if not summaries:
        return {}

    mem_readings: List[float] = []
    mem_ts: List[float] = []
    for ev in summaries:
        mem = ev.get("host_memory_mb")
        if mem is not None:
            mem_readings.append(float(mem))
            mem_ts.append(float(ev.get("_ts", 0.0)))

    if not mem_readings:
        return {}

    start_mb = mem_readings[0]
    peak_mb = max(mem_readings)
    end_mb = mem_readings[-1]
    mean_mb = round(statistics.mean(mem_readings), 1)

    result: dict = {
        "has_data": True,
        "start_mb": round(start_mb, 1),
        "peak_mb": round(peak_mb, 1),
        "end_mb": round(end_mb, 1),
        "mean_mb": mean_mb,
        "sample_count": len(mem_readings),
        "leak_detected": False,
        "post_reconnect_increase_pct": None,
        "gradual_increase_pct": None,
    }

    # Check post-reconnection memory increase
    reconnections = events.camera_reconnections
    reconnect_ts_list = sorted(
        r["_ts"]
        for r in reconnections
        if r.get("type") == "reconnected" and r.get("_ts") is not None
    )

    if reconnect_ts_list and len(mem_readings) >= 2:
        for rts in reconnect_ts_list:
            # Find memory readings before and after this reconnection
            before: List[float] = []
            after: List[float] = []
            for i, ts in enumerate(mem_ts):
                if ts < rts:
                    before.append(mem_readings[i])
                elif ts > rts:
                    after.append(mem_readings[i])

            if before and after:
                pre_mean = statistics.mean(before[-min(5, len(before)) :])
                post_mean = statistics.mean(after[: min(5, len(after))])
                if pre_mean > 0:
                    pct_change = (
                        (post_mean - pre_mean) / pre_mean * 100.0
                    )
                    if pct_change > _MEMORY_RECONNECT_INCREASE_PCT:
                        # Verify it stays elevated: check rest of
                        # post-reconnect readings
                        if len(after) >= 3:
                            late_mean = statistics.mean(
                                after[len(after) // 2 :]
                            )
                            still_elevated = (
                                late_mean > pre_mean * (
                                    1 + _MEMORY_RECONNECT_INCREASE_PCT / 100.0
                                )
                            )
                        else:
                            still_elevated = True

                        if still_elevated:
                            result["leak_detected"] = True
                            result["post_reconnect_increase_pct"] = (
                                round(pct_change, 1)
                            )
                            issues.append({
                                "severity": "medium",
                                "category": "memory",
                                "title": (
                                    "Memory Increase Post Camera"
                                    " Reconnection"
                                ),
                                "description": (
                                    f"Host memory increased"
                                    f" {pct_change:.1f}% after camera"
                                    f" reconnection"
                                    f" ({pre_mean:.1f}MB \u2192"
                                    f" {post_mean:.1f}MB) and"
                                    f" remains elevated."
                                ),
                                "node": "detection",
                                "timestamp": 0,
                                "message": (
                                    f"Memory +{pct_change:.1f}%"
                                    f" post-reconnection"
                                ),
                                "recommendation": (
                                    "Investigate resource cleanup"
                                    " during camera reconnection."
                                    " DepthAI pipeline may not"
                                    " fully release buffers."
                                ),
                            })
                            break  # one issue is enough

    # Check gradual growth (no reconnection required)
    if start_mb > 0:
        gradual_pct = (peak_mb - start_mb) / start_mb * 100.0
        result["gradual_increase_pct"] = round(gradual_pct, 1)
        if gradual_pct > _MEMORY_GRADUAL_INCREASE_PCT:
            result["leak_detected"] = True
            issues.append({
                "severity": "medium",
                "category": "memory",
                "title": "Gradual Memory Growth Detected",
                "description": (
                    f"Host memory grew {gradual_pct:.1f}% over"
                    f" the session ({start_mb:.1f}MB \u2192"
                    f" {peak_mb:.1f}MB). Threshold:"
                    f" {_MEMORY_GRADUAL_INCREASE_PCT}%."
                ),
                "node": "detection",
                "timestamp": 0,
                "message": (
                    f"Memory growth: {start_mb:.1f}MB \u2192"
                    f" {peak_mb:.1f}MB"
                    f" (+{gradual_pct:.1f}%)"
                ),
                "recommendation": (
                    "Profile memory usage over extended"
                    " sessions. Check for unbounded"
                    " queues or cached objects."
                ),
            })

    return result


# ---------------------------------------------------------------------------
# 10.3 — Camera reconnection timeline
# ---------------------------------------------------------------------------


def _analyze_reconnections(
    events: "EventStore",
    issues: List[dict],
) -> dict:
    """Parse camera reconnection events and build a timeline.

    Tracks trigger reason, outage duration, and post-reconnect first
    detection latency.  Raises High when >2 reconnections in a session.
    Notes latency spikes >5x session median detection time.
    """
    reconnections = events.camera_reconnections
    if not reconnections:
        return {"count": 0, "timeline": []}

    # Build timeline: pair triggers with successful reconnections
    timeline: List[dict] = []
    pending_trigger: Optional[dict] = None

    for r in reconnections:
        rtype = r.get("type", "")
        if rtype in ("xlink", "attempt", "timeout"):
            if pending_trigger is None:
                pending_trigger = {
                    "trigger": rtype,
                    "trigger_ts": r.get("_ts"),
                    "arm_id": r.get("arm_id"),
                }
        elif rtype == "reconnected":
            reconnect_ts = r.get("_ts")
            entry: dict = {
                "trigger": (
                    pending_trigger["trigger"]
                    if pending_trigger
                    else "unknown"
                ),
                "trigger_ts": (
                    pending_trigger.get("trigger_ts")
                    if pending_trigger
                    else None
                ),
                "reconnect_ts": reconnect_ts,
                "arm_id": r.get("arm_id"),
                "outage_duration_s": None,
                "post_reconnect_latency_ms": None,
            }
            # Compute outage duration
            if (
                entry["trigger_ts"] is not None
                and reconnect_ts is not None
            ):
                outage = reconnect_ts - entry["trigger_ts"]
                if outage >= 0:
                    entry["outage_duration_s"] = round(outage, 2)

            timeline.append(entry)
            pending_trigger = None

    # Compute post-reconnect first detection latency
    # from detection_summary timestamps after each reconnection
    summaries = events.detection_summaries
    summary_ts_list = [
        float(s.get("_ts", 0.0))
        for s in summaries
        if s.get("_ts") is not None
    ]
    summary_ts_list.sort()

    # Session median detection latency (from detection_summary latency_avg_ms)
    latency_values: List[float] = []
    for s in summaries:
        lat = s.get("latency_avg_ms")
        if lat is not None:
            latency_values.append(float(lat))

    session_median_latency: Optional[float] = None
    if latency_values:
        session_median_latency = statistics.median(latency_values)

    latency_spike_events: List[dict] = []

    for entry in timeline:
        rts = entry.get("reconnect_ts")
        if rts is not None and summary_ts_list:
            # Find first detection_summary after reconnection
            for sts in summary_ts_list:
                if sts > rts:
                    entry["post_reconnect_latency_ms"] = round(
                        (sts - rts) * 1000.0, 1
                    )
                    break

            # Check for latency spikes in the first detection after
            # reconnection
            if session_median_latency and session_median_latency > 0:
                for s in summaries:
                    s_ts = s.get("_ts")
                    if s_ts is not None and float(s_ts) > rts:
                        lat = s.get("latency_avg_ms")
                        if lat is not None:
                            ratio = float(lat) / session_median_latency
                            if ratio > _LATENCY_SPIKE_MULTIPLIER:
                                latency_spike_events.append({
                                    "reconnect_ts": rts,
                                    "latency_ms": float(lat),
                                    "median_ms": round(
                                        session_median_latency, 1
                                    ),
                                    "ratio": round(ratio, 1),
                                })
                        break

    successful_count = len(timeline)
    total_count = len(reconnections)

    result = {
        "count": total_count,
        "successful_count": successful_count,
        "timeline": timeline,
        "session_median_latency_ms": (
            round(session_median_latency, 1)
            if session_median_latency is not None
            else None
        ),
        "latency_spikes": latency_spike_events,
    }

    # Issue: >2 reconnections
    if successful_count > _RECONNECT_HIGH_THRESHOLD:
        issues.append({
            "severity": "high",
            "category": "camera",
            "title": "Excessive Camera Reconnections",
            "description": (
                f"{successful_count} camera reconnections"
                f" during session (threshold:"
                f" {_RECONNECT_HIGH_THRESHOLD})."
                f" Total reconnection events: {total_count}."
            ),
            "node": "detection",
            "timestamp": 0,
            "message": (
                f"Camera reconnections: {successful_count}"
                f" (>{_RECONNECT_HIGH_THRESHOLD})"
            ),
            "recommendation": (
                "Check USB cable quality, hub power"
                " delivery, and OAK-D thermal state."
                " Consider USB watchdog reset."
            ),
        })

    # Note latency spikes
    for spike in latency_spike_events:
        issues.append({
            "severity": "medium",
            "category": "camera",
            "title": "Post-Reconnect Latency Spike",
            "description": (
                f"Detection latency {spike['latency_ms']:.1f}ms"
                f" after reconnection is"
                f" {spike['ratio']:.1f}x the session median"
                f" ({spike['median_ms']:.1f}ms)."
            ),
            "node": "detection",
            "timestamp": 0,
            "message": (
                f"Post-reconnect latency:"
                f" {spike['latency_ms']:.1f}ms"
                f" ({spike['ratio']:.1f}x median)"
            ),
            "recommendation": (
                "Camera may need warm-up time after"
                " reconnection. Consider adding a"
                " stabilisation delay before accepting"
                " detections."
            ),
        })

    return result


# ---------------------------------------------------------------------------
# 10.4 — Stereo depth failure detection
# ---------------------------------------------------------------------------


def _analyze_depth_failures(
    events: "EventStore",
    issues: List[dict],
) -> dict:
    """Detect stereo depth failures from detection quality events.

    Depth failures are inferred from detection_quality_events where
    raw detections exceed the sum of accepted, border-skipped, and
    not-pickable (the remainder are depth failures).

    Also checks detection_frames_summary for aggregate depth failure
    indicators.

    Raises Medium when >5% of raw detections dropped due to depth
    failure.
    """
    quality_events = events.detection_quality_events
    if not quality_events:
        return {"has_data": False}

    # Compute depth failures from detection quality events
    # raw = accepted + border_skip + not_pickable + depth_failures
    total_raw = 0
    total_accepted = 0
    total_border = 0
    total_not_pickable = 0
    depth_failure_details: List[dict] = []

    for ev in quality_events:
        raw = ev.get("raw", 0)
        accepted = ev.get("cotton_accepted", 0)
        border = ev.get("border_skip", 0)
        not_pick = ev.get("not_pickable", 0)

        total_raw += raw
        total_accepted += accepted
        total_border += border
        total_not_pickable += not_pick

        # Depth failures = raw - accepted - border - not_pickable
        depth_fail = max(0, raw - accepted - border - not_pick)
        if depth_fail > 0:
            depth_failure_details.append({
                "timestamp": ev.get("_ts", 0),
                "raw": raw,
                "depth_failures": depth_fail,
                "arm_id": ev.get("arm_id"),
            })

    total_depth_failures = max(
        0,
        total_raw - total_accepted - total_border - total_not_pickable,
    )
    depth_failure_rate = (
        total_depth_failures / total_raw if total_raw > 0 else 0.0
    )

    result = {
        "has_data": True,
        "total_raw": total_raw,
        "total_depth_failures": total_depth_failures,
        "depth_failure_rate": round(depth_failure_rate, 4),
        "events_with_failures": len(depth_failure_details),
    }

    if (
        depth_failure_rate > _DEPTH_FAILURE_RATE_THRESHOLD
        and total_raw > 0
    ):
        pct = round(depth_failure_rate * 100, 1)
        issues.append({
            "severity": "medium",
            "category": "camera",
            "title": "Stereo Depth Failure Rate Elevated",
            "description": (
                f"{total_depth_failures}/{total_raw} raw"
                f" detections ({pct}%) dropped due to stereo"
                f" depth failure (threshold:"
                f" {_DEPTH_FAILURE_RATE_THRESHOLD * 100:.0f}%)."
            ),
            "node": "detection",
            "timestamp": 0,
            "message": (
                f"Depth failure rate: {pct}%"
                f" ({total_depth_failures}/{total_raw})"
            ),
            "recommendation": (
                "Check stereo calibration and baseline."
                " Ensure adequate lighting and texture"
                " in the scene for stereo matching."
            ),
        })

    return result


# ---------------------------------------------------------------------------
# 10.5 — Detection filtering statistics
# ---------------------------------------------------------------------------


def _analyze_filtering_stats(
    events: "EventStore",
) -> dict:
    """Aggregate border_filtered and not_pickable counts.

    Combines data from detection_quality_events (text-parsed) and
    detection_frames_summary (JSON-parsed) to compute total raw
    detections, accepted, border-filtered, not-pickable, depth
    failures, and acceptance rate.
    """
    quality_events = events.detection_quality_events
    frames_summary = events.detection_frames_summary

    if not quality_events and frames_summary.get("count", 0) == 0:
        return {}

    # Primary source: detection_quality_events (text-parsed, per-frame)
    total_raw = 0
    total_accepted = 0
    total_border = 0
    total_not_pickable = 0

    if quality_events:
        total_raw = sum(e.get("raw", 0) for e in quality_events)
        total_accepted = sum(
            e.get("cotton_accepted", 0) for e in quality_events
        )
        # Use running totals (max of cumulative totals)
        total_border = max(
            (e.get("border_skip_total", 0) for e in quality_events),
            default=0,
        )
        total_not_pickable = max(
            (e.get("not_pickable_total", 0) for e in quality_events),
            default=0,
        )
    elif frames_summary.get("count", 0) > 0:
        # Fallback to detection_frames_summary aggregate
        total_raw = frames_summary.get("raw_count", 0)
        total_accepted = frames_summary.get("accepted_count", 0)
        # border_filtered and not_pickable are last-seen values
        # from detection_frame events (not cumulative sums)
        border = frames_summary.get("border_filtered")
        not_pick = frames_summary.get("not_pickable")
        total_border = int(border) if border is not None else 0
        total_not_pickable = (
            int(not_pick) if not_pick is not None else 0
        )

    total_depth_failures = max(
        0,
        total_raw - total_accepted - total_border - total_not_pickable,
    )
    acceptance_rate = (
        round(total_accepted / total_raw * 100.0, 1)
        if total_raw > 0
        else 0.0
    )

    return {
        "total_raw": total_raw,
        "total_accepted": total_accepted,
        "total_border_filtered": total_border,
        "total_not_pickable": total_not_pickable,
        "total_depth_failures": total_depth_failures,
        "acceptance_rate_pct": acceptance_rate,
    }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
from .registry import register as _register

_register(
    "analyze_camera_health", analyze_camera_health,
    category="camera",
    description="Analyze camera health (thermal, memory, reconnections, depth, filtering).",
)
