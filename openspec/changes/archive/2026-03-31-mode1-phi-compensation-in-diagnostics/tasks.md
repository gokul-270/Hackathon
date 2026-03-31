## Execution Plan

| Group | Depends On | Can Parallelize With |
|-------|-----------|----------------------|
| 1     | —         | —                    |
| 2     | 1         | —                    |
| 3     | 2         | —                    |

## 1. RED — Failing Tests [SEQUENTIAL]

- [ ] 1.1 In `test_collision_diagnostics.py`, add `test_diagnostic_j3_uses_compensated_phi`:
  pick a known camera point, compute `raw_j3` and `j5` via `polar_decompose()`,
  compute expected `comp_j3 = phi_compensation(raw_j3, j5)`, call `diagnose_collision()`
  for that point, assert `report["arm1_joints"]["j3"] == comp_j3`.
  Run and confirm FAIL (currently returns raw j3).
- [ ] 1.2 In `test_collision_diagnostics.py`, update `_assert_paired_mode` Mode 1 block:
  change the local `j5_limit1` computation to use `compensated_j3` instead of
  `report["arm1_joints"]["j3"]`-from-report (pre-fix the test so it stays consistent
  after the production fix). Confirm this test now also fails for points where
  compensation shifts the verdict.

## 2. GREEN — Production Fix [SEQUENTIAL]

- [ ] 2.1 In `collision_diagnostics.py`, import `phi_compensation` from `fk_chain`
  (add to the existing `from fk_chain import ...` line).
- [ ] 2.2 In `collision_diagnostics._cam_to_joints()`, after `polar_decompose()` call,
  add: `result["j3"] = phi_compensation(result["j3"], result["j5"])`.
  Run the RED tests from step 1 — confirm they now pass GREEN.

## 3. REFACTOR and Verify [SEQUENTIAL]

- [ ] 3.1 Run full test suite: `python3 -m pytest test_baseline_mode.py features/test_collision_diagnostics.py features/test_mode1_bdd.py -q`.
  Fix any tests that break due to verdict shifts (update expected j3/j5_limit values
  to reflect compensated phi).
- [ ] 3.2 Confirm all 1172+ tests pass. Commit:
  `fix: apply phi_compensation in collision_diagnostics._cam_to_joints for Mode 1 consistency`
