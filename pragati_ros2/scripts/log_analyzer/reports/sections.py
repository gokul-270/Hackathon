"""
Field summary section builders — all _section_* functions.

Each function populates one section of the FieldSummary dataclass.
"""

from __future__ import annotations

import statistics as _statistics
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from ._helpers import (
    MG6010_ERROR_FLAGS,
    _group_by_arm,
    _hour_bucket,
    _is_multi_arm,
    _safe_pct,
    _stats,
    decode_error_flags,
)

if TYPE_CHECKING:
    from ..analyzer import ROS2LogAnalyzer
    from ..models import EventStore, FieldSummary


# ---------------------------------------------------------------------------
# task 16.3 — Pick performance
# ---------------------------------------------------------------------------


def _pick_stats_for(picks: list, session_duration_s: float) -> dict:
    """Compute pick performance stats for a subset of picks (one arm or all)."""
    total = len(picks)
    succeeded = sum(1 for p in picks if p.get("success"))
    failed = total - succeeded

    total_times = [p["total_ms"] for p in picks if "total_ms" in p]
    approach_times = [p["approach_ms"] for p in picks if "approach_ms" in p]
    capture_times = [p["capture_ms"] for p in picks if "capture_ms" in p]
    retreat_times = [p["retreat_ms"] for p in picks if "retreat_ms" in p]
    detection_ages = [
        p["detection_age_ms"]
        for p in picks
        if "detection_age_ms" in p and p["detection_age_ms"] is not None
    ]

    picks_per_hour = (
        round(3600.0 * total / session_duration_s, 1) if session_duration_s > 0 else 0.0
    )

    # EE on-time: mean ee_on_ms per pick for this arm (task 4.3 — not session-level duty cycle)
    ee_on_ms_vals = [p["ee_on_ms"] for p in picks if p.get("ee_on_ms") is not None]
    mean_ee_on_ms: Optional[float] = None
    if ee_on_ms_vals:
        mean_ee_on_ms = round(sum(ee_on_ms_vals) / len(ee_on_ms_vals), 1)

    return {
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "success_rate_pct": _safe_pct(succeeded, total),
        "picks_per_hour": picks_per_hour,
        "cycle_time_ms": _stats(total_times),
        "phase_breakdown": {
            "approach_ms": _stats(approach_times),
            "capture_ms": _stats(capture_times),
            "retreat_ms": _stats(retreat_times),
        },
        "detection_age_ms": _stats(detection_ages),
        "mean_ee_on_ms_per_pick": mean_ee_on_ms,
    }


def _section_pick_performance(
    analyzer: "ROS2LogAnalyzer",
    summary: "FieldSummary",
    session_start: float,
    session_duration_s: float,
) -> None:
    picks = analyzer.events.picks
    total = len(picks)
    succeeded = sum(1 for p in picks if p.get("success"))
    failed = total - succeeded

    total_times = [p["total_ms"] for p in picks if "total_ms" in p]
    approach_times = [p["approach_ms"] for p in picks if "approach_ms" in p]
    capture_times = [p["capture_ms"] for p in picks if "capture_ms" in p]
    retreat_times = [p["retreat_ms"] for p in picks if "retreat_ms" in p]
    detection_ages = [
        p["detection_age_ms"]
        for p in picks
        if "detection_age_ms" in p and p["detection_age_ms"] is not None
    ]

    picks_per_hour = (
        round(3600.0 * total / session_duration_s, 1) if session_duration_s > 0 else 0.0
    )

    # task 20.3 — FP proxy (accepted detections that did NOT lead to successful pick per cycle)
    df_summary = analyzer.events.detection_frames_summary
    accepted_total = df_summary.get("accepted_count", 0)
    fp_proxy: Optional[float] = None
    fp_note = ""
    if accepted_total > 0 and total > 0:
        wasted = max(0, accepted_total - succeeded)
        fp_proxy = _safe_pct(wasted, accepted_total)
        fp_note = (
            f"{wasted}/{accepted_total} accepted detections " f"did not lead to a successful pick"
        )

    # task 20.4 — ArUco gap reporting
    aruco_count = analyzer.events.aruco_mention_count

    # task 20.5 — EE duty cycle (session-level, for single-arm only)
    ee_on_ms_total = sum(p.get("ee_on_ms") or 0 for p in picks)
    ee_duty_pct: Optional[float] = None
    if session_duration_s > 0 and ee_on_ms_total > 0:
        ee_duty_pct = round(100.0 * (ee_on_ms_total / 1000.0) / session_duration_s, 1)

    # task 20.6 — Position tracking
    positions_seen: Dict[str, int] = defaultdict(int)
    for p in picks:
        pos = p.get("position")
        if pos and isinstance(pos, dict):
            key = f"({pos.get('x', 0):.2f}," f"{pos.get('y', 0):.2f}," f"{pos.get('z', 0):.2f})"
            positions_seen[key] += 1

    # task 14.5 — EE short retract: check if 100% of retreats are near-zero
    ee_short_retract_events = getattr(analyzer.events, "ee_short_retract_events", [])
    ee_short_retract_note = ""
    if ee_short_retract_events:
        zero_count = sum(1 for e in ee_short_retract_events if e.get("retract_mm", 1) == 0)
        if zero_count == len(ee_short_retract_events):
            ee_short_retract_note = (
                "EE retract distance: all picks had near-zero retract" " — J5 may not be extending"
            )

    # task 15.2 — stale detection age stats
    stale_detection_pct: Optional[float] = None
    severely_stale_count = 0
    if detection_ages:
        stale_count = sum(1 for a in detection_ages if a > 2000)
        stale_detection_pct = round(100.0 * stale_count / len(detection_ages), 1)
        severely_stale_count = sum(1 for a in detection_ages if a > 10000)

    # tasks 4.1-4.4 — per-arm grouping
    arm_groups = _group_by_arm(picks)
    multi_arm = _is_multi_arm(arm_groups)

    per_arm: Dict[str, dict] = {}
    arm_summary_table: List[dict] = []
    worst_arm: Optional[str] = None
    if multi_arm:
        worst_rate = 101.0  # find lowest success rate
        for arm_id, arm_picks in sorted(arm_groups.items(), key=lambda x: str(x[0])):
            arm_stats = _pick_stats_for(arm_picks, session_duration_s)
            per_arm[str(arm_id)] = arm_stats
            arm_summary_table.append(
                {
                    "arm": str(arm_id),
                    "total": arm_stats["total"],
                    "succeeded": arm_stats["succeeded"],
                    "failed": arm_stats["failed"],
                    "success_rate_pct": arm_stats["success_rate_pct"],
                    "avg_cycle_time_ms": arm_stats["cycle_time_ms"].get("avg"),
                }
            )
            if arm_stats["success_rate_pct"] < worst_rate:
                worst_rate = arm_stats["success_rate_pct"]
                worst_arm = str(arm_id)

    summary.pick_performance = {
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "success_rate_pct": _safe_pct(succeeded, total),
        "picks_per_hour": picks_per_hour,
        "cycle_time_ms": _stats(total_times),
        "phase_breakdown": {
            "approach_ms": _stats(approach_times),
            "capture_ms": _stats(capture_times),
            "retreat_ms": _stats(retreat_times),
        },
        "detection_age_ms": _stats(detection_ages),
        "stale_detection_pct": stale_detection_pct,
        "severely_stale_count": severely_stale_count,
        "ee_short_retract_note": ee_short_retract_note,
        "estimated_wasted_detections_pct": fp_proxy,
        "estimated_wasted_detections_note": fp_note if fp_proxy is not None else "",
        "aruco_mentions": aruco_count if aruco_count else "not instrumented",
        "ee_duty_cycle_pct": ee_duty_pct,
        "position_tracking": (dict(positions_seen) if positions_seen else "not instrumented"),
        # multi-arm additions (tasks 4.1-4.3)
        "multi_arm": multi_arm,
        "arm_summary_table": arm_summary_table,
        "worst_arm": worst_arm,
        "per_arm": per_arm,
    }


# ---------------------------------------------------------------------------
# task 13.6 — Launch process health
# ---------------------------------------------------------------------------


def _section_launch_health(
    analyzer: "ROS2LogAnalyzer",
    summary: "FieldSummary",
) -> None:
    """Render LAUNCH HEALTH section from EventStore.launch_events.

    task 13.6 — If launch_events is empty, skip entirely.
    """
    events = analyzer.events.launch_events
    if not events:
        return

    # Extract session timing from first event metadata
    first_ts = events[0].get("_session_first_ts")
    last_ts = events[0].get("_session_last_ts")
    session_dur_s = (last_ts - first_ts) if (first_ts and last_ts) else None

    # Collect per-process info
    # Build a dict keyed by (name, pid) — last entry wins for duplicates
    process_map: Dict = {}
    for ev in events:
        ev_type = ev.get("type")
        if ev_type == "start":
            key = (ev.get("name"), ev.get("pid"))
            process_map.setdefault(key, {}).update(
                {
                    "name": ev.get("name"),
                    "pid": ev.get("pid"),
                    "start_ts": ev.get("start_ts"),
                    "cmd": ev.get("cmd"),
                    "status": "still_running",
                    "exit_code": None,
                    "lifetime_s": None,
                    "external_log_hint": None,
                    "has_ros2_log": True,
                }
            )
        elif ev_type == "crash":
            key = (ev.get("name"), ev.get("pid"))
            info = process_map.setdefault(key, {})
            info.update(
                {
                    "name": ev.get("name"),
                    "pid": ev.get("pid"),
                    "start_ts": ev.get("start_ts"),
                    "cmd": ev.get("cmd"),
                    "status": "crashed",
                    "exit_code": ev.get("exit_code"),
                    "lifetime_s": ev.get("lifetime_s"),
                    "external_log_hint": ev.get("external_log_hint"),
                    "has_ros2_log": ev.get("has_ros2_log", True),
                    "crash_ts": ev.get("crash_ts"),
                }
            )
        elif ev_type == "still_running":
            key = (ev.get("name"), ev.get("pid"))
            process_map.setdefault(key, {}).update(
                {
                    "name": ev.get("name"),
                    "pid": ev.get("pid"),
                    "start_ts": ev.get("start_ts"),
                    "cmd": ev.get("cmd"),
                    "status": "still_running",
                    "exit_code": None,
                    "lifetime_s": None,
                    "external_log_hint": None,
                    "has_ros2_log": True,
                }
            )

    # Sort: crashed first, then still_running, then by name
    def _sort_key(item: Any) -> tuple:
        _, info = item
        return (
            0 if info.get("status") == "crashed" else 1,
            info.get("name", ""),
        )

    processes = sorted(process_map.items(), key=_sort_key)

    # Build summary data
    section: Dict = {
        "has_data": True,
        "session_duration_s": session_dur_s,
        "processes": [info for _, info in processes],
    }
    summary.launch_health = section


# ---------------------------------------------------------------------------
# task 16.4 — Vehicle performance
# ---------------------------------------------------------------------------


def _section_vehicle_performance(
    analyzer: "ROS2LogAnalyzer",
    summary: "FieldSummary",
    session_start: float,
) -> None:
    drive_cmds = analyzer.events.drive_commands
    steer_cmds = analyzer.events.steering_commands
    cmd_vels = analyzer.events.cmd_vel

    total_dist_mm = sum(dc.get("distance_mm") or 0 for dc in drive_cmds)
    drive_durations = [dc["duration_ms"] for dc in drive_cmds if "duration_ms" in dc]
    position_reached_rate = _safe_pct(
        sum(1 for dc in drive_cmds if dc.get("position_reached")),
        len(drive_cmds),
    )

    steer_success_rates = []
    for sc in steer_cmds:
        mc = sc.get("motor_count") or 0
        ss = sc.get("success_count") or 0
        if mc > 0:
            steer_success_rates.append(100.0 * ss / mc)

    cmd_vel_total = [c["total_ms"] for c in cmd_vels if "total_ms" in c]
    cmd_vel_steering = [c["steering_ms"] for c in cmd_vels if "steering_ms" in c]
    cmd_vel_drive = [c["drive_ms"] for c in cmd_vels if "drive_ms" in c]

    # time-in-state from detectors (stored as dynamic attribute)
    state_time = getattr(analyzer.events, "_state_time_s", {})

    summary.vehicle_performance = {
        "drive_commands": len(drive_cmds),
        "total_distance_m": round(total_dist_mm / 1000.0, 2),
        "drive_duration_ms": _stats(drive_durations),
        "position_reached_rate_pct": position_reached_rate,
        "steering_commands": len(steer_cmds),
        "steering_success_rate_pct": _stats(steer_success_rates),
        "cmd_vel_count": len(cmd_vels),
        "cmd_vel_latency_ms": _stats(cmd_vel_total),
        "cmd_vel_steering_ms": _stats(cmd_vel_steering),
        "cmd_vel_drive_ms": _stats(cmd_vel_drive),
        "time_in_state_s": state_time,
    }


# ---------------------------------------------------------------------------
# task 16.5 — Motor health trends
# ---------------------------------------------------------------------------


def _compute_arm_motor_summary(motor_health_events: list) -> Dict[str, Any]:
    """Compute per-joint arm motor stats from a list of motor_health events."""
    arm_joint_data: Dict[str, dict] = defaultdict(lambda: defaultdict(list))
    for mh in motor_health_events:
        for m in mh.get("motors") or []:
            joint = str(m.get("joint") or m.get("id") or "?")
            for field_name in (
                "temp_c",
                "voltage_v",
                "current_a",
                "health",
            ):
                val = m.get(field_name)
                if val is not None:
                    arm_joint_data[joint][field_name].append(val)
            err = m.get("err_flags") or 0
            arm_joint_data[joint]["err_flags"].append(err)
            arm_joint_data[joint]["err_decoded"] = decode_error_flags(err)

    arm_summary: Dict[str, Any] = {}
    for joint, fields in arm_joint_data.items():
        arm_summary[joint] = {
            k: (_stats(v) if k not in ("err_decoded",) else v) for k, v in fields.items()
        }
    return arm_summary


def _section_motor_health(
    analyzer: "ROS2LogAnalyzer",
    summary: "FieldSummary",
) -> None:
    # tasks 5.1-5.3 — per-arm grouping for arm-side motor health
    arm_groups = _group_by_arm(analyzer.events.motor_health_arm)
    multi_arm = _is_multi_arm(arm_groups)

    if multi_arm:
        # task 5.2 — per-arm sub-sections, never pool joints across arms
        per_arm_motor: Dict[str, Any] = {}
        for arm_id, arm_events in sorted(arm_groups.items(), key=lambda x: str(x[0])):
            per_arm_motor[str(arm_id)] = _compute_arm_motor_summary(arm_events)
        arm_summary = per_arm_motor
    else:
        # task 5.3 — single-arm: compute as before (flat joint dict)
        all_events = [e for evts in arm_groups.values() for e in evts]
        arm_summary = _compute_arm_motor_summary(all_events)

    # task 6.1 — vehicle motor data stays in motor_health_trends.vehicle
    #            (extracted to its own section in task 6.1-6.2)
    vehicle_motor_data: Dict[str, list] = defaultdict(list)
    for mh in analyzer.events.motor_health_vehicle:
        score = mh.get("health_score")
        if score is not None:
            vehicle_motor_data["health_score"].append(score)
        for m in mh.get("motors") or []:
            mid = str(m.get("motor_id") or m.get("id") or "?")
            ec = m.get("error_count") or 0
            vehicle_motor_data[f"motor_{mid}_errors"].append(ec)
            ss = m.get("stale_s") or 0
            vehicle_motor_data[f"motor_{mid}_stale_s"].append(ss)

    vehicle_summary = {k: _stats(v) for k, v in vehicle_motor_data.items()}

    summary.motor_health_trends = {
        "vehicle": vehicle_summary,
        "arm": arm_summary,
        "multi_arm": multi_arm,  # flag for print_field_summary to branch on
    }


def _section_vehicle_motor_health(
    analyzer: "ROS2LogAnalyzer",
    summary: "FieldSummary",
) -> None:
    """task 6.1 — Vehicle motor health as a distinct section."""
    if not analyzer.events.motor_health_vehicle:
        return

    vehicle_motor_data: Dict[str, list] = defaultdict(list)
    enable_latencies: list = []
    for mh in analyzer.events.motor_health_vehicle:
        score = mh.get("health_score")
        if score is not None:
            vehicle_motor_data["health_score"].append(score)
        for m in mh.get("motors") or []:
            mid = str(m.get("motor_id") or m.get("id") or "?")
            ec = m.get("error_count") or 0
            vehicle_motor_data[f"motor_{mid}_errors"].append(ec)
            ss = m.get("stale_s") or 0
            vehicle_motor_data[f"motor_{mid}_stale_s"].append(ss)
        lat = mh.get("enable_latency_ms")
        if lat is not None:
            enable_latencies.append(lat)

    # Store vehicle motor health in a dedicated summary field
    summary.motor_health_trends["vehicle_detail"] = {
        "health_score": _stats(vehicle_motor_data.get("health_score", [])),
        "per_motor": {k: _stats(v) for k, v in vehicle_motor_data.items() if k != "health_score"},
        "enable_latency_ms": _stats(enable_latencies),
        "has_data": True,
    }


# ---------------------------------------------------------------------------
# task 16.6 — Startup / shutdown
# ---------------------------------------------------------------------------


def _section_startup_shutdown(
    analyzer: "ROS2LogAnalyzer",
    summary: "FieldSummary",
) -> None:
    startups = analyzer.events.startup
    shutdowns = analyzer.events.shutdown

    def _flat_stats(events_list: list, keys: List[str]) -> dict:
        result = {}
        for key in keys:
            vals = [e[key] for e in events_list if key in e and e[key] is not None]
            result[key] = _stats(vals)
        return result

    startup_keys = [
        "total_ms",
        "hardware_init_ms",
        "motor_controller_init_ms",
        "joystick_init_ms",
        "service_client_ms",
        "self_test_ms",
    ]
    shutdown_keys = [
        "total_ms",
        "subprocess_cleanup_ms",
        "thread_join_ms",
        "motor_shutdown_ms",
    ]

    timeout_count = sum(1 for s in shutdowns if s.get("thread_join_timeout"))

    summary.startup_shutdown = {
        "restart_count": max(0, len(startups) - 1),
        "startup": _flat_stats(startups, startup_keys),
        "shutdown": _flat_stats(shutdowns, shutdown_keys),
        "thread_join_timeouts": timeout_count,
    }


# ---------------------------------------------------------------------------
# task 16.7 — Coordination
# ---------------------------------------------------------------------------


def _section_coordination(
    analyzer: "ROS2LogAnalyzer",
    summary: "FieldSummary",
) -> None:
    coords = analyzer.events.arm_coordination
    stop_ms = [c["vehicle_stop_ms"] for c in coords if "vehicle_stop_ms" in c]
    arm_ms = [c["arm_phase_ms"] for c in coords if "arm_phase_ms" in c]
    total_ms = [c["total_cycle_ms"] for c in coords if "total_cycle_ms" in c]

    pick_by_state = getattr(analyzer.events, "_pick_success_by_state", {})
    picks_during_motion = getattr(analyzer.events, "_picks_during_motion", 0)
    # _picks_during_motion is stored as an int count; support list form
    if isinstance(picks_during_motion, list):
        picks_during_motion_count = len(picks_during_motion)
    else:
        picks_during_motion_count = int(picks_during_motion)

    summary.coordination = {
        "coordination_cycles": len(coords),
        "vehicle_stop_ms": _stats(stop_ms),
        "arm_phase_ms": _stats(arm_ms),
        "total_cycle_ms": _stats(total_ms),
        "pick_success_by_vehicle_state": pick_by_state,
        "picks_during_vehicle_motion": picks_during_motion_count,
    }


# ---------------------------------------------------------------------------
# task 16.8 — Network health
# ---------------------------------------------------------------------------


def _section_network(
    analyzer: "ROS2LogAnalyzer",
    summary: "FieldSummary",
) -> None:
    net = analyzer.network

    router_latencies = [v for _, v in net.ping_router]
    broker_latencies = [v for _, v in net.ping_broker]
    cpu_temps = [v for _, v in net.cpu_temp]
    loads = [v for _, v in net.load_avg]

    total_router = len(router_latencies) + net.ping_router_timeouts
    total_broker = len(broker_latencies) + net.ping_broker_timeouts
    router_loss_pct = _safe_pct(net.ping_router_timeouts, total_router)
    broker_loss_pct = _safe_pct(net.ping_broker_timeouts, total_broker)

    # Count eth errors (total across all samples)
    rx_errors_total = sum(v for _, v in net.eth_rx_errors)
    tx_errors_total = sum(v for _, v in net.eth_tx_errors)
    drops_total = sum(v for _, v in net.eth_drops)
    link_changes = len(net.eth_state_changes)

    summary.network_health = {
        "ping_router_ms": _stats(router_latencies),
        "ping_router_loss_pct": router_loss_pct,
        "ping_broker_ms": _stats(broker_latencies),
        "ping_broker_loss_pct": broker_loss_pct,
        "eth_rx_errors": rx_errors_total,
        "eth_tx_errors": tx_errors_total,
        "eth_drops": drops_total,
        "eth_link_changes": link_changes,
        "cpu_temp_c": _stats(cpu_temps),
        "load_avg": _stats(loads),
    }


# ---------------------------------------------------------------------------
# task 16.9 — Hourly throughput
# ---------------------------------------------------------------------------


def _section_hourly_throughput(
    analyzer: "ROS2LogAnalyzer",
    summary: "FieldSummary",
    session_start: float,
) -> None:
    if not session_start:
        return

    picks = analyzer.events.picks

    def _build_buckets(pick_list: list) -> list:
        buckets: Dict[int, Dict[str, Any]] = defaultdict(
            lambda: {
                "hour": 0,
                "picks_total": 0,
                "picks_succeeded": 0,
                "cycle_times_ms": [],
            }
        )
        for p in pick_list:
            h = _hour_bucket(p.get("_ts"), session_start)
            buckets[h]["hour"] = h
            buckets[h]["picks_total"] += 1
            if p.get("success"):
                buckets[h]["picks_succeeded"] += 1
            t = p.get("total_ms")
            if t is not None:
                buckets[h]["cycle_times_ms"].append(t)
        result = []
        for h in sorted(buckets):
            b = buckets[h]
            times = b.pop("cycle_times_ms")
            b["avg_cycle_time_ms"] = round(sum(times) / len(times), 1) if times else None
            b["success_rate_pct"] = _safe_pct(b["picks_succeeded"], b["picks_total"])
            result.append(b)
        return result

    # task 7.4 — per-arm tables when multi-arm
    arm_groups = _group_by_arm(picks)
    multi_arm = _is_multi_arm(arm_groups)

    overall = _build_buckets(picks)

    per_arm_hourly: Dict[str, list] = {}
    if multi_arm:
        for arm_id, arm_picks in sorted(arm_groups.items(), key=lambda x: str(x[0])):
            per_arm_hourly[str(arm_id)] = _build_buckets(arm_picks)

    summary.hourly_throughput = overall
    # store per-arm for print section
    summary._hourly_throughput_per_arm = per_arm_hourly


# ---------------------------------------------------------------------------
# Session health section
# ---------------------------------------------------------------------------


def _section_session_health(
    analyzer: "ROS2LogAnalyzer",
    summary: "FieldSummary",
    session_duration_s: float,
) -> None:
    gaps = getattr(analyzer.events, "_timestamp_gaps", [])
    jumps = getattr(analyzer.events, "_clock_jumps", [])
    manual = getattr(
        analyzer.events,
        "_manual_interventions",
        {"count": 0, "total_s": 0.0},
    )
    restarts = max(0, len(analyzer.events.startup) - 1)

    # task 15.2 — compute operational duration from ROS2 source window
    source_ranges = getattr(analyzer, "_source_category_ranges", {})
    ros2_range = source_ranges.get("ros2")
    if ros2_range:
        operational_duration_s = ros2_range[1] - ros2_range[0]
        operational_start = ros2_range[0]
        operational_end = ros2_range[1]
    else:
        operational_duration_s = session_duration_s
        operational_start = analyzer.start_time
        operational_end = analyzer.end_time

    # Build source_durations dict for the report
    source_durations: dict = {}
    for cat, (lo, hi) in source_ranges.items():
        source_durations[cat] = {"start": lo, "end": hi}

    summary.session_health = {
        "session_duration_s": round(session_duration_s, 1),
        "operational_duration_s": round(operational_duration_s, 1),
        "operational_start": operational_start,
        "operational_end": operational_end,
        "source_durations": source_durations,
        "restarts": restarts,
        "log_gaps": len(gaps),
        "largest_gap_s": round(max((g for _, _, g in gaps), default=0.0), 1),
        "clock_jumps": len(jumps),
        "manual_interventions": manual["count"],
        "manual_duration_s": round(manual["total_s"], 1),
    }


# ---------------------------------------------------------------------------
# Failure chains section (from detectors, stored on events)
# ---------------------------------------------------------------------------


def _section_failure_chains(
    analyzer: "ROS2LogAnalyzer",
    summary: "FieldSummary",
) -> None:
    chains = getattr(analyzer.events, "_failure_chains", [])
    summary.failure_chains = chains


# ---------------------------------------------------------------------------
# Group 24 — Arm-side additions
# ---------------------------------------------------------------------------


# task 24.1 — Pick failure analysis
def _section_pick_failure_analysis(
    analyzer: "ROS2LogAnalyzer",
    summary: "FieldSummary",
    session_duration_s: float,
) -> None:
    failures = analyzer.events.pick_failures
    total_recovery_ms = analyzer.events.recovery_total_ms
    count = analyzer.events.recovery_count

    phase_counts: Dict[str, int] = defaultdict(int)
    reason_counts: Dict[str, int] = defaultdict(int)
    for f in failures:
        phase_counts[f.get("phase") or "unknown"] += 1
        reason_counts[f.get("reason") or "unknown"] += 1

    top_reasons = sorted(reason_counts.items(), key=lambda x: -x[1])[:10]

    # Emergency shutdowns from text patterns
    emergency_shutdowns = analyzer.events.emergency_shutdowns
    estop_from_state = [
        st
        for st in analyzer.events.state_transitions
        if st.get("to_state") == "ERROR" and st.get("estop_latency_ms")
    ]

    overhead_pct: Optional[float] = None
    if session_duration_s > 0 and total_recovery_ms > 0:
        overhead_pct = round(100.0 * (total_recovery_ms / 1000.0) / session_duration_s, 1)

    # task 7.1 — per-arm grouping for failures, motor alerts, emergency shutdowns
    failure_arm_groups = _group_by_arm(failures)
    motor_alert_arm_groups = _group_by_arm(analyzer.events.motor_alerts)
    estop_arm_groups = _group_by_arm(emergency_shutdowns)
    multi_arm = (
        _is_multi_arm(failure_arm_groups)
        or _is_multi_arm(motor_alert_arm_groups)
        or _is_multi_arm(estop_arm_groups)
    )

    per_arm_failures: Dict[str, dict] = {}
    if multi_arm:
        all_arm_ids = set(failure_arm_groups) | set(motor_alert_arm_groups) | set(estop_arm_groups)
        for aid in sorted(all_arm_ids, key=lambda x: str(x)):
            arm_fails = failure_arm_groups.get(aid, [])
            arm_alerts = motor_alert_arm_groups.get(aid, [])
            arm_estops = estop_arm_groups.get(aid, [])
            arm_phase: Dict[str, int] = defaultdict(int)
            arm_reason: Dict[str, int] = defaultdict(int)
            for f in arm_fails:
                arm_phase[f.get("phase") or "unknown"] += 1
                arm_reason[f.get("reason") or "unknown"] += 1
            per_arm_failures[str(aid)] = {
                "failures": len(arm_fails),
                "motor_alerts": len(arm_alerts),
                "emergency_shutdowns": len(arm_estops),
                "failure_by_phase": dict(arm_phase),
                "top_reasons": sorted(arm_reason.items(), key=lambda x: -x[1])[:5],
            }

    summary.pick_failure_analysis = {
        "text_failure_count": len(failures),
        "failure_by_phase": dict(phase_counts),
        "top_failure_reasons": top_reasons,
        "total_recovery_ms": total_recovery_ms,
        "recovery_count": count,
        "recovery_overhead_pct": overhead_pct,
        "emergency_shutdowns": len(emergency_shutdowns),
        "emergency_shutdown_reasons": [e.get("reason") for e in emergency_shutdowns],
        "estop_events": len(estop_from_state),
        # task 7.1 — per-arm breakdown
        "multi_arm": multi_arm,
        "per_arm": per_arm_failures,
    }


# task 24.2 — Arm state section
def _section_arm_state(
    analyzer: "ROS2LogAnalyzer",
    summary: "FieldSummary",
) -> None:
    transitions = analyzer.events.arm_status_transitions

    # task 7.3 — per-arm grouping
    arm_groups = _group_by_arm(transitions)
    multi_arm = _is_multi_arm(arm_groups)

    def _compute_state_time(trans_list: list) -> tuple:
        state_time: Dict[str, float] = defaultdict(float)
        prev_ts: Optional[float] = None
        prev_status = "UNINITIALISED"
        longest_error_s = 0.0
        for t in sorted(trans_list, key=lambda t: t.get("_ts") or 0):
            ts = t.get("_ts")
            status = t.get("status") or "unknown"
            if prev_ts is not None and ts is not None:
                duration = ts - prev_ts
                state_time[prev_status] += duration
                if prev_status == "error":
                    longest_error_s = max(longest_error_s, duration)
            prev_ts = ts
            prev_status = status
        return dict(state_time), round(longest_error_s, 1)

    overall_state_time, overall_longest_error = _compute_state_time(transitions)

    per_arm_state: Dict[str, dict] = {}
    if multi_arm:
        for aid, arm_trans in sorted(arm_groups.items(), key=lambda x: str(x[0])):
            arm_time, arm_longest = _compute_state_time(arm_trans)
            per_arm_state[str(aid)] = {
                "transition_count": len(arm_trans),
                "time_in_state_s": arm_time,
                "longest_error_s": arm_longest,
            }

    summary.arm_state = {
        "transition_count": len(transitions),
        "time_in_state_s": overall_state_time,
        "longest_error_s": overall_longest_error,
        # task 7.3 — per-arm breakdown
        "multi_arm": multi_arm,
        "per_arm": per_arm_state,
    }


# task 24.3 — Motor reliability
def _section_motor_reliability(
    analyzer: "ROS2LogAnalyzer",
    summary: "FieldSummary",
) -> None:
    reach_stats = analyzer.events.motor_reach_stats
    failure_counts = analyzer.events.motor_failure_counts

    reliability: Dict[str, Any] = {}
    for motor_id, stats in reach_stats.items():
        reached = stats.get("reached", 0)
        timeout = stats.get("timeout", 0)
        total_moves = reached + timeout
        failures = failure_counts.get(motor_id, 0)
        errors = stats.get("errors", [])
        avg_error = sum(errors) / len(errors) if errors else None
        reliability[motor_id] = {
            "moves_total": total_moves,
            "reached": reached,
            "timeout": timeout,
            "failure_count": failures,
            "timeout_rate_pct": _safe_pct(timeout, total_moves),
            "avg_position_error": (round(avg_error, 3) if avg_error is not None else None),
        }

    # Motors with failures but no reach stats (CAN errors only)
    for motor_id, count in failure_counts.items():
        if motor_id not in reliability:
            reliability[motor_id] = {
                "moves_total": 0,
                "reached": 0,
                "timeout": 0,
                "failure_count": count,
                "timeout_rate_pct": 0.0,
                "avg_position_error": None,
            }

    summary.motor_reliability = reliability


# task 24.4 — Camera reliability
def _section_camera_reliability(
    analyzer: "ROS2LogAnalyzer",
    summary: "FieldSummary",
    session_duration_s: float,
) -> None:
    reconnections = analyzer.events.camera_reconnections
    total = len(reconnections)

    xlink_triggers = sum(1 for r in reconnections if r.get("type") == "xlink_error")
    timeout_triggers = sum(1 for r in reconnections if r.get("type") == "consecutive_timeout")
    success_count = sum(1 for r in reconnections if r.get("success") is True)

    # MTBR (mean time between reconnections)
    mtbr_s: Optional[float] = None
    if total > 1:
        ts_vals = sorted(r["_ts"] for r in reconnections if r.get("_ts"))
        if len(ts_vals) >= 2:
            mtbr_s = round((ts_vals[-1] - ts_vals[0]) / (len(ts_vals) - 1), 1)
    elif total == 0 and session_duration_s > 0:
        mtbr_s = None  # no reconnections = good

    summary.camera_reliability = {
        "reconnection_count": total,
        "xlink_triggers": xlink_triggers,
        "timeout_triggers": timeout_triggers,
        "successful_reconnections": success_count,
        "mean_time_between_reconnections_s": mtbr_s,
    }


# task 24.5 — Communication health (MQTT, from Group 23)
def _section_communication_health(
    analyzer: "ROS2LogAnalyzer",
    summary: "FieldSummary",
    session_duration_s: float,
) -> None:
    mqtt = analyzer.mqtt

    total_connects = len(mqtt.connects)
    total_disconnects = len(mqtt.disconnects)
    unexpected_disconnects = sum(1 for d in mqtt.disconnects if d.get("type") == "unexpected")
    publish_failures = len(mqtt.publish_failures)

    # MQTT uptime estimate
    # task 15.4 — handle zero-connection case
    mqtt_uptime_pct: Any
    mqtt_status_note: Optional[str] = None
    if total_connects == 0:
        # MQTT connection was never established
        # Check if there were any connect attempts (disconnects/publish failures
        # imply attempts were made)
        attempts = total_disconnects + publish_failures
        if attempts > 0:
            mqtt_uptime_pct = 0.0
            mqtt_status_note = f"failed to connect ({attempts} attempts)"
        else:
            mqtt_uptime_pct = 0.0
            mqtt_status_note = "MQTT: not established"
    else:
        disconnect_periods: list = []
        for d in sorted(mqtt.disconnects, key=lambda x: x.get("_ts") or 0):
            d_ts = d.get("_ts")
            # find next reconnect
            reconnect_ts = next(
                (c.get("_ts") for c in mqtt.connects if c.get("_ts") and d_ts and c["_ts"] > d_ts),
                None,
            )
            if d_ts and reconnect_ts:
                gap = reconnect_ts - d_ts
                disconnect_periods.append(gap)

        total_disconnect_s = sum(disconnect_periods)
        mqtt_uptime_pct = (
            round(100.0 * (1 - total_disconnect_s / session_duration_s), 1)
            if session_duration_s > 0
            else 100.0
        )

    # Disconnect reasons
    reason_counts: Dict[str, int] = defaultdict(int)
    for d in mqtt.disconnects:
        reason_counts[d.get("type") or "unknown"] += 1

    # MTBF
    mtbf_s: Optional[float] = None
    if total_disconnects > 0 and session_duration_s > 0:
        mtbf_s = round(session_duration_s / total_disconnects, 0)

    # Per-arm status summary
    arm_status_summary: Dict[str, str] = {}
    for arm_s in mqtt.arm_statuses:
        arm_id = str(arm_s.get("arm_id") or "?")
        arm_status_summary[arm_id] = arm_s.get("status") or "unknown"

    # Broker health
    broker_restarts = len(mqtt.broker_starts)
    socket_errors = sum(1 for d in mqtt.broker_disconnects if d.get("socket_error"))

    # task 7.2 — per-arm MQTT grouping
    connect_arm_groups = _group_by_arm(mqtt.connects)
    disconnect_arm_groups = _group_by_arm(mqtt.disconnects)
    pub_fail_arm_groups = _group_by_arm(mqtt.publish_failures)
    multi_arm_mqtt = (
        _is_multi_arm(connect_arm_groups)
        or _is_multi_arm(disconnect_arm_groups)
        or _is_multi_arm(pub_fail_arm_groups)
    )

    per_arm_mqtt: Dict[str, dict] = {}
    if multi_arm_mqtt:
        all_arm_ids = (
            set(connect_arm_groups) | set(disconnect_arm_groups) | set(pub_fail_arm_groups)
        )
        for aid in sorted(all_arm_ids, key=lambda x: str(x)):
            arm_conns = connect_arm_groups.get(aid, [])
            arm_discs = disconnect_arm_groups.get(aid, [])
            arm_pubs = pub_fail_arm_groups.get(aid, [])
            arm_unexpected = sum(1 for d in arm_discs if d.get("type") == "unexpected")
            per_arm_mqtt[str(aid)] = {
                "connects": len(arm_conns),
                "disconnects": len(arm_discs),
                "unexpected_disconnects": arm_unexpected,
                "publish_failures": len(arm_pubs),
            }

    summary.communication_health = {
        "mqtt_connects": total_connects,
        "mqtt_disconnects": total_disconnects,
        "unexpected_disconnects": unexpected_disconnects,
        "publish_failures": publish_failures,
        "mqtt_uptime_pct": mqtt_uptime_pct,
        "mqtt_status_note": mqtt_status_note,
        "disconnect_by_reason": dict(reason_counts),
        "mtbf_s": mtbf_s,
        "per_arm_status": arm_status_summary,
        "broker_restarts": broker_restarts,
        "broker_socket_errors": socket_errors,
        # task 7.2 — per-arm breakdown
        "multi_arm": multi_arm_mqtt,
        "per_arm_mqtt": per_arm_mqtt,
    }


# ---------------------------------------------------------------------------
# task 16.5 — Joint limit analysis
# ---------------------------------------------------------------------------


def _section_joint_limits(
    analyzer: "ROS2LogAnalyzer",
    summary: "FieldSummary",
) -> None:
    """Render JOINT LIMIT ANALYSIS section."""
    events = analyzer.events.joint_limit_events
    if not events:
        return

    total_violations = len(events)
    joint_limit_total = getattr(analyzer.events, "_joint_limit_total", total_violations)

    # Per-joint breakdown
    by_joint: Dict[str, int] = defaultdict(int)
    by_direction: Dict[str, int] = defaultdict(int)
    # J4 offset → count (use calculated_m as proxy)
    by_j4_offset: Dict[str, int] = defaultdict(int)
    max_overshoot = 0.0
    for ev in events:
        joint = ev.get("joint_name", "unknown")
        by_joint[joint] += 1
        direction = ev.get("direction", "unknown")
        by_direction[direction] += 1
        calc_m = ev.get("calculated_m")
        if calc_m is not None:
            key = f"{calc_m:.3f}m"
            by_j4_offset[key] += 1
        overshoot = ev.get("overshoot_m", 0.0) or 0.0
        if overshoot > max_overshoot:
            max_overshoot = overshoot

    summary.joint_limits = {
        "total_violations": total_violations,
        "joint_limit_total": joint_limit_total,
        "by_joint": dict(by_joint),
        "by_direction": dict(by_direction),
        "by_j4_offset": dict(by_j4_offset),
        "max_overshoot_m": max_overshoot,
    }


# ---------------------------------------------------------------------------
# task 17.4 — Camera health (text-parsed stats blocks)
# ---------------------------------------------------------------------------


def _section_camera_health(
    analyzer: "ROS2LogAnalyzer",
    summary: "FieldSummary",
) -> None:
    """Render CAMERA HEALTH section from camera_stats_blocks."""
    blocks = analyzer.events.camera_stats_blocks
    if not blocks:
        return

    temps = [b["temp_c"] for b in blocks if b.get("temp_c") is not None]
    latency_avgs = [b["latency_avg_ms"] for b in blocks if b.get("latency_avg_ms") is not None]
    latency_maxs = [b["latency_max_ms"] for b in blocks if b.get("latency_max_ms") is not None]
    frame_wait_avgs = [
        b["frame_wait_avg_ms"] for b in blocks if b.get("frame_wait_avg_ms") is not None
    ]
    frame_wait_maxs = [
        b["frame_wait_max_ms"] for b in blocks if b.get("frame_wait_max_ms") is not None
    ]
    requests_list = [b["requests"] for b in blocks if b.get("requests") is not None]
    with_cotton_list = [b["with_cotton"] for b in blocks if b.get("with_cotton") is not None]
    css_pct_vals = [b["css_pct"] for b in blocks if b.get("css_pct") is not None]
    mss_pct_vals = [b["mss_pct"] for b in blocks if b.get("mss_pct") is not None]

    total_requests = sum(requests_list) if requests_list else 0
    total_with_cotton = sum(with_cotton_list) if with_cotton_list else 0
    with_cotton_rate_pct = (
        round(100.0 * total_with_cotton / total_requests, 1) if total_requests > 0 else 0.0
    )
    never_detected_note = (
        "camera never detected cotton in any request" " — verify camera position and model"
        if total_requests > 0 and with_cotton_rate_pct == 0.0
        else ""
    )

    summary.camera_health = {
        "total_blocks": len(blocks),
        "total_requests": total_requests,
        "total_with_cotton": total_with_cotton,
        "with_cotton_rate_pct": with_cotton_rate_pct,
        "never_detected_note": never_detected_note,
        "temp_c": _stats(temps),
        "latency_ms": _stats(latency_avgs),
        "latency_max_ms": _stats(latency_maxs),
        "frame_wait_ms": _stats(frame_wait_avgs),
        "frame_wait_max_ms": _stats(frame_wait_maxs),
        "css_pct": _stats(css_pct_vals),
        "mss_pct": _stats(mss_pct_vals),
    }


# ---------------------------------------------------------------------------
# task 18.5 — Scan effectiveness
# ---------------------------------------------------------------------------


def _section_scan_effectiveness(
    analyzer: "ROS2LogAnalyzer",
    summary: "FieldSummary",
) -> None:
    """Render SCAN EFFECTIVENESS section."""
    pos_results = analyzer.events.scan_position_results
    scan_summaries = analyzer.events.scan_summaries
    if not pos_results and not scan_summaries:
        return

    # Per-position table: J4 offset (mm) → {found, picked, scans}
    by_position: Dict[str, Dict[str, int]] = {}
    for ev in pos_results:
        j4_m = ev.get("j4_offset_m")
        if j4_m is not None:
            idx = f"{j4_m * 1000:+.0f}mm"
        else:
            raw_idx = ev.get("position_index")
            idx = str(raw_idx) if raw_idx is not None else "?"
        if idx not in by_position:
            by_position[idx] = {"found": 0, "picked": 0, "scans": 0}
        by_position[idx]["found"] += ev.get("cotton_found", 0)
        by_position[idx]["picked"] += ev.get("cotton_picked", 0)
        by_position[idx]["scans"] += 1

    # Best/worst positions
    best_pos: Optional[str] = None
    worst_pos: Optional[str] = None
    best_found = -1
    worst_found = 999999
    for pos_key, stats in by_position.items():
        found = stats["found"]
        if found > best_found:
            best_found = found
            best_pos = pos_key
        if found < worst_found:
            worst_found = found
            worst_pos = pos_key

    # Summary stats
    total_scans = len(scan_summaries)
    # task 15.5 — compute totals from per-position data so they match the breakdown
    total_cotton_found = sum(stats["found"] for stats in by_position.values())
    total_cotton_picked = sum(stats["picked"] for stats in by_position.values())

    # --- task 7.1: Dead zone identification ---
    # A dead zone is a J4 position with 0 cotton picked across 3+ scans
    # while at least one other position has non-zero picks.
    any_position_has_picks = any(s["picked"] > 0 for s in by_position.values())
    dead_zones: List[str] = []
    if any_position_has_picks:
        for pos_key, stats in by_position.items():
            if stats["picked"] == 0 and stats["scans"] >= 3:
                dead_zones.append(pos_key)
                analyzer._add_issue(
                    severity="medium",
                    category="scan",
                    title=f"Dead zone at J4 position {pos_key}",
                    description=(
                        f"J4 position {pos_key} picked 0 cotton across"
                        f" {stats['scans']} scans (found"
                        f" {stats['found']}) while other positions"
                        f" have non-zero picks"
                    ),
                    node="scan_effectiveness",
                    timestamp=0.0,
                    message=(
                        f"Dead zone: position {pos_key} —"
                        f" 0/{stats['found']} picked over"
                        f" {stats['scans']} scans"
                    ),
                    recommendation=(
                        "Investigate mechanical reach or camera" " alignment at this J4 position"
                    ),
                )

    # --- task 7.2: Position-to-pick yield correlation ---
    # When 5+ total scans are available, compute per-position yield
    # and rank positions by pick_yield_pct.
    yield_ranking: List[Dict[str, Any]] = []
    total_scan_events = len(pos_results)
    if total_scan_events >= 5 and by_position:
        for pos_key, stats in by_position.items():
            found = stats["found"]
            picked = stats["picked"]
            yield_pct = round(100.0 * picked / found, 1) if found > 0 else 0.0
            yield_ranking.append(
                {
                    "position": pos_key,
                    "cotton_found": found,
                    "cotton_picked": picked,
                    "pick_yield_pct": yield_pct,
                    "scans": stats["scans"],
                }
            )
        yield_ranking.sort(key=lambda r: r["pick_yield_pct"], reverse=True)

    summary.scan_effectiveness = {
        "total_scans": total_scans,
        "total_cotton_found": total_cotton_found,
        "total_cotton_picked": total_cotton_picked,
        "by_position": by_position,
        "best_position": best_pos,
        "worst_position": worst_pos,
        "dead_zones": dead_zones,
        "yield_ranking": yield_ranking,
    }


# ---------------------------------------------------------------------------
# task 19.4 — Motor homing verification
# ---------------------------------------------------------------------------


def _section_motor_homing(
    analyzer: "ROS2LogAnalyzer",
    summary: "FieldSummary",
) -> None:
    """Render MOTOR HOMING section from homing_events."""
    events = analyzer.events.homing_events
    if not events:
        return

    # Per-joint table: joint → latest homing record
    by_joint: Dict[str, dict] = {}
    for ev in events:
        joint = ev.get("joint_name", "unknown")
        by_joint[joint] = ev  # last record wins

    joint_table = []
    for joint, ev in sorted(by_joint.items()):
        pos_err = ev.get("position_error")
        tol = ev.get("tolerance")
        err_tol_ratio_pct: Optional[float] = None
        near_tolerance = False
        if pos_err is not None and tol is not None and tol > 0:
            err_tol_ratio_pct = round(100.0 * pos_err / tol, 1)
            near_tolerance = err_tol_ratio_pct > 80.0
        joint_table.append(
            {
                "joint": joint,
                "homed": ev.get("success", False),
                "position_error": pos_err,
                "tolerance": tol,
                "err_tol_ratio_pct": err_tol_ratio_pct,
                "near_tolerance": near_tolerance,
            }
        )

    summary.motor_homing = {
        "total_events": len(events),
        "joint_table": joint_table,
    }


# ---------------------------------------------------------------------------
# task 20.6 — Per-joint approach/retreat timing
# ---------------------------------------------------------------------------


def _section_per_joint_timing(
    analyzer: "ROS2LogAnalyzer",
    summary: "FieldSummary",
) -> None:
    """Render PER-JOINT TIMING section."""
    joint_timings = analyzer.events.per_joint_timings
    retreat_bds = analyzer.events.retreat_breakdowns
    ee_durs = analyzer.events.ee_on_durations
    if not joint_timings and not retreat_bds:
        return

    # Per-joint approach stats
    by_joint: Dict[str, List[float]] = defaultdict(list)
    for ev in joint_timings:
        joint = ev.get("joint", "unknown")
        ms = ev.get("duration_ms")
        if ms is not None:
            by_joint[joint].append(float(ms))

    joint_approach_stats = {}
    bottleneck_joint: Optional[str] = None
    max_p95 = 0.0
    for joint, times in sorted(by_joint.items()):
        st = _stats(times)
        joint_approach_stats[joint] = st
        p95 = st.get("p95") or 0.0
        if p95 > max_p95:
            max_p95 = p95
            bottleneck_joint = joint

    # Retreat breakdown: component → list of durations
    retreat_components: Dict[str, List[float]] = defaultdict(list)
    for ev in retreat_bds:
        for key in (
            "compressor_ms",
            "j5_ms",
            "j4_ms",
            "j3_ms",
            "total_ms",
        ):
            val = ev.get(key)
            if val is not None:
                retreat_components[key].append(float(val))

    retreat_stats = {k: _stats(v) for k, v in retreat_components.items()}

    # EE on durations
    ee_ms_vals = [float(e["ee_on_ms"]) for e in ee_durs if e.get("ee_on_ms") is not None]
    ee_on_stats = _stats(ee_ms_vals)

    # J5+EE approach breakdown (j5_travel, ee_pretravel, ee_overlap, ee_dwell)
    j5_ee_bds = analyzer.events.j5_ee_breakdowns
    j5_ee_breakdown_stats: Dict[str, dict] = {}
    if j5_ee_bds:
        component_lists: Dict[str, List[float]] = defaultdict(list)
        for ev in j5_ee_bds:
            for key in (
                "j5_travel_ms",
                "ee_pretravel_ms",
                "ee_overlap_ms",
                "ee_dwell_ms",
            ):
                val = ev.get(key)
                if val is not None:
                    component_lists[key].append(float(val))
        j5_ee_breakdown_stats = {k: _stats(v) for k, v in component_lists.items()}

    summary.per_joint_timing = {
        "joint_approach_stats": joint_approach_stats,
        "bottleneck_joint": bottleneck_joint,
        "retreat_stats": retreat_stats,
        "ee_on_stats": ee_on_stats,
        "j5_ee_breakdown": j5_ee_breakdown_stats,
    }


# ---------------------------------------------------------------------------
# task 21.6 — Detection quality and frame freshness
# ---------------------------------------------------------------------------


def _section_detection_quality(
    analyzer: "ROS2LogAnalyzer",
    summary: "FieldSummary",
) -> None:
    """Render DETECTION QUALITY section."""
    det_events = analyzer.events.detection_quality_events
    frame_events = analyzer.events.frame_freshness_events
    if not det_events and not frame_events:
        return

    # Aggregate detection counts
    total_requests = len(det_events)
    total_raw = sum(e.get("raw", 0) for e in det_events)
    total_accepted = sum(e.get("cotton_accepted", 0) for e in det_events)
    total_border_skipped = max((e.get("border_skip_total", 0) for e in det_events), default=0)
    total_not_pickable = max((e.get("not_pickable_total", 0) for e in det_events), default=0)
    total_workspace_rejected = max(
        (e.get("workspace_reject_total", 0) for e in det_events),
        default=0,
    )

    acceptance_rate_pct = round(100.0 * total_accepted / total_raw, 1) if total_raw > 0 else 0.0
    border_skip_rate_pct = (
        round(100.0 * total_border_skipped / total_raw, 1) if total_raw > 0 else 0.0
    )
    not_pickable_rate_pct = (
        round(100.0 * total_not_pickable / total_raw, 1) if total_raw > 0 else 0.0
    )
    workspace_reject_rate_pct = (
        round(100.0 * total_workspace_rejected / total_raw, 1) if total_raw > 0 else 0.0
    )

    # Frame freshness: stale flushed per request
    total_flushed = sum(e.get("stale_flushed", 0) for e in frame_events)
    total_fresh = len(frame_events)  # each event = 1 fresh frame obtained
    avg_stale_flushed = round(total_flushed / len(frame_events), 2) if frame_events else 0.0
    avg_frame_wait_ms_vals = [
        e.get("wait_ms") for e in frame_events if e.get("wait_ms") is not None
    ]
    avg_frame_wait_ms = (
        round(
            sum(avg_frame_wait_ms_vals) / len(avg_frame_wait_ms_vals),
            1,
        )
        if avg_frame_wait_ms_vals
        else None
    )

    fallback_count = getattr(analyzer.events, "_fallback_position_count", 0)

    summary.detection_quality = {
        "total_requests": total_requests,
        "total_raw": total_raw,
        "total_accepted": total_accepted,
        "acceptance_rate_pct": acceptance_rate_pct,
        "border_skip_rate_pct": border_skip_rate_pct,
        "not_pickable_rate_pct": not_pickable_rate_pct,
        "workspace_reject_total": total_workspace_rejected,
        "workspace_reject_rate_pct": workspace_reject_rate_pct,
        "fallback_position_count": fallback_count,
        "avg_stale_flushed_per_request": avg_stale_flushed,
        "avg_frame_wait_ms": avg_frame_wait_ms,
        "total_flushed_frames": total_flushed,
        "total_fresh_frames": total_fresh,
    }


# ---------------------------------------------------------------------------
# task 7.9 — Detection telemetry section
# ---------------------------------------------------------------------------


def _section_detection_telemetry(
    analyzer: "ROS2LogAnalyzer",
    summary: "FieldSummary",
) -> None:
    """Render DETECTION TELEMETRY section from JSON telemetry fields."""
    summaries = analyzer.events.detection_summaries
    idle_events = analyzer.events.detection_idle_events
    frames_s = analyzer.events.detection_frames_summary

    if not summaries and not idle_events:
        return

    result: dict = {}

    # Latency percentiles (averaged across summary periods)
    p50_vals = [s["latency_p50_ms"] for s in summaries if s.get("latency_p50_ms") is not None]
    p95_vals = [s["latency_p95_ms"] for s in summaries if s.get("latency_p95_ms") is not None]
    p99_vals = [s["latency_p99_ms"] for s in summaries if s.get("latency_p99_ms") is not None]
    if p50_vals:
        result["latency_p50_avg_ms"] = round(sum(p50_vals) / len(p50_vals), 1)
    if p95_vals:
        result["latency_p95_avg_ms"] = round(sum(p95_vals) / len(p95_vals), 1)
    if p99_vals:
        result["latency_p99_avg_ms"] = round(sum(p99_vals) / len(p99_vals), 1)

    # Frame drop rate (average and max)
    drop_vals = [
        s["frames_drop_rate_pct"] for s in summaries if s.get("frames_drop_rate_pct") is not None
    ]
    if drop_vals:
        result["frame_drop_rate_avg_pct"] = round(sum(drop_vals) / len(drop_vals), 2)
        result["frame_drop_rate_max_pct"] = round(max(drop_vals), 2)

    # VPU timing
    vpu_p50 = [s["vpu_p50_ms"] for s in summaries if s.get("vpu_p50_ms") is not None]
    vpu_p95 = [s["vpu_p95_ms"] for s in summaries if s.get("vpu_p95_ms") is not None]
    if vpu_p50:
        result["vpu_p50_avg_ms"] = round(sum(vpu_p50) / len(vpu_p50), 1)
    if vpu_p95:
        result["vpu_p95_avg_ms"] = round(sum(vpu_p95) / len(vpu_p95), 1)

    # Cache hit rate
    total_hits = sum((s.get("cache_hits") or 0) for s in summaries)
    total_misses = sum((s.get("cache_misses") or 0) for s in summaries)
    total_cache = total_hits + total_misses
    if total_cache > 0:
        result["cache_hit_rate_pct"] = round(100.0 * total_hits / total_cache, 1)
        result["cache_hits"] = total_hits
        result["cache_misses"] = total_misses

    # Idle periods
    if idle_events:
        result["idle_period_count"] = len(idle_events)
        total_idle_s = sum((e.get("duration_s") or 0.0) for e in idle_events)
        result["idle_total_duration_s"] = round(total_idle_s, 1)

    # Detection age from frames summary
    age_count = frames_s.get("detection_age_count", 0)
    if age_count > 0:
        result["avg_detection_age_ms"] = round(frames_s["total_detection_age_ms"] / age_count, 1)

    if result:
        summary.detection_telemetry = result


# ---------------------------------------------------------------------------
# tasks 6.1-6.3 — ARM_client health sections
# ---------------------------------------------------------------------------


def build_mqtt_health(
    events: "EventStore",
    arm_id: str,
) -> Optional[dict]:
    """Build MQTT health summary for a given arm."""
    mqtt_events = [e for e in events.arm_client_mqtt_events if e.get("arm_id") == arm_id]
    if not mqtt_events:
        return None

    connects = sum(1 for e in mqtt_events if e["event_type"] == "mqtt_connect")
    disconnects = sum(1 for e in mqtt_events if e["event_type"] == "mqtt_disconnect")
    timeouts = sum(1 for e in mqtt_events if e["event_type"] == "mqtt_timeout")

    # Calculate longest disconnection gap
    longest_disconnect = 0.0
    last_disconnect_ts: Optional[float] = None
    for e in sorted(mqtt_events, key=lambda x: x.get("timestamp", 0)):
        if e["event_type"] in (
            "mqtt_disconnect",
            "mqtt_timeout",
        ):
            last_disconnect_ts = e.get("timestamp", 0)
        elif e["event_type"] == "mqtt_connect" and last_disconnect_ts is not None:
            duration = e.get("timestamp", 0) - last_disconnect_ts
            longest_disconnect = max(longest_disconnect, duration)
            last_disconnect_ts = None

    # Last known status
    last_event = sorted(mqtt_events, key=lambda x: x.get("timestamp", 0))[-1]
    last_status = last_event["event_type"]

    return {
        "connects": connects,
        "disconnects": disconnects,
        "timeouts": timeouts,
        "longest_disconnect_s": longest_disconnect,
        "last_status": last_status,
    }


def build_service_health(
    events: "EventStore",
    arm_id: str,
) -> Optional[dict]:
    """Build service health summary for a given arm."""
    svc_events = [
        e
        for e in events.arm_client_events
        if e.get("arm_id") == arm_id and e.get("event_type") == "service_failure"
    ]
    if not svc_events:
        return None

    total_failures = len(svc_events)

    # Count by service name
    svc_counts: Dict[str, int] = defaultdict(int)
    for e in svc_events:
        svc_counts[e.get("service_name", "unknown")] += 1

    # Check for retry exhaustion (HIGH severity = exhausted)
    retry_exhaustion = any(e.get("severity") == "HIGH" for e in svc_events)

    # Service names summary
    svc_names = ", ".join(f"{name}" for name, _ in sorted(svc_counts.items(), key=lambda x: -x[1]))

    return {
        "total_failures": total_failures,
        "by_service": dict(svc_counts),
        "service_names": svc_names,
        "retry_exhaustion": retry_exhaustion,
    }


def build_error_recovery(
    events: "EventStore",
    arm_id: str,
) -> Optional[dict]:
    """Build error recovery summary for a given arm."""
    recovery_events = [
        e
        for e in events.arm_client_events
        if e.get("arm_id") == arm_id and e.get("event_type") == "error_recovery"
    ]
    if not recovery_events:
        return None

    error_states = sum(1 for e in recovery_events if e.get("outcome") == "error_persisted")
    attempts = sum(1 for e in recovery_events if e.get("outcome") == "recovery_attempt")
    succeeded = sum(1 for e in recovery_events if e.get("outcome") == "recovery_succeeded")
    failed = sum(1 for e in recovery_events if e.get("outcome") == "recovery_failed")

    return {
        "error_states": error_states,
        "recovery_attempts": attempts,
        "succeeded": succeeded,
        "failed": failed,
    }


# ---------------------------------------------------------------------------
# task 6.1-6.3 — Section builder that collects per-arm health
# ---------------------------------------------------------------------------


def _section_arm_client_health(
    analyzer: "ROS2LogAnalyzer",
    summary: "FieldSummary",
) -> None:
    """Build per-arm MQTT, service, and error-recovery health."""
    events = analyzer.events

    # Collect unique arm_ids from both event lists
    arm_ids: Set[str] = set()
    for e in events.arm_client_mqtt_events:
        aid = e.get("arm_id")
        if aid:
            arm_ids.add(aid)
    for e in events.arm_client_events:
        aid = e.get("arm_id")
        if aid:
            arm_ids.add(aid)

    if not arm_ids:
        return

    mqtt_data: Dict[str, dict] = {}
    svc_data: Dict[str, dict] = {}
    recovery_data: Dict[str, dict] = {}

    for aid in sorted(arm_ids):
        mh = build_mqtt_health(events, aid)
        if mh:
            mqtt_data[aid] = mh
        sh = build_service_health(events, aid)
        if sh:
            svc_data[aid] = sh
        er = build_error_recovery(events, aid)
        if er:
            recovery_data[aid] = er

    if mqtt_data:
        summary.mqtt_health = mqtt_data
    if svc_data:
        summary.service_health = svc_data
    if recovery_data:
        summary.error_recovery = recovery_data


# ---------------------------------------------------------------------------
# task 6.4 — Correlation findings section
# ---------------------------------------------------------------------------


def _section_correlation_findings(
    analyzer: "ROS2LogAnalyzer",
    summary: "FieldSummary",
) -> None:
    """Extract CORRELATION-category issues into a dedicated section."""
    issues = getattr(analyzer, "issues", {})
    if not issues:
        return

    correlation_issues = [i for i in issues.values() if getattr(i, "category", "") == "CORRELATION"]
    if not correlation_issues:
        return

    findings = []
    for issue in correlation_issues:
        findings.append(
            {
                "severity": issue.severity.upper(),
                "title": issue.title,
                "description": issue.description,
            }
        )

    summary.correlation_findings = findings


# ---------------------------------------------------------------------------
# task 6.5 — Verbose mode sections
# ---------------------------------------------------------------------------


def _section_verbose_diagnostics(
    analyzer: "ROS2LogAnalyzer",
    summary: "FieldSummary",
) -> None:
    """Populate verbose-only diagnostic sections from EventStore."""
    events = analyzer.events

    if events.parse_stats:
        summary.verbose_parse_stats = list(events.parse_stats)

    if events.suppressed_findings:
        summary.verbose_suppressed = list(events.suppressed_findings)

    if events.correlation_details:
        summary.verbose_correlation_details = list(events.correlation_details)


# ---------------------------------------------------------------------------
# task 2.5 — BUILD INFO section
# ---------------------------------------------------------------------------


def _section_build_info(
    analyzer: "ROS2LogAnalyzer",
    summary: "FieldSummary",
) -> None:
    """Populate build_info section from build provenances.

    Renders a per-node table with node, built_at, git_hash, branch,
    dirty flag. Adds [STALE] tag on nodes flagged as stale.
    Omits section when no build timestamps were found.
    """
    provenances = getattr(analyzer, "build_provenances", [])
    if not provenances:
        return

    threshold = getattr(analyzer, "stale_threshold_hours", 1.0)

    # Determine newest build timestamp for stale tagging
    newest_ts = max(p.build_timestamp for p in provenances)
    threshold_seconds = threshold * 3600.0

    nodes = []
    for p in provenances:
        delta = (newest_ts - p.build_timestamp).total_seconds()
        is_stale = delta > threshold_seconds and len(provenances) > 1
        nodes.append(
            {
                "node": p.node_name,
                "built_at": p.build_timestamp.strftime("%b %d %Y %H:%M:%S"),
                "git_hash": p.git_hash or "",
                "branch": p.git_branch or "",
                "dirty": p.is_dirty,
                "stale": is_stale,
            }
        )

    summary.build_info = {
        "has_data": True,
        "nodes": nodes,
    }


# ---------------------------------------------------------------------------
# task 4.4 — Motor position trending
# ---------------------------------------------------------------------------


def _section_motor_trending(
    analyzer: "ROS2LogAnalyzer",
    summary: "FieldSummary",
) -> None:
    """Populate MOTOR POSITION TRENDING section from pre-computed result.

    Reads the trending result already computed by the analyzer
    (via analyze_motor_trending) instead of re-calling the detector.
    Requires at least 2 homing events per joint to include in output.
    """
    result = getattr(analyzer, "_motor_trending_result", None)
    if not result:
        return
    joints = result.get("joints", {})
    if not joints:
        return

    summary.motor_trending = {
        "has_data": True,
        "joints": joints,
    }


# ---------------------------------------------------------------------------
# task 4.6 — J4 position breakdown
# ---------------------------------------------------------------------------


def _section_j4_position_breakdown(
    analyzer: "ROS2LogAnalyzer",
    summary: "FieldSummary",
) -> None:
    """Populate J4 POSITION BREAKDOWN from scan position results.

    Groups scan results by j4_offset_m, counts scans at each
    position, computes pick yield percentage, flags dead zones
    (0% yield across 3+ scans).
    """
    pos_results = analyzer.events.scan_position_results
    if not pos_results:
        return

    # Group by j4_offset_m value
    by_offset: Dict[str, dict] = {}
    for ev in pos_results:
        offset = ev.get("j4_offset_m")
        if offset is None:
            continue
        key = f"{float(offset):.3f}"
        if key not in by_offset:
            by_offset[key] = {
                "j4_offset_m": float(offset),
                "scans_at_position": 0,
                "cotton_found": 0,
                "cotton_picked": 0,
            }
        by_offset[key]["scans_at_position"] += 1
        by_offset[key]["cotton_found"] += ev.get("cotton_found", 0)
        by_offset[key]["cotton_picked"] += ev.get("cotton_picked", 0)

    if not by_offset:
        return

    # Compute pick_yield_pct and identify dead zones
    position_table = []
    dead_zones: List[float] = []
    for _key, data in sorted(
        by_offset.items(),
        key=lambda kv: kv[1]["cotton_picked"],
        reverse=True,
    ):
        found = data["cotton_found"]
        picked = data["cotton_picked"]
        yield_pct = round(100.0 * picked / found, 1) if found > 0 else 0.0
        entry = {
            "j4_offset_m": data["j4_offset_m"],
            "scans_at_position": data["scans_at_position"],
            "cotton_found": found,
            "cotton_picked": picked,
            "pick_yield_pct": yield_pct,
        }
        position_table.append(entry)

        # Dead zone: 0% yield across 3+ scans
        if yield_pct == 0.0 and data["scans_at_position"] >= 3:
            dead_zones.append(data["j4_offset_m"])

    summary.j4_position_breakdown = {
        "has_data": True,
        "position_table": position_table,
        "dead_zones": dead_zones,
    }


# ---------------------------------------------------------------------------
# task 4.13 — Camera thermal trending
# ---------------------------------------------------------------------------


def _section_camera_thermal(
    analyzer: "ROS2LogAnalyzer",
    summary: "FieldSummary",
) -> None:
    """Populate CAMERA THERMAL section from detection_summary events.

    Uses the camera_thermal detector to compute temperature stats
    and rate of rise. Omits section when no temperature data present.
    """
    from ..detectors.camera_thermal import analyze_camera_thermal

    result = analyze_camera_thermal(analyzer.events)
    thermal = result.get("thermal", {})
    if not thermal or not thermal.get("has_data"):
        return

    summary.camera_thermal = thermal


# ---------------------------------------------------------------------------
# task 4.19 — Motor current draw
# ---------------------------------------------------------------------------


def _section_motor_current(
    analyzer: "ROS2LogAnalyzer",
    summary: "FieldSummary",
) -> None:
    """Populate MOTOR CURRENT DRAW section from motor_health_arm events.

    Uses the motor_current detector to compute per-joint current
    statistics and health indicators. Omits section when no data.
    """
    from ..detectors.motor_current import analyze_motor_current

    result = analyze_motor_current(analyzer.events)
    joints = result.get("joints", {})
    if not joints:
        return

    summary.motor_current = {
        "has_data": True,
        "joints": joints,
    }


# ---------------------------------------------------------------------------
# task 6.1 — Dmesg summary
# ---------------------------------------------------------------------------


def _section_dmesg_summary(
    report: "FieldSummary",
    analyzer: "ROS2LogAnalyzer",
) -> None:
    """Aggregate kernel-level events from parsed dmesg data.

    Categories: USB disconnects, thermal throttling, memory pressure (OOM),
    CAN errors, SPI errors.  Shows event count by category with first/last
    timestamps.  Omits section when no dmesg data available.
    """
    categories = {
        "usb_disconnect": analyzer.events.dmesg_usb_disconnects,
        "thermal": analyzer.events.dmesg_thermal,
        "oom": analyzer.events.dmesg_oom,
        "can_error": analyzer.events.dmesg_can_errors,
        "spi_error": analyzer.events.dmesg_spi_errors,
    }

    # Skip entirely when no dmesg data at all
    total_events = sum(len(evts) for evts in categories.values())
    if total_events == 0:
        return

    by_category: Dict[str, dict] = {}
    for cat_name, events_list in categories.items():
        if not events_list:
            continue
        timestamps = [e.get("_ts") for e in events_list if e.get("_ts") is not None]
        first_ts: Optional[float] = min(timestamps) if timestamps else None
        last_ts: Optional[float] = max(timestamps) if timestamps else None
        by_category[cat_name] = {
            "count": len(events_list),
            "first_ts": first_ts,
            "last_ts": last_ts,
        }

    report.dmesg_summary = {
        "has_data": True,
        "total_events": total_events,
        "by_category": by_category,
    }


# ---------------------------------------------------------------------------
# task 6.2 — Pick success rate trend
# ---------------------------------------------------------------------------


def _section_pick_success_trend(
    report: "FieldSummary",
    analyzer: "ROS2LogAnalyzer",
) -> None:
    """Show success rate in rolling 10-pick windows.

    Compares first-quarter vs last-quarter success rate.
    Raises Medium severity issue when last-quarter drops >20pp below
    first-quarter.  Omits when <10 picks.
    """
    picks = analyzer.events.picks
    total = len(picks)
    if total < 10:
        return

    # Rolling 10-pick windows
    window_size = 10
    windows: List[dict] = []
    for i in range(0, total - window_size + 1):
        window_picks = picks[i : i + window_size]
        successes = sum(1 for p in window_picks if p.get("success"))
        rate = _safe_pct(successes, window_size)
        windows.append(
            {
                "start_index": i,
                "end_index": i + window_size - 1,
                "success_rate_pct": rate,
            }
        )

    # Quarter analysis
    quarter_len = max(1, total // 4)

    first_q_picks = picks[:quarter_len]
    last_q_picks = picks[-quarter_len:]
    first_q_successes = sum(1 for p in first_q_picks if p.get("success"))
    last_q_successes = sum(1 for p in last_q_picks if p.get("success"))
    first_q_rate = _safe_pct(first_q_successes, len(first_q_picks))
    last_q_rate = _safe_pct(last_q_successes, len(last_q_picks))

    delta = first_q_rate - last_q_rate

    if delta > 20:
        trend_direction = "degrading"
    elif delta < -20:
        trend_direction = "improving"
    else:
        trend_direction = "stable"

    # Raise issue when degrading significantly
    issue: Optional[dict] = None
    if delta > 20:
        issue = {
            "severity": "Medium",
            "description": (
                f"Pick success rate dropped {delta:.1f}pp: "
                f"first-quarter {first_q_rate}% -> "
                f"last-quarter {last_q_rate}%"
            ),
        }

    report.pick_success_trend = {
        "has_data": True,
        "total_picks": total,
        "window_size": window_size,
        "windows": windows,
        "first_quarter_rate_pct": first_q_rate,
        "last_quarter_rate_pct": last_q_rate,
        "delta_pp": round(delta, 1),
        "trend_direction": trend_direction,
        "issue": issue,
    }


# ---------------------------------------------------------------------------
# task 6.3 — Throughput trend (picks/hour)
# ---------------------------------------------------------------------------


def _section_throughput_trend(
    report: "FieldSummary",
    analyzer: "ROS2LogAnalyzer",
    session_duration_s: float,
) -> None:
    """Show picks/hour in 5-minute windows with overall session throughput.

    Raises Low severity issue when last-window throughput drops below 50%
    of peak-window throughput.  Omits when session <10 minutes.
    """
    if session_duration_s < 600:  # 10 minutes
        return

    picks = analyzer.events.picks
    if not picks:
        return

    session_start = analyzer.start_time or 0.0
    window_s = 300  # 5-minute windows

    # Build 5-minute buckets
    buckets: Dict[int, int] = {}
    for p in picks:
        ts = p.get("_ts")
        if ts is None:
            continue
        bucket_idx = int((ts - session_start) / window_s)
        buckets[bucket_idx] = buckets.get(bucket_idx, 0) + 1

    if not buckets:
        return

    # Convert counts to picks/hour
    windows: List[dict] = []
    for idx in sorted(buckets):
        count = buckets[idx]
        picks_per_hour = round(count * (3600.0 / window_s), 1)
        windows.append(
            {
                "window_index": idx,
                "start_min": idx * 5,
                "end_min": (idx + 1) * 5,
                "pick_count": count,
                "picks_per_hour": picks_per_hour,
            }
        )

    # Overall session throughput
    total_picks = len(picks)
    overall_pph = round(3600.0 * total_picks / session_duration_s, 1)

    # Peak and last window analysis
    peak_rate = max(w["picks_per_hour"] for w in windows)
    last_rate = windows[-1]["picks_per_hour"]

    issue: Optional[dict] = None
    if peak_rate > 0 and last_rate < 0.5 * peak_rate:
        issue = {
            "severity": "Low",
            "description": (
                f"Last-window throughput ({last_rate} picks/hr) "
                f"is below 50% of peak ({peak_rate} picks/hr)"
            ),
        }

    report.throughput_trend = {
        "has_data": True,
        "window_minutes": 5,
        "windows": windows,
        "overall_picks_per_hour": overall_pph,
        "peak_picks_per_hour": peak_rate,
        "last_window_picks_per_hour": last_rate,
        "issue": issue,
    }


# ---------------------------------------------------------------------------
# task 6.4 — Stale detection warnings section
# ---------------------------------------------------------------------------


def _section_stale_detection_warnings(
    report: "FieldSummary",
    analyzer: "ROS2LogAnalyzer",
) -> None:
    """Build STALE DETECTION WARNINGS subsection.

    Shows count, first/last timestamps, and staleness duration
    distribution.  Omits when no stale detection warnings present.
    """
    warnings = analyzer.events.stale_detection_warnings
    if not warnings:
        return

    count = len(warnings)
    timestamps = [w.get("_ts") for w in warnings if w.get("_ts") is not None]
    first_ts: Optional[float] = min(timestamps) if timestamps else None
    last_ts: Optional[float] = max(timestamps) if timestamps else None

    # Staleness duration distribution
    ages = [w["reported_age_ms"] for w in warnings if w.get("reported_age_ms") is not None]
    age_stats = _stats(ages) if ages else {"count": 0}

    # Distribution buckets
    buckets = {
        "<100ms": 0,
        "100-500ms": 0,
        "500-2000ms": 0,
        ">2000ms": 0,
    }
    for age in ages:
        if age < 100:
            buckets["<100ms"] += 1
        elif age < 500:
            buckets["100-500ms"] += 1
        elif age < 2000:
            buckets["500-2000ms"] += 1
        else:
            buckets[">2000ms"] += 1

    # Unique source nodes
    source_nodes = sorted(set(w.get("source_node") or "unknown" for w in warnings))

    report.stale_detection_section = {
        "has_data": True,
        "count": count,
        "first_ts": first_ts,
        "last_ts": last_ts,
        "age_stats": age_stats,
        "age_distribution": buckets,
        "source_nodes": source_nodes,
    }


# ---------------------------------------------------------------------------
# task 17.4 — EE start distance section
# ---------------------------------------------------------------------------

_IDLE_MEAN_THRESHOLD_S = 5.0  # mean idle > 5s → Low severity


def _section_ee_start_distance(
    report: "FieldSummary",
    analyzer: "ROS2LogAnalyzer",
) -> None:
    """Build EE START DISTANCE subsection.

    Shows distance distribution stats (mean, min, max, stddev) and
    inter-cycle idle timing from start switch transitions.
    Omits when no EE start distance data available.
    """
    distances = [
        e["distance_mm"]
        for e in analyzer.events.ee_start_distances
        if e.get("distance_mm") is not None
    ]
    switch_events = analyzer.events.start_switch_events

    if not distances and not switch_events:
        return

    # --- Distance distribution ---
    dist_stats: dict = {}
    if distances:
        mean_d = round(_statistics.mean(distances), 1)
        stddev_d = round(_statistics.stdev(distances), 1) if len(distances) >= 2 else 0.0
        dist_stats = {
            "count": len(distances),
            "mean_mm": mean_d,
            "min_mm": round(min(distances), 1),
            "max_mm": round(max(distances), 1),
            "stddev_mm": stddev_d,
        }

    # --- Idle timing from start switch transitions ---
    idle_stats: dict = {}
    idle_times: List[float] = []
    if switch_events:
        # Sort by timestamp
        sorted_sw = sorted(switch_events, key=lambda e: e.get("_ts") or 0)
        # Idle = time between deactivated → next activated
        last_deactivated_ts: Optional[float] = None
        for ev in sorted_sw:
            ts = ev.get("_ts")
            if ts is None:
                continue
            if ev["type"] == "deactivated":
                last_deactivated_ts = ts
            elif ev["type"] == "activated" and last_deactivated_ts is not None:
                gap = ts - last_deactivated_ts
                if gap > 0:
                    idle_times.append(gap)
                last_deactivated_ts = None

    idle_issue: Optional[dict] = None
    if idle_times:
        mean_idle = round(_statistics.mean(idle_times), 2)
        stddev_idle = round(_statistics.stdev(idle_times), 2) if len(idle_times) >= 2 else 0.0
        idle_stats = {
            "count": len(idle_times),
            "mean_s": mean_idle,
            "min_s": round(min(idle_times), 2),
            "max_s": round(max(idle_times), 2),
            "stddev_s": stddev_idle,
        }
        if mean_idle > _IDLE_MEAN_THRESHOLD_S:
            idle_issue = {
                "severity": "Low",
                "description": (
                    f"Mean inter-cycle idle time {mean_idle:.1f}s"
                    f" exceeds {_IDLE_MEAN_THRESHOLD_S}s threshold"
                ),
            }

    report.ee_start_distance = {
        "has_data": True,
        "distance": dist_stats,
        "idle_timing": idle_stats,
        "idle_issue": idle_issue,
        "switch_events_total": len(switch_events),
    }
