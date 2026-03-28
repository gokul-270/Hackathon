"""Arm JSON issue detection (Group 11) and ARM_client pattern detection."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from ..analyzer import ROS2LogAnalyzer
    from ..models import EventStore

_MOTOR_THERMAL_THRESHOLD_C = 55.0
_DETECTION_FAILURE_RATE_PCT = 50.0


def detect_arm_json_issues(analyzer: "ROS2LogAnalyzer") -> None:
    """tasks 11.1-11.5 — arm issue detection from JSON events."""
    events = analyzer.events

    # task 11.1 — Arm motor thermal
    for mh in events.motor_health_arm:
        for motor in mh.get("motors") or []:
            temp = motor.get("temp_c")
            joint = motor.get("joint", "?")
            if temp is not None and temp > _MOTOR_THERMAL_THRESHOLD_C:
                analyzer._add_issue(
                    severity="high",
                    category="motor",
                    title=f"Arm motor thermal: joint {joint}",
                    description=(
                        f"Joint {joint} temperature {temp:.1f}°C exceeds "
                        f"threshold {_MOTOR_THERMAL_THRESHOLD_C}°C"
                    ),
                    node=mh.get("_node") or "arm_control",
                    timestamp=mh.get("_ts") or 0,
                    message=f"motor_health joint={joint} temp_c={temp}",
                    recommendation="Check arm motor cooling; reduce duty cycle if needed",
                )

    # task 11.2 — Arm motor CAN errors
    for mh in events.motor_health_arm:
        for motor in mh.get("motors") or []:
            err_flags = motor.get("err_flags")
            joint = motor.get("joint", "?")
            if err_flags is not None and err_flags != 0:
                analyzer._add_issue(
                    severity="high",
                    category="motor",
                    title=f"Arm motor CAN errors: joint {joint}",
                    description=(
                        f"Joint {joint} error flags = {hex(err_flags)} (non-zero)"
                    ),
                    node=mh.get("_node") or "arm_control",
                    timestamp=mh.get("_ts") or 0,
                    message=f"motor_health joint={joint} err_flags={hex(err_flags)}",
                    recommendation="Check CAN bus wiring and motor driver for this joint",
                )

    # task 11.3 — Camera health
    for ds in events.detection_summaries:
        if ds.get("camera_healthy") is False:
            analyzer._add_issue(
                severity="high",
                category="camera",
                title="Camera reported unhealthy",
                description="detection_summary reported camera.healthy=False",
                node=ds.get("_node") or "cotton_detection",
                timestamp=ds.get("_ts") or 0,
                message="detection_summary camera.healthy=False",
                recommendation="Check OAK-D connection, power, and USB port",
            )

    # task 11.4 — Detection failure rate (aggregated across periodic reports)
    low_rate_summaries = [
        ds
        for ds in events.detection_summaries
        if ds.get("requests_detection_rate_pct") is not None
        and ds.get("requests_detection_rate_pct") < _DETECTION_FAILURE_RATE_PCT
    ]
    if low_rate_summaries:
        rates = [ds["requests_detection_rate_pct"] for ds in low_rate_summaries]
        last_rate = rates[-1]
        first_ts = low_rate_summaries[0].get("_ts") or 0
        last_ts = low_rate_summaries[-1].get("_ts") or 0
        analyzer._add_issue(
            severity="medium",
            category="detection",
            title=f"Low detection success rate: {last_rate:.1f}%",
            description=(
                f"Detection rate below {_DETECTION_FAILURE_RATE_PCT}% in "
                f"{len(low_rate_summaries)}/{len(events.detection_summaries)} "
                f"periodic reports (min={min(rates):.1f}%, max={max(rates):.1f}%)"
            ),
            node=low_rate_summaries[-1].get("_node") or "cotton_detection",
            timestamp=first_ts,
            message=f"detection_summary detection_rate_pct={last_rate}",
            recommendation=(
                "Check camera image quality, model accuracy, and detection confidence"
                " threshold"
            ),
        )

    # task 11.5 — Motor safety alert
    for ma in events.motor_alerts:
        # Accept both 'severity' and 'level' field names (C++ uses 'level')
        sev = ma.get("severity") or ma.get("level") or ""
        if sev == "critical":
            analyzer._add_issue(
                severity="critical",
                category="motor",
                title=f"Critical motor safety alert: {ma.get('check', '?')}",
                description=(
                    f"Motor alert: check={ma.get('check')}, joint={ma.get('joint')}, "
                    f"detail={ma.get('detail')}, action={ma.get('action')}"
                ),
                node=ma.get("_node") or "arm_control",
                timestamp=ma.get("_ts") or 0,
                message=f"motor_alert severity=critical check={ma.get('check')}",
                recommendation="Inspect motor for damage; do not run until cleared",
            )


# ---------------------------------------------------------------------------
# Zero joint movement detector
# ---------------------------------------------------------------------------


def detect_zero_joint_movement(
    events: "EventStore", verbose: bool = False,
) -> List[Dict[str, Any]]:
    """Detect picks where approach was recorded but all joint times are zero.

    This anomaly can indicate an instrumentation gap (all picks affected) or a
    stuck joint (only some picks affected).

    Suppressed when the arm is in fallback mode (0% detection acceptance rate
    and fallback positions being published), since zero joint movement is
    expected behaviour when no cotton is detected.
    """
    picks = events.picks
    if not picks:
        return []

    # Check if arm is in fallback mode: all detection summaries show 0%
    # acceptance rate AND fallback positions were published.
    in_fallback_mode = False
    detection_summaries = events.detection_summaries
    fallback_count = getattr(events, "_fallback_position_count", 0)

    if detection_summaries and fallback_count > 0:
        # Check if all detection summaries have 0% accepted detections
        all_zero_accepted = all(
            (ds.get("requests_detection_rate_pct") or 0) == 0
            for ds in detection_summaries
        )
        if not all_zero_accepted:
            # Also check detection_frames_summary aggregate
            frames_summary = events.detection_frames_summary
            all_zero_accepted = (
                frames_summary.get("count", 0) > 0
                and frames_summary.get("accepted_count", 0) == 0
            )
        if all_zero_accepted:
            in_fallback_mode = True

    affected = 0
    total = 0
    for p in picks:
        if (p.get("approach_ms") or 0) <= 0:
            continue
        total += 1
        if (
            (p.get("j3_ms") or 0) == 0
            and (p.get("j4_ms") or 0) == 0
            and (p.get("j5_ms") or 0) == 0
        ):
            affected += 1

    if affected == 0 or total == 0:
        return []

    # Suppress in fallback mode — zero joint movement is expected
    if in_fallback_mode:
        if verbose:
            events.suppressed_findings.append({
                "type": "zero_joint_movement_fallback_mode",
                "affected_picks": affected,
                "total_picks": total,
                "fallback_position_count": fallback_count,
                "reason": (
                    f"Zero joint movement in {affected}/{total} picks"
                    f" suppressed: arm is in fallback mode"
                    f" (0% detection rate,"
                    f" {fallback_count} fallback positions)"
                ),
            })
        return []

    pct = round(100.0 * affected / total, 1)

    if pct > 50.0:
        severity = "high"
    elif pct >= 10.0:
        severity = "medium"
    else:
        severity = "low"

    if affected == total:
        detail = "possible instrumentation gap"
    else:
        detail = "possible stuck joint"

    return [
        {
            "severity": severity,
            "category": "instrumentation",
            "title": f"Zero joint movement in {pct}% of picks",
            "description": (
                f"{affected}/{total} picks ({pct}%) had approach time but zero "
                f"joint movement (j3/j4/j5 all 0ms) — {detail}"
            ),
            "node": "arm_control",
            "timestamp": 0,
            "message": (
                f"{affected}/{total} picks ({pct}%) had approach time but zero "
                f"joint movement (j3/j4/j5 all 0ms) — {detail}"
            ),
            "affected_picks": affected,
            "total_picks": total,
            "pct": pct,
        }
    ]


# ---------------------------------------------------------------------------
# ARM_client pattern detection (tasks 2.1-2.6)
# ---------------------------------------------------------------------------


def check_arm_client_line(
    message: str,
    timestamp: float,
    arm_id: str,
    events: "EventStore",
) -> None:
    """Check a parsed ARM_client log line for known patterns and store events.

    Called during parsing when the source node is ``arm_client``.  Matched
    events are appended to *events.arm_client_mqtt_events* (for MQTT
    connect/disconnect/timeout) or *events.arm_client_events* (for service
    failures, error recovery, and queue overflow).
    """
    msg_lower = message.lower()

    # 2.1 — MQTT connect
    if any(
        p in message
        for p in ["Connected to MQTT broker", "on_connect", "MQTT RECONNECTED"]
    ):
        if (
            "rc=0" in message
            or "Connected to" in message
            or "RECONNECTED" in message
        ):
            events.arm_client_mqtt_events.append({
                "timestamp": timestamp,
                "arm_id": arm_id,
                "event_type": "mqtt_connect",
                "message": message,
            })
            return

    # 2.2 — MQTT disconnect
    if (
        "Disconnected from MQTT broker" in message
        or "on_disconnect" in message
    ):
        code = None
        reason = "unknown"
        code_match = re.search(r"rc=(\d+)", message)
        if code_match:
            code = int(code_match.group(1))
        reason_match = re.search(
            r"reason[=:]\s*(.+?)(?:\s*$|\s*,)", message, re.IGNORECASE
        )
        if reason_match:
            reason = reason_match.group(1).strip()
        events.arm_client_mqtt_events.append({
            "timestamp": timestamp,
            "arm_id": arm_id,
            "event_type": "mqtt_disconnect",
            "disconnect_code": code,
            "reason": reason,
            "message": message,
        })
        return

    # 2.3 — MQTT timeout
    if any(
        p in msg_lower
        for p in [
            "mqtt connection timeout",
            "connection timed out",
            "timed out",
        ]
    ):
        events.arm_client_mqtt_events.append({
            "timestamp": timestamp,
            "arm_id": arm_id,
            "event_type": "mqtt_timeout",
            "message": message,
        })
        return

    # 2.4 — Service failures
    if any(
        p in msg_lower
        for p in ["service not available", "consecutive service call failures"]
    ):
        svc_name = "unknown"
        svc_match = re.search(r"(\w+)\s+service not available", message)
        if svc_match:
            svc_name = svc_match.group(1)
        is_exhausted = "after" in msg_lower and "s" in msg_lower
        events.arm_client_events.append({
            "timestamp": timestamp,
            "arm_id": arm_id,
            "event_type": "service_failure",
            "service_name": svc_name,
            "message": message,
            "severity": "HIGH" if is_exhausted else "MEDIUM",
        })
        return

    # 2.5 — Error recovery
    _recovery_patterns = [
        ("Error state persisted", "error_persisted"),
        ("Attempting error recovery", "recovery_attempt"),
        ("recovery succeeded", "recovery_succeeded"),
        ("recovery failed", "recovery_failed"),
    ]
    for pattern, outcome in _recovery_patterns:
        if pattern.lower() in msg_lower:
            events.arm_client_events.append({
                "timestamp": timestamp,
                "arm_id": arm_id,
                "event_type": "error_recovery",
                "outcome": outcome,
                "message": message,
                "severity": (
                    "HIGH" if outcome == "recovery_failed" else "MEDIUM"
                ),
            })
            return

    # 2.6 — Command queue overflow
    if "command queue full" in msg_lower or "dropping oldest" in msg_lower:
        events.arm_client_events.append({
            "timestamp": timestamp,
            "arm_id": arm_id,
            "event_type": "queue_overflow",
            "message": message,
        })


def generate_arm_client_issues(events: "EventStore") -> List[Dict[str, Any]]:
    """Generate issues from accumulated ARM_client events.

    Currently checks for excessive command-queue overflow events per arm
    (threshold: >5 events → HIGH severity issue).
    """
    issues: List[Dict[str, Any]] = []

    # Queue overflow threshold check
    overflow_counts: Counter[str] = Counter()
    for evt in events.arm_client_events:
        if evt.get("event_type") == "queue_overflow":
            overflow_counts[evt["arm_id"]] += 1

    for arm_id, count in overflow_counts.items():
        if count > 5:
            issues.append({
                "severity": "HIGH",
                "category": "ARM_CLIENT",
                "description": (
                    f"Command queue overflow: {count} events on {arm_id}"
                ),
                "arm_id": arm_id,
                "count": count,
            })

    return issues


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
from .registry import register as _register

_register(
    "detect_arm_json_issues", detect_arm_json_issues,
    category="arm",
    description="Detect arm-side issues from structured JSON events.",
)
_register(
    "detect_zero_joint_movement", detect_zero_joint_movement,
    category="arm",
    description="Flag joints with no observed movement across all picks.",
)
_register(
    "generate_arm_client_issues", generate_arm_client_issues,
    category="arm",
    description="Generate issues from ARM_client pattern-based detection.",
)
