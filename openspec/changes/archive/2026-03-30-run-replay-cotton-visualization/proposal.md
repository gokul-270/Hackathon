## Why

During run replay in Gazebo, cotton bowls appear and disappear one at a time (one per arm-step), giving no visual overview of all pick targets. Additionally, there is no visual distinction between cotton intended for arm1 vs arm2. This makes it difficult to verify that the scenario is executing correctly.

## What Changes

- **Pre-spawn all cotton bowls** before any arm motion begins, so all pick targets are visible simultaneously from the start of the replay.
- **Remove each cotton bowl only after its specific pick motion completes**, not before the next pick starts.
- **Per-arm cotton color differentiation**: cotton assigned to `arm1` spawns with one color (white/default); cotton assigned to `arm2` spawns with a distinct color (yellow).
- **Parameterize the SDF template** for cotton bowls to accept a material/color argument.

## Capabilities

### New Capabilities
- None

### Modified Capabilities
- `gazebo-scenario-execution`: Requirements change for cotton bowl lifecycle (pre-spawn all before motions, remove after individual pick) and for per-arm color differentiation.

## Impact

- `testing_backend.py`: `_COTTON_SDF_TEMPLATE` must accept a color parameter; `_run_spawn_cotton` must accept a color.
- `run_step_executor.py`: `execute()` must be split into a pre-spawn phase (all bowls) and a motion phase (pick + remove per step).
- `run_controller.py`: May need to pass the full step map to the executor to support pre-spawning.
- Tests: `test_run_step_executor.py`, `test_motion_backed_e2e.py` need updates/additions.

## Non-goals

- Fixing arm joint motion in Gazebo (joint commands not being received by the model) — this is a separate investigation and out of scope for this change.
- Changing the pick motion sequence itself.
- Supporting more than two arm colors.
