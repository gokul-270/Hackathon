## Why

The web UI testing tool (`fk_chain.py`) has a phi compensation implementation that diverges
from the original C++ trajectory planner (`trajectory_planner.cpp`): it is missing the
`slope` term in the formula, uses hardcoded constants instead of production-tuned values,
and is completely absent from the dual-arm run path (`arm_runtime.py` → `run_controller.py`).
This means the testing UI cannot accurately validate phi compensation behavior against what
runs on real hardware, and dual-arm runs always use uncompensated J3 values.

## What Changes

- Update `fk_chain.py:phi_compensation()` to match the C++ formula:
  `base = slope × (phi_deg / 90) + offset` (currently only uses `offset`)
- Add slope constants using production.yaml values (all slopes currently 0.0)
- Wire phi compensation into the dual-arm run path:
  `arm_runtime.py` → `run_controller.py`
- Add `enable_phi_compensation` field to `RunStartRequest` in `testing_backend.py`
- Pass phi compensation checkbox state from UI when starting dual-arm runs
- Change `enable_phi_compensation` default from `false` to `true` across all endpoints

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `pick-compute-api`: phi_compensation formula changes to include slope term matching
  C++ trajectory planner; default changes from `false` to `true`
- `dual-arm-run-orchestration`: dual-arm run path gains phi compensation support
  (currently missing entirely)

## Impact

- **Files modified:** `fk_chain.py`, `arm_runtime.py`, `testing_backend.py`,
  `testing_ui.js`, `testing_ui.html`
- **Tests affected:** `test_fk_chain.py`, `test_arm_runtime.py`,
  backend integration tests
- **Behavior change:** phi compensation now defaults to ON — existing endpoints
  that previously defaulted to `false` will now apply compensation by default
- **No config file changes** — production.yaml values used as constants in Python

## Non-goals

- Not wiring actual YAML file reading into the Python web UI
- Not changing zone boundaries or compensation tuning values themselves
- Not modifying the C++ trajectory planner
