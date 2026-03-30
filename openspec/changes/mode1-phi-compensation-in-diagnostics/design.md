## Context

Mode 1 (`BASELINE_J5_BLOCK_SKIP`) limits each arm's horizontal reach using:

```
j5_limit = 0.20 / cos(|j3|)   (guard: cos < 0.1 → limit = inf)
```

`j3` is the arm tilt angle (phi).  The FK pipeline in `fk_chain.py` computes a
raw geometric phi from `polar_decompose()`, then `arm_runtime.py` applies
`phi_compensation()` — a zone-based correction (±5 degrees at j5=0, scaling with
j5 extension) — before the joints are passed to `BaselineMode`.  The cosine formula
therefore **always** receives the compensated phi at runtime.

`collision_diagnostics.py` — used by the diagnostic test suite — calls
`polar_decompose()` directly in `_cam_to_joints()` and never calls
`phi_compensation()`.  Its `result["j3"]` is raw phi.  The Mode 1 diagnostic
verdict thus diverges from the runtime verdict whenever compensation is non-zero
(all Zone 1 angles, i.e., `|phi| ≤ 50.5°`).

## Goals / Non-Goals

**Goals:**
- Make `collision_diagnostics._cam_to_joints()` apply `phi_compensation(j3, j5)`
  so diagnostic `j3` matches what `BaselineMode` receives at runtime.
- Update the test assertion in `_assert_paired_mode` to compute the expected
  `j5_limit` using the compensated j3.
- Lock the behaviour with a RED→GREEN unit test.

**Non-Goals:**
- No change to `baseline_mode.py` — it already uses compensated phi.
- No change to `arm_runtime.py` or `fk_chain.py`.
- No change to Mode 2, 3, or 4 logic.
- No change to the phi compensation algorithm itself.

## Decisions

### D1 — Apply compensation inside `_cam_to_joints()`, not the callers

**Decision**: add `result["j3"] = phi_compensation(result["j3"], result["j5"])`
inside `_cam_to_joints()` immediately after `polar_decompose()`.

**Rationale**: Every caller of `_cam_to_joints()` in `collision_diagnostics.py`
(`_diagnose_paired`, `_diagnose_solo`) needs compensated j3 for Mode 1.  Centralising
it in `_cam_to_joints()` keeps callers unchanged and mirrors what `compute_candidate_joints()`
does in `arm_runtime.py`.

**Alternative considered**: apply compensation only in the Mode 1 branch of
`_diagnose_paired`.  Rejected — it would leave `j3` in the returned report dict
as raw phi, confusing callers that display or test the value.

### D2 — Keep raw phi accessible via `result["phi"]`

`polar_decompose()` already stores the raw value in `result["phi"]`.
`_cam_to_joints()` does not clear or rename this key, so callers that need the
raw angle can still read it.  `j3` becomes the runtime-equivalent value.

### D3 — No `enable_phi_compensation` flag in diagnostics

`arm_runtime.py` guards the call with `if enable_phi_compensation`.  The diagnostics
engine has no such flag; compensation is always applied, matching the default
runtime configuration.  Adding a flag would over-engineer a diagnostic utility.

## Risks / Trade-offs

- **Verdict shifts**: A small number of CSV points at steep angles (Zone 1/3)
  will see their Mode 1 j5_limit change by ~5–8 degrees of compensation, potentially
  flipping a SAFE/COLLISION verdict.  This is the *correct* outcome — the diagnostic
  was wrong before.
- **Test churn**: The `_assert_paired_mode` Mode 1 expected j5_limit calculation
  must be updated to use compensated j3; otherwise passing tests would go RED after
  the fix.

## Migration Plan

1. RED — add unit test asserting diagnostic `j3` equals compensated phi.
2. GREEN — add `phi_compensation` import and call in `_cam_to_joints()`.
3. Update `_assert_paired_mode` Mode 1 computation to use compensated j3.
4. Run full suite; fix any verdict-shift test failures.
5. Commit.

## Open Questions

None — phi compensation algorithm and zone boundaries are already stable.
