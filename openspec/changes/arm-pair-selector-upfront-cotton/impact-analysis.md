# Impact Analysis: arm-pair-selector-upfront-cotton

## 1. Before / After Behavior

| Item | Before | After |
|------|--------|-------|
| Arms in a run | Always arm1 + arm2 (hardcoded) | Any two of arm1, arm2, arm3 (operator selects) |
| Arm pair UI | No selector — arm1+arm2 always | "Arm Pair" dropdown in Scenario Run panel |
| POST /api/run/start payload | `{mode, scenario}` | `{mode, scenario, arm_pair}` (arm_pair optional, defaults to arm1+arm2) |
| Scenario arm_id remapping | None — "arm1"/"arm2" in JSON must match actual arms | Remapped: scenario "arm1" → primary arm, "arm2" → secondary arm |
| Cotton visibility at run start | 0 balls visible; spawn one-at-a-time per step | All N cotton balls visible immediately at run start |
| Blocked/skipped step cotton | Never spawned (invisible) | Spawned at run start, stays visible for entire run |
| Cotton removal timing | Immediately after each step's animation | Same — removed only when pick completes |
| arm3 in scenario validation | `_VALID_ARM_IDS = {"arm1","arm2"}` — arm3 rejected | `_VALID_ARM_IDS = {"arm1","arm2","arm3"}` — arm3 accepted |
| arm3 in runtime registry | Not registered | Registered as third arm descriptor |

## 2. Performance Impact

| Item | CPU | Memory | Latency |
|------|-----|--------|---------|
| Upfront cotton spawn (N balls) | Negligible — N gz subprocess calls at run start (~N×50ms) | No change | Adds ~N×50ms pre-run overhead; per-step pick timing unchanged |
| Arm pair validation | Negligible — O(1) dict lookup | No change | None |
| controller cotton_models dict | Negligible — O(N) dict, N≤~10 for current scenarios | +~1KB per run | None |
| Additional ARM_CONFIGS lookup | Negligible | No change | None |

## 3. Unchanged Behavior

- Mode selection (0–3) and collision avoidance logic: no change.
- Scenario preset files (contention_pack.json, geometry_pack.json): unmodified.
- Pick animation timing (j4→j3→j5→retract→home, ~5.5s): no change.
- JSON and Markdown report format and download endpoints: no change.
- Manual arm controls, cotton placement, cosine test: no change.
- E-STOP behavior: no change.
- All existing API endpoints other than `/api/run/start`: no change.
- `fk_chain.py`, `arm_runtime.py`, `baseline_mode.py`, `peer_transport.py`, `truth_monitor.py`: unmodified.

## 4. Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| arm3 FK parameters in ARM_CONFIGS are miscalibrated | Low — arm3 was already calibrated for manual control | Cotton may spawn at slightly wrong position; pre-existing issue, not introduced here |
| Unanticipated test failures in existing suite | Low — API is backward compatible; default arm_pair=arm1+arm2 | Full suite (365 tests) must pass before commit |
| Upfront spawn increases run start latency noticeably | Low — 8–10 balls × ~50ms = ~400–500ms overhead before first step | Acceptable; Gazebo spawn is fire-and-forget subprocess |
| Custom scenario JSON with arm3 steps bypasses remap | Intentional — arm3 is a valid direct address | Documented in design.md as expected behavior |

## 5. Blast Radius

**Files modified (7 total):**

| File | Change type | Approx lines changed |
|------|-------------|----------------------|
| `testing_ui.html` | Add arm pair dropdown | ~10 lines added |
| `testing_ui.js` | Read pair, include in POST | ~5 lines changed |
| `testing_backend.py` | RunStartRequest field + validation + controller wiring | ~15 lines changed |
| `run_controller.py` | arm_pair + spawn_fn/remove_fn params + remap + upfront spawn | ~40 lines changed |
| `run_step_executor.py` | cotton_model param + conditional spawn/remove logic | ~15 lines changed |
| `scenario_json.py` | Expand _VALID_ARM_IDS | 1 line changed |
| `arm_runtime_registry.py` | Add arm3 to registry | ~5 lines changed |

**Files NOT modified:** `fk_chain.py`, `arm_runtime.py`, `baseline_mode.py`,
`peer_transport.py`, `truth_monitor.py`, all scenario JSON files, all other test files
(except additions).

**Packages affected:** `vehicle_arm_sim` web_ui only. No ROS2 C++ nodes affected.
