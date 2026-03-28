"""Cross-correlation detectors (Groups 11b, 12, cross-log 4.x)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List

if TYPE_CHECKING:
    from ..analyzer import ROS2LogAnalyzer
    from ..models import EventStore


# ---------------------------------------------------------------------------
# Cross-log correlation constants (tasks 4.1-4.5)
# ---------------------------------------------------------------------------

CORRELATION_WINDOW_S = 30.0  # seconds


# ---------------------------------------------------------------------------
# Group 11b — Motor-command cross-correlation detector
# ---------------------------------------------------------------------------


def correlate_motor_commands_with_picking(events: "EventStore") -> list:
    """tasks 11.1-11.3 — cross-reference motor cmds.rx against real picks.

    Returns a list of issue dicts (not added to analyzer directly so callers
    can choose how to wire them in).
    """

    # Picks with real joint motion (approach_ms > 10)
    real_picks = [p for p in events.picks if (p.get("approach_ms") or 0) > 10]
    if not real_picks:
        return []

    # Group motor_health_arm records by arm_id
    arm_motors: dict = {}
    for mh in events.motor_health_arm:
        arm_id = mh.get("arm_id")
        key = arm_id if arm_id is not None else "__single__"
        arm_motors.setdefault(key, []).append(mh)

    # Group real picks by arm_id too
    arm_picks: dict = {}
    for p in real_picks:
        arm_id = p.get("arm_id")
        key = arm_id if arm_id is not None else "__single__"
        arm_picks.setdefault(key, []).append(p)

    issues = []

    for arm_key in set(list(arm_picks.keys()) + list(arm_motors.keys())):
        if not arm_picks.get(arm_key):
            continue  # no real picks for this arm — nothing to correlate

        snapshots = arm_motors.get(arm_key, [])
        if not snapshots:
            continue  # no motor health data — cannot evaluate

        # Collect all joints seen across all snapshots, tracking max cmds.rx.
        # Initialise to -1 so that a value of 0 is correctly recorded.
        joint_max_cmds: dict = {}
        for mh in snapshots:
            for motor in mh.get("motors") or []:
                joint = motor.get("joint", "?")
                rx = (
                    motor.get("cmds", {}).get("rx")
                    if isinstance(motor.get("cmds"), dict)
                    else None
                )
                if rx is None:
                    rx = motor.get("cmds_rx")
                if rx is not None:
                    prev = joint_max_cmds.get(joint, -1)
                    if rx > prev:
                        joint_max_cmds[joint] = rx

        if not joint_max_cmds:
            continue  # motors have no cmds.rx data at all — skip

        zero_joints = [j for j, v in joint_max_cmds.items() if v == 0]
        nonzero_joints = [j for j, v in joint_max_cmds.items() if v > 0]
        total = len(joint_max_cmds)

        arm_label = (
            f"arm_id={arm_key}" if arm_key != "__single__" else "arm"
        )
        n_picks = len(arm_picks[arm_key])

        if zero_joints and not nonzero_joints:
            # All motors have cmds.rx == 0 — full mismatch (Critical)
            issues.append(
                {
                    "severity": "critical",
                    "category": "coordination",
                    "title": (
                        f"Motor controller received 0 commands during active picking"
                        f" ({arm_label})"
                    ),
                    "description": (
                        f"All {total} motor(s) report cmds.rx=0 while {n_picks} pick(s)"
                        f" with "
                        f"real joint motion occurred — likely publisher/subscriber topic"
                        f" mismatch"
                        f" (see commit 9b35007)"
                    ),
                    "node": "arm_control",
                    "timestamp": arm_picks[arm_key][0].get("_ts") or 0,
                    "message": (
                        "Motor controller received 0 commands while arm was actively"
                        " picking"
                        " — likely publisher/subscriber topic mismatch"
                        " (see commit 9b35007)"
                    ),
                    "recommendation": (
                        "Verify motor command topic is published; check ROS2 topic name "
                        "matches subscriber"
                    ),
                    "arm_id": arm_key if arm_key != "__single__" else None,
                }
            )
        elif zero_joints and nonzero_joints:
            # Partial mismatch (High)
            n_zero = len(zero_joints)
            issues.append(
                {
                    "severity": "high",
                    "category": "coordination",
                    "title": f"Partial motor command mismatch ({arm_label})",
                    "description": (
                        f"Partial motor command mismatch — {n_zero} of {total} motors "
                        f"received 0 commands while others were active: "
                        f"zero={zero_joints}, active={nonzero_joints}"
                    ),
                    "node": "arm_control",
                    "timestamp": arm_picks[arm_key][0].get("_ts") or 0,
                    "message": (
                        f"Partial motor command mismatch — {n_zero} of {total} motors "
                        f"received 0 commands while others were active"
                    ),
                    "recommendation": (
                        "Check joint-specific motor command topic mapping; some joints "
                        "may have incorrect subscriber configuration"
                    ),
                    "arm_id": arm_key if arm_key != "__single__" else None,
                }
            )
        # else: all motors have cmds.rx > 0 — healthy, no issue

    return issues


# ---------------------------------------------------------------------------
# Group 12 — Cross-correlation: picks ↔ vehicle state
# ---------------------------------------------------------------------------

# States that indicate the vehicle is moving / not stationary
_VEHICLE_MOTION_STATES = {
    "BUSY",
    "MANUAL_MODE",
    "MANUAL_LEFT",
    "MANUAL_RIGHT",
    "NONBRAKE_MANUAL",
}


def correlate_picks_with_vehicle_state(analyzer: "ROS2LogAnalyzer") -> None:
    """tasks 12.1-12.4 — for each pick, determine vehicle state at that time."""
    events = analyzer.events

    picks_during_motion = 0

    # Build sorted state timeline: list of (timestamp, state_name)
    state_timeline: List = []
    if events.state_transitions:
        for st in events.state_transitions:
            ts = st.get("_ts")
            if ts is not None:
                state_timeline.append((ts, st.get("to_state") or "UNKNOWN"))
        state_timeline.sort(key=lambda x: x[0])

    def _state_at(ts: float) -> str:
        """Return the vehicle state active at timestamp ts."""
        current = "UNKNOWN"
        for t, s in state_timeline:
            if t <= ts:
                current = s
            else:
                break
        return current

    # Build drive windows from drive_commands for overlap detection (task 12.2 fallback)
    drive_windows: List = []
    for dc in events.drive_commands:
        dc_ts = dc.get("_ts")
        if dc_ts is not None:
            dur_ms = dc.get("total_ms") or dc.get("duration_ms") or 0
            end_ts = dc_ts + dur_ms / 1000.0
            drive_windows.append((dc_ts, end_ts))

    # task 12.4 — success rate per vehicle state
    state_pick_stats: dict = {}

    for pick in events.picks:
        ts = pick.get("_ts")
        if ts is None:
            continue

        state = _state_at(ts)
        pick["_vehicle_state_at_pick"] = state

        # task 12.2 — detect picks during vehicle motion (state-based)
        in_motion_state = state in _VEHICLE_MOTION_STATES

        # Also detect via drive_command time window (when no state_transitions present)
        in_drive_window = any(start <= ts <= end for start, end in drive_windows)

        if in_motion_state or in_drive_window:
            picks_during_motion += 1
            if in_motion_state:
                reason = f"vehicle was in state {state}"
            else:
                reason = "vehicle had active drive_command"
            analyzer._add_issue(
                severity="medium",
                category="coordination",
                title=f"Pick attempted during vehicle motion",
                description=(
                    f"pick_complete at ts={ts:.1f} — {reason}"
                ),
                node=pick.get("_node") or "motion_controller",
                timestamp=ts,
                message=f"pick_complete while vehicle_motion ({reason})",
                recommendation=(
                    "Review arm-vehicle coordination; ensure vehicle is stationary before"
                    " picking"
                ),
            )

        # task 12.4 — aggregate success rate
        s_stats = state_pick_stats.setdefault(state, {"total": 0, "success": 0})
        s_stats["total"] += 1
        if pick.get("success"):
            s_stats["success"] += 1

    # Store aggregated stats on events for reports
    events._pick_success_by_state = state_pick_stats
    events._picks_during_motion = picks_during_motion

    # task 12.3 — vehicle-stop-to-pick latency from arm_coordination
    stop_latencies = [
        ac.get("vehicle_stop_ms")
        for ac in events.arm_coordination
        if ac.get("vehicle_stop_ms") is not None
    ]
    if stop_latencies:
        avg_stop = sum(stop_latencies) / len(stop_latencies)
        if avg_stop > 2000:
            analyzer._add_issue(
                severity="medium",
                category="coordination",
                title=f"Slow vehicle stop latency: avg {avg_stop:.0f}ms",
                description=(
                    f"Average vehicle stop latency is {avg_stop:.0f}ms across "
                    f"{len(stop_latencies)} arm coordination events"
                ),
                node="vehicle_control",
                timestamp=events.arm_coordination[0].get("_ts") or 0,
                message=f"arm_coordination vehicle_stop_ms avg={avg_stop:.0f}",
                recommendation="Tune vehicle brake control for faster stops before arm pick",
            )


# ---------------------------------------------------------------------------
# Task 4.1 — Main entry point for cross-log correlation
# ---------------------------------------------------------------------------


def detect_cross_log_correlations(
    analyzer: "ROS2LogAnalyzer",
) -> List[dict]:
    """Post-parse pass: detect causal chains across log sources.

    Called after all files are parsed and all events are in EventStore.
    Returns a list of issue dicts for the caller to add via _add_issue().
    """
    issues: List[dict] = []
    issues.extend(_detect_mqtt_failure_process_death(analyzer))
    issues.extend(_detect_zero_detection_fallback(analyzer))
    issues.extend(_detect_zero_capture_time(analyzer))
    issues.extend(_detect_disconnected_operation(analyzer))
    return issues


# ---------------------------------------------------------------------------
# Task 4.2 — MQTT failure → process death chain
# ---------------------------------------------------------------------------


def _detect_mqtt_failure_process_death(
    analyzer: "ROS2LogAnalyzer",
) -> List[dict]:
    """MQTT timeout/disconnect followed by launch.log exit code 1."""
    issues: List[dict] = []
    events = analyzer.events

    # Collect MQTT failure events (timeout or disconnect)
    mqtt_failures = [
        ev
        for ev in events.arm_client_mqtt_events
        if ev.get("event_type") in ("mqtt_timeout", "mqtt_disconnect")
    ]
    if not mqtt_failures:
        return issues

    # Collect launch crash events with exit_code == 1
    crash_events = [
        ev
        for ev in events.launch_events
        if ev.get("type") == "crash" and ev.get("exit_code") == 1
    ]
    if not crash_events:
        return issues

    # For each MQTT failure, look for a crash within the window
    for mf in mqtt_failures:
        ts1 = mf.get("timestamp")
        if ts1 is None:
            continue
        event_type = mf.get("event_type", "mqtt_failure")
        arm_id = mf.get("arm_id")

        for crash in crash_events:
            ts2 = crash.get("crash_ts")
            if ts2 is None:
                continue
            delta = ts2 - ts1
            if 0 <= delta <= CORRELATION_WINDOW_S:
                issues.append({
                    "severity": "high",
                    "category": "CORRELATION",
                    "title": (
                        "MQTT timeout/disconnect caused process exit"
                    ),
                    "description": (
                        f"MQTT {event_type} at {ts1} followed by "
                        f"process exit (code 1) at {ts2} "
                        f"(delta={delta:.1f}s)"
                    ),
                    "recommendation": (
                        "Check MQTT broker availability and "
                        "network connectivity"
                    ),
                    "arm_id": arm_id,
                    "timestamp": ts1,
                })
                break  # one chain per MQTT failure

    return issues


# ---------------------------------------------------------------------------
# Task 4.3 — 0% detection rate + fallback positions → model/config issue
# ---------------------------------------------------------------------------


def _detect_zero_detection_fallback(
    analyzer: "ROS2LogAnalyzer",
) -> List[dict]:
    """Detection pipeline producing zero results while fallback active."""
    issues: List[dict] = []
    events = analyzer.events

    detection_summaries = events.detection_summaries
    fallback_count = getattr(events, "_fallback_position_count", 0)

    if not detection_summaries or fallback_count <= 0:
        return issues

    # Check if ALL summaries show 0% acceptance rate
    all_zero = all(
        (ds.get("requests_detection_rate_pct") or 0) == 0
        for ds in detection_summaries
    )
    if not all_zero:
        # Also check aggregate detection_frames_summary
        fs = events.detection_frames_summary
        all_zero = (
            fs.get("count", 0) > 0
            and fs.get("accepted_count", 0) == 0
        )

    if not all_zero:
        return issues

    # Count total detection attempts from summaries
    count = 0
    for ds in detection_summaries:
        total = ds.get("requests_total")
        if total is not None:
            count += total
    if count == 0:
        count = events.detection_frames_summary.get("count", 0)

    # Determine arm_id from first summary
    arm_id = detection_summaries[0].get("arm_id")

    issues.append({
        "severity": "medium",
        "category": "CORRELATION",
        "title": (
            "Detection pipeline producing zero results "
            "- fallback mode active"
        ),
        "description": (
            f"Detection acceptance rate 0% with {count} "
            f"detection attempts. All picks using "
            f"fallback positions."
        ),
        "recommendation": (
            "Check model file (yolov112.blob), camera feed "
            "quality, and detection thresholds"
        ),
                "arm_id": arm_id,
                "timestamp": 0,
            })

    return issues


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
from .registry import register as _register

_register(
    "correlate_motor_commands_with_picking", correlate_motor_commands_with_picking,
    category="analysis",
    description="Cross-reference motor commands against actual pick events.",
)
_register(
    "correlate_picks_with_vehicle_state", correlate_picks_with_vehicle_state,
    category="analysis",
    description="Correlate pick timing with vehicle state for coordination issues.",
)
_register(
    "detect_cross_log_correlations", detect_cross_log_correlations,
    category="analysis",
    description="Detect multi-source correlations (MQTT failure, zero detection, etc.).",
)


# ---------------------------------------------------------------------------
# Task 4.4 — capture_time=0ms hardware issue
# ---------------------------------------------------------------------------


def _detect_zero_capture_time(
    analyzer: "ROS2LogAnalyzer",
) -> List[dict]:
    """Flag when >20% of picks have capture_ms=0 (compressor issue)."""
    issues: List[dict] = []
    events = analyzer.events

    picks = events.picks
    if not picks:
        return issues

    # Group picks by arm_id
    arm_picks: Dict[str, List[dict]] = {}
    for p in picks:
        arm_key = p.get("arm_id") or "__single__"
        arm_picks.setdefault(arm_key, []).append(p)

    for arm_key, arm_pick_list in arm_picks.items():
        total = len(arm_pick_list)
        if total == 0:
            continue

        zero_capture = sum(
            1
            for p in arm_pick_list
            if p.get("capture_ms") is not None
            and p["capture_ms"] == 0
        )
        if zero_capture == 0:
            continue

        pct = (zero_capture / total) * 100.0
        if pct > 20.0:
            arm_id = (
                arm_key if arm_key != "__single__" else None
            )
            issues.append({
                "severity": "high",
                "category": "CORRELATION",
                "title": (
                    "Compressor/vacuum hardware issue "
                    "- zero capture time"
                ),
                "description": (
                    f"{zero_capture}/{total} picks "
                    f"({pct:.0f}%) had zero capture time"
                ),
                "recommendation": (
                    "Check compressor, vacuum system, "
                    "and seal integrity"
                ),
                "arm_id": arm_id,
                "timestamp": 0,
            })

    return issues


# ---------------------------------------------------------------------------
# Task 4.5 — Disconnected operation detection
# ---------------------------------------------------------------------------


def _detect_disconnected_operation(
    analyzer: "ROS2LogAnalyzer",
) -> List[dict]:
    """Detect arms with picks but no MQTT or vehicle coordination."""
    issues: List[dict] = []
    events = analyzer.events

    picks = events.picks
    if not picks:
        return issues

    # Group picks by arm_id
    arm_picks: Dict[str, List[dict]] = {}
    for p in picks:
        arm_key = p.get("arm_id") or "__single__"
        arm_picks.setdefault(arm_key, []).append(p)

    # Collect arm_ids that have MQTT activity
    mqtt_arm_ids: set = set()
    for ev in events.arm_client_mqtt_events:
        aid = ev.get("arm_id")
        if aid is not None:
            mqtt_arm_ids.add(aid)

    # Check if vehicle-side logs exist (state_transitions or
    # drive_commands indicate vehicle coordination)
    has_vehicle_logs = bool(
        events.state_transitions or events.drive_commands
    )

    for arm_key, arm_pick_list in arm_picks.items():
        count = len(arm_pick_list)
        if count == 0:
            continue

        arm_id = (
            arm_key if arm_key != "__single__" else None
        )

        # Check if this arm has any MQTT events
        has_mqtt = arm_key in mqtt_arm_ids

        if not has_mqtt and not has_vehicle_logs:
            display_id = arm_id if arm_id else "arm"
            issues.append({
                "severity": "info",
                "category": "CORRELATION",
                "title": (
                    "Arm operating in disconnected mode"
                ),
                "description": (
                    f"{display_id} completed {count} picks "
                    f"with no MQTT connectivity or "
                    f"vehicle coordination"
                ),
                "arm_id": arm_id,
                "timestamp": 0,
            })

    return issues
