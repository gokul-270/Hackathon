"""
Field trial summary report generation and trend detection.

Groups 16, 17, 20, 24 of the vehicle-log-analyzer change:
  16 — Field trial summary report (_generate_field_summary / _print_field_summary)
  17 — Trend detection
  20 — Gap coverage features (pick numbering, error decoding, FP proxy, placeholders)
  24 — Arm-side additions to field summary
"""

from __future__ import annotations

from typing import TYPE_CHECKING

# Re-export shared helpers/constants so that existing imports
# like ``from log_analyzer.reports import _group_by_arm`` keep working.
from ._helpers import (
    MG6010_ERROR_FLAGS,
    _group_by_arm,
    _hour_bucket,
    _is_multi_arm,
    _safe_pct,
    _stats,
    decode_error_flags,
)

# Re-export printing
from .printing import _LINE, _hdr, _hr, _row, _sub, print_field_summary

# Re-export all section builders
from .sections import (
    _compute_arm_motor_summary,
    _pick_stats_for,
    _section_arm_client_health,
    _section_arm_state,
    _section_build_info,
    _section_camera_health,
    _section_camera_reliability,
    _section_camera_thermal,
    _section_communication_health,
    _section_coordination,
    _section_correlation_findings,
    _section_detection_quality,
    _section_detection_telemetry,
    _section_failure_chains,
    _section_hourly_throughput,
    _section_j4_position_breakdown,
    _section_joint_limits,
    _section_launch_health,
    _section_motor_current,
    _section_motor_health,
    _section_motor_homing,
    _section_motor_reliability,
    _section_motor_trending,
    _section_network,
    _section_per_joint_timing,
    _section_pick_failure_analysis,
    _section_pick_performance,
    _section_scan_effectiveness,
    _section_session_health,
    _section_startup_shutdown,
    _section_vehicle_motor_health,
    _section_vehicle_performance,
    _section_verbose_diagnostics,
    build_error_recovery,
    build_mqtt_health,
    build_service_health,
    _section_dmesg_summary,
    _section_pick_success_trend,
    _section_throughput_trend,
    _section_stale_detection_warnings,
    _section_ee_start_distance,
)

# Re-export trend detection
from .trends import (
    _linear_slope,
    _per_hour_averages,
    _trend_arm_motor_failures,
    _trend_arm_motor_temperature,
    _trend_camera_reconnections,
    _trend_detection_latency,
    _trend_mqtt_disconnects,
    _trend_pick_cycle_time,
    _trend_vehicle_health_score,
    detect_trends,
)

if TYPE_CHECKING:
    from ..analyzer import ROS2LogAnalyzer  # noqa: F401
    from ..models import FieldSummary


# ---------------------------------------------------------------------------
# Group 16 — Field summary generation
# ---------------------------------------------------------------------------


def generate_field_summary(
    analyzer: "ROS2LogAnalyzer",
    verbose: bool = False,
) -> "FieldSummary":
    """
    task 16.2 — Orchestrate all field summary sections.

    Returns a populated FieldSummary dataclass.
    """
    from ..models import FieldSummary

    summary = FieldSummary()
    session_start = analyzer.start_time or 0.0
    # Group files by parent directory so multi-session directories sum each
    # session's wall-clock span instead of reporting only the longest file.
    # Falls back to global start/end if unavailable.
    from collections import defaultdict
    from pathlib import Path

    file_ranges = getattr(analyzer, "_file_time_ranges", {})
    if file_ranges:
        groups: dict[str, list] = defaultdict(list)
        for fpath, (lo, hi) in file_ranges.items():
            parent = str(Path(fpath).parent)
            groups[parent].append((lo, hi))
        session_duration_s = sum(
            max(h for _, h in spans) - min(l for l, _ in spans)
            for spans in groups.values()
        )
    elif analyzer.start_time and analyzer.end_time:
        session_duration_s = analyzer.end_time - analyzer.start_time
    else:
        session_duration_s = 0.0

    # task 15.2 — use ROS2 operational duration for rate calculations
    source_ranges = getattr(analyzer, "_source_category_ranges", {})
    ros2_range = source_ranges.get("ros2")
    if ros2_range:
        operational_duration_s = ros2_range[1] - ros2_range[0]
    else:
        operational_duration_s = session_duration_s

    # task 8.2 — read topology from analyzer.topology
    topology = getattr(analyzer, "topology", None)
    topology_mode = getattr(topology, "mode", None)
    # Determine topology mode name for branching
    from ..analyzer import SessionTopologyMode

    is_vehicle_only = topology_mode == SessionTopologyMode.SINGLE_VEHICLE

    # task 8.3 — VEHICLE_ONLY: suppress arm pick and arm motor health sections
    if not is_vehicle_only:
        _section_pick_performance(
            analyzer, summary, session_start, operational_duration_s
        )
        _section_motor_health(analyzer, summary)
    _section_launch_health(analyzer, summary)  # task 13.7
    _section_build_info(analyzer, summary)  # task 2.5
    _section_vehicle_performance(analyzer, summary, session_start)
    _section_vehicle_motor_health(analyzer, summary)  # task 6.2
    _section_startup_shutdown(analyzer, summary)
    _section_coordination(analyzer, summary)
    _section_network(analyzer, summary)
    _section_hourly_throughput(analyzer, summary, session_start)
    _section_session_health(analyzer, summary, session_duration_s)
    _section_failure_chains(analyzer, summary)
    if not is_vehicle_only:
        _section_pick_failure_analysis(
            analyzer, summary, operational_duration_s
        )
        _section_arm_state(analyzer, summary)
        _section_motor_reliability(analyzer, summary)
        _section_camera_reliability(
            analyzer, summary, operational_duration_s
        )
    _section_communication_health(
        analyzer, summary, session_duration_s
    )

    # tasks 16.5–21.6 — new field diagnostics sections (arm-only)
    if not is_vehicle_only:
        _section_joint_limits(analyzer, summary)
        _section_camera_health(analyzer, summary)
        _section_scan_effectiveness(analyzer, summary)
        _section_motor_homing(analyzer, summary)
        _section_motor_trending(analyzer, summary)
        _section_per_joint_timing(analyzer, summary)
        _section_detection_quality(analyzer, summary)
        _section_detection_telemetry(analyzer, summary)
        _section_j4_position_breakdown(analyzer, summary)
        _section_camera_thermal(analyzer, summary)
        _section_motor_current(analyzer, summary)

    # task 17.1 — trend detection
    detect_trends(analyzer, summary)

    # tasks 6.1-6.4 — new report sections
    _section_dmesg_summary(summary, analyzer)
    if not is_vehicle_only:
        _section_pick_success_trend(summary, analyzer)
        _section_throughput_trend(
            summary, analyzer, operational_duration_s
        )
        _section_stale_detection_warnings(summary, analyzer)
        _section_ee_start_distance(summary, analyzer)

    # tasks 6.1-6.3 — ARM_client health sections
    _section_arm_client_health(analyzer, summary)

    # task 6.4 — correlation findings
    _section_correlation_findings(analyzer, summary)

    # task 6.5 — verbose diagnostics (only when verbose=True)
    if verbose:
        _section_verbose_diagnostics(analyzer, summary)

    return summary
