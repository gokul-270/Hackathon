## Execution Plan

| Group | Depends On | Can Parallelize With |
|-------|-----------|----------------------|
| 1. Instrumentation: run_controller.py | — | 2 |
| 2. Instrumentation: testing_backend.py | — | 1 |
| 3. Regression tests: emit path | 1, 2 | — |
| 4. UI terminal_status fix | — | 1, 2 |
| 5. Cotton cleanup fix | 1, 2, 3 | — |
| 6. Final verification & commit | 3, 4, 5 | — |

---

## 1. Instrumentation — run_controller.py [PARALLEL with 2, 4]

- [x] 1.1 Write a failing test asserting that `logger.debug` is called with "dispatched" before `ThreadPoolExecutor.submit()` for a reachable step (RED)
- [x] 1.2 Add `logger.debug("step %s arm %s dispatched → executor", step_id, arm)` before the `ThreadPoolExecutor.submit()` call at `run_controller.py:473` (GREEN)
- [x] 1.3 Add `logger.debug("step %s arm %s executor returned: %s", step_id, arm, result)` after the executor future resolves (GREEN)
- [x] 1.4 Add `logger.debug("step %s arm %s emitting step_complete", step_id, arm)` before the `step_complete` emit at line 561 (GREEN)
- [x] 1.5 Add `logger.debug("step %s arm %s step_complete emitted", step_id, arm)` after the emit (GREEN)
- [x] 1.6 Add `logger.info("step %s arm %s unreachable — skipping executor", step_id, arm)` in the skip-path branch at line 334 (GREEN)
- [x] 1.7 Add `logger.debug("run summary built — returning to backend")` after the summary is built at line 575 (GREEN)
- [x] 1.8 Confirm all new logger tests pass; commit

## 2. Instrumentation — testing_backend.py [PARALLEL with 1, 4]

- [x] 2.1 Write a failing test asserting `logger.info` is called before `run_complete` emit in `testing_backend.py` (RED)
- [x] 2.2 Add `logger.info("run_complete emitting — summary keys: %s", list(summary.keys()))` immediately before `run_complete` emit at line 1285 (GREEN)
- [x] 2.3 Add `logger.info("event_bus closed after run_complete")` immediately after `_event_bus.close()` at line 1292 (GREEN)
- [x] 2.4 Confirm logger tests pass; commit

## 3. Regression tests — emit path [SEQUENTIAL]

- [x] 3.1 Write failing test: unreachable tail step must still emit `step_complete` with `terminal_status="unreachable"` (RED) — `test_run_controller.py`
- [x] 3.2 Make it pass (confirm existing skip-path already calls emit; fix if not) (GREEN)
- [x] 3.3 Write failing test: three consecutive in-process reruns of an all-unreachable scenario each emit `run_complete` within 5 s (RED) — `test_run_controller.py`
- [x] 3.4 Make it pass (identify and fix any thread leak / event-bus state leak between reruns) (GREEN)
- [x] 3.5 Refactor: extract any shared scenario fixture used by both new tests; confirm no shared mutable state
- [x] 3.6 Run full test suite: `python3 -m pytest pragati_ros2/src/vehicle_arm_sim/web_ui/ -x` — confirm green
- [x] 3.7 Commit

## 4. UI — display terminal_status [PARALLEL with 1, 2]

- [x] 4.1 Write a Playwright (or manual) test noting current "complete" static text for an unreachable step
- [x] 4.2 In `testing_ui.js:1566`, change the step label to `data.terminal_status || "complete"` (one-line change)
- [x] 4.3 Confirm the static "complete" text is gone for unreachable steps in browser / test
- [x] 4.4 Commit

## 5. Cotton cleanup — unreachable/skipped steps [SEQUENTIAL]

- [x] 5.1 Write failing test: if cotton was spawned for a step, `_gz_remove_model()` is called even when the step is unreachable (RED) — `test_run_step_executor.py` or `test_run_controller.py`
- [x] 5.2 In `run_step_executor.py` (or `run_controller.py` skip-path), add `_gz_remove_model(cotton_name)` when cotton was spawned but step is unreachable/skipped (GREEN)
- [x] 5.3 Write failing test: no removal attempt when cotton was never spawned (RED)
- [x] 5.4 Guard the removal with `if cotton_was_spawned` (GREEN)
- [x] 5.5 Run full test suite; confirm green
- [x] 5.6 Commit

## 6. Final verification & commit [SEQUENTIAL]

- [x] 6.1 Run full test suite: `python3 -m pytest pragati_ros2/src/vehicle_arm_sim/web_ui/ -v`
- [x] 6.2 Confirm zero failures and zero skips (or document any intentional skips)
- [ ] 6.3 Manually trigger three consecutive reruns in the running sim and verify no stall (if Gazebo available)
- [x] 6.4 Commit any remaining uncommitted work with message `fix: run controller stall, instrumentation, ui terminal_status, cotton cleanup`
