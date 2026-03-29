"""
Tests for the contention scenario pack — designed to make overlap-zone contention visible.

The contention scenario pack lives at:
  scenarios/contention_pack.json

It must contain scenarios where both arms target cotton in the overlap zone
simultaneously, causing contention in sequential_pick mode and collisions in
unrestricted mode.

Design contract
---------------
The file scenarios/contention_pack.json must:
  1. Be valid JSON (loadable without error).
  2. Have at least 4 step_ids where BOTH arm1 and arm2 are present (dual-arm steps).
  3. When run with UNRESTRICTED mode, produce at least 1 step with collision
     (|j4_arm1 - j4_arm2| < 0.05 m).
  4. Have varied cam_z values across steps (not all identical) — scenario diversity.

These tests fail until the scenario file is created.
"""
import json
import os
import sys

import pytest

# Add web_ui to path so we can import fk_chain, run_controller, baseline_mode
_WEB_UI = os.path.dirname(__file__)
if _WEB_UI not in sys.path:
    sys.path.insert(0, _WEB_UI)

from baseline_mode import BaselineMode
from run_controller import RunController

_SCENARIO_PATH = os.path.join(
    os.path.dirname(__file__), "scenarios", "contention_pack.json"
)


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def contention_pack():
    """Load the contention scenario pack file."""
    with open(_SCENARIO_PATH) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Test 1: File is valid JSON
# ---------------------------------------------------------------------------


def test_contention_pack_file_is_valid_json():
    """The contention_pack.json file must exist and load without error."""
    assert os.path.exists(_SCENARIO_PATH), (
        f"contention_pack.json not found at {_SCENARIO_PATH}"
    )
    with open(_SCENARIO_PATH) as f:
        data = json.load(f)
    assert "steps" in data, "contention_pack.json must have a 'steps' key"


# ---------------------------------------------------------------------------
# Test 2: At least 4 dual-arm step_ids
# ---------------------------------------------------------------------------


def test_contention_pack_has_at_least_4_dual_arm_steps(contention_pack):
    """The pack must have at least 4 step_ids where both arm1 and arm2 are present."""
    step_map: dict[int, set] = {}
    for step in contention_pack["steps"]:
        step_map.setdefault(step["step_id"], set()).add(step["arm_id"])

    dual_arm_steps = [sid for sid, arms in step_map.items() if len(arms) == 2]
    assert len(dual_arm_steps) >= 4, (
        f"Expected >= 4 dual-arm step_ids (both arm1 and arm2), "
        f"got {len(dual_arm_steps)}: {dual_arm_steps}"
    )


# ---------------------------------------------------------------------------
# Test 3: UNRESTRICTED mode produces at least 1 collision
# ---------------------------------------------------------------------------


def test_contention_pack_unrestricted_run_produces_collisions():
    """Running with UNRESTRICTED mode must produce at least 1 collision step."""
    with open(_SCENARIO_PATH) as f:
        data = json.load(f)

    controller = RunController(mode=BaselineMode.UNRESTRICTED)
    controller.load_scenario(data)
    summary = controller.run()

    steps_with_collision = summary.get("steps_with_collision", 0)
    assert steps_with_collision >= 1, (
        f"Expected >= 1 collision step in UNRESTRICTED mode, got {steps_with_collision}. "
        f"Summary: {summary}"
    )


# ---------------------------------------------------------------------------
# Test 4: Varied cam_z values (scenario diversity)
# ---------------------------------------------------------------------------


def test_contention_pack_scenario_has_varied_cam_values(contention_pack):
    """Not all steps should have identical cam_z values — scenario must be diverse."""
    cam_z_values = {step["cam_z"] for step in contention_pack["steps"]}
    assert len(cam_z_values) >= 2, (
        f"Expected at least 2 distinct cam_z values for scenario diversity, "
        f"got {len(cam_z_values)}: {cam_z_values}"
    )


# ---------------------------------------------------------------------------
# Group 6 — Asymmetric arm counts and collision/safe mix
# ---------------------------------------------------------------------------


def test_contention_pack_has_asymmetric_arm_counts(contention_pack):
    """arm1 must have exactly 4 steps and arm2 must have exactly 6 steps."""
    arm1_steps = [s for s in contention_pack["steps"] if s["arm_id"] == "arm1"]
    arm2_steps = [s for s in contention_pack["steps"] if s["arm_id"] == "arm2"]
    assert len(arm1_steps) == 4, (
        f"arm1 must have 4 steps, got {len(arm1_steps)}"
    )
    assert len(arm2_steps) == 6, (
        f"arm2 must have 6 steps, got {len(arm2_steps)}"
    )


def _j4_for_contention_step(step: dict) -> float:
    """Compute the j4 for a step using FK (starting from j4_pos=0)."""
    import os
    import sys
    _WEB_UI = os.path.dirname(__file__)
    if _WEB_UI not in sys.path:
        sys.path.insert(0, _WEB_UI)
    from fk_chain import camera_to_arm, polar_decompose
    joints = polar_decompose(*camera_to_arm(step["cam_x"], step["cam_y"], step["cam_z"], j4_pos=0.0))
    return joints["j4"]


def test_contention_pack_contains_colliding_and_safe_steps(contention_pack):
    """Must have at least 1 paired step with j4 gap < 0.05 m and 1 with j4 gap > 0.08 m."""
    step_map: dict[int, dict] = {}
    for step in contention_pack["steps"]:
        step_map.setdefault(step["step_id"], {})[step["arm_id"]] = step

    colliding = 0
    safe = 0
    for step_id, arms in step_map.items():
        if "arm1" not in arms or "arm2" not in arms:
            continue
        j4_arm1 = _j4_for_contention_step(arms["arm1"])
        j4_arm2 = _j4_for_contention_step(arms["arm2"])
        gap = abs(j4_arm1 - j4_arm2)
        if gap < 0.05:
            colliding += 1
        if gap > 0.08:
            safe += 1

    assert colliding >= 1, (
        f"Must have >= 1 paired step with j4 gap < 0.05 m (collision zone); "
        f"gaps: {[round(abs(_j4_for_contention_step(arms['arm1'])-_j4_for_contention_step(arms['arm2'])),4) for arms in step_map.values() if 'arm1' in arms and 'arm2' in arms]}"
    )
    assert safe >= 1, (
        f"Must have >= 1 paired step with j4 gap > 0.08 m (safe zone); "
        f"gaps: {[round(abs(_j4_for_contention_step(arms['arm1'])-_j4_for_contention_step(arms['arm2'])),4) for arms in step_map.values() if 'arm1' in arms and 'arm2' in arms]}"
    )


# ---------------------------------------------------------------------------
# Group 7 — World-space cotton position spread (>= 5 cm per arm)
# ---------------------------------------------------------------------------


def test_contention_pack_arm1_cotton_positions_are_spread_at_least_5cm_apart(contention_pack):
    """Each pair of arm1 cotton world positions must be >= 5 cm apart."""
    import math
    from fk_chain import camera_to_world_fk, ARM_CONFIGS
    arm1_steps = [s for s in contention_pack["steps"] if s["arm_id"] == "arm1"]
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


def test_contention_pack_arm2_cotton_positions_are_spread_at_least_5cm_apart(contention_pack):
    """Each pair of arm2 cotton world positions must be >= 5 cm apart."""
    import math
    from fk_chain import camera_to_world_fk, ARM_CONFIGS
    arm2_steps = [s for s in contention_pack["steps"] if s["arm_id"] == "arm2"]
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
