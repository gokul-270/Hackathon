## Why

The Mode 1 cosine j5 limit formula (`j5_limit = 0.20 / cos(|j3|)`) must use the
**compensated phi** angle, not the raw geometric phi.  During a real run,
`ArmRuntime.compute_candidate_joints()` applies `phi_compensation()` to `j3`
before handing joints to `BaselineMode` — so the formula already uses the compensated
value at runtime.  However, `collision_diagnostics.py` bypasses
`compute_candidate_joints()` and calls `polar_decompose()` directly, so its `j3`
is raw phi.  This makes diagnostic Mode 1 verdicts inconsistent with what actually
happens during execution.

## What Changes

- `collision_diagnostics._cam_to_joints()`: apply `phi_compensation(j3, j5)` to
  `result["j3"]` after `polar_decompose()`, matching the `ArmRuntime` pipeline.
- `collision_diagnostics.py` imports `phi_compensation` from `fk_chain`.
- Test assertions in `test_collision_diagnostics.py` that compute the expected
  `j5_limit` must also use compensated j3.
- A new RED→GREEN unit test is added to lock in the compensated-phi behaviour.

## Capabilities

### New Capabilities

- `mode1-phi-compensation`: The Mode 1 cosine j5 limit formula must use the
  compensated phi angle (after `phi_compensation()`) both at runtime and in
  diagnostic evaluation, ensuring consistent verdicts.

### Modified Capabilities

- `collision-avoidance-modes`: The Mode 1 j3 input to the cosine formula is
  defined as the compensated phi, not the raw geometric phi.

## Impact

- **`collision_diagnostics.py`**: `_cam_to_joints()` gains a `phi_compensation()`
  call; imports `phi_compensation` from `fk_chain`.
- **`test_collision_diagnostics.py`**: `_assert_paired_mode` Mode 1 logic updates
  expected j5_limit to use compensated j3.
- **No change** to `baseline_mode.py` — it already receives compensated j3 from
  `RunController` at runtime.
- **No change** to `arm_runtime.py`, `fk_chain.py`, or any ROS2 node.
- Diagnostic Mode 1 verdicts may shift for a small number of CSV points at steep
  angles where compensation is non-negligible.
