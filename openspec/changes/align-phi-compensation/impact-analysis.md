## Before / After Behavior

| Item | Before (current) | After |
|---|---|---|
| `phi_compensation()` formula | `base = offset` | `base = slope * (phi_deg / 90) + offset` |
| Slope constants | Not defined | `PHI_ZONE{1,2,3}_SLOPE = 0.0` |
| `enable_phi_compensation` default | `False` (all endpoints) | `True` (all endpoints) |
| Dual-arm run J3 | Raw phi, no compensation | Compensated phi (matching single-pick) |
| UI checkbox default | Unchecked | Checked |
| `/api/run/start` request | No `enable_phi_compensation` field | Includes `enable_phi_compensation: true` |

Note: Since all slopes are 0.0, the formula change produces identical numeric output.
The behavioral change is the default flip from `false` to `true` and the dual-arm wiring.

## Performance Impact

| Item | CPU | Memory | Latency |
|---|---|---|---|
| Slope multiplication in phi_compensation | +1 multiply per call, negligible | None | None |
| Dual-arm compensation call | +2 calls per step (one per arm), ~microseconds | None | None |

No threads, timers, or polling loops added.

## Unchanged Behavior

- No breaking API shape changes — existing callers continue to work.
  One new optional field (`enable_phi_compensation`) added to `/api/run/start`
- No new endpoints or topics
- No config file changes (production.yaml, simulation.yaml untouched)
- No changes to C++ trajectory planner
- No changes to zone boundary values or offset values
- Camera-to-arm transform unchanged
- Cosine test path unchanged
- Scenario JSON format unchanged

## Risk Assessment

| Risk | Likelihood | Mitigation |
|---|---|---|
| Tests relying on default `false` break | High | Update expected values in affected tests |
| Dual-arm run produces different J3 values | Certain (intended) | This is the fix — uncompensated values were incorrect |
| Zone 2 still gives zero compensation | Known limitation | Out of scope — tuning values is separate work |

## Blast Radius

**Packages modified:** `vehicle_arm_sim` (web_ui only)

**Files touched:**
- `fk_chain.py` — add slope constants, update formula (~5 lines)
- `arm_runtime.py` — add import, add compensation call (~5 lines)
- `run_controller.py` — accept and forward `enable_phi_compensation` (~5 lines)
- `testing_backend.py` — change 3 defaults, add 1 field to RunStartRequest (~6 lines)
- `testing_ui.js` — add phi_compensation to run start fetch (~3 lines)
- `testing_ui.html` — add `checked` to checkbox (~1 line)
- `test_fk_chain.py` — add slope tests, update defaults (~30 lines)
- `test_arm_runtime.py` — add compensation tests (~20 lines)
- `test_run_controller.py` — add compensation forwarding test (~15 lines)
- Backend test files — update default expectations (~10 lines)

**Approximate total:** ~100 lines changed across 10 files.
