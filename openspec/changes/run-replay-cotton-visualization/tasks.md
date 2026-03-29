## Execution Plan

| Group | Depends On | Can Parallelize With |
|-------|-----------|----------------------|
| 1     | —         | —                    |
| 2     | 1         | —                    |
| 3     | 2         | —                    |

---

## 1. Cotton SDF Color Parameterization [SEQUENTIAL]

- [ ] 1.1 Write a failing test: `_run_spawn_cotton` called with `arm_id="arm2"` spawns a model whose SDF contains `1 1 0 1` (yellow), while `arm1` spawns `1 1 1 1` (white)
- [ ] 1.2 Add `{diffuse}` placeholder to `_COTTON_SDF_TEMPLATE` in `testing_backend.py`
- [ ] 1.3 Update `_run_spawn_cotton` to accept an optional `color_rgba` parameter and pass it to the template (default `"1 1 1 1"`)
- [ ] 1.4 Add an `ARM_COTTON_COLORS` map: `{"arm1": "1 1 1 1", "arm2": "1 1 0 1"}` in `testing_backend.py`
- [ ] 1.5 Run tests — confirm green; commit

## 2. Pre-Spawn Phase in RunStepExecutor [SEQUENTIAL]

- [ ] 2.1 Write a failing test: `RunStepExecutor.pre_spawn(step_map, spawn_fn)` calls `spawn_fn` once per allowed arm-step before `execute()` is called, and stores model names keyed by `(step_id, arm_id)`
- [ ] 2.2 Write a failing test: `pre_spawn` does NOT call `spawn_fn` for blocked or skipped arm-steps (steps not in the allowed set)
- [ ] 2.3 Write a failing test: after `pre_spawn`, calling `execute()` for a step uses the pre-stored model name when calling `remove_fn` (not a freshly spawned name)
- [ ] 2.4 Write a failing test: `execute()` calls `spawn_fn` if and only if no pre-spawn was done (backward-compatibility path)
- [ ] 2.5 Implement `pre_spawn(step_map, spawn_fn)` in `RunStepExecutor` — iterates allowed steps, spawns with per-arm color, stores model name map
- [ ] 2.6 Update `execute()` to use the pre-stored model name for removal when available; fall back to inline spawn+remove if no pre-spawn map entry exists
- [ ] 2.7 Run tests — confirm green; commit

## 3. Wire Pre-Spawn into RunController / run_start [SEQUENTIAL]

- [ ] 3.1 Write a failing test: `run_start()` (or `RunController.run()`) calls `executor.pre_spawn(step_map, spawn_fn)` before entering the step loop
- [ ] 3.2 Write a failing test: the color passed to `spawn_fn` during pre-spawn matches `ARM_COTTON_COLORS[arm_id]`
- [ ] 3.3 Update `run_start()` in `testing_backend.py` (or `RunController.run()`) to call `pre_spawn` with the full step map and the colored spawn function before the motion loop
- [ ] 3.4 Run the full test suite (`pytest` in `web_ui/`) — confirm all tests green; commit
