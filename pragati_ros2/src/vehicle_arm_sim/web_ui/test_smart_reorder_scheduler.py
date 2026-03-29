"""Tests for SmartReorderScheduler -- Mode 4 smart reorder."""

import pytest
from itertools import permutations
from smart_reorder_scheduler import SmartReorderScheduler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FK_OFFSET = 0.1005


def _j4(cam_z: float) -> float:
    """Compute j4 from cam_z using FK formula."""
    return FK_OFFSET - cam_z


def _make_step_data(cam_z: float, cam_x: float = 0.0, cam_y: float = 0.0) -> dict:
    """Build a minimal arm step dict with required cam fields."""
    return {"cam_x": cam_x, "cam_y": cam_y, "cam_z": cam_z}


def _min_j4_gap(step_map: dict, arm1_steps: list, arm2_steps: list) -> float:
    """Compute the minimum |j4_arm1 - j4_arm2| across all paired steps."""
    paired_count = min(len(arm1_steps), len(arm2_steps))
    if paired_count == 0:
        return float("inf")
    gaps = []
    for i in range(paired_count):
        sid = i  # sequential IDs after reorder
        a1 = step_map[sid]["arm1"]
        a2 = step_map[sid]["arm2"]
        j4_a1 = _j4(a1["cam_z"])
        j4_a2 = _j4(a2["cam_z"])
        gaps.append(abs(j4_a1 - j4_a2))
    return min(gaps)


def _collect_cam_z_values(step_map: dict, arm: str) -> set:
    """Collect all cam_z values for an arm across the step_map."""
    values = set()
    for sid, data in step_map.items():
        if arm in data:
            values.add(data[arm]["cam_z"])
    return values


# ---------------------------------------------------------------------------
# Test 1: reorder preserves all steps (no data lost)
# ---------------------------------------------------------------------------


def test_reorder_preserves_all_steps():
    """After reorder, all original step data is present -- no data lost."""
    step_map = {
        0: {
            "arm1": _make_step_data(cam_z=0.10, cam_x=1.0, cam_y=2.0),
            "arm2": _make_step_data(cam_z=0.20, cam_x=3.0, cam_y=4.0),
        },
        1: {
            "arm1": _make_step_data(cam_z=0.15, cam_x=5.0, cam_y=6.0),
            "arm2": _make_step_data(cam_z=0.25, cam_x=7.0, cam_y=8.0),
        },
        2: {
            "arm1": _make_step_data(cam_z=0.30, cam_x=9.0, cam_y=10.0),
            "arm2": _make_step_data(cam_z=0.35, cam_x=11.0, cam_y=12.0),
        },
    }
    arm1_steps = [0, 1, 2]
    arm2_steps = [0, 1, 2]

    scheduler = SmartReorderScheduler()
    result = scheduler.reorder(step_map, arm1_steps, arm2_steps)

    # Collect all cam_z, cam_x, cam_y values from the original for each arm
    orig_arm1_cam_z = {step_map[s]["arm1"]["cam_z"] for s in arm1_steps}
    orig_arm1_cam_x = {step_map[s]["arm1"]["cam_x"] for s in arm1_steps}
    orig_arm1_cam_y = {step_map[s]["arm1"]["cam_y"] for s in arm1_steps}
    orig_arm2_cam_z = {step_map[s]["arm2"]["cam_z"] for s in arm2_steps}
    orig_arm2_cam_x = {step_map[s]["arm2"]["cam_x"] for s in arm2_steps}
    orig_arm2_cam_y = {step_map[s]["arm2"]["cam_y"] for s in arm2_steps}

    result_arm1_cam_z = set()
    result_arm1_cam_x = set()
    result_arm1_cam_y = set()
    result_arm2_cam_z = set()
    result_arm2_cam_x = set()
    result_arm2_cam_y = set()

    for sid, data in result.items():
        if "arm1" in data:
            result_arm1_cam_z.add(data["arm1"]["cam_z"])
            result_arm1_cam_x.add(data["arm1"]["cam_x"])
            result_arm1_cam_y.add(data["arm1"]["cam_y"])
        if "arm2" in data:
            result_arm2_cam_z.add(data["arm2"]["cam_z"])
            result_arm2_cam_x.add(data["arm2"]["cam_x"])
            result_arm2_cam_y.add(data["arm2"]["cam_y"])

    assert orig_arm1_cam_z == result_arm1_cam_z
    assert orig_arm1_cam_x == result_arm1_cam_x
    assert orig_arm1_cam_y == result_arm1_cam_y
    assert orig_arm2_cam_z == result_arm2_cam_z
    assert orig_arm2_cam_x == result_arm2_cam_x
    assert orig_arm2_cam_y == result_arm2_cam_y


# ---------------------------------------------------------------------------
# Test 2: reorder improves min gap
# ---------------------------------------------------------------------------


def test_reorder_improves_min_gap():
    """Build a step_map where original pairing has a very small min j4 gap.

    After reorder, min j4 gap across all paired steps should be >= original.
    """
    # Original pairing: step 0 has arm1 cam_z=0.15 (j4=-0.0495) and
    # arm2 cam_z=0.16 (j4=-0.0595) -> gap = 0.01 (tiny!)
    # step 1: arm1 cam_z=0.30 (j4=-0.1995), arm2 cam_z=0.10 (j4=0.0005) -> gap=0.20
    # step 2: arm1 cam_z=0.25 (j4=-0.1495), arm2 cam_z=0.35 (j4=-0.2495) -> gap=0.10
    # Original min gap = 0.01
    step_map = {
        0: {
            "arm1": _make_step_data(cam_z=0.15),
            "arm2": _make_step_data(cam_z=0.16),
        },
        1: {
            "arm1": _make_step_data(cam_z=0.30),
            "arm2": _make_step_data(cam_z=0.10),
        },
        2: {
            "arm1": _make_step_data(cam_z=0.25),
            "arm2": _make_step_data(cam_z=0.35),
        },
    }
    arm1_steps = [0, 1, 2]
    arm2_steps = [0, 1, 2]

    # Compute original min gap
    orig_gaps = []
    for s in range(3):
        j4_a1 = _j4(step_map[s]["arm1"]["cam_z"])
        j4_a2 = _j4(step_map[s]["arm2"]["cam_z"])
        orig_gaps.append(abs(j4_a1 - j4_a2))
    orig_min_gap = min(orig_gaps)
    assert orig_min_gap == pytest.approx(0.01, abs=1e-6)  # sanity check

    scheduler = SmartReorderScheduler()
    result = scheduler.reorder(step_map, arm1_steps, arm2_steps)

    new_min_gap = _min_j4_gap(result, arm1_steps, arm2_steps)
    assert new_min_gap >= orig_min_gap - 1e-9


# ---------------------------------------------------------------------------
# Test 3: already optimal unchanged
# ---------------------------------------------------------------------------


def test_already_optimal_unchanged():
    """When arm1 cam_z values are far from arm2 cam_z values at every step,
    the min gap is already large. After reorder, min gap should be same or better.
    """
    # arm1 always cam_z=0.10 (j4=0.0005), arm2 always cam_z=0.30 (j4=-0.1995)
    # gap = 0.20 at every step -- already very separated
    step_map = {
        0: {
            "arm1": _make_step_data(cam_z=0.10),
            "arm2": _make_step_data(cam_z=0.30),
        },
        1: {
            "arm1": _make_step_data(cam_z=0.10),
            "arm2": _make_step_data(cam_z=0.30),
        },
        2: {
            "arm1": _make_step_data(cam_z=0.10),
            "arm2": _make_step_data(cam_z=0.30),
        },
    }
    arm1_steps = [0, 1, 2]
    arm2_steps = [0, 1, 2]

    orig_min_gap = 0.20  # |0.0005 - (-0.1995)| = 0.20

    scheduler = SmartReorderScheduler()
    result = scheduler.reorder(step_map, arm1_steps, arm2_steps)

    new_min_gap = _min_j4_gap(result, arm1_steps, arm2_steps)
    assert new_min_gap >= orig_min_gap - 1e-9


# ---------------------------------------------------------------------------
# Test 4: j4 computed from cam_z via FK
# ---------------------------------------------------------------------------


def test_j4_computed_from_cam_z_via_fk():
    """Verify the FK formula is used correctly.

    arm1 cam_z=0.15 -> j4 = 0.1005 - 0.15 = -0.0495
    arm2 cam_z=0.25 -> j4 = 0.1005 - 0.25 = -0.1495
    gap = |-0.0495 - (-0.1495)| = 0.10
    """
    step_map = {
        0: {
            "arm1": _make_step_data(cam_z=0.15),
            "arm2": _make_step_data(cam_z=0.25),
        },
    }
    arm1_steps = [0]
    arm2_steps = [0]

    scheduler = SmartReorderScheduler()
    result = scheduler.reorder(step_map, arm1_steps, arm2_steps)

    # With only 1 step, result should be identical
    a1_cam_z = result[0]["arm1"]["cam_z"]
    a2_cam_z = result[0]["arm2"]["cam_z"]
    j4_a1 = FK_OFFSET - a1_cam_z
    j4_a2 = FK_OFFSET - a2_cam_z

    assert j4_a1 == pytest.approx(-0.0495, abs=1e-9)
    assert j4_a2 == pytest.approx(-0.1495, abs=1e-9)
    assert abs(j4_a1 - j4_a2) == pytest.approx(0.10, abs=1e-9)


# ---------------------------------------------------------------------------
# Test 5: unequal step counts -- solo tail
# ---------------------------------------------------------------------------


def test_unequal_step_counts_solo_tail():
    """arm1 has 4 steps, arm2 has 2 steps.

    After reorder, output step_map has the right number of entries.
    Solo-tail steps (arm1's extra 2) are preserved at the end with only arm1 data.
    """
    step_map = {
        0: {
            "arm1": _make_step_data(cam_z=0.10),
            "arm2": _make_step_data(cam_z=0.20),
        },
        1: {
            "arm1": _make_step_data(cam_z=0.15),
            "arm2": _make_step_data(cam_z=0.25),
        },
        2: {
            "arm1": _make_step_data(cam_z=0.30),
        },
        3: {
            "arm1": _make_step_data(cam_z=0.35),
        },
    }
    arm1_steps = [0, 1, 2, 3]
    arm2_steps = [0, 1]

    scheduler = SmartReorderScheduler()
    result = scheduler.reorder(step_map, arm1_steps, arm2_steps)

    # Total entries = 4 (2 paired + 2 solo-tail)
    assert len(result) == 4

    # Paired steps (IDs 0, 1) have both arms
    for sid in [0, 1]:
        assert "arm1" in result[sid]
        assert "arm2" in result[sid]

    # Solo-tail steps (IDs 2, 3) have only arm1
    for sid in [2, 3]:
        assert "arm1" in result[sid]
        assert "arm2" not in result[sid]

    # All original arm1 cam_z values preserved
    orig_arm1_cam_z = {step_map[s]["arm1"]["cam_z"] for s in arm1_steps}
    result_arm1_cam_z = {
        result[sid]["arm1"]["cam_z"] for sid in result if "arm1" in result[sid]
    }
    assert orig_arm1_cam_z == result_arm1_cam_z


# ---------------------------------------------------------------------------
# Test 6: brute force small N -- truly optimal
# ---------------------------------------------------------------------------


def test_brute_force_small_n():
    """With N=3 steps per arm (3! = 6 permutations), verify the result is truly
    optimal by checking all permutations manually.
    """
    # arm1 j4s: cam_z = [0.10, 0.20, 0.30] -> j4 = [-0.0005+0.1005=0.0005, -0.0995, -0.1995]
    # Wait, j4 = 0.1005 - cam_z:
    #   cam_z=0.10 -> j4=0.0005
    #   cam_z=0.20 -> j4=-0.0995
    #   cam_z=0.30 -> j4=-0.1995
    # arm2 j4s: cam_z = [0.12, 0.22, 0.28] -> j4 = [-0.0195, -0.1195, -0.1795]
    arm1_cam_z = [0.10, 0.20, 0.30]
    arm2_cam_z = [0.12, 0.22, 0.28]

    step_map = {
        0: {
            "arm1": _make_step_data(cam_z=arm1_cam_z[0]),
            "arm2": _make_step_data(cam_z=arm2_cam_z[0]),
        },
        1: {
            "arm1": _make_step_data(cam_z=arm1_cam_z[1]),
            "arm2": _make_step_data(cam_z=arm2_cam_z[1]),
        },
        2: {
            "arm1": _make_step_data(cam_z=arm1_cam_z[2]),
            "arm2": _make_step_data(cam_z=arm2_cam_z[2]),
        },
    }
    arm1_steps = [0, 1, 2]
    arm2_steps = [0, 1, 2]

    # Manually check all 6 permutations of arm2 against fixed arm1 order
    arm1_j4s = [_j4(z) for z in arm1_cam_z]
    arm2_j4s = [_j4(z) for z in arm2_cam_z]

    best_min_gap = -1.0
    for perm in permutations(range(3)):
        gaps = [abs(arm1_j4s[i] - arm2_j4s[perm[i]]) for i in range(3)]
        mg = min(gaps)
        if mg > best_min_gap:
            best_min_gap = mg

    scheduler = SmartReorderScheduler()
    result = scheduler.reorder(step_map, arm1_steps, arm2_steps)

    result_min_gap = _min_j4_gap(result, arm1_steps, arm2_steps)
    assert result_min_gap == pytest.approx(best_min_gap, abs=1e-9)


# ---------------------------------------------------------------------------
# Test 7: greedy fallback for large N
# ---------------------------------------------------------------------------


def test_greedy_fallback_large_n():
    """With N=10 steps per arm (10! = 3.6M permutations), verify it returns a
    valid result in reasonable time and min gap >= original pairing's min gap.
    """
    import time

    # Generate 10 arm1 cam_z values linearly spaced 0.05..0.50
    # and 10 arm2 cam_z values linearly spaced 0.06..0.51
    # Original pairing will have small gaps at some steps
    n = 10
    arm1_cam_z_vals = [0.05 + i * 0.05 for i in range(n)]
    arm2_cam_z_vals = [0.06 + i * 0.05 for i in range(n)]

    step_map = {}
    for i in range(n):
        step_map[i] = {
            "arm1": _make_step_data(cam_z=arm1_cam_z_vals[i]),
            "arm2": _make_step_data(cam_z=arm2_cam_z_vals[i]),
        }
    arm1_steps = list(range(n))
    arm2_steps = list(range(n))

    # Original min gap
    orig_gaps = []
    for i in range(n):
        j4_a1 = _j4(arm1_cam_z_vals[i])
        j4_a2 = _j4(arm2_cam_z_vals[i])
        orig_gaps.append(abs(j4_a1 - j4_a2))
    orig_min_gap = min(orig_gaps)

    scheduler = SmartReorderScheduler()
    start = time.monotonic()
    result = scheduler.reorder(step_map, arm1_steps, arm2_steps)
    elapsed = time.monotonic() - start

    # Must complete in reasonable time (< 5 seconds)
    assert elapsed < 5.0, f"Greedy fallback took too long: {elapsed:.2f}s"

    # Result must be valid
    assert len(result) == n

    # Min gap must be >= original
    new_min_gap = _min_j4_gap(result, arm1_steps, arm2_steps)
    assert new_min_gap >= orig_min_gap - 1e-9


# ---------------------------------------------------------------------------
# Test 8: single step passthrough
# ---------------------------------------------------------------------------


def test_single_step_passthrough():
    """Only 1 step for each arm. Reorder returns the same mapping."""
    step_map = {
        0: {
            "arm1": _make_step_data(cam_z=0.15),
            "arm2": _make_step_data(cam_z=0.25),
        },
    }
    arm1_steps = [0]
    arm2_steps = [0]

    scheduler = SmartReorderScheduler()
    result = scheduler.reorder(step_map, arm1_steps, arm2_steps)

    assert len(result) == 1
    assert result[0]["arm1"]["cam_z"] == 0.15
    assert result[0]["arm2"]["cam_z"] == 0.25


# ---------------------------------------------------------------------------
# Test 9: empty arm passthrough
# ---------------------------------------------------------------------------


def test_empty_arm_passthrough():
    """One arm has 0 steps. Reorder returns step_map unchanged."""
    step_map = {
        0: {
            "arm1": _make_step_data(cam_z=0.15),
        },
        1: {
            "arm1": _make_step_data(cam_z=0.25),
        },
    }
    arm1_steps = [0, 1]
    arm2_steps = []

    scheduler = SmartReorderScheduler()
    result = scheduler.reorder(step_map, arm1_steps, arm2_steps)

    assert len(result) == 2
    assert result[0]["arm1"]["cam_z"] == 0.15
    assert result[1]["arm1"]["cam_z"] == 0.25
    # No arm2 data in any step
    for sid in result:
        assert "arm2" not in result[sid]


# ---------------------------------------------------------------------------
# Test 10: returned step_map has sequential IDs
# ---------------------------------------------------------------------------


def test_returned_step_map_has_sequential_ids():
    """After reorder, step_map keys should be sequential integers starting from 0."""
    step_map = {
        0: {
            "arm1": _make_step_data(cam_z=0.10),
            "arm2": _make_step_data(cam_z=0.20),
        },
        1: {
            "arm1": _make_step_data(cam_z=0.15),
            "arm2": _make_step_data(cam_z=0.25),
        },
        2: {
            "arm1": _make_step_data(cam_z=0.30),
            "arm2": _make_step_data(cam_z=0.35),
        },
        3: {
            "arm1": _make_step_data(cam_z=0.40),
        },
    }
    arm1_steps = [0, 1, 2, 3]
    arm2_steps = [0, 1, 2]

    scheduler = SmartReorderScheduler()
    result = scheduler.reorder(step_map, arm1_steps, arm2_steps)

    expected_keys = list(range(len(result)))
    assert sorted(result.keys()) == expected_keys
