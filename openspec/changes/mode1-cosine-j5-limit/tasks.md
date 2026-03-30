## Execution Plan

| Group | Depends On | Can Parallelize With |
|-------|-----------|----------------------|
| 1. RED — Failing Tests | — | — |
| 2. GREEN — Implementation | 1 | — |
| 3. Diagnostics Update | 2 | — |
| 4. Cross-Mode BDD Update | 2 | 3 |
| 5. Verify & Commit | 3, 4 | — |

---

## 1. RED — Failing Tests [SEQUENTIAL]

- [x] 1.1 In `test_baseline_mode.py`, replace `test_baselinemode_baseline_j5_block_skip_blocks_j5_when_peer_active_and_j4_within_0_05m` with a test that asserts j5 is zeroed when `j3=0.0, j5=0.25` (exceeds `0.20 / cos(0) = 0.20`)
- [x] 1.2 In `test_baseline_mode.py`, replace `test_baselinemode_baseline_j5_block_skip_does_not_block_j5_when_j4_difference_exceeds_0_05m` with a test that asserts j5 is safe when `j3=0.0, j5=0.19` (below `0.20 / cos(0) = 0.20`)
- [x] 1.3 Add test: `j3=0.0, j5=0.20` (boundary — exactly at limit) → j5 not zeroed
- [x] 1.4 Add test: `j3=-0.5236 (30°), j5=0.24` → j5 zeroed (`0.20/cos(30°) ≈ 0.231`)
- [x] 1.5 Add test: `j3=-0.5236 (30°), j5=0.22` → j5 not zeroed (below limit)
- [x] 1.6 Add test: `j3=-0.89 (≈51°), j5=0.30` → j5 not zeroed (below cosine limit at 51°)
- [x] 1.7 Rewrite `features/mode1_baseline_j5_block.feature` — replace all j4-gap scenarios with `(j3, j5)` cosine-limit scenarios matching the spec
- [x] 1.8 Run `python3 -m pytest test_baseline_mode.py features/test_mode1_bdd.py -x` — confirm RED

## 2. GREEN — Implement Cosine Blocking [SEQUENTIAL]

- [x] 2.1 In `baseline_mode.py`, add constant `_MODE1_ADJ = 0.20` at module level
- [x] 2.2 Rewrite `_apply_baseline_j5_block_skip()`: compute `theta = abs(own_joints["j3"])`, `cos_theta = math.cos(theta)`, `j5_limit = _MODE1_ADJ / cos_theta if cos_theta > 0.01 else float("inf")`, block if `own_joints["j5"] > j5_limit`
- [x] 2.3 Add `import math` to `baseline_mode.py` if not already present
- [x] 2.4 Run `python3 -m pytest test_baseline_mode.py features/test_mode1_bdd.py -x` — confirm GREEN
- [x] 2.5 Commit: `feat: replace mode1 j4-gap threshold with cosine-derived J5 reach limit`

## 3. Diagnostics Update [PARALLEL with 4]

- [x] 3.1 In `collision_diagnostics.py`, rename `MODE1_THRESHOLD` to `MODE1_ADJ` and set to `0.20`
- [x] 3.2 Update Mode 1 section in `_diagnose_paired()`: compute `theta = abs(fk1["j3"])`, `cos_theta = math.cos(theta)`, `j5_limit = MODE1_ADJ / cos_theta if cos_theta > 0.01 else float("inf")`, check `arm1_j5 > j5_limit`
- [x] 3.3 Update the `verdict`, `reason`, and `details` strings in both COLLISION and SAFE branches to reference the cosine limit instead of j4 gap
- [x] 3.4 In `test_collision_diagnostics.py`, update all Mode 1 assertions to use cosine-limit inputs and expected verdicts
- [x] 3.5 Run `python3 -m pytest test_collision_diagnostics.py -x` — confirm GREEN

## 4. Cross-Mode BDD Update [PARALLEL with 3]

- [x] 4.1 In `features/cross_mode_comparison.feature`, remove or rewrite the "Mode 1 threshold (0.05m) is stricter than Mode 3 (0.10m)" scenario — the 0.05m j4 gap no longer applies to Mode 1
- [x] 4.2 Update "Arms at j4 gap of 0.03m trigger both Mode 1 and Mode 3" — verify whether Mode 1 still triggers given new criterion (it depends on j3/j5, not j4 gap); rewrite scenario accordingly
- [x] 4.3 Update "Arms at j4 gap of 0.11m trigger neither Mode 1 nor Mode 3" — same: Mode 1 outcome now depends on j3/j5
- [x] 4.4 Run `python3 -m pytest features/test_cross_mode_bdd.py -x` — confirm GREEN

## 5. Verify & Commit [SEQUENTIAL]

- [x] 5.1 Run full suite: `python3 -m pytest . -x` from `web_ui/` — all tests must pass (16 pre-existing failures confirmed unchanged)
- [x] 5.2 Confirm no test references the old `MODE1_THRESHOLD = 0.05` constant or j4-gap Mode 1 logic
- [x] 5.3 Commit: `feat: update diagnostics and cross-mode BDD for cosine-based mode1 blocking`
