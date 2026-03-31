## Before / After Behavior

| Item | Before (current) | After |
|------|-----------------|-------|
| `_cam_to_joints()` returns `j3` | Raw phi from `polar_decompose()` | Compensated phi: `phi_compensation(raw_j3, j5)` |
| Mode 1 diagnostic j5_limit | `0.20 / cos(\|raw_j3\|)` | `0.20 / cos(\|compensated_j3\|)` |
| Mode 1 diagnostic verdict consistency | May differ from runtime verdict at steep angles | Matches runtime verdict |
| `result["phi"]` in diagnostic report | Raw phi | Raw phi (unchanged) |
| `baseline_mode.py` runtime formula | Uses compensated j3 (unchanged — always was) | Uses compensated j3 (unchanged) |

## Performance Impact

| Item | CPU | Memory | Latency |
|------|-----|--------|---------|
| `phi_compensation()` added to `_cam_to_joints()` | Negligible (+3 arithmetic ops per FK call) | None | None |

`phi_compensation()` performs only floating-point arithmetic (compare, multiply, add).
No I/O, no allocation, no change to test count or loop count.

## Unchanged Behavior

- `baseline_mode.py` — no code change; it already receives compensated j3 from `RunController`
- `arm_runtime.py` — no change
- `fk_chain.py` — no change
- All ROS2 nodes, topics, services, launch files — no change
- Mode 2, 3, 4 logic — no change
- `result["phi"]` key in diagnostic report — still holds raw phi
- API surface of `diagnose_collision()` — signature unchanged
- `_test_options`, `_csv_paths` conftest infrastructure — unchanged

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|-----------|
| Mode 1 SAFE/COLLISION verdict flips for some CSV points | Low — compensation is small (~5°) and most test points are not near the limit | TDD RED confirms the fix before applying; full suite run catches any broken assertions |
| `phi_compensation` import breaks if `fk_chain` API changes | Very low — function is stable and already imported elsewhere | Import error is immediate and obvious at test time |

## Blast Radius

- **Files modified**: 2 (`collision_diagnostics.py`, `test_collision_diagnostics.py`)
- **Approximate lines changed**: ~5 production lines, ~15 test lines
- **Packages affected**: `vehicle_arm_sim` (web_ui only)
- **No ROS2 nodes modified**
- **No config or launch files modified**
