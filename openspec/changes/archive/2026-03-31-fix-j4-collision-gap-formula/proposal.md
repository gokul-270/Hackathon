## Why

The two robot arms face opposite directions on the vehicle, so J4 (prismatic lateral slide) has opposite sign conventions per arm. The current collision avoidance formula `abs(j4_arm1 - j4_arm2)` computes an incorrect lateral gap — it underestimates when arms converge and overestimates when they diverge. The correct formula is `abs(j4_arm1 + j4_arm2)`, which accounts for the mirrored orientation. This affects all 7 call sites across truth monitoring, geometry checks, sequential pick policy, overlap zone detection, collision diagnostics, and smart reorder scheduling.

## What Changes

- **New helper module** `collision_math.py` with `j4_collision_gap(j4_a, j4_b)` returning `abs(j4_a + j4_b)`
- **Replace inline formula** at all 7 call sites: `truth_monitor.py`, `geometry_check.py` (2 sites), `sequential_pick_policy.py`, `overlap_zone_state.py`, `collision_diagnostics.py`, `smart_reorder_scheduler.py`
- **Update all unit tests** to use opposite-sign J4 values reflecting the real physical setup (negate peer/arm2 J4 values)

## Non-goals

- Changing the FK pipeline or joint-limit definitions in `fk_chain.py`
- Modifying the arm configuration data structures
- Changing any UI display logic for collision distances
- Altering the collision threshold values themselves

## Capabilities

### New Capabilities
- `j4-collision-gap-helper`: Centralized helper function for computing lateral collision gap between opposite-facing arms

### Modified Capabilities
- `collision-truth-monitoring`: Gap calculation changes from `abs(a-b)` to `j4_collision_gap(a,b)`
- `collision-avoidance-modes`: Geometry check stages 1 and 2 use new formula
- `sequential-pick-policy`: Contention detection uses new formula
- `smart-reorder-scheduler`: Pre-run step reorder optimizer uses new formula

## Impact

- **Source files** (7 modifications): `truth_monitor.py`, `geometry_check.py`, `sequential_pick_policy.py`, `overlap_zone_state.py`, `collision_diagnostics.py`, `smart_reorder_scheduler.py`
- **New files** (2): `collision_math.py`, `test_collision_math.py`
- **Test files** (6+ modifications): All corresponding test files need peer J4 values negated
- **All files under**: `pragati_ros2/src/vehicle_arm_sim/web_ui/`
