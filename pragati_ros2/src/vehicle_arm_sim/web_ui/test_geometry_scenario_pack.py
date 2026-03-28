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

import pytest

# Add web_ui to path so we can import fk_chain
_WEB_UI = os.path.dirname(__file__)
if _WEB_UI not in sys.path:
    sys.path.insert(0, _WEB_UI)

from fk_chain import camera_to_arm, polar_decompose

_SCENARIO_PATH = os.path.join(
    os.path.dirname(__file__), "scenarios", "geometry_pack.json"
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
        if abs(j4_arm1 - j4_arm2) < 0.12:
            overlap_count += 1

    assert overlap_count >= 2, (
        f"Expected >= 2 overlap-heavy paired steps (j4 gap < 0.12 m), got {overlap_count}"
    )
