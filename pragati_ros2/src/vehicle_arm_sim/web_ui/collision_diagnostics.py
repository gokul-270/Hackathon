"""collision_diagnostics.py — Diagnostic engine for collision avoidance analysis.

Given camera coordinates (cam_x, cam_y, cam_z) for two arms, converts them to
joint values (j3, j4, j5) using the real FK pipeline (camera_to_arm +
polar_decompose from fk_chain.py), then evaluates all 5 collision avoidance
modes and returns a structured report explaining:
  - The FK conversion result (camera coords → joint values)
  - Whether a collision/contention is detected
  - Which threshold was violated (and by how much)
  - How the mode intervenes (j5 zeroed, sequenced, reordered, etc.)

This module is imported by test_collision_diagnostics.py.
"""
from __future__ import annotations

import dataclasses
import math
from typing import Optional

from baseline_mode import BaselineMode
from fk_chain import camera_to_arm, polar_decompose
from sequential_pick_policy import SequentialPickPolicy


# ── Thresholds (from source) ──────────────────────────────────────────────
MODE1_THRESHOLD = 0.05
MODE2_STAGE1_THRESHOLD = 0.12
MODE2_STAGE2_LATERAL = 0.06
MODE2_STAGE2_J5_SUM = 0.5
MODE3_THRESHOLD = 0.10


@dataclasses.dataclass
class PeerStatePacket:
    """Minimal stand-in for arm_runtime.PeerStatePacket."""

    candidate_joints: Optional[dict]


def _cam_to_joints(cam_x: float, cam_y: float, cam_z: float) -> dict:
    """Convert camera coordinates to joint values using real FK pipeline.

    Uses j4_pos=0.0 (arm at home position before run starts).

    Returns dict with j3, j4, j5, reachable, r, phi, and the intermediate
    arm-frame coordinates (ax, ay, az).
    """
    ax, ay, az = camera_to_arm(cam_x, cam_y, cam_z, j4_pos=0.0)
    result = polar_decompose(ax, ay, az)
    result["ax"] = ax
    result["ay"] = ay
    result["az"] = az
    return result


def diagnose_collision(
    arm1_cam_x: float,
    arm1_cam_y: float,
    arm1_cam_z: float,
    arm2_cam_x: float,
    arm2_cam_y: float,
    arm2_cam_z: float,
) -> dict:
    """Evaluate all 5 modes and return a structured diagnostic report.

    Parameters
    ----------
    arm1_cam_x, arm1_cam_y, arm1_cam_z : float
        Camera coordinates for arm1's target cotton boll.
    arm2_cam_x, arm2_cam_y, arm2_cam_z : float
        Camera coordinates for arm2's target cotton boll.

    Returns
    -------
    dict with keys:
        arm1_joints, arm2_joints: {j3, j4, j5}
        arm1_reachable, arm2_reachable: bool
        j4_gap, combined_j5: float
        modes: { mode_0..mode_4: {verdict, reason, intervention, details} }
        formatted_output: str
    """
    # ── FK conversion: camera coords → joint values ───────────────────
    fk1 = _cam_to_joints(arm1_cam_x, arm1_cam_y, arm1_cam_z)
    fk2 = _cam_to_joints(arm2_cam_x, arm2_cam_y, arm2_cam_z)

    arm1_joints = {"j3": fk1["j3"], "j4": fk1["j4"], "j5": fk1["j5"]}
    arm2_joints = {"j3": fk2["j3"], "j4": fk2["j4"], "j5": fk2["j5"]}

    arm1_j5 = fk1["j5"]
    arm2_j5 = fk2["j5"]
    j4_gap = abs(fk1["j4"] - fk2["j4"])
    combined_j5 = arm1_j5 + arm2_j5

    peer_state = PeerStatePacket(candidate_joints=dict(arm2_joints))

    modes = {}

    # ── Mode 0: Unrestricted ──────────────────────────────────────────
    modes["mode_0"] = {
        "verdict": "NO_CHECK",
        "reason": "Mode 0 performs no collision checks",
        "intervention": "none",
        "details": "Both arms execute freely in parallel",
    }

    # ── Mode 1: Baseline j5 block ────────────────────────────────────
    bm = BaselineMode()
    bm.apply_with_skip(
        BaselineMode.BASELINE_J5_BLOCK_SKIP, dict(arm1_joints), peer_state
    )
    if j4_gap < MODE1_THRESHOLD:
        modes["mode_1"] = {
            "verdict": "COLLISION",
            "reason": (
                f"j4 gap {j4_gap:.4f}m < {MODE1_THRESHOLD}m threshold"
            ),
            "intervention": "j5_zeroed",
            "details": (
                f"j5 set to 0 (was {arm1_j5:.4f}). "
                f"Gap shortfall: {MODE1_THRESHOLD - j4_gap:.4f}m"
            ),
        }
    else:
        modes["mode_1"] = {
            "verdict": "SAFE",
            "reason": (
                f"j4 gap {j4_gap:.4f}m >= {MODE1_THRESHOLD}m threshold"
            ),
            "intervention": "none",
            "details": (
                f"Gap margin: {j4_gap - MODE1_THRESHOLD:.4f}m above threshold"
            ),
        }

    # ── Mode 2: Geometry block (two-stage) ────────────────────────────
    if j4_gap >= MODE2_STAGE1_THRESHOLD:
        modes["mode_2"] = {
            "verdict": "SAFE",
            "reason": (
                f"Stage 1: j4 gap {j4_gap:.4f}m >= "
                f"{MODE2_STAGE1_THRESHOLD}m "
                f"-> not risky, Stage 2 skipped"
            ),
            "intervention": "none",
            "details": (
                f"Gap margin from Stage 1: "
                f"{j4_gap - MODE2_STAGE1_THRESHOLD:.4f}m"
            ),
        }
    elif j4_gap < MODE2_STAGE2_LATERAL and combined_j5 > MODE2_STAGE2_J5_SUM:
        modes["mode_2"] = {
            "verdict": "COLLISION",
            "reason": (
                f"Stage 1: j4 gap {j4_gap:.4f}m < "
                f"{MODE2_STAGE1_THRESHOLD}m -> risky. "
                f"Stage 2: gap {j4_gap:.4f}m < {MODE2_STAGE2_LATERAL}m AND "
                f"combined j5 {combined_j5:.3f} > "
                f"{MODE2_STAGE2_J5_SUM} -> unsafe"
            ),
            "intervention": "j5_zeroed",
            "details": (
                f"j5 set to 0 (was {arm1_j5:.4f}). "
                f"Stage 2 lateral shortfall: "
                f"{MODE2_STAGE2_LATERAL - j4_gap:.4f}m. "
                f"j5 sum excess: {combined_j5 - MODE2_STAGE2_J5_SUM:.3f}"
            ),
        }
    else:
        stage2_reason_parts = []
        if j4_gap >= MODE2_STAGE2_LATERAL:
            stage2_reason_parts.append(
                f"gap {j4_gap:.4f}m >= {MODE2_STAGE2_LATERAL}m (lateral safe)"
            )
        if combined_j5 <= MODE2_STAGE2_J5_SUM:
            stage2_reason_parts.append(
                f"combined j5 {combined_j5:.3f} <= {MODE2_STAGE2_J5_SUM} "
                f"(extension safe)"
            )
        modes["mode_2"] = {
            "verdict": "SAFE",
            "reason": (
                f"Stage 1: j4 gap {j4_gap:.4f}m < "
                f"{MODE2_STAGE1_THRESHOLD}m -> risky. "
                f"Stage 2: {'; '.join(stage2_reason_parts)}"
            ),
            "intervention": "none",
            "details": "Stage 2 conditions not both met -> no block",
        }

    # ── Mode 3: Sequential pick ───────────────────────────────────────
    policy = SequentialPickPolicy()
    _, _, is_contention, is_winner = policy.apply(
        0, "arm1", dict(arm1_joints), dict(arm2_joints)
    )
    if is_contention:
        modes["mode_3"] = {
            "verdict": "CONTENTION",
            "reason": (
                f"j4 gap {j4_gap:.4f}m < {MODE3_THRESHOLD}m AND "
                f"both arms extending "
                f"(arm1 j5={arm1_j5:.4f}, arm2 j5={arm2_j5:.4f})"
            ),
            "intervention": "sequenced",
            "details": (
                f"Winner arm dispatched first, loser waits. "
                f"arm1 is {'winner' if is_winner else 'loser'} at step 0"
            ),
        }
    else:
        no_contention_parts = []
        if j4_gap >= MODE3_THRESHOLD:
            no_contention_parts.append(
                f"gap {j4_gap:.4f}m >= {MODE3_THRESHOLD}m"
            )
        if arm1_j5 <= 0:
            no_contention_parts.append(
                f"arm1 not extending (j5={arm1_j5:.4f})"
            )
        if arm2_j5 <= 0:
            no_contention_parts.append(
                f"arm2 not extending (j5={arm2_j5:.4f})"
            )
        modes["mode_3"] = {
            "verdict": "SAFE",
            "reason": (
                f"No contention: {'; '.join(no_contention_parts)}"
                if no_contention_parts
                else "No contention: conditions not met"
            ),
            "intervention": "none",
            "details": "Both arms execute in parallel without sequencing",
        }

    # ── Mode 4: Smart reorder ─────────────────────────────────────────
    modes["mode_4"] = {
        "verdict": "REORDER_CANDIDATE",
        "reason": (
            f"Pre-run scheduler would rearrange step pairings to maximize "
            f"minimum j4 gap (current gap: {j4_gap:.4f}m)"
        ),
        "intervention": "reorder",
        "details": (
            f"Per-step execution is passthrough. "
            f"FK: arm1 j4={fk1['j4']:.4f}, arm2 j4={fk2['j4']:.4f}"
        ),
    }

    # ── Build formatted output ────────────────────────────────────────
    formatted = _format_report(
        arm1_cam_x, arm1_cam_y, arm1_cam_z, fk1,
        arm2_cam_x, arm2_cam_y, arm2_cam_z, fk2,
        j4_gap, combined_j5, modes,
    )

    return {
        "arm1_joints": arm1_joints,
        "arm2_joints": arm2_joints,
        "arm1_reachable": fk1["reachable"],
        "arm2_reachable": fk2["reachable"],
        "j4_gap": j4_gap,
        "combined_j5": combined_j5,
        "modes": modes,
        "formatted_output": formatted,
    }


# ── Pretty-printer ────────────────────────────────────────────────────────

_MODE_NAMES = {
    "mode_0": "Mode 0 (unrestricted)",
    "mode_1": "Mode 1 (baseline_j5_block)",
    "mode_2": "Mode 2 (geometry_block)",
    "mode_3": "Mode 3 (sequential_pick)",
    "mode_4": "Mode 4 (smart_reorder)",
}

_VERDICT_SYMBOLS = {
    "NO_CHECK": "  ",
    "SAFE": "\u2705",
    "COLLISION": "\u274c",
    "CONTENTION": "\u26a0\ufe0f ",
    "REORDER_CANDIDATE": "\u2194\ufe0f ",
}


def _format_report(
    arm1_cx, arm1_cy, arm1_cz, fk1,
    arm2_cx, arm2_cy, arm2_cz, fk2,
    j4_gap, combined_j5, modes,
) -> str:
    w = 80
    lines = []
    lines.append("=" * w)
    lines.append("  FK Conversion: camera (cam_x, cam_y, cam_z) -> joints (j3, j4, j5)")
    lines.append("-" * w)

    reach1 = "reachable" if fk1["reachable"] else "UNREACHABLE"
    reach2 = "reachable" if fk2["reachable"] else "UNREACHABLE"

    lines.append(
        f"  arm1: cam({arm1_cx:.3f}, {arm1_cy:.3f}, {arm1_cz:.3f}) "
        f"-> j3={fk1['j3']:+.4f}rad  j4={fk1['j4']:.4f}m  "
        f"j5={fk1['j5']:.4f}m  [{reach1}]"
    )
    lines.append(
        f"  arm2: cam({arm2_cx:.3f}, {arm2_cy:.3f}, {arm2_cz:.3f}) "
        f"-> j3={fk2['j3']:+.4f}rad  j4={fk2['j4']:.4f}m  "
        f"j5={fk2['j5']:.4f}m  [{reach2}]"
    )
    lines.append("")
    lines.append(
        f"  j4 gap = {j4_gap:.4f}m    combined j5 = {combined_j5:.4f}m"
    )
    lines.append("-" * w)

    for mode_key in sorted(modes.keys()):
        mr = modes[mode_key]
        name = _MODE_NAMES.get(mode_key, mode_key)
        sym = _VERDICT_SYMBOLS.get(mr["verdict"], "?")
        verdict = mr["verdict"]

        lines.append(f"  {sym} {name:<30s} {verdict:<20s}")
        lines.append(f"     Reason:       {mr['reason']}")
        lines.append(f"     Intervention: {mr['intervention']}")
        lines.append(f"     Details:      {mr['details']}")
        lines.append("")

    lines.append("=" * w)
    return "\n".join(lines)
