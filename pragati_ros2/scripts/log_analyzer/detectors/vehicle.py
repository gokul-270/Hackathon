"""Vehicle-specific issue detection (Group 10)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..analyzer import ROS2LogAnalyzer

# Thresholds
_DEADLINE_MISS_RATE_HIGH = 0.01    # 1 % missed deadlines → high
_DEADLINE_MISS_RATE_MEDIUM = 0.001  # 0.1 % → medium
_ESTOP_LATENCY_THRESHOLD_MS = 100
_DRIVE_TIMEOUT_ITERATION_THRESHOLD = 50


def detect_vehicle_issues(analyzer: "ROS2LogAnalyzer") -> None:
    """task 10.1 — check EventStore for vehicle-specific issues."""
    events = analyzer.events

    # task 10.2 — Drive position timeout
    for dc in events.drive_commands:
        if dc.get("position_reached") is False:
            iters = dc.get("iterations") or 0
            if iters > _DRIVE_TIMEOUT_ITERATION_THRESHOLD:
                analyzer._add_issue(
                    severity="high",
                    category="vehicle",
                    title="Drive position timeout",
                    description=(
                        f"Drive command did not reach position target after "
                        f"{iters} iterations (position_reached=False)"
                    ),
                    node=dc.get("_node") or "vehicle_control",
                    timestamp=dc.get("_ts") or 0,
                    message=f"drive_command position_reached=False iterations={iters}",
                    recommendation="Check wheel encoders and motor power for drive motors",
                )

    # task 10.3 — Steering partial failure
    for sc in events.steering_commands:
        motor_count = sc.get("motor_count") or 0
        success_count = sc.get("success_count") or 0
        if motor_count > 0 and success_count < motor_count:
            analyzer._add_issue(
                severity="high",
                category="vehicle",
                title="Steering partial failure",
                description=(
                    f"Steering command: only {success_count}/{motor_count} motors succeeded"
                ),
                node=sc.get("_node") or "vehicle_control",
                timestamp=sc.get("_ts") or 0,
                message=f"steering_command success={success_count}/{motor_count}",
                recommendation="Check CAN bus and motor power for steering motors",
            )

    # task 10.4 — Drive motor failure
    for dc in events.drive_commands:
        commanded = dc.get("motors_commanded") or 0
        succeeded = dc.get("motors_succeeded") or 0
        if commanded > 0 and succeeded < commanded:
            analyzer._add_issue(
                severity="high",
                category="vehicle",
                title="Drive motor failure",
                description=(
                    f"Drive command: only {succeeded}/{commanded} motors succeeded"
                ),
                node=dc.get("_node") or "vehicle_control",
                timestamp=dc.get("_ts") or 0,
                message=f"drive_command motors succeeded={succeeded}/{commanded}",
                recommendation="Check CAN bus and motor power for drive motors",
            )

    # task 10.5 — Control loop deadline miss
    for cl in events.control_loop:
        missed = cl.get("missed_deadlines") or 0
        loop_count = cl.get("loop_count") or 1
        if missed > 0:
            rate = missed / max(loop_count, 1)
            severity = "high" if rate > _DEADLINE_MISS_RATE_HIGH else "medium"
            analyzer._add_issue(
                severity=severity,
                category="vehicle",
                title="Control loop deadline miss",
                description=(
                    f"Control loop missed {missed}/{loop_count} deadlines "
                    f"({rate * 100:.2f}%)"
                ),
                node=cl.get("_node") or "vehicle_control",
                timestamp=cl.get("_ts") or 0,
                message=f"control_loop_health missed_deadlines={missed}",
                recommendation=(
                    "Reduce control loop overhead; check GPIO and joystick SPI timing"
                ),
            )

    # task 10.6 — Stale motor feedback
    for cl in events.control_loop:
        stale = cl.get("stale_motor_count") or 0
        if stale > 0:
            analyzer._add_issue(
                severity="medium",
                category="vehicle",
                title="Stale motor feedback",
                description=(
                    f"Control loop: {stale} motor(s) provided stale feedback"
                ),
                node=cl.get("_node") or "vehicle_control",
                timestamp=cl.get("_ts") or 0,
                message=f"control_loop_health stale_motor_count={stale}",
                recommendation="Check CAN bus cable and motor controller connectivity",
            )

    # task 10.7 — Vehicle motor health degradation
    for mh in events.motor_health_vehicle:
        score = mh.get("health_score")
        if score is not None and score < 100:
            analyzer._add_issue(
                severity="medium",
                category="vehicle",
                title=f"Vehicle motor health degraded: {score}%",
                description=(
                    f"Vehicle motor health score is {score}% (below 100%)"
                ),
                node=mh.get("_node") or "vehicle_control",
                timestamp=mh.get("_ts") or 0,
                message=f"motor_health health_score={score}",
                recommendation="Review per-motor error counts in logs",
            )

    # task 10.8 — State machine error
    for st in events.state_transitions:
        if st.get("to_state") == "ERROR":
            cause = st.get("error_cause") or "unknown"
            analyzer._add_issue(
                severity="high",
                category="vehicle",
                title="Vehicle state machine error",
                description=(
                    f"Vehicle entered ERROR state "
                    f"(from={st.get('from_state')}, cause={cause})"
                ),
                node=st.get("_node") or "vehicle_control",
                timestamp=st.get("_ts") or 0,
                message=f"state_transition to_state=ERROR error_cause={cause}",
                recommendation="Investigate error cause and review state machine transitions",
            )

    # task 10.9 — E-stop latency
    for st in events.state_transitions:
        estop_ms = st.get("estop_latency_ms")
        if estop_ms is not None and estop_ms > _ESTOP_LATENCY_THRESHOLD_MS:
            analyzer._add_issue(
                severity="high",
                category="vehicle",
                title=f"E-stop latency too high: {estop_ms:.0f}ms",
                description=(
                    f"Emergency stop latency {estop_ms:.0f}ms exceeds threshold "
                    f"{_ESTOP_LATENCY_THRESHOLD_MS}ms"
                ),
                node=st.get("_node") or "vehicle_control",
                timestamp=st.get("_ts") or 0,
                message=f"state_transition estop_latency_ms={estop_ms}",
                recommendation="Profile e-stop code path; reduce control loop period if needed",
            )

    # task 10.10 — Joystick release during drive
    for dc in events.drive_commands:
        if dc.get("joystick_released") is True:
            analyzer._add_issue(
                severity="medium",
                category="vehicle",
                title="Joystick released during drive command",
                description="Drive command was interrupted by joystick release",
                node=dc.get("_node") or "vehicle_control",
                timestamp=dc.get("_ts") or 0,
                message="drive_command joystick_released=True",
                recommendation="Ensure joystick is fully pressed before automated drives",
            )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
from .registry import register as _register

_register(
    "detect_vehicle_issues", detect_vehicle_issues,
    category="vehicle",
    description="Detect vehicle-specific issues (deadline misses, e-stop latency, etc.).",
)
