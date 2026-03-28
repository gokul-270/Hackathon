"""
Session lifecycle analysis detector.

Tasks 12.2-12.5 of log-analyzer-enhancements:
  12.2 — Node lifecycle timeline with gap detection
  12.3 — RPi reboot detection via PID wraparound
  12.4 — Shutdown type classification (clean/crash/kill)
  12.5 — ARM_client MQTT failure pattern detection
"""

from __future__ import annotations

import re
import statistics
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from ..analyzer import ROS2LogAnalyzer

# Critical nodes whose downtime warrants a Medium severity issue
_CRITICAL_NODES = {
    "yanthra_move",
    "cotton_detection",
    "mg6010_controller",
}

# Maximum acceptable downtime (seconds) for critical nodes
_CRITICAL_DOWNTIME_S = 30.0

# PID reset detection: minimum temporal gap (seconds) to consider a reboot
_REBOOT_GAP_S = 60.0

# PID reset detection: PID must drop by at least this ratio to be a wraparound
# (e.g. going from PID 15000 to PID 500)
_PID_DROP_RATIO = 0.5

# MQTT failure threshold: minimum repeated failures to raise an issue
_MQTT_FAILURE_THRESHOLD = 3


def analyze_session_lifecycle(
    analyzer: "ROS2LogAnalyzer",
) -> dict:
    """Analyze session lifecycle from launch_events and ARM_client events.

    Args:
        analyzer: ROS2LogAnalyzer with populated events.

    Returns:
        Dict with keys:
          - "timeline": dict mapping node_name -> list of run periods
          - "gaps": list of gap dicts for critical nodes
          - "reboots": list of detected reboot events
          - "shutdown_types": dict mapping node_name -> shutdown type info
          - "mqtt_failures": list of MQTT failure pattern dicts
          - "issues": list of issue dicts for anomalies
    """
    events = analyzer.events
    launch_events = events.launch_events

    issues: List[dict] = []

    # 12.2 — Node lifecycle timeline
    timeline, gaps = _build_node_timeline(launch_events)
    issues.extend(_detect_critical_downtime(gaps))

    # 12.3 — RPi reboot detection
    reboots = _detect_reboots(launch_events)
    issues.extend(_reboot_issues(reboots))

    # 12.4 — Shutdown type classification
    shutdown_types = _classify_shutdowns(launch_events)

    # 12.5 — ARM_client MQTT failure patterns
    mqtt_failures = _detect_mqtt_failure_patterns(events)
    issues.extend(_mqtt_failure_issues(mqtt_failures))

    return {
        "timeline": timeline,
        "gaps": gaps,
        "reboots": reboots,
        "shutdown_types": shutdown_types,
        "mqtt_failures": mqtt_failures,
        "issues": issues,
    }


# ---------------------------------------------------------------------------
# 12.2 — Node lifecycle timeline
# ---------------------------------------------------------------------------


def _build_node_timeline(
    launch_events: List[dict],
) -> Tuple[Dict[str, list], List[dict]]:
    """Build per-node run periods and detect gaps.

    Returns:
        (timeline, gaps) where:
          timeline: {node_name: [{start_ts, end_ts, pid}, ...]}
          gaps: [{node, gap_start, gap_end, gap_s}, ...]
    """
    # Collect start/end for each node
    # A node can start multiple times (restart after crash)
    node_periods: Dict[str, list] = {}

    # Track active processes: pid -> {name, start_ts}
    active: Dict[int, dict] = {}

    for ev in launch_events:
        ev_type = ev.get("type")

        if ev_type == "start":
            name = ev.get("name", "unknown")
            pid = ev.get("pid")
            start_ts = ev.get("start_ts")
            if pid is not None:
                active[pid] = {"name": name, "start_ts": start_ts}

        elif ev_type == "crash":
            name = ev.get("name", "unknown")
            pid = ev.get("pid")
            end_ts = ev.get("crash_ts")
            start_ts = ev.get("start_ts")

            period = {
                "start_ts": start_ts,
                "end_ts": end_ts,
                "pid": pid,
            }
            node_periods.setdefault(name, []).append(period)
            active.pop(pid, None)

        elif ev_type == "still_running":
            name = ev.get("name", "unknown")
            pid = ev.get("pid")
            start_ts = ev.get("start_ts")

            period = {
                "start_ts": start_ts,
                "end_ts": None,  # still running at log end
                "pid": pid,
            }
            node_periods.setdefault(name, []).append(period)
            active.pop(pid, None)

        elif ev_type == "shutdown":
            # Shutdown signal — mark all active processes as ended
            ts = ev.get("ts")
            for pid, info in list(active.items()):
                name = info["name"]
                period = {
                    "start_ts": info["start_ts"],
                    "end_ts": ts,
                    "pid": pid,
                }
                node_periods.setdefault(name, []).append(period)
            active.clear()

    # Close any remaining active (not handled by shutdown event)
    for pid, info in active.items():
        name = info["name"]
        period = {
            "start_ts": info["start_ts"],
            "end_ts": None,
            "pid": pid,
        }
        node_periods.setdefault(name, []).append(period)

    # Sort periods by start_ts
    for name in node_periods:
        node_periods[name].sort(
            key=lambda p: p.get("start_ts") or 0
        )

    # Detect gaps between consecutive periods for the same node
    gaps: List[dict] = []
    for name, periods in node_periods.items():
        for i in range(1, len(periods)):
            prev_end = periods[i - 1].get("end_ts")
            curr_start = periods[i].get("start_ts")
            if prev_end is not None and curr_start is not None:
                gap_s = curr_start - prev_end
                if gap_s > 0:
                    gaps.append({
                        "node": name,
                        "gap_start": prev_end,
                        "gap_end": curr_start,
                        "gap_s": gap_s,
                    })

    return node_periods, gaps


def _detect_critical_downtime(gaps: List[dict]) -> List[dict]:
    """Raise Medium issues for critical nodes with >30s downtime."""
    issues: List[dict] = []
    for gap in gaps:
        node = gap["node"]
        gap_s = gap["gap_s"]
        if node in _CRITICAL_NODES and gap_s > _CRITICAL_DOWNTIME_S:
            issues.append({
                "severity": "medium",
                "category": "lifecycle",
                "title": f"Critical node downtime: {node}",
                "description": (
                    f"Node '{node}' was down for {gap_s:.1f}s "
                    f"(threshold: {_CRITICAL_DOWNTIME_S:.0f}s). "
                    f"Gap from {gap['gap_start']:.3f} to {gap['gap_end']:.3f}."
                ),
                "node": node,
                "timestamp": gap["gap_start"],
                "message": (
                    f"Critical node '{node}' downtime: {gap_s:.1f}s"
                ),
                "recommendation": (
                    "Investigate why this critical node was not running. "
                    "Consider adding automatic restart via launch respawn."
                ),
        })
    return issues


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
from .registry import register as _register

_register(
    "analyze_session_lifecycle", analyze_session_lifecycle,
    category="system",
    description="Analyze node lifecycle timeline, reboots, shutdown types, and MQTT failures.",
)


# ---------------------------------------------------------------------------
# 12.3 — RPi reboot detection
# ---------------------------------------------------------------------------


def _detect_reboots(launch_events: List[dict]) -> List[dict]:
    """Detect probable RPi reboots from PID wraparound + temporal gaps.

    A reboot is indicated when:
      1. PIDs drop significantly (high -> low) between consecutive start events
      2. There is a temporal gap of at least _REBOOT_GAP_S

    Returns list of reboot dicts with timestamp, old/new PID, gap info.
    """
    reboots: List[dict] = []

    # Collect all start events with valid PID and timestamp, sorted by time
    starts = [
        ev for ev in launch_events
        if ev.get("type") == "start"
        and ev.get("pid") is not None
        and ev.get("start_ts") is not None
    ]
    starts.sort(key=lambda e: e["start_ts"])

    if len(starts) < 2:
        return reboots

    prev = starts[0]
    for curr in starts[1:]:
        prev_pid = prev["pid"]
        curr_pid = curr["pid"]
        prev_ts = prev["start_ts"]
        curr_ts = curr["start_ts"]

        gap_s = curr_ts - prev_ts

        # Check for PID wraparound: current PID much lower than previous
        # AND a meaningful temporal gap
        if (
            prev_pid > 0
            and curr_pid < prev_pid * (1 - _PID_DROP_RATIO)
            and gap_s > _REBOOT_GAP_S
        ):
            reboots.append({
                "timestamp": curr_ts,
                "prev_pid": prev_pid,
                "curr_pid": curr_pid,
                "gap_s": gap_s,
                "prev_ts": prev_ts,
            })

        prev = curr

    return reboots


def _reboot_issues(reboots: List[dict]) -> List[dict]:
    """Generate Medium severity issues for detected reboots."""
    issues: List[dict] = []
    for reboot in reboots:
        gap_min = reboot["gap_s"] / 60.0
        issues.append({
            "severity": "medium",
            "category": "lifecycle",
            "title": "Probable RPi reboot detected",
            "description": (
                f"Probable RPi reboot detected at {reboot['timestamp']:.3f}"
                f" - PID reset from {reboot['prev_pid']}"
                f" to {reboot['curr_pid']}"
                f" with {gap_min:.1f}-minute gap"
            ),
            "node": "launch",
            "timestamp": reboot["timestamp"],
            "message": (
                f"PID reset {reboot['prev_pid']}"
                f" -> {reboot['curr_pid']},"
                f" gap {gap_min:.1f}min"
            ),
            "recommendation": (
                "Investigate cause of reboot. Check power supply stability, "
                "thermal throttling, or watchdog timer triggers."
            ),
        })
    return issues


# ---------------------------------------------------------------------------
# 12.4 — Shutdown type classification
# ---------------------------------------------------------------------------


def _classify_shutdowns(
    launch_events: List[dict],
) -> Dict[str, dict]:
    """Classify shutdown type per node from exit signals.

    Returns dict mapping node_name -> {
        shutdown_type: "clean" | "crash" | "kill" | "unknown",
        exit_code: int,
        exit_signal: str or None,
        crash_ts: float or None,
    }

    If a node has multiple crashes, the last one is used.
    """
    shutdown_types: Dict[str, dict] = {}

    for ev in launch_events:
        if ev.get("type") != "crash":
            continue

        name = ev.get("name", "unknown")
        shutdown_types[name] = {
            "shutdown_type": ev.get("shutdown_type", "unknown"),
            "exit_code": ev.get("exit_code"),
            "exit_signal": ev.get("exit_signal"),
            "crash_ts": ev.get("crash_ts"),
            "pid": ev.get("pid"),
        }

    return shutdown_types


# ---------------------------------------------------------------------------
# 12.5 — ARM_client MQTT failure pattern detection
# ---------------------------------------------------------------------------

# Regex to extract broker address from MQTT messages
_RE_BROKER_ADDR = re.compile(
    r"(?:broker|host|connect(?:ing)?\s+to)\s+"
    r"['\"]?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?::\d+)?)['\"]?",
    re.IGNORECASE,
)


def _detect_mqtt_failure_patterns(events) -> List[dict]:
    """Detect repeated MQTT connection failure patterns from ARM_client logs.

    Analyzes arm_client_mqtt_events for timeout and disconnect patterns,
    grouping by arm_id and broker address.

    Returns list of failure pattern dicts.
    """
    mqtt_events = events.arm_client_mqtt_events
    if not mqtt_events:
        return []

    # Group failures by (arm_id, broker_addr)
    failure_groups: Dict[tuple, list] = {}

    for ev in mqtt_events:
        event_type = ev.get("event_type", "")
        if event_type not in ("mqtt_timeout", "mqtt_disconnect"):
            continue

        arm_id = ev.get("arm_id", "unknown")
        message = ev.get("message", "")
        ts = ev.get("timestamp")

        # Try to extract broker address from message
        addr_m = _RE_BROKER_ADDR.search(message)
        broker = addr_m.group(1) if addr_m else "unknown"

        key = (arm_id, broker)
        failure_groups.setdefault(key, []).append({
            "timestamp": ts,
            "event_type": event_type,
            "message": message,
        })

    # Build failure pattern summaries
    patterns: List[dict] = []
    for (arm_id, broker), failures in failure_groups.items():
        if len(failures) < _MQTT_FAILURE_THRESHOLD:
            continue

        timestamps = [
            f["timestamp"] for f in failures
            if f.get("timestamp") is not None
        ]
        timestamps.sort()

        # Compute timing stats
        intervals: List[float] = []
        for i in range(1, len(timestamps)):
            intervals.append(timestamps[i] - timestamps[i - 1])

        timing = {}
        if intervals:
            timing["mean_interval_s"] = round(
                statistics.mean(intervals), 1
            )
            timing["min_interval_s"] = round(min(intervals), 1)
            timing["max_interval_s"] = round(max(intervals), 1)

        first_ts = timestamps[0] if timestamps else None
        last_ts = timestamps[-1] if timestamps else None
        duration_s = (last_ts - first_ts) if (first_ts and last_ts) else None

        patterns.append({
            "arm_id": arm_id,
            "broker": broker,
            "failure_count": len(failures),
            "first_failure": first_ts,
            "last_failure": last_ts,
            "duration_s": duration_s,
            "timing": timing,
            "timeout_count": sum(
                1 for f in failures if f["event_type"] == "mqtt_timeout"
            ),
            "disconnect_count": sum(
                1 for f in failures if f["event_type"] == "mqtt_disconnect"
            ),
        })

    return patterns


def _mqtt_failure_issues(patterns: List[dict]) -> List[dict]:
    """Generate Medium severity issues for MQTT failure patterns."""
    issues: List[dict] = []
    for pat in patterns:
        arm_id = pat["arm_id"]
        broker = pat["broker"]
        count = pat["failure_count"]
        timing = pat.get("timing", {})

        timing_desc = ""
        if timing:
            timing_desc = (
                f" Mean interval: {timing.get('mean_interval_s', '?')}s."
            )

        issues.append({
            "severity": "medium",
            "category": "mqtt",
            "title": f"ARM_client MQTT connection failures ({arm_id})",
            "description": (
                f"ARM_client on {arm_id} had {count} MQTT connection"
                f" failures to broker {broker}."
                f" Timeouts: {pat['timeout_count']},"
                f" disconnects: {pat['disconnect_count']}."
                f"{timing_desc}"
            ),
            "node": "arm_client",
            "timestamp": pat.get("first_failure") or 0,
            "message": (
                f"MQTT failures: {count}x to {broker}"
                f" ({arm_id})"
            ),
            "recommendation": (
                "Check network connectivity between RPi and MQTT broker. "
                "Verify broker address and port are correct. "
                "Consider increasing MQTT keepalive timeout."
            ),
        })
    return issues
