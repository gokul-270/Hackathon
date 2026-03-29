## Execution Plan

| Group | Depends On | Can Parallelize With |
|-------|-----------|----------------------|
| 1     | —         | —                    |
| 2     | 1         | 3                    |
| 3     | 1         | 2                    |
| 4     | 2, 3      | —                    |
| 5     | 4         | —                    |
| 6     | 5         | —                    |

---

## 1. Foundation — Expand Arm Registry and Scenario Validator [SEQUENTIAL]

- [ ] 1.1 RED: Write `test_scenario_json.py` test asserting arm3 is a valid `arm_id` in `parse_scenario()` (currently fails).
- [ ] 1.2 GREEN: Expand `_VALID_ARM_IDS` in `scenario_json.py` to `{"arm1", "arm2", "arm3"}`.
- [ ] 1.3 RED: Write `test_arm_runtime_registry.py` test asserting `ARM_RUNTIME_IDS` contains arm3 and `get_runtime_manifest()` returns 3 descriptors.
- [ ] 1.4 GREEN: Add arm3 to `ARM_RUNTIME_IDS` and `get_runtime_manifest()` in `arm_runtime_registry.py`.
- [ ] 1.5 REFACTOR: Confirm all 365 tests pass. Commit: `feat: expand arm registry and scenario validator to include arm3`.

## 2. Upfront Cotton Spawning — Executor [PARALLEL with 3]

- [ ] 2.1 RED: Write test in `test_run_step_executor.py`: `execute(cotton_model="pre_cotton")` does NOT call `spawn_fn` and DOES call `remove_fn("pre_cotton")` on completion.
- [ ] 2.2 RED: Write test: `execute(cotton_model="pre_cotton", blocked=True)` does NOT call `remove_fn`.
- [ ] 2.3 RED: Write test: `execute(cotton_model="pre_cotton", skipped=True)` does NOT call `remove_fn`.
- [ ] 2.4 GREEN: Add `cotton_model: str = ""` parameter to `RunStepExecutor.execute()`. If non-empty, skip `spawn_fn` call and use provided model name. If blocked/skipped with `cotton_model` provided, skip `remove_fn`.
- [ ] 2.5 REFACTOR: Ensure legacy path (`cotton_model=""`) still calls `spawn_fn` as before. Confirm all existing executor tests pass.

## 3. Arm Pair Remapping — RunController [PARALLEL with 2]

- [ ] 3.1 RED: Write test in `test_run_controller.py`: controller constructed with `arm_pair=("arm1","arm3")` creates ArmRuntime instances named "arm1" and "arm3" (not "arm2").
- [ ] 3.2 RED: Write test: `load_scenario()` remaps `arm_id="arm2"` steps to "arm3" when `arm_pair=("arm1","arm3")`.
- [ ] 3.3 RED: Write test: `load_scenario()` remaps both roles when `arm_pair=("arm2","arm3")` — arm1 steps → arm2, arm2 steps → arm3.
- [ ] 3.4 GREEN: Add `arm_pair: tuple[str, str] = ("arm1", "arm2")` to `RunController.__init__()`. Store as `_primary_id`, `_secondary_id`. Create ArmRuntime instances with those IDs. Apply remap dict in `load_scenario()`.
- [ ] 3.5 REFACTOR: Replace all remaining hardcoded `"arm1"`/`"arm2"` string literals in `run()` with `self._primary_id`/`self._secondary_id`. Confirm all existing controller tests pass.

## 4. Upfront Cotton Spawning — RunController Integration [SEQUENTIAL]

- [ ] 4.1 RED: Write test: `RunController` constructor accepts `spawn_fn` and `remove_fn` callables. After `run()`, `spawn_fn` was called once per step before any executor call (i.e., all spawns precede all executions in `step_map` order).
- [ ] 4.2 RED: Write test: executor's `execute()` is called with `cotton_model` matching the model name returned by `spawn_fn` for that step, AND the outcome has `pick_completed=True` and `executed_in_gazebo=True` for an allowed step.
- [ ] 4.3 RED: Write test: controller with a paired step_id (both arms active) processes both arms and advances to the next step_id only after both arms are terminal (existing sequential pairing behavior preserved with new arm-pair and upfront-cotton wiring).
- [ ] 4.4 RED: Write test: controller with a solo-tail step (only one arm active) records a terminal outcome for that arm and advances correctly.
- [ ] 4.5 GREEN: Add `spawn_fn` and `remove_fn` params to `RunController.__init__()` (defaulting to `_noop_spawn`/`_noop_remove` from `run_step_executor`). In `run()`, before the main step loop, iterate all steps in `step_map`, call `spawn_fn` for each, store results in `cotton_models: dict[(step_id, arm_id), str]`. Pass `cotton_model=cotton_models[...]` in each `executor.execute()` call.
- [ ] 4.6 REFACTOR: Confirm all 365 tests pass.

## 5. Backend API + UI [SEQUENTIAL]

- [ ] 5.1 RED: Write test in `test_motion_backed_e2e.py`: `POST /api/run/start` with `arm_pair=["arm1","arm3"]` returns 200 and publishes to arm3 Gazebo topics (`/arm_joint3_copy1_cmd` etc.).
- [ ] 5.2 RED: Write test: `POST /api/run/start` with `arm_pair=["arm2","arm3"]` returns 200 and publishes to arm2 topics for primary steps and arm3 topics for secondary steps.
- [ ] 5.3 RED: Write test: `POST /api/run/start` with `arm_pair=["arm1","arm1"]` returns 422.
- [ ] 5.4 RED: Write test: `POST /api/run/start` with `arm_pair=["arm1","arm99"]` returns 422.
- [ ] 5.5 RED: Write test: `POST /api/run/start` with no `arm_pair` field defaults to arm1+arm2 (existing behavior unchanged).
- [ ] 5.6 GREEN: Add `arm_pair: list[str] = ["arm1", "arm2"]` to `RunStartRequest`. Add validation: must be 2 distinct IDs from `ARM_CONFIGS.keys()`. Pass `arm_pair=tuple(req.arm_pair)` and `spawn_fn=_run_spawn_cotton`, `remove_fn=_run_remove_cotton` to `RunController`.
- [ ] 5.7 GREEN (UI): Add arm pair dropdown to `testing_ui.html` in the Scenario Run section, positioned above the Mode dropdown. Update `testing_ui.js` `setupRunFlow()` to read selected pair and include `arm_pair` in the POST body.
- [ ] 5.8 REFACTOR: Confirm all 365 tests pass.

## 6. Final Verification and Commit [SEQUENTIAL]

- [ ] 6.1 Run full test suite (`python3 -m pytest .`) — must be 365+ passed, 0 failed.
- [ ] 6.2 Verify new test count matches expected additions (≥16 new tests across groups 1–5).
- [ ] 6.3 Commit all implementation: `feat: arm pair selector and upfront cotton spawning`.
