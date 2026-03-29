# Design: Arm Pair Selector + Upfront Cotton Spawning

**Date:** 2026-03-29
**Status:** Approved

---

## 1. Problem Statement

Two independent usability gaps exist in the dual-arm collision avoidance UI:

1. **Arm pair is hardcoded to arm1+arm2.** The system already has arm3 defined in
   `ARM_CONFIGS` with its own Gazebo topics and FK, but the run/scenario pipeline only
   ever runs arm1 vs arm2. There is no way to select a different pairing (e.g. arm1+arm3
   or arm2+arm3) without editing code.

2. **Cotton appears one ball at a time.** During a run, cotton is spawned at the start of
   each arm-step, picked, then removed before the next step begins. The user cannot see
   where all the cotton targets are before the run starts. Cotton that is blocked or
   skipped by collision avoidance never appears at all.

---

## 2. Goals

- Let the user choose any pair of arms (arm1+arm2, arm1+arm3, arm2+arm3) from a UI
  dropdown before starting a run.
- Spawn all cotton balls for the full scenario at run start so the user sees the entire
  field of targets immediately.
- Each cotton ball disappears only when its pick animation completes.
- Blocked or skipped cotton stays visible for the duration of the run (shows the user
  which targets were unreachable).
- Existing preset scenarios (contention_pack, geometry_pack) continue to work with the
  default arm1+arm2 pair — no migration required.
- All changes are covered by tests before implementation (red-green-refactor).

---

## 3. Non-Goals

- Running more than 2 arms simultaneously in a single run.
- Running a single arm solo (no collision avoidance partner).
- Cleaning up unpicked cotton at run end (stays visible by design).
- Adding new scenario files for arm3 pairs (existing scenarios are remapped automatically).

---

## 4. Design

### 4.1 Arm Pair Remapping

Existing scenario files use `arm_id: "arm1"` and `arm_id: "arm2"` in their step JSON.
When the user selects a different pair (e.g. arm1+arm3), the selected pair is treated as
`[primary, secondary]` and the scenario is remapped:

- Scenario steps with `arm_id="arm1"` → `primary` arm
- Scenario steps with `arm_id="arm2"` → `secondary` arm

This remapping happens in `RunController.load_scenario()` before distributing steps to
the two `ArmRuntime` instances. No scenario file changes are needed.

### 4.2 Architecture Changes

#### UI layer (`testing_ui.html` + `testing_ui.js`)

Add an "Arm Pair" dropdown above the Mode dropdown in the "Scenario Run" section:

```
Arm Pair: [ arm1 + arm2 ▼ ]     ← new
Mode:     [ 0 — Unrestricted ▼ ]
Preset:   [ -- none --        ▼ ]
```

The JS click handler reads the selected pair as a `[string, string]` array and includes
it in the POST body: `{ mode, scenario, arm_pair: ["arm1", "arm2"] }`.

#### API layer (`testing_backend.py`)

`RunStartRequest` gains an optional field:

```python
class RunStartRequest(BaseModel):
    mode: int
    scenario: dict
    arm_pair: list[str] = ["arm1", "arm2"]
```

Validation: `arm_pair` must be a list of exactly 2 distinct, known arm IDs from
`ARM_CONFIGS`. Returns HTTP 422 if invalid.

The pair is passed straight through to `RunController`:

```python
controller = RunController(req.mode, executor=executor, arm_pair=tuple(req.arm_pair))
```

Cotton is still spawned from `_run_spawn_cotton` (unchanged signature) — it's just
called earlier (at run start) by the controller rather than per-step by the executor.

#### RunController (`run_controller.py`)

Constructor changes:

```python
def __init__(
    self,
    mode: int = BaselineMode.UNRESTRICTED,
    executor: Optional[object] = None,
    arm_pair: tuple[str, str] = ("arm1", "arm2"),
) -> None:
```

- Stores `self._primary_id, self._secondary_id = arm_pair`
- Creates `self._arm1 = ArmRuntime(self._primary_id)` and `self._arm2 = ArmRuntime(self._secondary_id)`
- All hardcoded `"arm1"` / `"arm2"` strings in `run()` are replaced with
  `self._primary_id` / `self._secondary_id`

`load_scenario()` remaps arm IDs before constructing `ScenarioStep` objects:

```python
remap = {"arm1": self._primary_id, "arm2": self._secondary_id}
arm_id = remap.get(raw["arm_id"], raw["arm_id"])
```

`run()` spawns all cotton upfront (see §4.3).

#### RunStepExecutor (`run_step_executor.py`)

`execute()` gains an optional parameter:

```python
def execute(
    self,
    arm_id: str,
    applied_joints: dict,
    blocked: bool = False,
    skipped: bool = False,
    cam_x: float = 0.0,
    cam_y: float = 0.0,
    cam_z: float = 0.0,
    j4_pos: float = 0.0,
    cotton_model: str = "",   # ← new
) -> dict:
```

Behaviour:
- If `cotton_model` is non-empty, skip the `self._spawn_fn(...)` call and use the
  provided name directly.
- If `cotton_model` is empty, fall back to calling `self._spawn_fn(...)` as before
  (backward-compatible for existing tests and callers).
- On `blocked` or `skipped`, do NOT call `self._remove_fn` — the pre-spawned cotton
  stays visible.
- On completion, call `self._remove_fn(cotton_model)` as before.

#### scenario_json.py

`_VALID_ARM_IDS = {"arm1", "arm2", "arm3"}`

This allows custom scenario JSON files to use arm3 steps directly if desired.

#### arm_runtime_registry.py

`ARM_RUNTIME_IDS = ("arm1", "arm2", "arm3")`

`get_runtime_manifest()` returns descriptors for all 3 arms.

### 4.3 Upfront Cotton Spawn Flow

Inside `RunController.run()`, before the main step loop:

```python
# Spawn all cotton at run start
cotton_models: dict[tuple[int, str], str] = {}
for step_id, arm_steps in sorted(step_map.items()):
    for arm_id, step in arm_steps.items():
        model_name = self._executor.spawn_fn(arm_id, step.cam_x, step.cam_y, step.cam_z, j4=0.0)
        cotton_models[(step_id, arm_id)] = model_name
```

Then inside the per-step loop, the executor is called with the pre-spawned name:

```python
outcome = self._executor.execute(
    ...,
    cotton_model=cotton_models.get((step_id, arm_id), ""),
)
```

To enable this, `RunStepExecutor` needs to expose `spawn_fn` as a callable the
controller can call directly. The cleanest approach: the controller calls the same
`spawn_fn` that was injected into the executor, stored as `executor.spawn_fn` (a
public attribute on `RunStepExecutor`).

Alternatively (simpler): the backend passes `spawn_fn` to the controller directly as a
separate argument. **Chosen approach:** pass `spawn_fn` and `remove_fn` into the
controller as separate callables, independent of the executor. This keeps the executor
focused on per-step animation and the controller in charge of lifecycle management.

```python
controller = RunController(
    req.mode,
    executor=executor,
    arm_pair=tuple(req.arm_pair),
    spawn_fn=_run_spawn_cotton,
    remove_fn=_run_remove_cotton,
)
```

For tests that don't need real spawning, `spawn_fn` defaults to `_noop_spawn` and
`remove_fn` defaults to `_noop_remove` (already defined in `run_step_executor.py`,
importable from there).

---

## 5. File Change Summary

| File | Type of change |
|------|---------------|
| `testing_ui.html` | Add arm-pair dropdown in Scenario Run section |
| `testing_ui.js` | Read arm-pair and include in POST body |
| `testing_backend.py` | `RunStartRequest.arm_pair` field; pass to controller; pass spawn/remove fns |
| `run_controller.py` | `arm_pair` + `spawn_fn` + `remove_fn` params; remap scenario; spawn all cotton upfront |
| `run_step_executor.py` | `cotton_model` param in `execute()`; skip spawn if provided; skip remove on blocked/skipped |
| `scenario_json.py` | Expand `_VALID_ARM_IDS` to include `"arm3"` |
| `arm_runtime_registry.py` | Expand to include arm3 |

**Unchanged:** `fk_chain.py`, `arm_runtime.py`, `baseline_mode.py`, `peer_transport.py`,
`truth_monitor.py`, all scenario JSON files.

---

## 6. Testing Strategy

Every change follows red-green-refactor. Key test areas:

| Test file | What to verify |
|-----------|---------------|
| `test_run_step_executor.py` | `execute()` with pre-supplied `cotton_model` skips spawn; blocked/skipped with `cotton_model` does not call remove |
| `test_run_controller.py` | Arm pair remapping; upfront cotton spawn ordering; spawn_fn called once per step at start; cotton_models correctly keyed |
| `test_scenario_json.py` | arm3 accepted as valid `arm_id`; arm3 steps parse correctly |
| `test_arm_runtime_registry.py` | Registry returns 3 arms |
| `test_motion_backed_e2e.py` | E2E run with arm1+arm3 pair publishes to arm3 Gazebo topics |
| Playwright (existing) | UI arm-pair dropdown present and sends correct payload |

---

## 7. Backward Compatibility

- Default `arm_pair=["arm1", "arm2"]` in `RunStartRequest` means all existing API calls
  and tests continue to work without changes.
- `RunController` default `arm_pair=("arm1", "arm2")` means direct constructor usage in
  tests is unchanged.
- `execute()` with no `cotton_model` argument falls back to calling `spawn_fn` as before.
- All 365 existing tests must pass after each change.
