"""Failure chain, launch crash, and session health detectors (Groups 13, 13b, 14)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..analyzer import ROS2LogAnalyzer


# ---------------------------------------------------------------------------
# Group 13 — Failure chains
# ---------------------------------------------------------------------------

_USB_CAMERA_WINDOW_S = 5.0  # USB disconnect → camera failure within 5s


def detect_failure_chains(analyzer: "ROS2LogAnalyzer") -> None:
    """tasks 13.1-13.4 — scan for sequential failure patterns."""
    events = analyzer.events

    # Initialise _failure_chains for later use by reports (task 13.1)
    failure_chains: list = []

    # task 13.1 — consecutive pick failure chains (≥3 in a row)
    _MIN_CHAIN_LENGTH = 3
    sorted_picks = sorted(events.picks, key=lambda p: p.get("_ts") or 0)
    chain_start = None
    chain_len = 0
    for pick in sorted_picks:
        if pick.get("success") is False:
            if chain_start is None:
                chain_start = pick.get("_ts") or 0
            chain_len += 1
        else:
            if chain_len >= _MIN_CHAIN_LENGTH:
                failure_chains.append(
                    {"start_ts": chain_start, "length": chain_len, "type": "consecutive_pick_failures"}
                )
            chain_start = None
            chain_len = 0
    # Flush trailing chain
    if chain_len >= _MIN_CHAIN_LENGTH:
        failure_chains.append(
            {"start_ts": chain_start, "length": chain_len, "type": "consecutive_pick_failures"}
        )

    for chain in failure_chains:
        analyzer._add_issue(
            severity="high",
            category="failure_chain",
            title=f"Consecutive pick failure chain: {chain['length']} failures",
            description=(
                f"{chain['length']} consecutive pick failures starting at "
                f"ts={chain['start_ts']:.1f}"
            ),
            node="motion_controller",
            timestamp=chain["start_ts"],
            message=f"consecutive_pick_failures length={chain['length']}",
            recommendation="Inspect arm mechanics, camera, and cotton boll accessibility",
        )

    # task 13.2 — Camera → Detection → Pick chain
    if (
        any(ds.get("camera_healthy") is False for ds in events.detection_summaries)
        and events.picks
    ):
        failed_picks = [p for p in events.picks if p.get("success") is False]
        if failed_picks:
            analyzer._add_issue(
                severity="high",
                category="failure_chain",
                title="Camera failure chain: unhealthy camera → pick failures",
                description=(
                    f"Camera reported unhealthy and {len(failed_picks)} pick(s) failed"
                ),
                node="cotton_detection",
                timestamp=failed_picks[0].get("_ts") or 0,
                message=f"camera_healthy=False → pick failures={len(failed_picks)}",
                recommendation="Stabilise camera connection before field operation",
            )

    # task 13.3 — USB disconnect → Camera unhealthy within 5s
    usb_disconnect_times = [
        e.get("_ts")
        for e in events.dmesg_usb_disconnects
        if e.get("_ts") is not None
    ]
    for ts_usb in usb_disconnect_times:
        for ds in events.detection_summaries:
            ts_cam = ds.get("_ts")
            if (
                ts_cam is not None
                and ds.get("camera_healthy") is False
                and abs(ts_cam - ts_usb) < _USB_CAMERA_WINDOW_S
            ):
                analyzer._add_issue(
                    severity="high",
                    category="failure_chain",
                    title="USB disconnect caused camera failure",
                    description=(
                        f"USB disconnect (ts={ts_usb:.1f}) followed by camera "
                        f"healthy=False within {_USB_CAMERA_WINDOW_S}s"
                    ),
                    node="cotton_detection",
                    timestamp=ts_usb,
                    message=f"dmesg USB disconnect → camera unhealthy {ts_cam - ts_usb:.1f}s later",
                    recommendation="Use a powered USB hub; check cable quality",
                )
                break  # one issue per USB disconnect

    # task 13.4 — Motor alert → Pick failure chain
    emergency_alerts = [
        ma for ma in events.motor_alerts if ma.get("action") == "emergency_shutdown"
    ]
    for alert in emergency_alerts:
        alert_ts = alert.get("_ts")
        if alert_ts is None:
            continue
        # Find pick failure after this alert
        for pick in events.picks:
            pick_ts = pick.get("_ts")
            if pick_ts is not None and pick_ts >= alert_ts and pick.get("success") is False:
                analyzer._add_issue(
                    severity="critical",
                    category="failure_chain",
                    title="Motor emergency shutdown caused pick failure",
                    description=(
                        f"motor_alert action=emergency_shutdown at ts={alert_ts:.1f} "
                        f"→ pick failure at ts={pick_ts:.1f}"
                    ),
                    node=alert.get("_node") or "arm_control",
                    timestamp=alert_ts,
                    message=f"motor_alert emergency_shutdown → pick_failed",
                    recommendation=(
                        "Resolve motor alert before resuming operation; inspect joint for"
                        " damage"
                    ),
                )
                break  # one issue per alert

    # Store chains for reports
    events._failure_chains = failure_chains


# ---------------------------------------------------------------------------
# Group 13b — Launch process health detector
# ---------------------------------------------------------------------------


def detect_launch_crashes(analyzer: "ROS2LogAnalyzer") -> None:
    """task 13.3 — emit Critical issues for every crashed process in launch_events."""
    for ev in analyzer.events.launch_events:
        if ev.get("type") != "crash":
            continue
        exit_code = ev.get("exit_code", 0)
        if exit_code == 0:
            continue  # clean exit — not a crash

        name = ev.get("name", "unknown")
        pid = ev.get("pid", "?")
        cmd = ev.get("cmd", "")
        lifetime_s = ev.get("lifetime_s")
        hint = ev.get("external_log_hint")
        has_ros2_log = ev.get("has_ros2_log", True)

        desc_parts = [
            f"Node {name} crashed (exit code {exit_code}) — {cmd}",
        ]
        if lifetime_s is not None:
            desc_parts.append(f"Lifetime: {lifetime_s:.1f}s")
        if not has_ros2_log:
            desc_parts.append("No ROS2 log file found in session directory")
        if hint:
            desc_parts.append(f"See {hint} for details")

        analyzer._add_issue(
            severity="critical",
            category="process",
            title=f"Node {name} crashed (exit code {exit_code})",
            description="; ".join(desc_parts),
            node=name,
            timestamp=ev.get("crash_ts") or ev.get("start_ts") or 0,
            message=f"Node {name} crashed (exit code {exit_code}) — {cmd}",
            recommendation=(
                f"Check logs for {name}; if the process dies immediately, verify "
                "imports, dependencies, and ROS2 topic configuration"
            ),
        )


# ---------------------------------------------------------------------------
# Group 14 — Session health analysis
# ---------------------------------------------------------------------------

_TIMESTAMP_GAP_S = 30.0     # gaps > 30s are reported
_MAX_CLOCK_JUMP_S = 5.0     # backward jumps > 5s reported


def analyze_session_health(analyzer: "ROS2LogAnalyzer") -> None:
    """tasks 14.1-14.6 — session-level health analysis."""
    _compute_uptime_ratio(analyzer)
    _detect_restarts(analyzer)
    _detect_timestamp_gaps(analyzer)
    _track_manual_interventions(analyzer)
    _validate_timestamp_monotonicity(analyzer)


def _compute_uptime_ratio(analyzer: "ROS2LogAnalyzer") -> None:
    """task 14.2 — time in each VehicleState."""
    events = analyzer.events
    state_time: dict = {}
    for st in events.state_transitions:
        duration = st.get("time_in_previous_state_ms")
        prev_state = st.get("from_state") or "UNKNOWN"
        if duration is not None:
            state_time[prev_state] = state_time.get(prev_state, 0.0) + duration / 1000.0
    events._state_time_s = state_time


def _detect_restarts(analyzer: "ROS2LogAnalyzer") -> None:
    """task 14.3 — count startup_timing events."""
    count = len(analyzer.events.startup)
    if count > 1:
        analyzer._add_issue(
            severity="medium",
            category="session",
            title=f"System restarted during session ({count} startups)",
            description=f"{count} startup_timing events detected (expected 1)",
            node="vehicle_control",
            timestamp=analyzer.events.startup[0].get("_ts") or 0,
            message=f"startup_timing count={count}",
            recommendation="Investigate crash or manual restart cause",
        )


def _detect_timestamp_gaps(analyzer: "ROS2LogAnalyzer") -> None:
    """task 14.4 — detect >30s gaps between consecutive events.

    Computes gaps within each individual log file so that time between
    separate process invocations (different log files) is never flagged
    as a logging gap.
    """
    from collections import defaultdict

    # Group entries by individual file (not category) so inter-file
    # boundaries are never counted as gaps
    per_file_ts: dict[str, list[float]] = defaultdict(list)
    for e in analyzer.entries:
        if e.timestamp > 0:
            per_file_ts[e.file].append(e.timestamp)

    gap_events = []
    _MIN_ENTRIES_FOR_GAP = 10  # skip files with few entries (e.g. robot_state_publisher)
    for _file, timestamps in per_file_ts.items():
        if len(timestamps) < _MIN_ENTRIES_FOR_GAP:
            continue
        timestamps.sort()
        for i in range(1, len(timestamps)):
            gap = timestamps[i] - timestamps[i - 1]
            if gap > _TIMESTAMP_GAP_S:
                gap_events.append((timestamps[i - 1], timestamps[i], gap))

    if gap_events:
        total_gap_s = sum(g for _, _, g in gap_events)
        analyzer._add_issue(
            severity="medium",
            category="session",
            title=f"Log gaps detected ({len(gap_events)} gap(s), {total_gap_s:.0f}s total)",
            description=(
                f"Largest gap: {max(g for _, _, g in gap_events):.0f}s "
                f"({len(gap_events)} gaps > {_TIMESTAMP_GAP_S}s)"
            ),
            node="log_system",
            timestamp=gap_events[0][0],
            message=f"timestamp_gap count={len(gap_events)} total_s={total_gap_s:.0f}",
            recommendation="Check for logging interruptions or system sleep",
        )

    # Store on analyzer for reports
    analyzer.events._timestamp_gaps = gap_events


def _track_manual_interventions(analyzer: "ROS2LogAnalyzer") -> None:
    """task 14.5 — count/duration of manual mode states."""
    _MANUAL_STATES = {"MANUAL_MODE", "MANUAL_LEFT", "MANUAL_RIGHT", "NONBRAKE_MANUAL"}
    manual_duration_s = 0.0
    manual_count = 0
    for st in analyzer.events.state_transitions:
        if st.get("from_state") in _MANUAL_STATES:
            d = st.get("time_in_previous_state_ms") or 0
            manual_duration_s += d / 1000.0
            manual_count += 1
    analyzer.events._manual_interventions = {
        "count": manual_count,
        "total_s": manual_duration_s,
    }


def _validate_timestamp_monotonicity(analyzer: "ROS2LogAnalyzer") -> None:
    """task 14.6 — verify timestamps never go backward; report clock jumps.

    Only compares consecutive timestamps WITHIN the same file to avoid
    false positives when timestamps reset between different log files.
    """
    jump_events = []
    prev_ts = None
    prev_file = None
    for entry in analyzer.entries:
        ts = entry.timestamp
        # Reset timestamp tracking at file boundaries to avoid
        # false clock-jump detections across different log files.
        if entry.file != prev_file:
            prev_ts = None
            prev_file = entry.file
        if prev_ts is not None and ts < prev_ts:
            magnitude = prev_ts - ts
            if magnitude > _MAX_CLOCK_JUMP_S:
                jump_events.append(
                    {
                        "line": entry.line_number,
                        "file": entry.file,
                        "prev_ts": prev_ts,
                        "ts": ts,
                        "jump_s": magnitude,
                    }
                )
        prev_ts = ts

    if jump_events:
        worst = max(jump_events, key=lambda x: x["jump_s"])
        analyzer._add_issue(
            severity="medium",
            category="session",
            title=f"Clock jumps detected ({len(jump_events)} event(s))",
            description=(
                f"Largest backward clock jump: {worst['jump_s']:.1f}s "
                f"at line {worst['line']} in {worst['file']}"
            ),
            node="log_system",
            timestamp=worst["prev_ts"],
            message=f"clock_jump magnitude={worst['jump_s']:.1f}s",
            recommendation="Check NTP sync and system clock stability on RPi",
        )

    analyzer.events._clock_jumps = jump_events


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
from .registry import register as _register

_register(
    "detect_failure_chains", detect_failure_chains,
    category="analysis",
    description="Scan for sequential failure patterns (USB disconnect -> camera failure).",
)
_register(
    "detect_launch_crashes", detect_launch_crashes,
    category="system",
    description="Flag processes that crashed during the session from launch.log.",
)
_register(
    "analyze_session_health", analyze_session_health,
    category="system",
    description="Compute uptime ratio, detect restarts, timestamp gaps, and clock jumps.",
)
