## Why

Mode 1's current blocking criterion — `|j4_own − j4_peer| < 0.05 m` — is geometry-blind:
it ignores the arm's tilt angle (J3), so it can block picks that are geometrically safe and
allow picks that would actually collide. The arm's real collision risk depends on its
*horizontal reach* (`J5 × cos(|J3|)`), not raw lateral distance. Replacing the check with a
cosine-derived reach limit makes Mode 1 physically correct and consistent with the Arm Cosine
Test already validated in the UI.

## What Changes

- **BREAKING**: Mode 1 (`BASELINE_J5_BLOCK_SKIP`) blocking criterion changes from
  `|j4_own − j4_peer| < 0.05 m` to `j5_own > 0.20 / cos(|j3_own|)`.
- The j4 lateral gap is no longer used in Mode 1; only own-arm tilt (J3) and extension (J5)
  are evaluated.
- The 0.20 m constant (`adj`) is the fixed safe horizontal reach boundary.
- Peer-presence guard is unchanged: no peer or idle peer → always safe.
- `collision_diagnostics.py` Mode 1 section updated to reflect the new criterion.
- All Mode 1 BDD scenarios and unit tests replaced to exercise the cosine formula.

## Capabilities

### New Capabilities

- `mode1-cosine-blocking`: Mode 1 uses `J5_limit = 0.20 / cos(|J3|)` as the blocking
  threshold — if the arm's candidate J5 exceeds this limit while a peer is active, j5 is
  zeroed. Covers the formula, boundary cases, guard against cos ≈ 0, and peer-presence
  semantics.

### Modified Capabilities

- `collision-avoidance-modes`: Mode 1 requirement changes — blocking is no longer based on
  j4 lateral gap but on cosine-derived horizontal reach limit.

## Non-goals

- No change to Modes 0, 2, 3, or 4.
- No change to the Arm Cosine Test UI panel (it uses the same formula independently for
  hardware validation, not blocking).
- No change to how `adj = 0.20 m` is configured (hard-coded constant for now).
- No change to joint limits, FK chain, or scenario JSON format.

## Impact

- `baseline_mode.py` — `_apply_baseline_j5_block_skip()` rewritten
- `test_baseline_mode.py` — Mode 1 unit tests replaced
- `features/mode1_baseline_j5_block.feature` — all BDD scenarios rewritten
- `features/test_mode1_bdd.py` — step bindings updated if needed
- `collision_diagnostics.py` — Mode 1 diagnostic section + `MODE1_THRESHOLD` constant
- `test_collision_diagnostics.py` — Mode 1 diagnostic assertions updated
- `features/cross_mode_comparison.feature` — threshold comparison scenarios updated
