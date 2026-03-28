"""Hardware-related detectors (EE timeout, joint limits, camera, homing, compressor)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import EventStore


# ---------------------------------------------------------------------------
# task 14.4 — EE position monitoring timeout detector
# ---------------------------------------------------------------------------


def detect_ee_timeout_rate(events: "EventStore") -> list:
    """task 14.4 — High issue when EE timeout rate > 50% and >= 5 events."""

    ee_events = events.ee_monitoring_events
    if not ee_events:
        return []

    # Group by arm_id
    arm_groups: dict = {}
    for ev in ee_events:
        aid = ev.get("arm_id")
        key = aid if aid is not None else "__single__"
        arm_groups.setdefault(key, []).append(ev)

    issues = []
    for arm_key, arm_ee in arm_groups.items():
        total = len(arm_ee)
        if total < 5:
            continue
        timeouts = sum(1 for e in arm_ee if e.get("type") == "timeout")
        rate = timeouts / total
        if rate > 0.5:
            arm_label = f"arm_id={arm_key}" if arm_key != "__single__" else "arm"
            issues.append(
                {
                    "severity": "high",
                    "category": "hardware",
                    "title": (
                        f"EE position monitoring timed out on {timeouts}/{total} picks "
                        f"({rate * 100:.0f}%) ({arm_label})"
                    ),
                    "description": (
                        f"EE position monitoring timed out on {timeouts}/{total} picks "
                        f"({rate * 100:.0f}%) — J5 may not be extending to target position"
                    ),
                    "node": "arm_control",
                    "timestamp": arm_ee[0].get("_ts") or 0,
                    "message": (
                        f"EE position monitoring timed out on {timeouts}/{total} picks"
                    ),
                    "recommendation": (
                        "Inspect J5 joint and EE actuator; verify EE extends fully during picks"
                    ),
                    "arm_id": arm_key if arm_key != "__single__" else None,
                }
            )
    return issues


# ---------------------------------------------------------------------------
# task 16.3 — Joint limit pattern detector
# ---------------------------------------------------------------------------


def detect_joint_limit_pattern(events: "EventStore") -> list:
    """task 16.3 — joint limit concentrated violations + too-wide violations."""

    violations = events.joint_limit_events
    if not violations:
        return []

    issues = []
    total_picks = len(events.picks)

    # Group by arm_id
    arm_groups: dict = {}
    for v in violations:
        aid = v.get("arm_id")
        key = aid if aid is not None else "__single__"
        arm_groups.setdefault(key, []).append(v)

    for arm_key, arm_violations in arm_groups.items():
        n = len(arm_violations)
        arm_label = f"arm_id={arm_key}" if arm_key != "__single__" else "arm"

        # (a) Concentrated at same J4 offset — group by calculated_m
        offset_counts: dict = {}
        for v in arm_violations:
            offset = v.get("calculated_m")
            if offset is not None:
                offset_counts[offset] = offset_counts.get(offset, 0) + 1
        if n >= 2:
            for offset, count in offset_counts.items():
                if count / n > 0.5:
                    pct = round(100.0 * count / n, 1)
                    issues.append(
                        {
                            "severity": "medium",
                            "category": "configuration",
                            "title": (
                                f"Joint limit violations concentrated at "
                                f"J4 offset {offset}m ({arm_label})"
                            ),
                            "description": (
                                f"Joint limit violations concentrated at "
                                f"J4 offset {offset}m — "
                                f"{count} of {n} violations ({pct}%). "
                                f"Consider narrowing scan range."
                            ),
                            "node": "arm_control",
                            "timestamp": arm_violations[0].get("_ts") or 0,
                            "message": (
                                f"Joint limit concentrated: J4={offset}m "
                                f"{count}/{n} ({pct}%)"
                            ),
                            "recommendation": (
                                "Review J4 scan range and arm calibration "
                                "for this offset"
                            ),
                            "arm_id": arm_key if arm_key != "__single__" else None,
                        }
                    )

        # (b) Violations on > 20% of total picks
        if total_picks > 0 and n / total_picks > 0.2:
            pct = round(100.0 * n / total_picks, 1)
            issues.append(
                {
                    "severity": "high",
                    "category": "configuration",
                    "title": (
                        f"Frequent joint limit violations: {n}/{total_picks} picks ({arm_label})"
                    ),
                    "description": (
                        f"{n} of {total_picks} pick attempts ({pct}%) failed due to "
                        f"joint limit violations"
                    ),
                    "node": "arm_control",
                    "timestamp": arm_violations[0].get("_ts") or 0,
                    "message": (
                        f"Joint limit violations on {n}/{total_picks} picks ({pct}%)"
                    ),
                    "recommendation": (
                        "Reduce scan range width or adjust cotton row alignment"
                    ),
                    "arm_id": arm_key if arm_key != "__single__" else None,
                }
            )
    return issues


# ---------------------------------------------------------------------------
# task 17.2 — Camera frame wait degradation detector
# ---------------------------------------------------------------------------


def detect_camera_frame_wait_degradation(events: "EventStore") -> list:
    """task 17.2 — Medium issue when frame_wait_max increases > 2x."""

    blocks = events.camera_stats_blocks
    if len(blocks) < 2:
        return []

    first_max = blocks[0].get("frame_wait_max_ms")
    last_max = blocks[-1].get("frame_wait_max_ms")

    if first_max is None or last_max is None or first_max == 0:
        return []

    if last_max > 2 * first_max:
        return [
            {
                "severity": "medium",
                "category": "hardware",
                "title": (
                    f"Camera frame wait degradation: max wait increased from "
                    f"{first_max}ms to {last_max}ms over session"
                ),
                "description": (
                    f"Camera frame wait max increased from {first_max}ms to {last_max}ms "
                    f"over session (>{2}x increase)"
                ),
                "node": "cotton_detection",
                "timestamp": blocks[0].get("_ts") or 0,
                "message": (
                    f"frame_wait_max increased from {first_max}ms to {last_max}ms"
                ),
                "recommendation": (
                    "Check OAK-D thermal state and USB bandwidth; consider shorter sessions"
                ),
                "arm_id": None,
            }
        ]
    return []


# ---------------------------------------------------------------------------
# task 19.2 — Motor homing failure detector
# ---------------------------------------------------------------------------


def detect_homing_failures(events: "EventStore") -> list:
    """task 19.2 — Critical for failed homing; Medium for near-tolerance."""

    issues = []
    for ev in events.homing_events:
        joint = ev.get("joint_name", "unknown")
        arm_id = ev.get("arm_id")
        arm_label = f"arm_id={arm_id} " if arm_id is not None else ""
        ts = ev.get("_ts") or 0

        if not ev.get("success"):
            issues.append(
                {
                    "severity": "critical",
                    "category": "hardware",
                    "title": f"Motor homing failed for {joint} ({arm_label.strip()})",
                    "description": (
                        f"Motor homing failed for {joint} — arm position may be incorrect "
                        f"for entire session"
                    ),
                    "node": "arm_control",
                    "timestamp": ts,
                    "message": f"Motor homing failed for {joint}",
                    "recommendation": (
                        "Manually home the arm before resuming; check joint mechanics"
                    ),
                    "arm_id": arm_id,
                }
            )
            continue

        err = ev.get("position_error")
        tol = ev.get("tolerance")
        if err is not None and tol is not None and tol > 0 and err > 0.8 * tol:
            issues.append(
                {
                    "severity": "medium",
                    "category": "hardware",
                    "title": (
                        f"{joint} homed near tolerance limit ({arm_label.strip()})"
                    ),
                    "description": (
                        f"{joint} homed with position error near tolerance limit "
                        f"(err={err:.4f}, tol={tol:.4f}) — may affect pick accuracy"
                    ),
                    "node": "arm_control",
                    "timestamp": ts,
                    "message": (
                        f"{joint} homed near tolerance limit err={err:.4f} tol={tol:.4f}"
                    ),
                    "recommendation": (
                        "Check joint calibration; re-home if position error is critical"
                    ),
                    "arm_id": arm_id,
                }
            )
    return issues


# ---------------------------------------------------------------------------
# task 20.4 — Compressor dominance + bottleneck joint detector
# ---------------------------------------------------------------------------


def detect_compressor_dominance(events: "EventStore") -> list:
    """task 20.4 — Low issues for compressor dominance and bottleneck joints."""

    issues = []

    # Compressor dominance across all retreats
    breakdowns = events.retreat_breakdowns
    if breakdowns:
        compressor_totals = []
        full_retreat_totals = []
        for rb in breakdowns:
            j5 = rb.get("j5_ms", 0)
            ee_off = rb.get("ee_off_ms", 0)
            j3 = rb.get("j3_ms", 0)
            j4 = rb.get("j4_ms", 0)
            comp = rb.get("compressor_ms", 0)
            total = j5 + ee_off + j3 + j4 + comp
            if total > 0:
                compressor_totals.append(comp)
                full_retreat_totals.append(total)

        if compressor_totals and full_retreat_totals:
            total_comp = sum(compressor_totals)
            total_retreat = sum(full_retreat_totals)
            avg_pct = total_comp / total_retreat if total_retreat > 0 else 0.0
            sorted_comp = sorted(compressor_totals)
            n = len(sorted_comp)
            p50_comp = sorted_comp[n // 2]
            if avg_pct > 0.8:
                issues.append(
                    {
                        "severity": "low",
                        "category": "performance",
                        "title": (
                            f"Compressor burst accounts for {avg_pct * 100:.0f}% of retreat time"
                        ),
                        "description": (
                            f"Compressor burst accounts for {avg_pct * 100:.0f}% of retreat"
                            f" time "
                            f"(p50={p50_comp}ms) — reducing burst duration would directly"
                            f" improve "
                            f"cycle time"
                        ),
                        "node": "arm_control",
                        "timestamp": 0,
                        "message": (
                            f"Compressor burst: {avg_pct * 100:.0f}% of retreat time "
                            f"p50={p50_comp}ms"
                        ),
                        "recommendation": (
                            "Reduce EE compressor burst duration in arm firmware configuration"
                        ),
                        "arm_id": None,
                    }
                )

    # Bottleneck joint: one joint's p95 approach > 2x next-slowest
    timings = events.per_joint_timings
    if len(timings) >= 2:
        joint_durations: dict = {}
        for t in timings:
            joint = t.get("joint", "?")
            joint_durations.setdefault(joint, []).append(t.get("duration_ms", 0))

        if len(joint_durations) >= 2:
            joint_p95: dict = {}
            for joint, vals in joint_durations.items():
                sorted_v = sorted(vals)
                n = len(sorted_v)
                joint_p95[joint] = sorted_v[min(int(n * 0.95), n - 1)]

            sorted_joints = sorted(joint_p95.items(), key=lambda x: -x[1])
            if len(sorted_joints) >= 2:
                worst_joint, worst_p95 = sorted_joints[0]
                second_p95 = sorted_joints[1][1]
                if second_p95 > 0 and worst_p95 > 2 * second_p95:
                    issues.append(
                        {
                            "severity": "low",
                            "category": "performance",
                            "title": (
                                f"{worst_joint} approach time (p95={worst_p95}ms) is"
                                f" significantly "
                                f"slower than other joints"
                            ),
                            "description": (
                                f"{worst_joint} approach motion p95={worst_p95}ms vs"
                                f" next-slowest "
                                f"p95={second_p95}ms — over 2x slower"
                            ),
                            "node": "arm_control",
                            "timestamp": 0,
                            "message": (
                                f"Bottleneck joint {worst_joint} p95={worst_p95}ms > 2x "
                                f"next-slowest {second_p95}ms"
                            ),
                            "recommendation": (
                                f"Review motion profile speed for {worst_joint}; check for "
                                f"mechanical friction or CAN bus slowness"
                            ),
                            "arm_id": None,
                        }
                    )

    return issues


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
from .registry import register as _register

_register(
    "detect_ee_timeout_rate", detect_ee_timeout_rate,
    category="arm",
    description="Flag high end-effector position monitoring timeout rates.",
)
_register(
    "detect_joint_limit_pattern", detect_joint_limit_pattern,
    category="motor",
    description="Detect joints repeatedly hitting position limits.",
)
_register(
    "detect_camera_frame_wait_degradation", detect_camera_frame_wait_degradation,
    category="camera",
    description="Detect increasing camera frame wait times over a session.",
)
_register(
    "detect_homing_failures", detect_homing_failures,
    category="motor",
    description="Flag joints with high homing failure rates or excessive retries.",
)
_register(
    "detect_compressor_dominance", detect_compressor_dominance,
    category="arm",
    description="Detect joints whose frame wait p95 dominates the session.",
)
