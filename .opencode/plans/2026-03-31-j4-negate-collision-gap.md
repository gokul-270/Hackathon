# J4 Negate Collision Gap Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix collision avoidance J4 gap calculation to account for opposite-facing arms by negating arm2's J4 (`abs(j4_a + j4_b)` instead of `abs(j4_a - j4_b)`).

**Architecture:** Create a centralized `j4_collision_gap(j4_a, j4_b)` helper in a new `collision_math.py` module. All 7 call sites switch from inline `abs(j4_a - j4_b)` to calling this helper. Tests updated to use opposite-sign J4 values that reflect the real physical setup.

**Tech Stack:** Python 3.12, pytest

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `collision_math.py` | **Create** | Single helper function `j4_collision_gap()` |
| `test_collision_math.py` | **Create** | Unit tests for the helper |
| `truth_monitor.py` | Modify (line 26) | Use `j4_collision_gap` |
| `test_truth_monitor.py` | Modify | Update J4 test values to opposite-sign pairs |
| `geometry_check.py` | Modify (lines 51, 75) | Use `j4_collision_gap` in both stages |
| `test_geometry_stage1.py` | Modify | Update J4 test values |
| `test_geometry_stage2.py` | Modify | Update J4 test values |
| `sequential_pick_policy.py` | Modify (line 49) | Use `j4_collision_gap` |
| `test_sequential_pick_policy.py` | Modify | Update J4 test values |
| `overlap_zone_state.py` | Modify (line 11) | Use `j4_collision_gap` |
| `test_overlap_zone_state.py` | Modify | Update J4 test values |
| `collision_diagnostics.py` | Modify (line 195) | Use `j4_collision_gap` |
| `smart_reorder_scheduler.py` | Modify (line 121) | Use `j4_collision_gap` |
| `test_smart_reorder_scheduler.py` | Modify | Update `_min_j4_gap` helper and manual gap calcs |

All files are under `pragati_ros2/src/vehicle_arm_sim/web_ui/`.

---

## J4 Test Value Conversion Guide

The old formula was `abs(j4_a - j4_b)`. The new formula is `abs(j4_a + j4_b)`.

To preserve the same expected gap `G`, **negate every peer/arm2 J4 value** in tests.

Example: old test had `own_j4=0.30, peer_j4=0.35` → gap was `abs(0.30 - 0.35) = 0.05`.
New test: `own_j4=0.30, peer_j4=-0.35` → gap is `abs(0.30 + (-0.35)) = 0.05`. Same gap.

This works because `abs(a + (-b)) = abs(a - b)`.

---

### Task 1: Create `collision_math.py` with `j4_collision_gap` helper

**Files:**
- Create: `collision_math.py`
- Create: `test_collision_math.py`

- [ ] **Step 1: Write failing tests for `j4_collision_gap`**

```python
"""Tests for collision_math — centralized collision distance helpers."""

import pytest
from collision_math import j4_collision_gap


def test_j4_collision_gap_same_sign_gives_large_gap():
    """Both J4 positive (arms sliding same direction) → large gap."""
    # abs(0.10 + 0.10) = 0.20
    assert j4_collision_gap(0.10, 0.10) == pytest.approx(0.20, abs=1e-9)


def test_j4_collision_gap_opposite_signs_gives_small_gap():
    """J4 values with opposite signs (arms converging) → small gap."""
    # abs(0.10 + (-0.10)) = 0.00
    assert j4_collision_gap(0.10, -0.10) == pytest.approx(0.00, abs=1e-9)


def test_j4_collision_gap_realistic_near_collision():
    """Realistic near-collision: arm1=+0.05, arm2=-0.02 → gap=0.03."""
    # abs(0.05 + (-0.02)) = 0.03
    assert j4_collision_gap(0.05, -0.02) == pytest.approx(0.03, abs=1e-9)


def test_j4_collision_gap_symmetric():
    """Gap is the same regardless of which arm is first."""
    assert j4_collision_gap(0.10, -0.05) == j4_collision_gap(-0.05, 0.10)


def test_j4_collision_gap_both_zero():
    """Both at zero → gap is zero."""
    assert j4_collision_gap(0.0, 0.0) == pytest.approx(0.0, abs=1e-9)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test_collision_math.py -v`
(from `pragati_ros2/src/vehicle_arm_sim/web_ui/`)

Expected: `ModuleNotFoundError: No module named 'collision_math'`

- [ ] **Step 3: Write minimal implementation**

```python
"""collision_math.py — centralized collision distance helpers.

Arms face opposite directions on the vehicle. J4 (prismatic lateral slide)
has opposite sign conventions for each arm. To get the true lateral distance
for collision avoidance, we compute abs(j4_a + j4_b) instead of
abs(j4_a - j4_b).
"""


def j4_collision_gap(j4_a: float, j4_b: float) -> float:
    """Compute lateral gap between two opposite-facing arms for collision avoidance.

    Because the arms face opposite directions, arm2's J4 is effectively
    negated in world-frame. The true lateral distance is:
        abs(j4_arm1 - (-j4_arm2)) = abs(j4_arm1 + j4_arm2)

    Args:
        j4_a: J4 position of the first arm (meters).
        j4_b: J4 position of the second arm (meters).

    Returns:
        Absolute lateral gap in meters.
    """
    return abs(j4_a + j4_b)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test_collision_math.py -v`

Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add collision_math.py test_collision_math.py
git commit -m "feat: add j4_collision_gap helper for opposite-facing arm collision math"
```

---

### Task 2: Update `truth_monitor.py` and its tests

**Files:**
- Modify: `truth_monitor.py:26`
- Modify: `test_truth_monitor.py`

- [ ] **Step 1: Update test J4 values — negate arm2 J4 in every test**

In `test_truth_monitor.py`, negate every `j4_arm2` value:

| Test | Old j4_arm1/j4_arm2 | New j4_arm2 | Gap unchanged |
|------|---------------------|-------------|---------------|
| Line 8 | 0.5, 0.3 | **-0.3** | abs(0.5+(-0.3))=0.2 |
| Line 16 | 0.5, 0.3 | **-0.3** | 0.2 |
| Line 17 | 0.45, 0.36 | **-0.36** | 0.09 |
| Line 24 | 0.45, 0.36 | **-0.36** | 0.09 |
| Line 25 | 0.5, 0.3 | **-0.3** | 0.2 |
| Line 33 | 0.0, distance | **-distance** | same |
| Line 41 | 0.0, distance | **-distance** | same |
| Line 49 | 0.0, distance | **-distance** | same |
| Line 61 | 0.5, 0.3 | **-0.3** | 0.2 |
| Line 62 | 0.6, 0.4 | **-0.4** | 0.2 |
| Line 71 | 0.5, 0.3 | **-0.3** | 0.2 |
| Line 72 | 0.6, 0.4 | **-0.4** | 0.2 |
| Line 73 | 0.7, 0.5 | **-0.5** | 0.2 |
| Line 94 | 0.0, distance | **-distance** | same |
| Line 122-123 | 0.10+offset, 0.20+offset | **-(0.20+offset)** | same |

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test_truth_monitor.py -v`

Expected: Most tests FAIL

- [ ] **Step 3: Update `truth_monitor.py` to use `j4_collision_gap`**

Add import at top (after line 2):
```python
from collision_math import j4_collision_gap
```

Change line 26 from:
```python
distance = abs(j4_arm1 - j4_arm2)
```
to:
```python
distance = j4_collision_gap(j4_arm1, j4_arm2)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test_truth_monitor.py -v`

Expected: All 11 tests PASS

- [ ] **Step 5: Commit**

```bash
git add truth_monitor.py test_truth_monitor.py
git commit -m "fix: negate arm2 J4 in truth_monitor collision gap calculation"
```

---

### Task 3: Update `geometry_check.py` and its tests

**Files:**
- Modify: `geometry_check.py:51,75`
- Modify: `test_geometry_stage1.py`
- Modify: `test_geometry_stage2.py`

- [ ] **Step 1: Update Stage 1 test J4 values — negate `peer["j4"]`**

In `test_geometry_stage1.py`, negate every `peer["j4"]`:

| Test (line) | Old peer j4 | New peer j4 | Gap unchanged |
|-------------|-------------|-------------|---------------|
| 35 | 0.50 | **-0.50** | abs(0.10+(-0.50))=0.40 |
| 44 | 0.08 | **-0.08** | abs(0.00+(-0.08))=0.08 |
| 57 | 0.35 | **-0.35** | abs(0.30+(-0.35))=0.05 |
| 66 | 0.25 | **-0.25** | abs(0.25+(-0.25))=0.00 |
| 74 | 0.079 | **-0.079** | abs(0.000+(-0.079))=0.079 |
| 87 | 0.50 | **-0.50** | symmetric test |
| 95 | 0.35 | **-0.35** | symmetric test |
| 113 | 0.08 | **-0.08** | 0.08 |
| 122 | 0.079 | **-0.079** | 0.079 |

Also update inline comments referencing the old formula.

- [ ] **Step 2: Update Stage 2 test J4 values — negate `peer["j4"]`**

In `test_geometry_stage2.py`, negate every `peer["j4"]`:

| Test (line) | Old peer j4 | New peer j4 | Gap unchanged |
|-------------|-------------|-------------|---------------|
| 38 | 0.34 | **-0.34** | abs(0.30+(-0.34))=0.04 |
| 47 | 0.059 | **-0.059** | abs(0.00+(-0.059))=0.059 |
| 60 | 0.06 | **-0.06** | abs(0.00+(-0.06))=0.06 |
| 69 | 0.40 | **-0.40** | abs(0.10+(-0.40))=0.30 |
| 82 | 0.33 | **-0.33** | abs(0.30+(-0.33))=0.03 |
| 91 | 0.33 | **-0.33** | 0.03 |
| 104 | 0.34 | **-0.34** | 0.04 |
| 112 | 0.33 | **-0.33** | 0.03 |

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m pytest test_geometry_stage1.py test_geometry_stage2.py -v`

Expected: Most tests FAIL

- [ ] **Step 4: Update `geometry_check.py` to use `j4_collision_gap`**

Add import at top (after line 19):
```python
from collision_math import j4_collision_gap
```

Change line 51 (Stage 1) from:
```python
lateral_gap = abs(own_joints["j4"] - peer_joints["j4"])
```
to:
```python
lateral_gap = j4_collision_gap(own_joints["j4"], peer_joints["j4"])
```

Change line 75 (Stage 2) — same change.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest test_geometry_stage1.py test_geometry_stage2.py -v`

Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add geometry_check.py test_geometry_stage1.py test_geometry_stage2.py
git commit -m "fix: negate arm2 J4 in geometry_check collision gap calculation"
```

---

### Task 4: Update `sequential_pick_policy.py` and its tests

**Files:**
- Modify: `sequential_pick_policy.py:49`
- Modify: `test_sequential_pick_policy.py`

- [ ] **Step 1: Update test J4 values — negate peer J4 values**

Update `PEER_*` constants (lines 12-29):

```python
# Both arms at j4=0.0 → gap = abs(0.0 + 0.0) = 0.0 → contention (unchanged)
PEER_CONTENTION = {"j1": 0, "j2": 0, "j3": 0, "j4": 0.0, "j5": 1.0}  # no change

# Far apart: abs(0.0 + (-0.20)) = 0.20 >= 0.08 → no contention
PEER_FAR = {"j1": 0, "j2": 0, "j3": 0, "j4": -0.20, "j5": 1.0}  # was 0.20

PEER_J5_ZERO = {"j1": 0, "j2": 0, "j3": 0, "j4": 0.0, "j5": 0.0}  # no change

# Boundary: abs(0.0 + (-0.08)) = 0.08 → NOT contention
PEER_BOUNDARY_AT = {"j1": 0, "j2": 0, "j3": 0, "j4": -0.08, "j5": 1.0}  # was 0.08

# Boundary: abs(0.0 + (-0.079)) = 0.079 → IS contention
PEER_BOUNDARY_BELOW = {"j1": 0, "j2": 0, "j3": 0, "j4": -0.079, "j5": 1.0}  # was 0.079
```

Update inline peer dicts:
- Line 214 `peer`: `"j4": 0.05` → `"j4": -0.05`
- Line 234 `peer_arm2`: `"j4": 0.02` → `"j4": -0.02`
- Line 240 inline peer dict: `"j4": 0.02` → `"j4": -0.02`
- Line 346 `peer`: `"j4": 0.08` → `"j4": -0.08`
- Line 355 `peer`: `"j4": 0.079` → `"j4": -0.079`

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test_sequential_pick_policy.py -v`

Expected: Several tests FAIL

- [ ] **Step 3: Update `sequential_pick_policy.py` to use `j4_collision_gap`**

Add import at top (after line 17):
```python
from collision_math import j4_collision_gap
```

Change line 49 from:
```python
gap = abs(own_joints["j4"] - peer_joints["j4"])
```
to:
```python
gap = j4_collision_gap(own_joints["j4"], peer_joints["j4"])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test_sequential_pick_policy.py -v`

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add sequential_pick_policy.py test_sequential_pick_policy.py
git commit -m "fix: negate arm2 J4 in sequential_pick_policy collision gap calculation"
```

---

### Task 5: Update `overlap_zone_state.py` and its tests

**Files:**
- Modify: `overlap_zone_state.py:11`
- Modify: `test_overlap_zone_state.py`

- [ ] **Step 1: Update test J4 values — negate peer J4**

In `test_overlap_zone_state.py`, negate every `peer["j4"]`:

| Test (line) | Old peer j4 | New peer j4 | Gap unchanged |
|-------------|-------------|-------------|---------------|
| 18 | 0.35 | **-0.35** | abs(0.30+(-0.35))=0.05 |
| 27 | 0.35 | **-0.35** | abs(0.20+(-0.35))=0.15 |
| 36 | 0.08 | **-0.08** | abs(0.0+(-0.08))=0.08 |
| 49 | 0.35 | **-0.35** | 0.05 |
| 58 | 0.35 | **-0.35** | 0.05 |
| 67 | 0.35 | **-0.35** | 0.15 |
| 85 | 0.08 | **-0.08** | 0.08 |
| 94 | 0.079 | **-0.079** | 0.079 |

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test_overlap_zone_state.py -v`

Expected: Most tests FAIL

- [ ] **Step 3: Update `overlap_zone_state.py` to use `j4_collision_gap`**

Add import at top (after line 1):
```python
from collision_math import j4_collision_gap
```

Change line 11 from:
```python
return abs(own_joints["j4"] - peer_joints["j4"]) < self.OVERLAP_THRESHOLD
```
to:
```python
return j4_collision_gap(own_joints["j4"], peer_joints["j4"]) < self.OVERLAP_THRESHOLD
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test_overlap_zone_state.py -v`

Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add overlap_zone_state.py test_overlap_zone_state.py
git commit -m "fix: negate arm2 J4 in overlap_zone_state collision gap calculation"
```

---

### Task 6: Update `collision_diagnostics.py`

**Files:**
- Modify: `collision_diagnostics.py:195`

- [ ] **Step 1: Update `collision_diagnostics.py` to use `j4_collision_gap`**

Add import (after line 24):
```python
from collision_math import j4_collision_gap
```

Change line 195 from:
```python
j4_gap = abs(fk1["j4"] - fk2["j4"])
```
to:
```python
j4_gap = j4_collision_gap(fk1["j4"], fk2["j4"])
```

- [ ] **Step 2: Run diagnostics tests**

Run: `python3 -m pytest features/test_collision_diagnostics.py -v`

Expected: Tests pass (or need assertion value updates — fix case by case).

- [ ] **Step 3: Commit**

```bash
git add collision_diagnostics.py
git commit -m "fix: negate arm2 J4 in collision_diagnostics gap calculation"
```

---

### Task 7: Update `smart_reorder_scheduler.py` and its tests

**Files:**
- Modify: `smart_reorder_scheduler.py:121`
- Modify: `test_smart_reorder_scheduler.py`

- [ ] **Step 1: Update test helper `_min_j4_gap` to use addition**

In `test_smart_reorder_scheduler.py`, change line 37 from:
```python
gaps.append(abs(j4_a1 - j4_a2))
```
to:
```python
gaps.append(abs(j4_a1 + j4_a2))
```

Update all manual gap calculations in tests:
- Line 147: `abs(j4_a1 - j4_a2)` → `abs(j4_a1 + j4_a2)`
- Line 227: `abs(j4_a1 - j4_a2)` → `abs(j4_a1 + j4_a2)` and update expected value
  - j4_a1=-0.0495, j4_a2=-0.1495 → old gap=0.10, new gap=abs(-0.199)=0.199
- Line 325: `abs(arm1_j4s[i] - arm2_j4s[perm[i]])` → `abs(arm1_j4s[i] + arm2_j4s[perm[i]])`
- Line 369: `abs(j4_a1 - j4_a2)` → `abs(j4_a1 + j4_a2)`

Recalculate and update expected gap values in assertions for:
- Test 3 (`test_already_optimal_unchanged`): orig_min_gap was 0.20, becomes ~0.199
- Test 4 (`test_j4_computed_from_cam_z_via_fk`): gap was 0.10, becomes 0.199

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test_smart_reorder_scheduler.py -v`

Expected: Several tests FAIL

- [ ] **Step 3: Update `smart_reorder_scheduler.py`**

Add import at top (after line 13):
```python
from collision_math import j4_collision_gap
```

Change line 121 from:
```python
return min(abs(arm1_j4s[i] - arm2_j4s[perm[i]]) for i in range(len(arm1_j4s)))
```
to:
```python
return min(j4_collision_gap(arm1_j4s[i], arm2_j4s[perm[i]]) for i in range(len(arm1_j4s)))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test_smart_reorder_scheduler.py -v`

Expected: All 11 tests PASS

- [ ] **Step 5: Commit**

```bash
git add smart_reorder_scheduler.py test_smart_reorder_scheduler.py
git commit -m "fix: negate arm2 J4 in smart_reorder_scheduler collision gap calculation"
```

---

### Task 8: Full regression test suite

- [ ] **Step 1: Run all collision avoidance unit tests**

```bash
python3 -m pytest test_collision_math.py test_truth_monitor.py test_geometry_stage1.py test_geometry_stage2.py test_sequential_pick_policy.py test_overlap_zone_state.py test_smart_reorder_scheduler.py test_baseline_mode.py test_run_controller.py -v
```

Expected: All PASS

- [ ] **Step 2: Run BDD tests**

```bash
python3 -m pytest features/ -v
```

Expected: All PASS (fix any failures by updating J4 values in feature steps)

- [ ] **Step 3: Run E2E tests**

```bash
python3 -m pytest test_geometry_block_e2e.py test_overlap_zone_wait_e2e.py -v
```

Expected: All PASS

- [ ] **Step 4: Fix any remaining failures and commit**

If any tests fail, update their J4 values following the negate-peer pattern.

```bash
git add -A
git commit -m "fix: update remaining tests for J4 negate collision gap formula"
```
