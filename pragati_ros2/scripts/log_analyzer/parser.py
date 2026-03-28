"""
Dual-path JSON event parser and all event-type handlers.

Groups 3-9 of the vehicle-log-analyzer change:
  - _try_parse_json_event  : Path 1 ([TIMING] prefix) and Path 2 (bare JSON)
  - _handle_json_event     : dispatcher to type-specific handlers
  - _normalize_timestamp   : unify three timestamp formats → epoch-seconds
  - handlers for all 18 JSON event types
"""

import json
import re
from datetime import datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .analyzer import ROS2LogAnalyzer


# ---------------------------------------------------------------------------
# Timestamp normalisation  (task 3.6)
# ---------------------------------------------------------------------------

def normalize_timestamp(event: dict, log_timestamp: Optional[float]) -> Optional[float]:
    """Return epoch-seconds float from the best available source.

    Priority:
      1. log_timestamp  — from ROS2 log prefix (canonical, most reliable)
      2. event['ts'] as ISO-8601 string  — vehicle-side Python nodes
      3. event['ts'] as int milliseconds — arm-side C++ nodes (divide by 1000)
    """
    if log_timestamp is not None:
        return log_timestamp

    ts = event.get("ts")
    if ts is None:
        return None

    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts).timestamp()
        except ValueError:
            return None
    if isinstance(ts, (int, float)):
        # Heuristic: values > 1e12 are milliseconds
        if ts > 1e12:
            return ts / 1000.0
        return float(ts)
    return None


# ---------------------------------------------------------------------------
# Dual-path JSON extraction  (tasks 3.1, 3.4)
# ---------------------------------------------------------------------------

def try_parse_json_event(message: str) -> Optional[dict]:
    """Attempt to extract a JSON event dict from a log message string.

    Path 1 – vehicle-side: message starts with '[TIMING] ' followed by JSON.
    Path 2 – arm-side: message starts directly with '{' and contains '"event"'.

    Returns the parsed dict (with at least an 'event' key) or None.
    Raises nothing — all JSON errors are caught here.
    """
    # Path 1: [TIMING] prefix
    if message.startswith("[TIMING]"):
        payload = message[len("[TIMING]"):].strip()
        try:
            data = json.loads(payload)
            if isinstance(data, dict) and "event" in data:
                return data
        except json.JSONDecodeError:
            # Non-JSON [TIMING] line (e.g. C++ motion_controller text) — caller
            # is responsible for routing to _parse_timing_text.
            raise  # re-raise so caller can distinguish JSON vs text [TIMING]
        return None

    # Path 2: bare JSON from arm-side C++ nodes
    if message.startswith("{") and '"event"' in message:
        try:
            data = json.loads(message)
            if isinstance(data, dict) and "event" in data:
                return data
        except json.JSONDecodeError:
            pass

    return None


# ---------------------------------------------------------------------------
# Event dispatcher  (task 3.5)
# ---------------------------------------------------------------------------

# Maps event-type strings to handler method names on ROS2LogAnalyzer
_EVENT_HANDLERS = {
    "startup_timing": "_handle_startup_timing",
    "shutdown_timing": "_handle_shutdown_timing",
    "state_transition": "_handle_state_transition",
    "steering_command": "_handle_steering_command",
    "steering_settle": "_handle_steering_settle",
    "drive_command": "_handle_drive_command",
    "cmd_vel_latency": "_handle_cmd_vel_latency",
    "control_loop_health": "_handle_control_loop_health",
    "motor_health": "_handle_motor_health",
    "arm_coordination": "_handle_arm_coordination",
    "auto_mode_session": "_handle_auto_mode_session",
    "motor_command": "_handle_motor_command",
    "pick_complete": "_handle_pick_complete",
    "cycle_complete": "_handle_cycle_complete",
    "detection_summary": "_handle_detection_summary",
    "detection_frame": "_handle_detection_frame",
    "detection_idle": "_handle_detection_idle",
    "motor_alert": "_handle_motor_alert",
}


def handle_json_event(
    analyzer: "ROS2LogAnalyzer",
    event: dict,
    timestamp: Optional[float],
    node: Optional[str],
) -> None:
    """Dispatch a parsed JSON event to the appropriate handler."""
    event_type = event.get("event")
    if not event_type:
        return

    ts = normalize_timestamp(event, timestamp)
    event["_ts"] = ts
    event["_node"] = node

    # task 2.3 — inject arm_id from the analyzer's current file context
    event["arm_id"] = analyzer._current_arm_id

    handler_name = _EVENT_HANDLERS.get(event_type)
    if handler_name:
        getattr(analyzer, handler_name)(event)
    else:
        analyzer.events.unknown_events[event_type] = (
            analyzer.events.unknown_events.get(event_type, 0) + 1
        )


# ---------------------------------------------------------------------------
# Group 4: startup / shutdown handlers
# ---------------------------------------------------------------------------

def handle_startup_timing(analyzer: "ROS2LogAnalyzer", event: dict) -> None:
    """task 4.1 — extract flat startup timing fields."""
    record = {
        "_ts": event.get("_ts"),
        "_node": event.get("_node"),
        "arm_id": event.get("arm_id"),
        "total_ms": event.get("total_ms"),
        "hardware_init_ms": event.get("hardware_init_ms"),
        "motor_controller_init_ms": event.get("motor_controller_init_ms"),
        "joystick_init_ms": event.get("joystick_init_ms"),
        "service_client_ms": event.get("service_client_ms"),
        "self_test_ms": event.get("self_test_ms"),
    }
    analyzer.events.startup.append(record)


def handle_shutdown_timing(analyzer: "ROS2LogAnalyzer", event: dict) -> None:
    """task 4.2 — extract flat shutdown timing fields."""
    record = {
        "_ts": event.get("_ts"),
        "_node": event.get("_node"),
        "arm_id": event.get("arm_id"),
        "total_ms": event.get("total_ms"),
        "subprocess_cleanup_ms": event.get("subprocess_cleanup_ms"),
        "thread_join_ms": event.get("thread_join_ms"),
        "motor_shutdown_ms": event.get("motor_shutdown_ms"),
        "thread_join_timeout": event.get("thread_join_timeout"),
    }
    analyzer.events.shutdown.append(record)


# ---------------------------------------------------------------------------
# Group 5: state and steering handlers
# ---------------------------------------------------------------------------

def handle_state_transition(analyzer: "ROS2LogAnalyzer", event: dict) -> None:
    """task 5.1 — extract state transition fields (from_state/to_state NOT from/to)."""
    record = {
        "_ts": event.get("_ts"),
        "_node": event.get("_node"),
        "arm_id": event.get("arm_id"),
        "from_state": event.get("from_state"),
        "to_state": event.get("to_state"),
        "trigger": event.get("trigger"),
        "time_in_previous_state_ms": event.get("time_in_previous_state_ms"),
        "transition_ms": event.get("transition_ms"),
        "error_cause": event.get("error_cause"),
        "estop_latency_ms": event.get("estop_latency_ms"),
    }
    analyzer.events.state_transitions.append(record)


def handle_steering_command(analyzer: "ROS2LogAnalyzer", event: dict) -> None:
    """task 5.2 — extract steering command fields."""
    record = {
        "_ts": event.get("_ts"),
        "_node": event.get("_node"),
        "arm_id": event.get("arm_id"),
        "commanded_rad": event.get("commanded_rad"),
        "commanded_deg": event.get("commanded_deg"),
        "motor_count": event.get("motor_count"),
        "success_count": event.get("success_count"),
        "duration_ms": event.get("duration_ms"),
        "all_wheels": event.get("all_wheels"),
    }
    analyzer.events.steering_commands.append(record)


def handle_steering_settle(analyzer: "ROS2LogAnalyzer", event: dict) -> None:
    """task 5.3 — extract steering settle fields."""
    record = {
        "_ts": event.get("_ts"),
        "_node": event.get("_node"),
        "arm_id": event.get("arm_id"),
        "target_rad": event.get("target_rad"),
        "settle_ms": event.get("settle_ms"),
        "all_reached": event.get("all_reached"),
        "motors_reached": event.get("motors_reached"),
        "motors_total": event.get("motors_total"),
    }
    analyzer.events.steering_settle.append(record)


# ---------------------------------------------------------------------------
# Group 6: drive and cmd_vel handlers
# ---------------------------------------------------------------------------

def handle_drive_command(analyzer: "ROS2LogAnalyzer", event: dict) -> None:
    """task 6.1 — extract drive command fields."""
    record = {
        "_ts": event.get("_ts"),
        "_node": event.get("_node"),
        "arm_id": event.get("arm_id"),
        "velocity_mps": event.get("velocity_mps"),
        "distance_mm": event.get("distance_mm"),
        "duration_ms": event.get("duration_ms"),
        "command_send_ms": event.get("command_send_ms"),
        "wait_loop_ms": event.get("wait_loop_ms"),
        "position_wait_ms": event.get("position_wait_ms"),
        "total_ms": event.get("total_ms"),
        "motors_commanded": event.get("motors_commanded"),
        "motors_succeeded": event.get("motors_succeeded"),
        "position_reached": event.get("position_reached"),
        "joystick_released": event.get("joystick_released"),
        "iterations": event.get("iterations"),
        "final_position_error_rad": event.get("final_position_error_rad"),
        "position_errors": event.get("position_errors"),
    }
    analyzer.events.drive_commands.append(record)


def handle_cmd_vel_latency(analyzer: "ROS2LogAnalyzer", event: dict) -> None:
    """task 6.2 — extract cmd_vel latency fields."""
    record = {
        "_ts": event.get("_ts"),
        "_node": event.get("_node"),
        "arm_id": event.get("arm_id"),
        "linear_vel": event.get("linear_vel"),
        "angular_cmd": event.get("angular_cmd"),
        "total_ms": event.get("total_ms"),
        "steering_ms": event.get("steering_ms"),
        "drive_ms": event.get("drive_ms"),
    }
    analyzer.events.cmd_vel.append(record)


# ---------------------------------------------------------------------------
# Group 7: health and coordination handlers
# ---------------------------------------------------------------------------

def handle_control_loop_health(analyzer: "ROS2LogAnalyzer", event: dict) -> None:
    """task 7.1 — extract control loop health fields."""
    record = {
        "_ts": event.get("_ts"),
        "_node": event.get("_node"),
        "arm_id": event.get("arm_id"),
        "loop_count": event.get("loop_count"),
        "avg_loop_time_ms": event.get("avg_loop_time_ms"),
        "max_loop_time_ms": event.get("max_loop_time_ms"),
        "missed_deadlines": event.get("missed_deadlines"),
        "uptime_s": event.get("uptime_s"),
        "stale_motor_count": event.get("stale_motor_count"),
        "total_motor_count": event.get("total_motor_count"),
        "gpio_avg_ms": event.get("gpio_avg_ms"),
        "joystick_spi_avg_ms": event.get("joystick_spi_avg_ms"),
        "safety_check_avg_ms": event.get("safety_check_avg_ms"),
        "safety_check_max_ms": event.get("safety_check_max_ms"),
    }
    analyzer.events.control_loop.append(record)


def handle_motor_health(analyzer: "ROS2LogAnalyzer", event: dict) -> None:
    """task 7.2 — disambiguate arm vs vehicle motor_health and store."""
    if "health_score" in event:
        # Vehicle-side
        record = {
            "_ts": event.get("_ts"),
            "_node": event.get("_node"),
            "arm_id": event.get("arm_id"),
            "health_score": event.get("health_score"),
            "uptime_s": event.get("uptime_s"),
            "motors": event.get("motors", []),
            "enable_call_count": event.get("enable_call_count"),
            "enable_avg_latency_ms": event.get("enable_avg_latency_ms"),
            "enable_max_latency_ms": event.get("enable_max_latency_ms"),
        }
        analyzer.events.motor_health_vehicle.append(record)
    elif "vbus_v" in event:
        # Arm-side
        record = {
            "_ts": event.get("_ts"),
            "_node": event.get("_node"),
            "arm_id": event.get("arm_id"),
            "vbus_v": event.get("vbus_v"),
            "uptime_s": event.get("uptime_s"),
            "degraded": event.get("degraded"),
            "motors": event.get("motors", []),
        }
        analyzer.events.motor_health_arm.append(record)
    # If neither key, skip (malformed event)


def handle_arm_coordination(analyzer: "ROS2LogAnalyzer", event: dict) -> None:
    """task 7.3 — extract arm coordination fields."""
    record = {
        "_ts": event.get("_ts"),
        "_node": event.get("_node"),
        "arm_id": event.get("arm_id"),
        "vehicle_stop_ms": event.get("vehicle_stop_ms"),
        "arm_phase_ms": event.get("arm_phase_ms"),
        "vehicle_resume_ms": event.get("vehicle_resume_ms"),
        "total_cycle_ms": event.get("total_cycle_ms"),
        "vehicle_stop_ts": event.get("vehicle_stop_ts"),
    }
    analyzer.events.arm_coordination.append(record)


def handle_auto_mode_session(analyzer: "ROS2LogAnalyzer", event: dict) -> None:
    """task 7.4 — extract auto mode session fields."""
    record = {
        "_ts": event.get("_ts"),
        "_node": event.get("_node"),
        "arm_id": event.get("arm_id"),
        "duration_s": event.get("duration_s"),
        "cycles_completed": event.get("cycles_completed"),
    }
    analyzer.events.auto_sessions.append(record)


# ---------------------------------------------------------------------------
# Group 8: motor_command — count only, never store
# ---------------------------------------------------------------------------

def handle_motor_command(analyzer: "ROS2LogAnalyzer", event: dict) -> None:
    """task 8.1 — increment per-command-type count; do NOT store individual events.

    Key used for counting is the 'command' field (e.g. "velocity", "position").
    Falls back to 'motor_id' if 'command' is absent, then "unknown".
    """
    key = str(event.get("command") or event.get("motor_id") or "unknown")
    analyzer.events.motor_command_counts[key] = (
        analyzer.events.motor_command_counts.get(key, 0) + 1
    )


# ---------------------------------------------------------------------------
# Group 9: arm event handlers
# ---------------------------------------------------------------------------

def handle_pick_complete(analyzer: "ROS2LogAnalyzer", event: dict) -> None:
    """task 9.1 — extract pick_complete fields including nested position/polar."""
    pos = event.get("position") or {}
    polar = event.get("polar") or {}
    record = {
        "_ts": event.get("_ts"),
        "_node": event.get("_node"),
        "arm_id": event.get("arm_id"),
        "cotton_id": event.get("cotton_id"),
        "confidence": event.get("confidence"),
        "detection_id": event.get("detection_id"),
        "detection_age_ms": event.get("detection_age_ms"),
        "approach_ms": event.get("approach_ms"),
        "capture_ms": event.get("capture_ms"),
        "retreat_ms": event.get("retreat_ms"),
        "delay_ms": event.get("delay_ms"),
        "total_ms": event.get("total_ms"),
        "success": event.get("success"),
        "ee_on_ms": event.get("ee_on_ms"),
        "j3_ms": event.get("j3_ms"),
        "j4_ms": event.get("j4_ms"),
        "j5_ms": event.get("j5_ms"),
        "position_x": pos.get("x"),
        "position_y": pos.get("y"),
        "position_z": pos.get("z"),
        "polar_r": polar.get("r"),
        "polar_theta": polar.get("theta"),
        "polar_phi": polar.get("phi"),
        "recovery_ms": event.get("recovery_ms"),
        # Global pick number assigned after parse (task 20.1)
        "pick_id": None,
    }
    analyzer.events.picks.append(record)


def handle_cycle_complete(analyzer: "ROS2LogAnalyzer", event: dict) -> None:
    """task 9.2 — extract cycle_complete fields."""
    record = {
        "_ts": event.get("_ts"),
        "_node": event.get("_node"),
        "arm_id": event.get("arm_id"),
        "total_ms": event.get("total_ms"),
        "cottons_attempted": event.get("cottons_attempted"),
        "cottons_succeeded": event.get("cottons_succeeded"),
        "cottons_failed": event.get("cottons_failed"),
        "pick_rate_pct": event.get("pick_rate_pct"),
        "detection_count": event.get("detection_count"),
        "optimizer_strategy": event.get("optimizer_strategy"),
        "detection_age_ms": event.get("detection_age_ms"),
    }
    analyzer.events.cycles.append(record)


def handle_detection_summary(analyzer: "ROS2LogAnalyzer", event: dict) -> None:
    """task 9.3 — extract nested detection_summary fields."""
    requests = event.get("requests") or {}
    latency = event.get("latency_ms") or {}
    camera = event.get("camera") or {}
    reliability = event.get("reliability") or {}
    host = event.get("host") or {}
    vpu = event.get("vpu_ms") or {}
    exposure = event.get("exposure") or {}
    frames = event.get("frames") or {}
    depth_quality = event.get("depth_quality") or {}
    queues = event.get("queues") or {}
    thermal = event.get("thermal") or {}
    record = {
        "_ts": event.get("_ts"),
        "_node": event.get("_node"),
        "arm_id": event.get("arm_id"),
        "uptime_s": event.get("uptime_s"),
        "requests_total": requests.get("total"),
        "requests_success": requests.get("success"),
        "requests_with_cotton": requests.get("with_cotton"),
        "requests_detection_rate_pct": requests.get("detection_rate_pct"),
        "latency_avg_ms": latency.get("avg"),
        "latency_min_ms": latency.get("min"),
        "latency_max_ms": latency.get("max"),
        "latency_p50_ms": latency.get("p50"),
        "latency_p95_ms": latency.get("p95"),
        "latency_p99_ms": latency.get("p99"),
        "camera_healthy": camera.get("healthy"),
        "camera_temp_c": camera.get("temp_c"),
        "camera_usb_speed": camera.get("usb_speed"),
        "camera_css_cpu_pct": camera.get("css_cpu_pct"),
        "camera_mss_cpu_pct": camera.get("mss_cpu_pct"),
        "camera_reconnect_count": camera.get("reconnect_count"),
        "reliability_reconnects": reliability.get("reconnects"),
        "reliability_downtime_s": reliability.get("downtime_s"),
        "reliability_xlink_errors": reliability.get("xlink_errors"),
        "reliability_sync_mismatches": reliability.get("sync_mismatches"),
        "host_memory_mb": host.get("memory_mb"),
        "model": event.get("model"),
        "vpu_p50_ms": vpu.get("p50"),
        "vpu_p95_ms": vpu.get("p95"),
        "exposure_avg_us": exposure.get("avg_us"),
        "exposure_avg_iso": exposure.get("avg_iso"),
        "frames_processed": frames.get("processed"),
        "frames_dropped": frames.get("dropped"),
        "frames_drop_rate_pct": frames.get("drop_rate_pct"),
        "depth_valid_pct_avg": depth_quality.get("valid_depth_pct_avg"),
        "depth_zero_spatial_count": depth_quality.get(
            "zero_spatial_count"
        ),
        "queue_detection": queues.get("detection"),
        "queue_rgb": queues.get("rgb"),
        "queue_depth": queues.get("depth"),
        "thermal_throttle": thermal.get("throttle_effective"),
        "cache_hits": requests.get("cache_hits"),
        "cache_misses": requests.get("cache_misses"),
    }
    analyzer.events.detection_summaries.append(record)


def handle_detection_frame(analyzer: "ROS2LogAnalyzer", event: dict) -> None:
    """task 9.4 — update aggregate counters only; do NOT store full event.

    Supports two layouts:
      Nested (production):  timing_ms.total, detections.accepted, detections.raw
      Flat (test/legacy):   latency_ms, accepted_count, count (frames)
    """
    timing = event.get("timing_ms") or {}
    detections = event.get("detections") or {}

    # Latency: prefer nested timing_ms.total, fall back to flat latency_ms
    total_ms = timing.get("total") or timing.get("detect") or event.get("latency_ms") or 0.0
    # Accepted: prefer nested detections.accepted, fall back to flat accepted_count
    accepted = detections.get("accepted") or event.get("accepted_count") or 0
    raw = detections.get("raw") or 0

    s = analyzer.events.detection_frames_summary
    s["count"] += 1
    s["total_latency_ms"] += float(total_ms)
    s["accepted_count"] += int(accepted)
    s["raw_count"] += int(raw)

    # Task 3.1 — store additional fields from detection_frame JSON
    s["inference_time_ms"] = event.get("inference_time_ms")
    s["frame_seq"] = event.get("frame_seq")
    s["model_name"] = event.get("model_name")
    s["positions"] = event.get("positions")
    s["border_filtered"] = event.get("border_filtered")
    s["not_pickable"] = event.get("not_pickable")
    s["success"] = event.get("success")

    # Task 7.9 — aggregate new per-frame fields
    det_age = event.get("detection_age_ms")
    if det_age is not None:
        s["total_detection_age_ms"] += float(det_age)
        s["detection_age_count"] += 1

    # Per-detection roi_pct and valid_depth_pct
    per_det = event.get("detections") or {}
    items = per_det.get("items") or []
    for item in items:
        roi = item.get("roi_pct")
        if roi is not None:
            s["total_roi_pct"] += float(roi)
            s["roi_pct_count"] += 1
        vdp = item.get("valid_depth_pct")
        if vdp is not None:
            s["total_valid_depth_pct"] += float(vdp)
            s["valid_depth_pct_count"] += 1


def handle_motor_alert(analyzer: "ROS2LogAnalyzer", event: dict) -> None:
    """task 9.5 — extract motor_alert fields."""
    record = {
        "_ts": event.get("_ts"),
        "_node": event.get("_node"),
        "arm_id": event.get("arm_id"),
        "severity": event.get("severity"),
        "level": event.get("level"),
        "check": event.get("check"),
        "joint": event.get("joint"),
        "detail": event.get("detail"),
        "value": event.get("value"),
        "threshold": event.get("threshold"),
        "action": event.get("action"),
    }
    analyzer.events.motor_alerts.append(record)


def handle_detection_idle(analyzer: "ROS2LogAnalyzer", event: dict) -> None:
    """task 7.9 — extract detection_idle fields."""
    record = {
        "_ts": event.get("_ts"),
        "_node": event.get("_node"),
        "arm_id": event.get("arm_id"),
        "duration_s": event.get("duration_s"),
        "reason": event.get("reason"),
    }
    analyzer.events.detection_idle_events.append(record)
