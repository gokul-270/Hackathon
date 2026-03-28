"""
Data models for the log analyzer.

Contains all dataclasses used across the package:
  - EventStore       : typed storage for all parsed JSON and text events
  - NetworkMetrics   : parsed network_monitor.log data
  - FieldSummary     : computed report sections for --field-summary
  - MQTTMetrics      : parsed MQTT client and broker events
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# BuildProvenance  (task 2.2)
# ---------------------------------------------------------------------------

@dataclass
class BuildProvenance:
    """Build provenance extracted from a node's startup banner.

    Captures the build timestamp and optional git metadata from
    'Built: <date> <time> (<hash> on <branch>)' log lines.
    """

    node_name: str
    build_timestamp: datetime
    git_hash: Optional[str] = None
    git_branch: Optional[str] = None
    is_dirty: bool = False


# ---------------------------------------------------------------------------
# MotorTrendingResult  (task 4.2)
# ---------------------------------------------------------------------------

@dataclass
class MotorTrendingResult:
    """Per-joint motor position trending statistics.

    Computed from homing events across the session to detect
    progressive mechanical wear or calibration drift.
    """

    joint_id: str = ""
    event_count: int = 0
    mean_error: float = 0.0
    max_error: float = 0.0
    stddev: float = 0.0
    trend_direction: str = "stable"  # "improving" | "stable" | "degrading"


# ---------------------------------------------------------------------------
# MotorCurrentResult  (task 4.18)
# ---------------------------------------------------------------------------

@dataclass
class MotorCurrentResult:
    """Per-joint motor current draw statistics.

    Computed from motor_health_arm events to detect current
    anomalies (spikes, gradual increases) indicating mechanical
    or electrical issues.
    """

    joint_id: str = ""
    sample_count: int = 0
    mean_a: float = 0.0
    max_a: float = 0.0
    min_a: float = 0.0
    stddev_a: float = 0.0
    transmission_ratio: float = 0.0
    spike_count: int = 0
    health_indicator: str = "OK"  # "OK" | "WATCH" | "ALERT"


# ---------------------------------------------------------------------------
# EventStore  (tasks 2.1, 22.11)
# ---------------------------------------------------------------------------

@dataclass
class EventStore:
    """Typed storage for all parsed events (JSON and text patterns)."""

    # --- JSON event storage (Groups 4-9) ---
    picks: List[dict] = field(default_factory=list)              # pick_complete
    cycles: List[dict] = field(default_factory=list)             # cycle_complete
    state_transitions: List[dict] = field(default_factory=list)  # state_transition
    drive_commands: List[dict] = field(default_factory=list)     # drive_command
    steering_commands: List[dict] = field(default_factory=list)  # steering_command
    control_loop: List[dict] = field(default_factory=list)       # control_loop_health
    motor_health_arm: List[dict] = field(default_factory=list)   # arm-side motor_health
    motor_health_vehicle: List[dict] = field(default_factory=list)  # vehicle-side motor_health
    arm_coordination: List[dict] = field(default_factory=list)   # arm_coordination
    auto_sessions: List[dict] = field(default_factory=list)      # auto_mode_session
    detection_summaries: List[dict] = field(default_factory=list)  # detection_summary
    motor_alerts: List[dict] = field(default_factory=list)       # motor_alert
    startup: List[dict] = field(default_factory=list)            # startup_timing
    shutdown: List[dict] = field(default_factory=list)           # shutdown_timing
    cmd_vel: List[dict] = field(default_factory=list)            # cmd_vel_latency
    steering_settle: List[dict] = field(default_factory=list)    # steering_settle

    # detection_frame: store only aggregate counters, not full events (memory efficiency)
    detection_frames_summary: dict = field(default_factory=lambda: {
        "count": 0,
        "total_latency_ms": 0.0,
        "accepted_count": 0,
        "raw_count": 0,
        "total_detection_age_ms": 0.0,
        "detection_age_count": 0,
        "total_roi_pct": 0.0,
        "roi_pct_count": 0,
        "total_valid_depth_pct": 0.0,
        "valid_depth_pct_count": 0,
    })

    # detection_idle events
    detection_idle_events: List[dict] = field(default_factory=list)

    # motor_command: count-only — high frequency, never store individual events
    motor_command_counts: Dict[str, int] = field(default_factory=dict)

    # unknown event types encountered during dispatch
    unknown_events: Dict[str, int] = field(default_factory=dict)

    # --- Arm text pattern storage (Group 22) ---
    pick_failures: List[dict] = field(default_factory=list)            # {phase, reason, recovery_ms, _ts}
    arm_status_transitions: List[dict] = field(default_factory=list)   # {status, _ts}
    motor_failure_counts: Dict[str, int] = field(default_factory=dict) # motor_id → count
    motor_failure_details: List[dict] = field(default_factory=list)    # first N failures per motor
    motor_reach_stats: Dict[str, dict] = field(default_factory=dict)   # motor_id → {reached, timeout, errors}
    emergency_shutdowns: List[dict] = field(default_factory=list)      # {reason, _ts}
    camera_reconnections: List[dict] = field(default_factory=list)     # {type, _ts, success}
    gpio_failures: int = 0                                              # cumulative count

    # dmesg events (populated by system_logs.py)
    dmesg_usb_disconnects: List[dict] = field(default_factory=list)    # {_ts, message}
    dmesg_thermal: List[dict] = field(default_factory=list)            # {_ts, message}
    dmesg_oom: List[dict] = field(default_factory=list)                # {_ts, message}
    dmesg_can_errors: List[dict] = field(default_factory=list)         # {_ts, message}
    dmesg_spi_errors: List[dict] = field(default_factory=list)         # {_ts, message}

    # aruco mention count (Gap 20)
    aruco_mention_count: int = 0

    # recovery stats (Group 22.7)
    recovery_count: int = 0
    recovery_total_ms: float = 0.0

    # --- Dynamic attributes written by detectors/arm_patterns ---
    # These used to be set via setattr with ``# type: ignore[attr-defined]``.
    # Declaring them as proper fields removes all such suppressions.
    _pick_success_by_state: dict = field(default_factory=dict)
    _picks_during_motion: int = 0
    _failure_chains: List[dict] = field(default_factory=list)
    _state_time_s: dict = field(default_factory=dict)
    _timestamp_gaps: List[tuple] = field(default_factory=list)
    _manual_interventions: dict = field(
        default_factory=lambda: {"count": 0, "total_s": 0.0}
    )
    _clock_jumps: List[tuple] = field(default_factory=list)
    _joint_limit_total: int = 0
    _fallback_position_count: int = 0

    # task 12.1 — new typed list fields for extended parsers/detectors
    launch_events: List[dict] = field(default_factory=list)               # launch process start/crash events
    ee_monitoring_events: List[dict] = field(default_factory=list)        # [EE] Dynamic position monitoring
    ee_short_retract_events: List[dict] = field(default_factory=list)     # [EE] Retreat: Very short retract
    joint_limit_events: List[dict] = field(default_factory=list)          # joint limit violation events
    homing_events: List[dict] = field(default_factory=list)               # homing sequence events per joint
    scan_position_results: List[dict] = field(default_factory=list)       # per-scan-position results
    scan_summaries: List[dict] = field(default_factory=list)              # scan summary blocks
    per_joint_timings: List[dict] = field(default_factory=list)           # [TIMING] per-joint approach/retreat
    retreat_breakdowns: List[dict] = field(default_factory=list)          # [TIMING] retreat phase breakdown
    ee_on_durations: List[dict] = field(default_factory=list)             # [TIMING] EE total ON duration
    j5_ee_breakdowns: List[dict] = field(default_factory=list)            # [TIMING] J5+EE breakdown (j5_travel, ee_pretravel, ee_overlap, ee_dwell)
    detection_quality_events: List[dict] = field(default_factory=list)    # detection count / quality events
    frame_freshness_events: List[dict] = field(default_factory=list)      # frame freshness / flushed events
    camera_stats_blocks: List[dict] = field(default_factory=list)         # camera stats block (════ delimited)
    stale_detection_warnings: List[dict] = field(default_factory=list)    # {_ts, reported_age_ms, source_node}
    ee_start_distances: List[dict] = field(default_factory=list)          # {distance_mm, _ts, arm_id}
    start_switch_events: List[dict] = field(default_factory=list)         # {type, _ts, arm_id}

    # --- ARM_client events (from Python logging format) ---
    arm_client_mqtt_events: List[dict] = field(default_factory=list)     # connect/disconnect/timeout
    arm_client_events: List[dict] = field(default_factory=list)          # service/recovery/queue events

    # --- Verbose mode diagnostics ---
    parse_stats: List[dict] = field(default_factory=list)
    suppressed_findings: List[dict] = field(default_factory=list)
    correlation_details: List[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# NetworkMetrics  (task 2.2)
# ---------------------------------------------------------------------------

@dataclass
class NetworkMetrics:
    """Parsed data from network_monitor.log."""

    ping_router: List[Tuple[datetime, float]] = field(default_factory=list)
    ping_broker: List[Tuple[datetime, float]] = field(default_factory=list)
    ping_router_timeouts: int = 0
    ping_broker_timeouts: int = 0
    eth_state_changes: List[Tuple[datetime, str]] = field(default_factory=list)
    eth_rx_errors: List[Tuple[datetime, int]] = field(default_factory=list)
    eth_tx_errors: List[Tuple[datetime, int]] = field(default_factory=list)
    eth_drops: List[Tuple[datetime, int]] = field(default_factory=list)
    cpu_temp: List[Tuple[datetime, float]] = field(default_factory=list)
    load_avg: List[Tuple[datetime, float]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# FieldSummary  (task 2.3)
# ---------------------------------------------------------------------------

@dataclass
class FieldSummary:
    """Computed metrics for the --field-summary report."""

    pick_performance: dict = field(default_factory=dict)
    pick_failure_analysis: dict = field(default_factory=dict)
    vehicle_performance: dict = field(default_factory=dict)
    arm_state: dict = field(default_factory=dict)
    motor_health_trends: dict = field(default_factory=dict)
    motor_reliability: dict = field(default_factory=dict)
    startup_shutdown: dict = field(default_factory=dict)
    coordination: dict = field(default_factory=dict)
    network_health: dict = field(default_factory=dict)
    communication_health: dict = field(default_factory=dict)
    camera_reliability: dict = field(default_factory=dict)
    hourly_throughput: List[dict] = field(default_factory=list)
    failure_chains: List[dict] = field(default_factory=list)
    trend_alerts: List[dict] = field(default_factory=list)
    session_health: dict = field(default_factory=dict)
    launch_health: dict = field(default_factory=dict)  # task 13.6
    # Dynamic attribute written by _section_hourly_throughput
    _hourly_throughput_per_arm: dict = field(default_factory=dict)
    # tasks 16.5-21.6 — new field diagnostics sections
    joint_limits: dict = field(default_factory=dict)
    camera_health: dict = field(default_factory=dict)
    scan_effectiveness: dict = field(default_factory=dict)
    motor_homing: dict = field(default_factory=dict)
    per_joint_timing: dict = field(default_factory=dict)
    detection_quality: dict = field(default_factory=dict)
    detection_telemetry: dict = field(default_factory=dict)
    # --- ARM_client report sections (tasks 6.1-6.4) ---
    mqtt_health: dict = field(default_factory=dict)       # per-arm MQTT health
    service_health: dict = field(default_factory=dict)    # per-arm service health
    error_recovery: dict = field(default_factory=dict)    # per-arm error recovery
    correlation_findings: List[dict] = field(default_factory=list)
    # --- Verbose mode diagnostics (task 6.5) ---
    verbose_parse_stats: List[dict] = field(default_factory=list)
    verbose_suppressed: List[dict] = field(default_factory=list)
    verbose_correlation_details: List[dict] = field(default_factory=list)
    # --- Build provenance (task 2.5) ---
    build_info: dict = field(default_factory=dict)
    # --- Motor position trending (task 4.4) ---
    motor_trending: dict = field(default_factory=dict)
    # --- J4 position breakdown (task 4.6) ---
    j4_position_breakdown: dict = field(default_factory=dict)
    # --- Camera thermal trending (task 4.13) ---
    camera_thermal: dict = field(default_factory=dict)
    # --- Motor current draw (task 4.19) ---
    motor_current: dict = field(default_factory=dict)
    # --- New report sections (tasks 6.1-6.4) ---
    dmesg_summary: dict = field(default_factory=dict)
    pick_success_trend: dict = field(default_factory=dict)
    throughput_trend: dict = field(default_factory=dict)
    stale_detection_section: dict = field(default_factory=dict)
    # --- EE start distance (task 17.4) ---
    ee_start_distance: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# MQTTMetrics  (task 23.1)
# ---------------------------------------------------------------------------

@dataclass
class MQTTMetrics:
    """Parsed MQTT client and mosquitto broker events."""

    connects: List[dict] = field(default_factory=list)           # {_ts, type: initial|reconnect, count, total}
    disconnects: List[dict] = field(default_factory=list)        # {_ts, type: unexpected|clean, rc, desc}
    health_checks: List[dict] = field(default_factory=list)      # {_ts, connected, failures, disconnect_duration_s}
    publish_failures: List[dict] = field(default_factory=list)   # {_ts, topic, attempts}
    arm_statuses: List[dict] = field(default_factory=list)       # {_ts, arm_id, status}
    broker_connects: List[dict] = field(default_factory=list)    # {_ts, ip, client_id}
    broker_disconnects: List[dict] = field(default_factory=list) # {_ts, client_id, socket_error}
    broker_starts: List[dict] = field(default_factory=list)      # {_ts, version}
