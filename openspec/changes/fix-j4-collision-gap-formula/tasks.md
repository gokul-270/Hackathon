## Execution Plan

| Group | Depends On | Can Parallelize With |
|-------|-----------|---------------------|
| 1. Helper module | None | None |
| 2. truth_monitor | 1 | 3, 4, 5, 6 |
| 3. geometry_check | 1 | 2, 4, 5, 6 |
| 4. sequential_pick_policy | 1 | 2, 3, 5, 6 |
| 5. overlap_zone_state | 1 | 2, 3, 4, 6 |
| 6. collision_diagnostics | 1 | 2, 3, 4, 5 |
| 7. smart_reorder_scheduler | 1 | 2, 3, 4, 5, 6 |
| 8. Full regression | 2, 3, 4, 5, 6, 7 | None |

## 1. Create collision_math helper module [SEQUENTIAL]

- [x] 1.1 Write failing tests for `j4_collision_gap` in `test_collision_math.py` (same-sign, opposite-sign, symmetric, zero cases)
- [x] 1.2 Create `collision_math.py` with `j4_collision_gap(j4_a, j4_b)` returning `abs(j4_a + j4_b)`
- [x] 1.3 Run tests green and commit

## 2. Migrate truth_monitor.py [PARALLEL with 3, 4, 5, 6, 7]

- [x] 2.1 Negate all arm2 J4 values in `test_truth_monitor.py` fixture data
- [x] 2.2 Run tests to confirm they fail (RED)
- [x] 2.3 Add `from collision_math import j4_collision_gap` to `truth_monitor.py` and replace `abs(j4_arm1 - j4_arm2)` with `j4_collision_gap(j4_arm1, j4_arm2)` on line 26
- [x] 2.4 Run tests green and commit

## 3. Migrate geometry_check.py (Stages 1 & 2) [PARALLEL with 2, 4, 5, 6, 7]

- [x] 3.1 Negate all `peer["j4"]` values in `test_geometry_stage1.py`
- [x] 3.2 Negate all `peer["j4"]` values in `test_geometry_stage2.py`
- [x] 3.3 Run tests to confirm they fail (RED)
- [x] 3.4 Add `from collision_math import j4_collision_gap` to `geometry_check.py` and replace `abs(own_joints["j4"] - peer_joints["j4"])` with `j4_collision_gap(own_joints["j4"], peer_joints["j4"])` on lines 51 and 75
- [x] 3.5 Run tests green and commit

## 4. Migrate sequential_pick_policy.py [PARALLEL with 2, 3, 5, 6, 7]

- [x] 4.1 Negate all peer J4 values in `test_sequential_pick_policy.py` (PEER_FAR, PEER_BOUNDARY_AT, PEER_BOUNDARY_BELOW constants and inline dicts)
- [x] 4.2 Run tests to confirm they fail (RED)
- [x] 4.3 Add `from collision_math import j4_collision_gap` to `sequential_pick_policy.py` and replace `abs(own_joints["j4"] - peer_joints["j4"])` with `j4_collision_gap(own_joints["j4"], peer_joints["j4"])` on line 49
- [x] 4.4 Run tests green and commit

## 5. Migrate overlap_zone_state.py [PARALLEL with 2, 3, 4, 6, 7]

- [x] 5.1 Negate all `peer["j4"]` values in `test_overlap_zone_state.py`
- [x] 5.2 Run tests to confirm they fail (RED)
- [x] 5.3 Add `from collision_math import j4_collision_gap` to `overlap_zone_state.py` and replace `abs(own_joints["j4"] - peer_joints["j4"])` with `j4_collision_gap(own_joints["j4"], peer_joints["j4"])` on line 11
- [x] 5.4 Run tests green and commit

## 6. Migrate collision_diagnostics.py [PARALLEL with 2, 3, 4, 5, 7]

- [x] 6.1 Add `from collision_math import j4_collision_gap` to `collision_diagnostics.py` and replace `abs(fk1["j4"] - fk2["j4"])` with `j4_collision_gap(fk1["j4"], fk2["j4"])` on line 195
- [x] 6.2 Run `features/test_collision_diagnostics.py` and fix any assertion failures case-by-case
- [x] 6.3 Commit when green

## 7. Migrate smart_reorder_scheduler.py [PARALLEL with 2, 3, 4, 5, 6]

- [x] 7.1 Update `_min_j4_gap` helper in `test_smart_reorder_scheduler.py` to use `abs(j4_a1 + j4_a2)` and update all manual gap calculations
- [x] 7.2 Recalculate expected gap assertion values for FK-derived tests (test 3: ~0.199, test 4: 0.199)
- [x] 7.3 Run tests to confirm they fail (RED)
- [x] 7.4 Add `from collision_math import j4_collision_gap` to `smart_reorder_scheduler.py` and replace inline formula on line 121
- [x] 7.5 Run tests green and commit

## 8. Full regression test suite [SEQUENTIAL]

- [x] 8.1 Run all collision avoidance unit tests together
- [x] 8.2 Run BDD tests (`features/`) and fix any J4-related failures
- [x] 8.3 Run E2E tests (`test_geometry_block_e2e.py`, `test_overlap_zone_wait_e2e.py`) and fix any failures
- [x] 8.4 Grep for any remaining `abs(.*j4.*-.*j4)` patterns to ensure no call sites were missed
- [x] 8.5 Final commit if any fixes were needed
