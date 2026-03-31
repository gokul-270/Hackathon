"""
Tests for the geometry scenario pack — overlap-heavy scenarios for geometry comparison.

The geometry scenario pack lives at:
  scenarios/geometry_pack.json

It must contain scenarios that make the geometry mode visibly different from both
unrestricted and baseline modes by having many paired steps where both arms
target cotton that is laterally close (producing near-collision geometry).

Design contract
---------------
The file scenarios/geometry_pack.json must:
  1. Be valid JSON with a "steps" key.
  2. Have at least 6 steps total.
  3. Have at least 3 paired steps (step_ids where BOTH arm1 and arm2 have entries).
  4. Among the paired steps, at least 2 must use camera coordinates where
     the arms' j4 lateral gap will be small (< 0.12 m) — i.e., overlap-heavy.
     We test this by computing FK on the camera coords and checking j4 proximity.
  5. Use valid arm_ids ("arm1", "arm2") and numeric cam_x/cam_y/cam_z.

These tests fail until the scenario file is created.
"""
import json
import os
import sys
from pathlib import Path

import pytest

# web_ui/ is injected by tests/conftest.py; no per-file sys.path hack needed
_WEB_UI = str(Path(__file__).resolve().parent.parent.parent)

from collision_math import j4_collision_gap
from fk_chain import camera_to_arm, polar_decompose

_SCENARIO_PATH = os.path.join(
    _WEB_UI, "scenarios", "geometry_pack.json"
)


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def geometry_pack():
    """Load the geometry scenario pack file."""
    with open(_SCENARIO_PATH) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Structure validation
# ---------------------------------------------------------------------------

def test_geometry_pack_file_exists():
    """The geometry_pack.json file must exist."""
    assert os.path.exists(_SCENARIO_PATH), (
        f"geometry_pack.json not found at {_SCENARIO_PATH}"
    )


def test_geometry_pack_has_steps_key(geometry_pack):
    """The file must have a 'steps' key."""
    assert "steps" in geometry_pack


def test_geometry_pack_has_at_least_six_steps(geometry_pack):
    """The scenario must have at least 6 steps to be meaningful."""
    assert len(geometry_pack["steps"]) >= 6


def test_geometry_pack_all_steps_have_valid_arm_ids(geometry_pack):
    """Every step must have arm_id of 'arm1' or 'arm2'."""
    for step in geometry_pack["steps"]:
        assert step["arm_id"] in ("arm1", "arm2"), (
            f"Invalid arm_id in step {step.get('step_id', '?')}: {step['arm_id']!r}"
        )


def test_geometry_pack_all_steps_have_numeric_cam_coords(geometry_pack):
    """Every step must have numeric cam_x, cam_y, cam_z."""
    for step in geometry_pack["steps"]:
        for key in ("cam_x", "cam_y", "cam_z"):
            assert isinstance(step[key], (int, float)), (
                f"step {step.get('step_id', '?')} has non-numeric {key}: {step[key]!r}"
            )


# ---------------------------------------------------------------------------
# Paired / overlap-heavy validation
# ---------------------------------------------------------------------------

def test_geometry_pack_has_at_least_three_paired_step_ids(geometry_pack):
    """The pack must have at least 3 step_ids where both arms are present."""
    step_map: dict[int, set] = {}
    for step in geometry_pack["steps"]:
        step_map.setdefault(step["step_id"], set()).add(step["arm_id"])
    paired = [sid for sid, arms in step_map.items() if len(arms) == 2]
    assert len(paired) >= 3, (
        f"Expected >= 3 paired step_ids, got {len(paired)}: {paired}"
    )


def _j4_for_step(step: dict) -> float:
    """Compute the j4 for a step using FK (starting from j4_pos=0)."""
    joints = polar_decompose(*camera_to_arm(step["cam_x"], step["cam_y"], step["cam_z"], j4_pos=0.0))
    return joints["j4"]


def test_geometry_pack_has_at_least_two_overlap_heavy_paired_steps(geometry_pack):
    """At least 2 paired step_ids must have |j4_arm1 - j4_arm2| < 0.12 m (overlap-heavy)."""
    step_map: dict[int, dict] = {}
    for step in geometry_pack["steps"]:
        step_map.setdefault(step["step_id"], {})[step["arm_id"]] = step

    overlap_count = 0
    for step_id, arms in step_map.items():
        if "arm1" not in arms or "arm2" not in arms:
            continue
        j4_arm1 = _j4_for_step(arms["arm1"])
        j4_arm2 = _j4_for_step(arms["arm2"])
        if j4_collision_gap(j4_arm1, j4_arm2) < 0.12:
            overlap_count += 1

    assert overlap_count >= 2, (
        f"Expected >= 2 overlap-heavy paired steps (j4 gap < 0.12 m), got {overlap_count}"
    )


# ---------------------------------------------------------------------------
# Group 6 — Asymmetric arm counts and collision/safe mix
# ---------------------------------------------------------------------------


def test_geometry_pack_has_asymmetric_arm_counts(geometry_pack):
    """arm1 must have exactly 3 steps and arm2 must have exactly 5 steps."""
    arm1_steps = [s for s in geometry_pack["steps"] if s["arm_id"] == "arm1"]
    arm2_steps = [s for s in geometry_pack["steps"] if s["arm_id"] == "arm2"]
    assert len(arm1_steps) == 3, (
        f"arm1 must have 3 steps, got {len(arm1_steps)}"
    )
    assert len(arm2_steps) == 5, (
        f"arm2 must have 5 steps, got {len(arm2_steps)}"
    )


def test_geometry_pack_contains_colliding_and_safe_steps(geometry_pack):
    """Must have at least 1 step with j4 gap < 0.05 m and 1 step with j4 gap > 0.08 m."""
    step_map: dict[int, dict] = {}
    for step in geometry_pack["steps"]:
        step_map.setdefault(step["step_id"], {})[step["arm_id"]] = step

    colliding = 0
    safe = 0
    for step_id, arms in step_map.items():
        if "arm1" not in arms or "arm2" not in arms:
            continue
        j4_arm1 = _j4_for_step(arms["arm1"])
        j4_arm2 = _j4_for_step(arms["arm2"])
        gap = j4_collision_gap(j4_arm1, j4_arm2)
        if gap < 0.05:
            colliding += 1
        if gap > 0.08:
            safe += 1

    assert colliding >= 1, (
        f"Must have >= 1 paired step with j4 gap < 0.05 m (collision zone); "
        f"step_map j4 gaps: "
        f"{[round(j4_collision_gap(_j4_for_step(arms['arm1']), _j4_for_step(arms['arm2'])),4) for arms in step_map.values() if 'arm1' in arms and 'arm2' in arms]}"
    )
    assert safe >= 1, (
        f"Must have >= 1 paired step with j4 gap > 0.08 m (safe zone); "
        f"step_map j4 gaps: "
        f"{[round(j4_collision_gap(_j4_for_step(arms['arm1']), _j4_for_step(arms['arm2'])),4) for arms in step_map.values() if 'arm1' in arms and 'arm2' in arms]}"
    )


# ---------------------------------------------------------------------------
# Group 7 — World-space cotton position spread (>= 5 cm per arm)
# ---------------------------------------------------------------------------


def test_geometry_pack_arm1_cotton_positions_are_spread_at_least_5cm_apart(geometry_pack):
    """Each pair of arm1 cotton world positions must be >= 5 cm apart."""
    import math
    from fk_chain import camera_to_world_fk, ARM_CONFIGS
    arm1_steps = [s for s in geometry_pack["steps"] if s["arm_id"] == "arm1"]
    cfg = ARM_CONFIGS["arm1"]
    positions = [
        camera_to_world_fk(s["cam_x"], s["cam_y"], s["cam_z"], j3=0.0, j4=0.0, arm_config=cfg)
        for s in arm1_steps
    ]
    for i in range(len(positions)):
        for j in range(i + 1, len(positions)):
            wx1, wy1, wz1 = positions[i]
            wx2, wy2, wz2 = positions[j]
            dist = math.sqrt((wx1 - wx2) ** 2 + (wy1 - wy2) ** 2 + (wz1 - wz2) ** 2)
            assert dist >= 0.05, (
                f"arm1 steps {i} and {j} are only {dist:.4f} m apart "
                f"(cam_z: {arm1_steps[i]['cam_z']}, {arm1_steps[j]['cam_z']})"
            )


def test_geometry_pack_arm2_cotton_positions_are_spread_at_least_5cm_apart(geometry_pack):
    """Each pair of arm2 cotton world positions must be >= 5 cm apart."""
    import math
    from fk_chain import camera_to_world_fk, ARM_CONFIGS
    arm2_steps = [s for s in geometry_pack["steps"] if s["arm_id"] == "arm2"]
    cfg = ARM_CONFIGS["arm2"]
    positions = [
        camera_to_world_fk(s["cam_x"], s["cam_y"], s["cam_z"], j3=0.0, j4=0.0, arm_config=cfg)
        for s in arm2_steps
    ]
    for i in range(len(positions)):
        for j in range(i + 1, len(positions)):
            wx1, wy1, wz1 = positions[i]
            wx2, wy2, wz2 = positions[j]
            dist = math.sqrt((wx1 - wx2) ** 2 + (wy1 - wy2) ** 2 + (wz1 - wz2) ** 2)
            assert dist >= 0.05, (
                f"arm2 steps {i} and {j} are only {dist:.4f} m apart "
                f"(cam_z: {arm2_steps[i]['cam_z']}, {arm2_steps[j]['cam_z']})"
            )
