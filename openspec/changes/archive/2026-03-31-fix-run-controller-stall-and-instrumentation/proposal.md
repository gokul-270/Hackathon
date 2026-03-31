## Why

The run controller intermittently stalls after the third consecutive rerun of a scenario: the log stops at `parallel dispatch` and neither `step_complete` nor `run_complete` is ever emitted. Separately, unreachable steps (caused by cumulative j4 joint drift) silently skip execution but still display "complete" in the UI — hiding real failures and leaving cotton unremoved.

## What Changes

- Add structured `logger` instrumentation around the critical emit path in `run_controller.py` (dispatch → step_complete → summary → run_complete) to produce reproducible evidence of where the stall occurs.
- Add instrumentation to `testing_backend.py` around the `run_complete` SSE emit and `_event_bus.close()` call.
- Write regression tests: (a) an unreachable tail step must still emit `step_complete`; (b) three consecutive reruns of the same scenario must each complete without hanging.
- Fix the UI to display the actual `terminal_status` (e.g. `unreachable`, `skipped`) instead of always saying "complete".
- Fix cotton cleanup so unreachable/skipped steps remove their assigned cotton ball if one was already spawned.

## Capabilities

### New Capabilities
- `controller-emit-instrumentation`: Structured log coverage of the controller's step dispatch → step_complete → run_complete path, enabling stall diagnosis and regression detection.

### Modified Capabilities
- `dual-arm-run-orchestration`: Adds regression tests for repeated reruns and unreachable-step emit guarantee.
- `pick-outcome-reporting`: UI must render `terminal_status` from `step_complete` events instead of a static "complete" label.
- `multi-cotton-management`: Cotton assigned to unreachable/skipped steps must be removed (cleanup gap fix).

## Impact

- `run_controller.py`: add logger calls at lines 334, 473, 561–573, 575
- `testing_backend.py`: add logger calls at lines 1283–1292
- `testing_ui.js`: update `step_complete` SSE handler at line 1566 to display `terminal_status`
- `run_step_executor.py`: no changes expected
- `test_run_controller.py`: new regression tests added
- `test_testing_backend.py`: new run_complete emit test added

## Non-goals

- Fixing the root cause of j4 cumulative drift (FK baseline reset) — that is a separate change.
- Changing dual-arm orchestration logic, step ordering, or scheduling.
- Modifying Gazebo topic wiring or arm topic naming.
