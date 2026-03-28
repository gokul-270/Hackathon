"""
Terminal output formatter for field summary reports.

task 16.10 — print_field_summary renders the FieldSummary to stdout.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._helpers import MG6010_ERROR_FLAGS, _safe_pct, decode_error_flags
from ..utils import format_duration as _fmt_dur

if TYPE_CHECKING:
    from ..analyzer import ROS2LogAnalyzer

_LINE = "\u2500" * 72


def _hr() -> None:
    print(_LINE)


def _hdr(title: str) -> None:
    print(f"\n{'\u2550' * 72}")
    print(f"  {title}")
    print(f"{'\u2550' * 72}")


def _sub(title: str) -> None:
    print(f"\n  \u2500\u2500 {title}")


def _row(label: str, value: Any, indent: int = 4) -> None:
    pad = " " * indent
    print(f"{pad}{label:<40}{value}")


# ---------------------------------------------------------------------------
# task 14.3 — mode-aware section filtering
# ---------------------------------------------------------------------------

# Sections that should be omitted entirely in bench mode
_BENCH_OMIT_SECTIONS = frozenset({
    "VEHICLE PERFORMANCE",
    "COORDINATION CYCLES",
    "VEHICLE STATE TRANSITIONS",
    "ARM-VEHICLE COORDINATION",
    "VEHICLE MOTOR HEALTH",
})

# Sections that should be downgraded (show a placeholder) in bench mode
_BENCH_DOWNGRADE_SECTIONS = frozenset({
    "COMMUNICATION HEALTH (MQTT)",
})


def mode_filter(section_name: str, mode: str) -> str:
    """Return rendering disposition for *section_name* given *mode*.

    Returns one of:
      - ``"omit"``      — skip the section entirely
      - ``"downgrade"`` — show a brief placeholder instead of full data
      - ``"show"``      — render normally
    """
    if mode == "bench":
        if section_name in _BENCH_OMIT_SECTIONS:
            return "omit"
        if section_name in _BENCH_DOWNGRADE_SECTIONS:
            return "downgrade"
    return "show"


# ---------------------------------------------------------------------------
# ARM_client health rendering (tasks 6.1-6.3)
# ---------------------------------------------------------------------------


def _print_arm_client_health(s: Any) -> None:
    """Render MQTT HEALTH, SERVICE HEALTH, ERROR RECOVERY per arm."""
    mqtt = s.mqtt_health
    svc = s.service_health
    recovery = s.error_recovery

    if not mqtt and not svc and not recovery:
        return

    # Collect all arm IDs across the three dicts
    arm_ids = sorted(
        set(mqtt) | set(svc) | set(recovery)
    )

    for arm_id in arm_ids:
        arm_mqtt = mqtt.get(arm_id)
        arm_svc = svc.get(arm_id)
        arm_rec = recovery.get(arm_id)

        if arm_mqtt:
            _sub(f"MQTT HEALTH ({arm_id})")
            _row(
                "Connects/Disconnects/Timeouts:",
                f"{arm_mqtt['connects']}"
                f" | {arm_mqtt['disconnects']}"
                f" | {arm_mqtt['timeouts']}",
            )
            longest = arm_mqtt.get("longest_disconnect_s", 0.0)
            if longest > 0:
                _row(
                    "Longest disconnection:",
                    f"{longest:.1f}s",
                )
            _row(
                "Last status:",
                arm_mqtt.get("last_status", "unknown"),
            )

        if arm_svc:
            _sub(f"SERVICE HEALTH ({arm_id})")
            svc_detail = arm_svc.get("by_service", {})
            svc_parts = [
                f"{cnt} ({name})"
                for name, cnt in sorted(
                    svc_detail.items(), key=lambda x: -x[1]
                )
            ]
            _row(
                "Service failures:",
                ", ".join(svc_parts)
                if svc_parts
                else arm_svc.get("total_failures", 0),
            )
            exhausted = arm_svc.get("retry_exhaustion", False)
            _row(
                "Retry exhaustion:",
                "Yes" if exhausted else "No",
            )

        if arm_rec:
            _sub(f"ERROR RECOVERY ({arm_id})")
            _row(
                "Error states/Recovery attempts:",
                f"{arm_rec.get('error_states', 0)}"
                f" | {arm_rec.get('recovery_attempts', 0)}",
            )
            succ = arm_rec.get("succeeded", 0)
            fail = arm_rec.get("failed", 0)
            _row(
                "Outcomes:",
                f"{succ} succeeded, {fail} failed",
            )


# ---------------------------------------------------------------------------
# Correlation findings rendering (task 6.4)
# ---------------------------------------------------------------------------


def _print_correlation_findings(s: Any) -> None:
    """Render CROSS-LOG CORRELATIONS section."""
    findings = s.correlation_findings
    if not findings:
        return

    _hdr("CROSS-LOG CORRELATIONS")
    for f in findings:
        sev = f.get("severity", "INFO")
        title = f.get("title", "")
        desc = f.get("description", "")
        display = desc if desc else title
        print(f"    [{sev}] {display}")


# ---------------------------------------------------------------------------
# Verbose diagnostics rendering (task 6.5)
# ---------------------------------------------------------------------------


def _print_verbose_diagnostics(s: Any) -> None:
    """Render PARSE DIAGNOSTICS, SUPPRESSED FINDINGS, CORRELATION DETAILS."""
    parse = s.verbose_parse_stats
    if parse:
        _hdr("PARSE DIAGNOSTICS")
        for p in parse:
            fname = p.get("file", "unknown")
            total_lines = p.get("total_lines", 0)
            parsed = p.get("parsed", 0)
            ros2 = p.get("ros2", 0)
            python = p.get("python", 0)
            journalctl = p.get("journalctl", 0)
            print(
                f"    {fname}: {total_lines} lines,"
                f" {parsed} parsed"
                f" (ROS2: {ros2},"
                f" Python: {python},"
                f" journalctl: {journalctl})"
            )

    suppressed = s.verbose_suppressed
    if suppressed:
        _hdr(f"SUPPRESSED FINDINGS ({len(suppressed)} total)")
        from collections import Counter

        reason_counts = Counter(
            sf.get("reason", "") for sf in suppressed
        )
        for reason, count in reason_counts.items():
            suffix = f" (x{count})" if count > 1 else ""
            print(f"    [{reason}]{suffix}")

    corr = s.verbose_correlation_details
    if corr:
        _hdr("CORRELATION DETAILS")
        for cd in corr:
            desc = cd.get("description", "")
            result = cd.get("result", "")
            print(f"    {desc} = {result}")


def print_field_summary(
    analyzer: "ROS2LogAnalyzer", verbose: bool = False,
) -> None:
    """
    task 16.10 — Print the field summary to stdout.

    Generates the summary if not already done, then formats it.
    """
    from . import generate_field_summary

    if analyzer.field_summary is None:
        analyzer.field_summary = generate_field_summary(
            analyzer, verbose=verbose,
        )

    s = analyzer.field_summary

    # task 16.3 — executive summary as first prominent line
    exec_summary = getattr(analyzer, "_last_executive_summary", None)
    if not exec_summary:
        # Try to get from the most recent report stored on the analyzer
        report = getattr(analyzer, "_last_report", None)
        if report and hasattr(report, "executive_summary"):
            exec_summary = report.executive_summary
    if exec_summary:
        print(f"\n\033[1m  {exec_summary}\033[0m")
        print()

    # task 14.4 — mode indicator in field summary header
    report = getattr(analyzer, "_last_report", None)
    _session_mode = getattr(analyzer, "_session_mode", "")
    _session_mode_source = getattr(
        analyzer, "_session_mode_source", ""
    )
    if not _session_mode and report:
        _session_mode = getattr(report, "session_mode", "")
        _session_mode_source = getattr(
            report, "session_mode_source", ""
        )
    if _session_mode:
        source_label = (
            "auto-detected"
            if _session_mode_source == "auto"
            else "user override"
        )
        print(f"   Mode: {_session_mode} ({source_label})\n")

    _hdr("PICK PERFORMANCE")
    pp = s.pick_performance
    _row("Total picks:", pp.get("total", 0))
    _row("  Succeeded:", pp.get("succeeded", 0))
    _row("  Failed:", pp.get("failed", 0))
    _row("Success rate:", f"{pp.get('success_rate_pct', 0.0)}%")
    _row("Throughput:", f"{pp.get('picks_per_hour', 0.0)} picks/hour")

    # tasks 4.2-4.3 — multi-arm ARM SUMMARY table + per-arm sub-sections
    if pp.get("multi_arm"):
        _sub("ARM SUMMARY")
        arm_tbl = pp.get("arm_summary_table", [])
        worst_arm = pp.get("worst_arm")
        print(
            f"    {'Arm':<10}  {'Total':>6}  {'Succ':>6}  {'Fail':>6}  "
            f"{'Rate%':>7}  {'AvgCycle':>10}"
        )
        print(
            f"    {'\u2500' * 10:<10}  {'\u2500' * 6:>6}  {'\u2500' * 6:>6}"
            f"  {'\u2500' * 6:>6}  "
            f"{'\u2500' * 7:>7}  {'\u2500' * 10:>10}"
        )
        for row in arm_tbl:
            marker = " [worst]" if row["arm"] == worst_arm else ""
            avg_c = row.get("avg_cycle_time_ms")
            avg_str = f"{avg_c:.0f}ms" if avg_c else "n/a"
            print(
                f"    {row['arm']:<10}  {row['total']:>6}"
                f"  {row['succeeded']:>6}  "
                f"{row['failed']:>6}"
                f"  {row['success_rate_pct']:>6.1f}%"
                f"  {avg_str:>10}"
                f"{marker}"
            )

        for arm_id, arm_pp in pp.get("per_arm", {}).items():
            _sub(f"ARM {arm_id.upper()}")
            _row(
                "  Total picks:",
                arm_pp.get("total", 0),
                indent=4,
            )
            _row(
                "  Succeeded:",
                arm_pp.get("succeeded", 0),
                indent=4,
            )
            _row("  Failed:", arm_pp.get("failed", 0), indent=4)
            _row(
                "  Success rate:",
                f"{arm_pp.get('success_rate_pct', 0.0)}%",
                indent=4,
            )
            _row(
                "  Throughput:",
                f"{arm_pp.get('picks_per_hour', 0.0)} picks/hour",
                indent=4,
            )
            arm_ct = arm_pp.get("cycle_time_ms", {})
            if arm_ct.get("count"):
                _row(
                    "  Cycle time p50/p95/max (ms):",
                    f"{arm_ct.get('p50')}/{arm_ct.get('p95')}"
                    f"/{arm_ct.get('max')}",
                    indent=4,
                )
            arm_ph = arm_pp.get("phase_breakdown", {})
            if arm_ph:
                for phase, pst in arm_ph.items():
                    if pst.get("count"):
                        _row(
                            f"  {phase} avg:",
                            pst.get("avg"),
                            indent=4,
                        )
            arm_da = arm_pp.get("detection_age_ms", {})
            if arm_da.get("count"):
                _row(
                    "  Detection age avg/max (ms):",
                    f"{arm_da.get('avg')}/{arm_da.get('max')}",
                    indent=4,
                )
            ee_per_pick = arm_pp.get("mean_ee_on_ms_per_pick")
            if ee_per_pick is not None:
                _row(
                    "  Mean EE on-time/pick (ms):",
                    ee_per_pick,
                    indent=4,
                )

    else:
        # task 4.4 — single-arm: render as before
        ct = pp.get("cycle_time_ms", {})
        if ct.get("count"):
            _sub("Cycle time (ms)")
            _row("  avg:", ct.get("avg"))
            _row("  p50:", ct.get("p50"))
            _row("  p95:", ct.get("p95"))
            _row("  max:", ct.get("max"))

        ph = pp.get("phase_breakdown", {})
        if ph:
            _sub("Phase breakdown (avg ms)")
            for phase, stats in ph.items():
                if stats.get("count"):
                    _row(f"  {phase}:", stats.get("avg"))

    wasted = pp.get("estimated_wasted_detections_pct")
    if wasted is not None:
        _sub("Detection efficiency")
        _row("  Estimated wasted detections:", f"{wasted}%")
        _row(
            "  Note:",
            pp.get("estimated_wasted_detections_note", ""),
        )

    # task 15.2 — stale detection age
    stale_pct = pp.get("stale_detection_pct")
    if stale_pct is not None:
        _sub("Detection age (stale picks)")
        _row("  Stale picks (>2s):", f"{stale_pct}%")
        sev_stale = pp.get("severely_stale_count", 0)
        if sev_stale:
            _row(
                "  Note:",
                f"(severely stale: {sev_stale} picks"
                f" had detection age > 10s)",
            )

    # task 14.5 — EE short retract note
    ee_sr_note = pp.get("ee_short_retract_note", "")
    if ee_sr_note:
        _sub("EE retract")
        _row("  Note:", ee_sr_note)

    aruco = pp.get("aruco_mentions")
    _sub("ArUco detection")
    if aruco == "not instrumented":
        _row("  Status:", "not instrumented (Gap 20)")
    else:
        _row("  Mentions in log:", aruco)

    ee_duty = pp.get("ee_duty_cycle_pct")
    if ee_duty is not None:
        _sub("End-effector (compressor)")
        _row("  Duty cycle:", f"{ee_duty}%")

    pos = pp.get("position_tracking")
    _sub("Position tracking")
    if pos == "not instrumented":
        _row("  Status:", "not instrumented (Gap 22)")
    else:
        _row(
            "  Unique positions seen:",
            len(pos) if isinstance(pos, dict) else pos,
        )

    # --- Pick failure analysis ---
    if s.pick_failure_analysis:
        _hdr("PICK FAILURE ANALYSIS")
        pfa = s.pick_failure_analysis
        _row(
            "Text-based failure events:",
            pfa.get("text_failure_count", 0),
        )
        _row(
            "Emergency shutdowns:",
            pfa.get("emergency_shutdowns", 0),
        )
        _row(
            "E-stop events (state machine):",
            pfa.get("estop_events", 0),
        )
        by_phase = pfa.get("failure_by_phase", {})
        if by_phase:
            _sub("Failures by phase")
            for phase, cnt in sorted(
                by_phase.items(), key=lambda x: -x[1]
            ):
                _row(f"  {phase}:", cnt)
        top = pfa.get("top_failure_reasons", [])
        if top:
            _sub("Top failure reasons")
            for reason, cnt in top[:5]:
                _row(f"  {reason[:38]}:", cnt)
        overhead = pfa.get("recovery_overhead_pct")
        if overhead is not None:
            _row("Recovery time overhead:", f"{overhead}%")
        # task 7.1 — per-arm sub-sections when multi-arm
        if pfa.get("multi_arm") and pfa.get("per_arm"):
            _sub("Per-arm breakdown")
            for arm_id, arm_pfa in sorted(pfa["per_arm"].items()):
                _row(
                    f"  {arm_id} failures:",
                    arm_pfa.get("failures", 0),
                )
                _row(
                    f"  {arm_id} motor alerts:",
                    arm_pfa.get("motor_alerts", 0),
                )
                _row(
                    f"  {arm_id} emergency shutdowns:",
                    arm_pfa.get("emergency_shutdowns", 0),
                )

    # --- Vehicle performance ---
    _vp_filter = mode_filter("VEHICLE PERFORMANCE", _session_mode)
    if _vp_filter != "omit":
        _hdr("VEHICLE PERFORMANCE")
        vp = s.vehicle_performance
        _row("Drive commands:", vp.get("drive_commands", 0))
        _row(
            "Total distance:",
            f"{vp.get('total_distance_m', 0.0)} m",
        )
        _row(
            "Position reached rate:",
            f"{vp.get('position_reached_rate_pct', 0.0)}%",
        )
        _row("Steering commands:", vp.get("steering_commands", 0))
        _row("cmd_vel commands:", vp.get("cmd_vel_count", 0))

        state_time = vp.get("time_in_state_s", {})
        if state_time:
            _sub("Time in state (s)")
            for state, secs in sorted(
                state_time.items(), key=lambda x: -x[1]
            ):
                _row(f"  {state}:", f"{secs:.1f}s")

        cvl = vp.get("cmd_vel_latency_ms", {})
        if cvl.get("count"):
            _sub("cmd_vel latency (ms)")
            _row("  avg:", cvl.get("avg"))
            _row("  p95:", cvl.get("p95"))

    # --- Arm state ---
    if s.arm_state:
        _hdr("ARM STATE")
        arm_s = s.arm_state
        _row(
            "State transitions:",
            arm_s.get("transition_count", 0),
        )
        _row(
            "Longest error duration:",
            f"{arm_s.get('longest_error_s', 0.0):.1f}s",
        )
        arm_time = arm_s.get("time_in_state_s", {})
        if arm_time:
            _sub("Time in arm state (s)")
            for state, secs in sorted(
                arm_time.items(), key=lambda x: -x[1]
            ):
                _row(f"  {state}:", f"{secs:.1f}s")
        # task 7.3 — per-arm sub-sections when multi-arm
        if arm_s.get("multi_arm") and arm_s.get("per_arm"):
            _sub("Per-arm arm state")
            for aid, arm_state_data in sorted(
                arm_s["per_arm"].items()
            ):
                _row(
                    f"  {aid} transitions:",
                    arm_state_data.get("transition_count", 0),
                )
                _row(
                    f"  {aid} longest error:",
                    f"{arm_state_data.get('longest_error_s', 0.0):.1f}s",
                )
                for state, secs in sorted(
                    arm_state_data.get(
                        "time_in_state_s", {}
                    ).items(),
                    key=lambda x: -x[1],
                ):
                    _row(f"    {aid}/{state}:", f"{secs:.1f}s")

    # --- Motor health --- (tasks 5.1-5.3, 6.3)
    _hdr("MOTOR HEALTH")
    mh = s.motor_health_trends

    arm_mh = mh.get("arm", {})
    multi_arm_mh = mh.get("multi_arm", False)
    if arm_mh:
        if multi_arm_mh:
            # task 5.2 — per-arm sub-sections
            for arm_id, joint_map in sorted(arm_mh.items()):
                _sub(f"Arm {arm_id} motors (per joint)")
                for joint, fields in joint_map.items():
                    temp_stats = fields.get("temp_c", {})
                    err = fields.get("err_decoded") or fields.get(
                        "err_flags", {}
                    )
                    if temp_stats.get("count"):
                        _row(
                            f"  {joint} temp (\u00b0C):",
                            f"avg={temp_stats.get('avg')}"
                            f" max={temp_stats.get('max')}",
                        )
                    if isinstance(err, str) and err != "none":
                        _row(f"  {joint} errors:", err)
        else:
            # task 5.3 — single-arm: render as before (unlabelled)
            _sub("Arm motors (per joint)")
            for joint, fields in arm_mh.items():
                temp_stats = fields.get("temp_c", {})
                err = fields.get("err_decoded") or fields.get(
                    "err_flags", {}
                )
                if temp_stats.get("count"):
                    _row(
                        f"  {joint} temp (\u00b0C):",
                        f"avg={temp_stats.get('avg')}"
                        f" max={temp_stats.get('max')}",
                    )
                if isinstance(err, str) and err != "none":
                    _row(f"  {joint} errors:", err)

    # task 6.3 — vehicle motor data in VEHICLE MOTOR HEALTH section

    # Motor reliability (task 24.3)
    if s.motor_reliability:
        _sub("Motor reliability (from text patterns)")
        for motor_id, rel in s.motor_reliability.items():
            if rel.get("failure_count") or rel.get("timeout"):
                _row(
                    f"  {motor_id} failures:",
                    rel.get("failure_count"),
                )
                _row(
                    f"  {motor_id} timeout rate:",
                    f"{rel.get('timeout_rate_pct')}%",
                )

    # --- Vehicle motor health (task 6.2) ---
    veh_detail = mh.get("vehicle_detail", {})
    if (
        veh_detail.get("has_data")
        and mode_filter("VEHICLE MOTOR HEALTH", _session_mode)
        != "omit"
    ):
        _hdr("VEHICLE MOTOR HEALTH")
        hs = veh_detail.get("health_score", {})
        if hs.get("count"):
            _row("Health score avg:", hs.get("avg"))
            _row("Health score min:", hs.get("min"))
        per_m = veh_detail.get("per_motor", {})
        if per_m:
            _sub("Per-motor stats")
            for key, st in per_m.items():
                if st.get("count"):
                    _row(
                        f"  {key}:",
                        f"avg={st.get('avg')} max={st.get('max')}",
                    )
        el = veh_detail.get("enable_latency_ms", {})
        if el.get("count"):
            _sub("Enable service latency (ms)")
            _row("  avg:", el.get("avg"))
            _row("  max:", el.get("max"))

    # --- Startup / shutdown ---
    _hdr("STARTUP / SHUTDOWN")
    ss = s.startup_shutdown
    restarts = ss.get("restart_count", 0)
    _row("Session restarts:", restarts)
    startup = ss.get("startup", {})
    st_total = startup.get("total_ms", {})
    if st_total.get("count"):
        _row("Startup total:", f"{st_total.get('avg')}ms avg")
        hw = startup.get("hardware_init_ms", {})
        if hw.get("count"):
            _row("  hardware_init:", f"{hw.get('avg')}ms")
        mc = startup.get("motor_controller_init_ms", {})
        if mc.get("count"):
            _row("  motor_controller_init:", f"{mc.get('avg')}ms")

    # --- Coordination ---
    if mode_filter(
        "ARM-VEHICLE COORDINATION", _session_mode
    ) != "omit":
        _hdr("ARM-VEHICLE COORDINATION")
        coord = s.coordination
        _row(
            "Coordination cycles:",
            coord.get("coordination_cycles", 0),
        )
        _row(
            "Picks during vehicle motion:",
            coord.get("picks_during_vehicle_motion", 0),
        )
        vs = coord.get("vehicle_stop_ms", {})
        if vs.get("count"):
            _row("Vehicle stop ms (avg):", vs.get("avg"))
        ap = coord.get("arm_phase_ms", {})
        if ap.get("count"):
            _row("Arm phase ms (avg):", ap.get("avg"))

        pick_by_state = coord.get(
            "pick_success_by_vehicle_state", {}
        )
        if pick_by_state:
            _sub("Pick success rate by vehicle state")
            for state, data in pick_by_state.items():
                total_p = data.get("total", 0)
                succ_p = data.get("succeeded", 0)
                pct = _safe_pct(succ_p, total_p)
                _row(
                    f"  {state}:",
                    f"{succ_p}/{total_p} ({pct}%)",
                )

    # --- Camera reliability ---
    _hdr("CAMERA RELIABILITY")
    cr = s.camera_reliability
    _row("Reconnections:", cr.get("reconnection_count", 0))
    if cr.get("reconnection_count", 0) > 0:
        _row("  XLink triggers:", cr.get("xlink_triggers", 0))
        _row(
            "  Timeout triggers:",
            cr.get("timeout_triggers", 0),
        )
        mtbr = cr.get("mean_time_between_reconnections_s")
        if mtbr:
            _row("  MTBR:", f"{mtbr}s")

    # --- Network health ---
    _hdr("NETWORK HEALTH")
    nh = s.network_health
    pr = nh.get("ping_router_ms", {})
    if pr.get("count"):
        _row("Ping router (ms avg):", pr.get("avg"))
        _row(
            "Router packet loss:",
            f"{nh.get('ping_router_loss_pct', 0.0)}%",
        )
    pb = nh.get("ping_broker_ms", {})
    if pb.get("count"):
        _row("Ping broker (ms avg):", pb.get("avg"))
        _row(
            "Broker packet loss:",
            f"{nh.get('ping_broker_loss_pct', 0.0)}%",
        )
    _row("Eth Rx errors:", nh.get("eth_rx_errors", 0))
    _row("Eth Tx errors:", nh.get("eth_tx_errors", 0))
    _row("Eth drops:", nh.get("eth_drops", 0))
    _row("Link state changes:", nh.get("eth_link_changes", 0))
    cpu = nh.get("cpu_temp_c", {})
    if cpu.get("count"):
        _row("CPU temp (\u00b0C avg):", cpu.get("avg"))

    # --- Communication health ---
    _mqtt_filter = mode_filter(
        "COMMUNICATION HEALTH (MQTT)", _session_mode
    )
    _hdr("COMMUNICATION HEALTH (MQTT)")
    if _mqtt_filter == "downgrade":
        _row("MQTT:", "not applicable (bench mode)")
    else:
        ch = s.communication_health
        # task 15.4 — show status note when MQTT was not established
        mqtt_note = ch.get("mqtt_status_note")
        if mqtt_note:
            _row("MQTT uptime:", mqtt_note)
        else:
            _row(
                "MQTT uptime:",
                f"{ch.get('mqtt_uptime_pct', 100.0)}%",
            )
        _row("Connects:", ch.get("mqtt_connects", 0))
        _row("Disconnects:", ch.get("mqtt_disconnects", 0))
        _row(
            "  Unexpected:",
            ch.get("unexpected_disconnects", 0),
        )
        _row(
            "Publish failures:",
            ch.get("publish_failures", 0),
        )
        mtbf = ch.get("mtbf_s")
        if mtbf:
            _row("MTBF:", f"{mtbf}s")
        _row(
            "Broker restarts:",
            ch.get("broker_restarts", 0),
        )
        _row(
            "Broker socket errors:",
            ch.get("broker_socket_errors", 0),
        )
        per_arm = ch.get("per_arm_status", {})
        if per_arm:
            _sub("Per-arm status (last seen)")
            for arm_id, status in per_arm.items():
                _row(f"  arm {arm_id}:", status)
        # task 7.2 — per-arm MQTT sub-table
        if ch.get("multi_arm") and ch.get("per_arm_mqtt"):
            _sub("Per-arm MQTT stats")
            print(
                f"    {'Arm':<12}  {'Conn':>5}"
                f"  {'Disc':>5}"
                f"  {'Unexp':>5}  {'PubFail':>7}"
            )
            print(
                f"    {'\u2500' * 12:12}"
                f"  {'\u2500' * 4:>5}"
                f"  {'\u2500' * 4:>5}"
                f"  {'\u2500' * 5:>5}"
                f"  {'\u2500' * 7:>7}"
            )
            for aid, arm_mqtt in sorted(
                ch["per_arm_mqtt"].items()
            ):
                unexp = arm_mqtt["unexpected_disconnects"]
                pubf = arm_mqtt["publish_failures"]
                print(
                    f"    {str(aid):<12}"
                    f"  {arm_mqtt['connects']:>5}  "
                    f"{arm_mqtt['disconnects']:>5}"
                    f"  {unexp:>5}  "
                    f"{pubf:>7}"
                )

    # --- ARM_client health (tasks 6.1-6.3) ---
    _print_arm_client_health(s)

    # --- Hourly throughput ---
    if s.hourly_throughput:
        _hdr("HOURLY THROUGHPUT")

        def _print_hourly_table(
            rows: list, label: str = ""
        ) -> None:
            if label:
                _sub(label)
            print(
                f"    {'Hour':>4}  {'Picks':>6}  {'Succ':>6}"
                f"  {'Rate%':>6}  {'AvgCycle':>10}"
            )
            print(
                f"    {'\u2500' * 4:>4}  {'\u2500' * 5:>6}"
                f"  {'\u2500' * 4:>6}  {'\u2500' * 5:>6}"
                f"  {'\u2500' * 8:>10}"
            )
            for b in rows:
                avg_c = b.get("avg_cycle_time_ms")
                avg_str = (
                    f"{avg_c:.0f}ms" if avg_c else "n/a"
                )
                print(
                    f"    {b['hour']:>4}"
                    f"  {b['picks_total']:>6}  "
                    f"{b['picks_succeeded']:>6}"
                    f"  {b['success_rate_pct']:>6.1f}  "
                    f"{avg_str:>10}"
                )

        # task 7.4 — per-arm tables when multi-arm
        per_arm_hourly = getattr(
            s, "_hourly_throughput_per_arm", {}
        )
        if per_arm_hourly:
            _print_hourly_table(
                s.hourly_throughput, label="All arms combined"
            )
            for arm_id, arm_rows in sorted(
                per_arm_hourly.items()
            ):
                if arm_rows:
                    _print_hourly_table(
                        arm_rows, label=f"Arm {arm_id}"
                    )
        else:
            _print_hourly_table(s.hourly_throughput)

    # --- Trend alerts ---
    if s.trend_alerts:
        _hdr("TREND ALERTS")
        for alert in s.trend_alerts:
            print(f"  [!] {alert.get('description', '')}")

    # --- Launch health (task 13.6) ---
    lh = s.launch_health
    if lh.get("has_data"):
        _hdr("LAUNCH HEALTH")
        dur_s = lh.get("session_duration_s")
        if dur_s is not None:
            _row("Session duration:", _fmt_dur(dur_s))
        processes = lh.get("processes", [])
        if processes:
            print(
                f"  {'Node':<22}  {'PID':>6}  {'Start':>10}"
                f"  {'Status':<30}  {'Uptime':<12}"
            )
            print(
                f"  {'\u2500' * 22}  {'\u2500' * 6}  {'\u2500' * 10}"
                f"  {'\u2500' * 30}  {'\u2500' * 12}"
            )
            for proc in processes:
                name = proc.get("name", "?")[:22]
                pid = proc.get("pid", "?")
                start_ts = proc.get("start_ts")
                start_str = (
                    f"{start_ts:.0f}" if start_ts else "?"
                )
                status = proc.get("status", "?")
                exit_code = proc.get("exit_code")
                lifetime_s = proc.get("lifetime_s")

                if (
                    status == "crashed"
                    and exit_code is not None
                ):
                    status_str = f"CRASHED (exit {exit_code})"
                elif status == "still_running":
                    status_str = "running at shutdown"
                else:
                    status_str = "clean exit"

                uptime_str = ""
                if lifetime_s is not None:
                    uptime_str = _fmt_dur(lifetime_s)

                print(
                    f"  {name:<22}  {str(pid):>6}"
                    f"  {start_str:>10}"
                    f"  {status_str:<30}"
                    f"  {uptime_str:<12}"
                )

                hint = proc.get("external_log_hint")
                has_ros2_log = proc.get("has_ros2_log", True)
                if status == "crashed":
                    if hint:
                        print(f"    -> See {hint} for details")
                    if not has_ros2_log:
                        print(
                            "    -> No ROS2 log file found"
                            " in session directory"
                        )

    # --- Joint limit analysis (task 16.5) ---
    bi = s.build_info
    if bi.get("has_data"):
        _hdr("BUILD INFO")
        nodes = bi.get("nodes", [])
        print(
            f"  {'Node':<24}  {'Built At':<22}"
            f"  {'Git Hash':<14}  {'Branch':<16}"
            f"  {'Flags'}"
        )
        print(
            f"  {'\u2500' * 24}  {'\u2500' * 22}"
            f"  {'\u2500' * 14}  {'\u2500' * 16}"
            f"  {'\u2500' * 12}"
        )
        for n in nodes:
            flags = []
            if n.get("stale"):
                flags.append("[STALE]")
            if n.get("dirty"):
                flags.append("[DIRTY]")
            flags_str = " ".join(flags)
            print(
                f"  {n['node']:<24}"
                f"  {n['built_at']:<22}"
                f"  {n.get('git_hash', '') or '-':<14}"
                f"  {n.get('branch', '') or '-':<16}"
                f"  {flags_str}"
            )

    if s.joint_limits:
        _hdr("JOINT LIMIT ANALYSIS")
        jl = s.joint_limits
        _row(
            "Total violations:",
            jl.get("total_violations", 0),
        )
        running_total = jl.get("joint_limit_total", 0)
        if running_total and running_total != jl.get(
            "total_violations", 0
        ):
            _row("  (running counter):", running_total)
        by_joint = jl.get("by_joint", {})
        if by_joint:
            _sub("Per-joint")
            for joint, cnt in sorted(by_joint.items()):
                _row(f"  {joint}:", cnt)
        by_dir = jl.get("by_direction", {})
        if by_dir:
            _sub("By direction")
            for direction, cnt in sorted(by_dir.items()):
                _row(f"  {direction}:", cnt)
        max_ov = jl.get("max_overshoot_m", 0.0)
        if max_ov:
            _row("Max overshoot:", f"{max_ov:.4f}m")

    # --- Camera health (task 17.4) ---
    if s.camera_health:
        _hdr("CAMERA HEALTH")
        ch = s.camera_health
        _row(
            "Stat blocks parsed:",
            ch.get("total_blocks", 0),
        )
        _row(
            "Total detection requests:",
            ch.get("total_requests", 0),
        )
        _row(
            "With-cotton rate:",
            f"{ch.get('with_cotton_rate_pct', 0.0)}%",
        )
        note = ch.get("never_detected_note", "")
        if note:
            _row("  Note:", note)
        lms = ch.get("latency_ms", {})
        lms_max = ch.get("latency_max_ms", {})
        if lms.get("count"):
            _row(
                "Latency avg/max (ms):",
                f"{lms.get('avg')}/{lms_max.get('max')}",
            )
        fw = ch.get("frame_wait_ms", {})
        fw_max = ch.get("frame_wait_max_ms", {})
        if fw.get("count"):
            _row(
                "Frame wait avg/max (ms):",
                f"{fw.get('avg')}/{fw_max.get('max')}",
            )
        tmp = ch.get("temp_c", {})
        if tmp.get("count"):
            _row(
                "Temp range (\u00b0C):",
                f"{tmp.get('min')}\u2013{tmp.get('max')}",
            )
        css = ch.get("css_pct", {})
        if css.get("count"):
            _row("OAK-D CSS avg (%):", css.get("avg"))
        mss = ch.get("mss_pct", {})
        if mss.get("count"):
            _row("OAK-D MSS avg (%):", mss.get("avg"))

    # --- Scan effectiveness (task 18.5) ---
    if s.scan_effectiveness:
        _hdr("SCAN EFFECTIVENESS")
        se = s.scan_effectiveness
        _row("Total scans:", se.get("total_scans", 0))
        _row(
            "Total cotton found:",
            se.get("total_cotton_found", 0),
        )
        _row(
            "Total cotton picked:",
            se.get("total_cotton_picked", 0),
        )
        by_pos = se.get("by_position", {})
        if by_pos:
            _sub(
                "Per-position (J4 offset \u2192 found/picked)"
            )
            def _pos_sort_key(kv):
                """Sort mm-suffixed keys numerically, others lexically."""
                k = kv[0]
                if k.endswith("mm"):
                    try:
                        return (0, float(k[:-2]))
                    except ValueError:
                        pass
                return (1, k)

            for pos_key, stats in sorted(
                by_pos.items(), key=_pos_sort_key
            ):
                _row(
                    f"  {pos_key}:",
                    f"found={stats['found']}"
                    f"  picked={stats['picked']}",
                )
        best = se.get("best_position")
        worst = se.get("worst_position")
        if best:
            _row("Best position:", best)
        if worst and worst != best:
            _row("Worst position:", worst)

    # --- Motor homing (task 19.4) ---
    if s.motor_homing:
        _hdr("MOTOR HOMING")
        mh = s.motor_homing
        _row("Homing events:", mh.get("total_events", 0))
        jtbl = mh.get("joint_table", [])
        if jtbl:
            _sub("Per-joint")
            for jrow in jtbl:
                homed_str = (
                    "YES" if jrow.get("homed") else "NO"
                )
                err = jrow.get("position_error")
                tol = jrow.get("tolerance")
                ratio = jrow.get("err_tol_ratio_pct")
                warn = (
                    " [NEAR LIMIT]"
                    if jrow.get("near_tolerance")
                    else ""
                )
                err_str = (
                    f"err={err:.4f} tol={tol:.4f}"
                    f" ({ratio:.1f}%){warn}"
                    if err is not None
                    and tol is not None
                    and ratio is not None
                    else "no verify data"
                )
                _row(
                    f"  {jrow['joint']}:",
                    f"homed={homed_str}  {err_str}",
                )

    # --- Per-joint timing (task 20.6) ---
    if s.per_joint_timing:
        _hdr("PER-JOINT TIMING")
        pjt = s.per_joint_timing
        approach = pjt.get("joint_approach_stats", {})
        bottleneck = pjt.get("bottleneck_joint")
        if approach:
            _sub("Approach time per joint (ms)")
            for joint, st in sorted(approach.items()):
                if st.get("count"):
                    marker = (
                        " [bottleneck]"
                        if joint == bottleneck
                        else ""
                    )
                    _row(
                        f"  {joint} p50/p95/max:",
                        f"{st.get('p50')}/{st.get('p95')}"
                        f"/{st.get('max')}{marker}",
                    )
        retreat = pjt.get("retreat_stats", {})
        if retreat:
            _sub("Retreat breakdown (ms)")
            for comp, st in sorted(retreat.items()):
                if st.get("count"):
                    _row(
                        f"  {comp} p50/max:",
                        f"{st.get('p50')}/{st.get('max')}",
                    )
        ee_on = pjt.get("ee_on_stats", {})
        if ee_on.get("count"):
            _sub("EE ON duration (ms)")
            _row(
                "  p50/p95/max:",
                f"{ee_on.get('p50')}/{ee_on.get('p95')}"
                f"/{ee_on.get('max')}",
            )
        j5_ee_bd = pjt.get("j5_ee_breakdown", {})
        if j5_ee_bd:
            _sub("J5+EE approach breakdown (ms)")
            labels = {
                "j5_travel_ms": "J5 travel",
                "ee_pretravel_ms": "EE pre-travel (J5 move before EE ON)",
                "ee_overlap_ms": "EE overlap (EE ON while J5 moving)",
                "ee_dwell_ms": "EE dwell (at cotton before retreat)",
            }
            for key in (
                "j5_travel_ms",
                "ee_pretravel_ms",
                "ee_overlap_ms",
                "ee_dwell_ms",
            ):
                st = j5_ee_bd.get(key, {})
                if st.get("count"):
                    label = labels.get(key, key)
                    _row(
                        f"  {label} p50/p95:",
                        f"{st.get('p50')}/{st.get('p95')}",
                    )

    # --- Detection quality (task 21.6) ---
    if s.detection_quality:
        _hdr("DETECTION QUALITY")
        dq = s.detection_quality
        _row(
            "Total requests:",
            dq.get("total_requests", 0),
        )
        _row(
            "Total raw detections:",
            dq.get("total_raw", 0),
        )
        _row("Total accepted:", dq.get("total_accepted", 0))
        _row(
            "Acceptance rate:",
            f"{dq.get('acceptance_rate_pct', 0.0)}%",
        )
        _row(
            "Border skip rate:",
            f"{dq.get('border_skip_rate_pct', 0.0)}%",
        )
        _row(
            "Not-pickable rate:",
            f"{dq.get('not_pickable_rate_pct', 0.0)}%",
        )
        fallback = dq.get("fallback_position_count", 0)
        if fallback:
            _row("Fallback positions used:", fallback)
        avg_stale = dq.get(
            "avg_stale_flushed_per_request", 0.0
        )
        if avg_stale:
            _row("Avg stale frames flushed/req:", avg_stale)
        avg_wait = dq.get("avg_frame_wait_ms")
        if avg_wait is not None:
            _row("Avg frame wait (ms):", avg_wait)

    # --- Detection telemetry (task 7.9) ---
    if s.detection_telemetry:
        _hdr("DETECTION TELEMETRY")
        dt = s.detection_telemetry
        if "latency_p50_avg_ms" in dt:
            _row(
                "Latency p50/p95/p99 (avg ms):",
                f"{dt.get('latency_p50_avg_ms', '-')}"
                f"/{dt.get('latency_p95_avg_ms', '-')}"
                f"/{dt.get('latency_p99_avg_ms', '-')}",
            )
        if "frame_drop_rate_avg_pct" in dt:
            _row(
                "Frame drop rate (avg/max):",
                f"{dt['frame_drop_rate_avg_pct']}%"
                f" / {dt.get('frame_drop_rate_max_pct', '-')}%",
            )
        if "vpu_p50_avg_ms" in dt:
            _row(
                "VPU inference p50/p95 (avg ms):",
                f"{dt.get('vpu_p50_avg_ms', '-')}"
                f"/{dt.get('vpu_p95_avg_ms', '-')}",
            )
        if "cache_hit_rate_pct" in dt:
            _row(
                "Cache hit rate:",
                f"{dt['cache_hit_rate_pct']}%"
                f" ({dt.get('cache_hits', 0)}"
                f" hits, {dt.get('cache_misses', 0)}"
                f" misses)",
            )
        if "avg_detection_age_ms" in dt:
            _row(
                "Avg detection age (ms):",
                dt["avg_detection_age_ms"],
            )
        if "idle_period_count" in dt:
            _row(
                "Idle periods:",
                f"{dt['idle_period_count']}"
                f" ({dt.get('idle_total_duration_s', 0)}s"
                f" total)",
            )

    # --- Motor position trending (task 4.5) ---
    if s.motor_trending:
        mt = s.motor_trending
        if mt.get("has_data"):
            _hdr("MOTOR POSITION TRENDING")
            joints = mt.get("joints", {})
            print(
                f"  {'Joint':<12}  {'Events':>6}"
                f"  {'Mean Err':>10}  {'Max Err':>10}"
                f"  {'StdDev':>10}  {'Trend':<10}"
            )
            print(
                f"  {'\u2500' * 12}  {'\u2500' * 6}"
                f"  {'\u2500' * 10}  {'\u2500' * 10}"
                f"  {'\u2500' * 10}  {'\u2500' * 10}"
            )
            for jid, jdata in sorted(joints.items()):
                trend = jdata.get("trend_direction", "stable")
                indicator = {
                    "improving": "\u2193",
                    "degrading": "\u2191",
                    "stable": "\u2194",
                }.get(trend, "?")
                print(
                    f"  {jid:<12}"
                    f"  {jdata.get('event_count', 0):>6}"
                    f"  {jdata.get('mean_error', 0.0):>10.4f}"
                    f"  {jdata.get('max_error', 0.0):>10.4f}"
                    f"  {jdata.get('stddev', 0.0):>10.4f}"
                    f"  {indicator} {trend}"
                )

    # --- J4 position breakdown (task 4.7) ---
    if s.j4_position_breakdown:
        j4 = s.j4_position_breakdown
        if j4.get("has_data"):
            _hdr("J4 POSITION BREAKDOWN")
            pos_table = j4.get("position_table", [])
            if pos_table:
                print(
                    f"  {'J4 Offset':>10}  {'Scans':>6}"
                    f"  {'Found':>6}  {'Picked':>7}"
                    f"  {'Yield':>7}"
                )
                print(
                    f"  {'\u2500' * 10}  {'\u2500' * 6}"
                    f"  {'\u2500' * 6}  {'\u2500' * 7}"
                    f"  {'\u2500' * 7}"
                )
                for row in pos_table:
                    print(
                        f"  {row['j4_offset_m']:>10.3f}"
                        f"  {row['scans_at_position']:>6}"
                        f"  {row['cotton_found']:>6}"
                        f"  {row['cotton_picked']:>7}"
                        f"  {row['pick_yield_pct']:>6.1f}%"
                    )
            dead = j4.get("dead_zones", [])
            if dead:
                _sub("Dead zones (0% yield, 3+ scans)")
                for dz in dead:
                    _row(f"  J4 offset:", f"{dz:.3f}m")

    # --- Camera thermal trending (task 4.13) ---
    if s.camera_thermal:
        ct = s.camera_thermal
        if ct.get("has_data"):
            _hdr("CAMERA THERMAL")
            _row(
                "Start temp:",
                f"{ct.get('start_temp', 0)}\u00b0C",
            )
            _row(
                "End temp:",
                f"{ct.get('end_temp', 0)}\u00b0C",
            )
            _row(
                "Max temp:",
                f"{ct.get('max_temp', 0)}\u00b0C",
            )
            _row(
                "Min temp:",
                f"{ct.get('min_temp', 0)}\u00b0C",
            )
            _row(
                "Mean temp:",
                f"{ct.get('mean_temp', 0)}\u00b0C",
            )
            _row("Samples:", ct.get("sample_count", 0))
            ror = ct.get("rate_of_rise", 0.0)
            _row(
                "Rate of rise:",
                f"{ror}\u00b0C/min",
            )
            ttt = ct.get("time_to_threshold")
            if ttt is not None:
                _row(
                    "Time to critical (85\u00b0C):",
                    f"{ttt} min",
                )

    # --- Motor current draw (task 4.20) ---
    if s.motor_current:
        mc = s.motor_current
        if mc.get("has_data"):
            _hdr("MOTOR CURRENT DRAW")
            joints = mc.get("joints", {})
            print(
                f"  {'Joint':<12}  {'Samples':>7}"
                f"  {'Mean A':>8}  {'Max A':>8}"
                f"  {'StdDev':>8}  {'Spikes':>6}"
                f"  {'Health':<6}"
            )
            print(
                f"  {'\u2500' * 12}  {'\u2500' * 7}"
                f"  {'\u2500' * 8}  {'\u2500' * 8}"
                f"  {'\u2500' * 8}  {'\u2500' * 6}"
                f"  {'\u2500' * 6}"
            )
            for jid, jdata in sorted(joints.items()):
                health = jdata.get(
                    "health_indicator", "OK"
                )
                print(
                    f"  {jid:<12}"
                    f"  {jdata.get('sample_count', 0):>7}"
                    f"  {jdata.get('mean_a', 0.0):>8.3f}"
                    f"  {jdata.get('max_a', 0.0):>8.3f}"
                    f"  {jdata.get('stddev_a', 0.0):>8.3f}"
                    f"  {jdata.get('spike_count', 0):>6}"
                    f"  {health}"
                )

    # --- Session health ---
    _hdr("SESSION HEALTH")
    sh = s.session_health
    # task 15.2 — show operational duration as primary, total log span as secondary
    op_dur = sh.get("operational_duration_s", 0)
    total_dur = sh.get("session_duration_s", 0)
    op_start = sh.get("operational_start")
    op_end = sh.get("operational_end")
    if op_start and op_end:
        from datetime import datetime as _dt
        try:
            start_hm = _dt.fromtimestamp(op_start).strftime("%H:%M")
            end_hm = _dt.fromtimestamp(op_end).strftime("%H:%M")
            _row(
                "Operational duration:",
                f"{_fmt_dur(op_dur)} (ROS2 nodes: {start_hm}-{end_hm})",
            )
        except (ValueError, OSError, OverflowError):
            _row("Operational duration:", _fmt_dur(op_dur))
    else:
        _row("Operational duration:", _fmt_dur(op_dur))
    source_durs = sh.get("source_durations", {})
    # Show per-source spans when multiple log sources exist,
    # so the reader can see which sources contributed and their
    # individual durations. Skip the misleading "Total log span"
    # aggregate which sums non-overlapping windows.
    if source_durs and len(source_durs) > 1:
        parts = []
        for src in sorted(source_durs.keys()):
            sd = source_durs[src]
            if isinstance(sd, dict):
                dur = (sd.get("end", 0) or 0) - (sd.get("start", 0) or 0)
            else:
                dur = sd
            parts.append(f"{src} {_fmt_dur(dur)}")
        _row("Log sources:", ", ".join(parts))
    _row("Restarts:", sh.get("restarts", 0))
    _row("Log gaps (>30s):", sh.get("log_gaps", 0))
    if sh.get("largest_gap_s", 0):
        _row(
            "  Largest gap:",
            f"{sh.get('largest_gap_s')}s",
        )
    _row("Clock jumps:", sh.get("clock_jumps", 0))
    _row(
        "Manual interventions:",
        sh.get("manual_interventions", 0),
    )
    if sh.get("manual_duration_s", 0):
        _row(
            "  Manual duration:",
            f"{sh.get('manual_duration_s')}s",
        )

    # --- Dmesg summary (task 6.1) ---
    ds = s.dmesg_summary
    if ds.get("has_data"):
        _hdr("DMESG SUMMARY (KERNEL EVENTS)")
        _row("Total kernel events:", ds.get("total_events", 0))
        by_cat = ds.get("by_category", {})
        if by_cat:
            _sub("Events by category")
            _DMESG_LABELS = {
                "usb_disconnect": "USB disconnects",
                "thermal": "Thermal throttling",
                "oom": "Memory pressure (OOM)",
                "can_error": "CAN bus errors",
                "spi_error": "SPI errors",
            }
            for cat, info in sorted(by_cat.items()):
                label = _DMESG_LABELS.get(cat, cat)
                cnt = info.get("count", 0)
                first = info.get("first_ts")
                last = info.get("last_ts")
                ts_str = ""
                if first is not None and last is not None:
                    if first == last:
                        ts_str = f" (at {first:.0f})"
                    else:
                        ts_str = (
                            f" (first: {first:.0f},"
                            f" last: {last:.0f})"
                        )
                _row(f"  {label}:", f"{cnt}{ts_str}")

    # --- Pick success rate trend (task 6.2) ---
    pst = s.pick_success_trend
    if pst.get("has_data"):
        _hdr("PICK SUCCESS RATE TREND")
        _row("Total picks:", pst.get("total_picks", 0))
        _row(
            "Window size:",
            f"{pst.get('window_size', 10)} picks (rolling)",
        )
        _row(
            "First-quarter rate:",
            f"{pst.get('first_quarter_rate_pct', 0.0)}%",
        )
        _row(
            "Last-quarter rate:",
            f"{pst.get('last_quarter_rate_pct', 0.0)}%",
        )
        delta = pst.get("delta_pp", 0.0)
        trend = pst.get("trend_direction", "stable")
        _TREND_INDICATORS = {
            "improving": "\u2193",
            "degrading": "\u2191",
            "stable": "\u2194",
        }
        indicator = _TREND_INDICATORS.get(trend, "?")
        _row("Trend:", f"{indicator} {trend} ({delta:+.1f}pp)")
        issue = pst.get("issue")
        if issue:
            _row(
                f"  [{issue['severity']}]:",
                issue["description"],
            )

    # --- Throughput trend (task 6.3) ---
    tt = s.throughput_trend
    if tt.get("has_data"):
        _hdr("THROUGHPUT TREND (PICKS/HOUR)")
        _row(
            "Overall throughput:",
            f"{tt.get('overall_picks_per_hour', 0.0)} picks/hr",
        )
        _row(
            "Peak window:",
            f"{tt.get('peak_picks_per_hour', 0.0)} picks/hr",
        )
        _row(
            "Last window:",
            f"{tt.get('last_window_picks_per_hour', 0.0)}"
            f" picks/hr",
        )
        windows = tt.get("windows", [])
        if windows:
            _sub(
                f"5-minute windows ({len(windows)} windows)"
            )
            print(
                f"    {'Window':>8}  {'Picks':>6}"
                f"  {'Picks/hr':>10}"
            )
            print(
                f"    {'\u2500' * 8:>8}  {'\u2500' * 6:>6}"
                f"  {'\u2500' * 10:>10}"
            )
            for w in windows:
                start_m = w.get("start_min", 0)
                end_m = w.get("end_min", 0)
                print(
                    f"    {start_m:>3}-{end_m:<3}m"
                    f"  {w.get('pick_count', 0):>6}"
                    f"  {w.get('picks_per_hour', 0.0):>10.1f}"
                )
        issue = tt.get("issue")
        if issue:
            _row(
                f"  [{issue['severity']}]:",
                issue["description"],
            )

    # --- Stale detection warnings (task 6.4) ---
    sdw = s.stale_detection_section
    if sdw.get("has_data"):
        _hdr("STALE DETECTION WARNINGS")
        _row("Total warnings:", sdw.get("count", 0))
        first_ts = sdw.get("first_ts")
        last_ts = sdw.get("last_ts")
        if first_ts is not None:
            _row("First occurrence:", f"{first_ts:.0f}")
        if last_ts is not None:
            _row("Last occurrence:", f"{last_ts:.0f}")
        age_stats = sdw.get("age_stats", {})
        if age_stats.get("count"):
            _sub("Staleness duration (ms)")
            _row("  avg:", age_stats.get("avg"))
            _row("  p50:", age_stats.get("p50"))
            _row("  p95:", age_stats.get("p95"))
            _row("  max:", age_stats.get("max"))
        dist = sdw.get("age_distribution", {})
        if any(v > 0 for v in dist.values()):
            _sub("Distribution")
            for bucket, cnt in dist.items():
                if cnt > 0:
                    _row(f"  {bucket}:", cnt)
        sources = sdw.get("source_nodes", [])
        if sources and sources != ["unknown"]:
            _row(
                "Source nodes:", ", ".join(sources)
            )

    # --- EE start distance (task 17.4) ---
    ee_sd = s.ee_start_distance
    if ee_sd.get("has_data"):
        _hdr("EE START DISTANCE")
        dist_data = ee_sd.get("distance", {})
        if dist_data:
            _row("Measurements:", dist_data.get("count", 0))
            _row(
                "Distance (mm):",
                f"mean={dist_data.get('mean_mm', 0)}"
                f"  min={dist_data.get('min_mm', 0)}"
                f"  max={dist_data.get('max_mm', 0)}",
            )
            _row(
                "Stddev (mm):",
                dist_data.get("stddev_mm", 0),
            )
        idle_data = ee_sd.get("idle_timing", {})
        if idle_data:
            _sub("Inter-cycle idle timing")
            _row("Idle intervals:", idle_data.get("count", 0))
            _row(
                "Idle time (s):",
                f"mean={idle_data.get('mean_s', 0)}"
                f"  min={idle_data.get('min_s', 0)}"
                f"  max={idle_data.get('max_s', 0)}",
            )
            _row(
                "Idle stddev (s):",
                idle_data.get("stddev_s", 0),
            )
        idle_issue = ee_sd.get("idle_issue")
        if idle_issue:
            _row(
                f"  [{idle_issue['severity']}]:",
                idle_issue["description"],
            )

    # --- Correlation findings (task 6.4) ---
    _print_correlation_findings(s)

    # --- Verbose diagnostics (task 6.5) ---
    if verbose:
        _print_verbose_diagnostics(s)

    print()
