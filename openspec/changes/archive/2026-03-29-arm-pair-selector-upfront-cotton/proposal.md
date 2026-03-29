## Why

The run pipeline is hardcoded to arm1+arm2, excluding arm3 which already has full FK and
Gazebo topic support. Additionally, cotton balls appear one at a time during a run, so the
operator cannot see the full field of targets before picks begin — targets that are blocked
or skipped by collision avoidance are never visible at all.

## What Changes

- Add an "Arm Pair" dropdown to the Scenario Run UI panel so the operator can select which
  two arms participate in a run (arm1+arm2, arm1+arm3, arm2+arm3).
- Existing scenario files (contention_pack, geometry_pack) are auto-remapped at run start:
  steps with `arm_id="arm1"` go to the selected primary arm, `arm_id="arm2"` to the
  secondary arm. No scenario file edits required.
- Spawn all cotton balls for every step in the scenario at run start, so the full field of
  targets is visible immediately.
- Each cotton ball disappears only when its pick animation completes (removed on success).
- Blocked or skipped cotton stays visible for the duration of the run.
- Expand `_VALID_ARM_IDS` in scenario_json.py to include `arm3` so custom scenario files
  can target arm3 directly.
- Expand `arm_runtime_registry.py` to register arm3 alongside arm1 and arm2.

## Capabilities

### New Capabilities

- `arm-pair-selection`: Operator selects which two arms run the collision avoidance
  scenario. UI sends the pair to the backend; backend validates and passes it to
  RunController; controller remaps scenario arm_ids to the selected pair.

### Modified Capabilities

- `gazebo-scenario-execution`: Cotton spawn timing changes from per-step (inside the
  executor, just before animation) to upfront (all balls spawned before the step loop
  begins). Blocked and skipped steps no longer prevent cotton from appearing — cotton is
  always visible, removed only on successful pick.
- `ui-run-flow`: UI gains an arm-pair dropdown. The POST payload gains an `arm_pair`
  field. No change to mode selection or report download behaviour.
- `dual-arm-run-orchestration`: RunController accepts a dynamic `arm_pair` parameter
  instead of always creating arm1 and arm2 runtimes. Scenario remapping from generic
  arm1/arm2 roles to the selected pair happens in `load_scenario()`.

## Impact

- **Files changed**: `testing_ui.html`, `testing_ui.js`, `testing_backend.py`,
  `run_controller.py`, `run_step_executor.py`, `scenario_json.py`,
  `arm_runtime_registry.py`
- **API change**: `POST /api/run/start` gains optional `arm_pair` field (default
  `["arm1","arm2"]` — fully backward compatible).
- **No Gazebo world changes**: arm3 Gazebo topics (`/arm_joint3_copy1_cmd`, etc.) already
  exist; this change just makes the run pipeline use them.
- **No scenario file changes**: existing JSON files are remapped automatically.
