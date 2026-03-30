## Why

Mode 4 ("Smart Reorder") has only a single-line assertion in `test_collision_diagnostics.py`
(`assert mr["verdict"] == "REORDER_CANDIDATE"`) that does not verify the reorder actually
improves the minimum j4 gap. The real CSV data in `arm1.csv` / `arm2.csv` is never fed
through `SmartReorderScheduler` during diagnostic testing, leaving the end-to-end reorder
benefit unproven.

## What Changes

- Add `test_mode4_reorder_improves_gap()` to
  `pragati_ros2/src/vehicle_arm_sim/web_ui/features/test_collision_diagnostics.py`
- The test builds a step_map from the existing `_ARM1_POINTS` / `_ARM2_POINTS` globals
  (loaded from `arm1.csv` and `arm2.csv`), runs `SmartReorderScheduler.reorder()`, and
  asserts `reordered_min_j4_gap >= original_min_j4_gap`
- The test prints a **before/after table** (visible with `-s`) showing per-step arm order,
  cam_z, j4, and gap values, plus a summary delta line
- Solo tail rows (unmatched steps) are included in the table with `---` for missing-arm
  columns; they are excluded from the min gap assertion
- Add `from smart_reorder_scheduler import SmartReorderScheduler` import to the test file

## Capabilities

### New Capabilities

- `mode4-reorder-gap-verification`: End-to-end verification that `SmartReorderScheduler`
  does not decrease the minimum j4 gap when applied to the real arm CSV data, with a
  printed before/after order table for diagnostic visibility.

### Modified Capabilities

- `smart-reorder-scheduler`: Adding a test scenario that exercises the scheduler against
  real CSV cam-point data (no requirement change, coverage extension only).

## Impact

- **File modified:** `web_ui/features/test_collision_diagnostics.py` (new test function +
  one new import)
- **No production code changes** — test-only
- **No API, topic, service, or config changes**
- **Dependencies:** `SmartReorderScheduler` (already importable via existing `sys.path`
  setup in `conftest.py`)
- Run with: `python3 -m pytest features/test_collision_diagnostics.py -s -v -k "reorder_improves_gap"`

## Non-goals

- Not changing the existing parametric `test_collision_diagnostic` assertions for mode 4
- Not adding `reorder_applied` or gap-improvement fields to `diagnose_collision()` return value
- Not testing the scheduler against synthetic/hardcoded data (that is already covered in
  `test_smart_reorder_scheduler.py`)
- Not adding Playwright E2E browser verification of the reorder output
