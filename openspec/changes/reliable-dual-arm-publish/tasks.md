## Execution Plan

| Group | Label | Depends On | Can Parallelize With |
|---|---|---|---|
| 1 | Pre-implementation prep | — | — |
| 2 | Triple-publish (`_gz_publish`) | 1 | — |
| 3 | RunStepExecutor E-STOP support | 1 | 4 |
| 4 | RunController parallel animation | 1 | 3 |
| 5 | testing_backend.py integration | 2, 3, 4 | — |
| 6 | Final verification | 5 | — |

---

## 1. Pre-implementation prep [SEQUENTIAL]

- [x] 1.1 Write `impact-analysis.md` in the change directory (required by AGENTS.md before artifact commit): Before/After table, Performance Impact, Unchanged Behaviour, Risk Assessment, Blast Radius
- [x] 1.2 Dispatch cross-artifact review subagent: verify all 4 specs have a corresponding test task, numbers are consistent (150ms gaps, 7.3s timing, 3x publish), every capability in proposal has a matching spec, no missing edge cases
- [x] 1.3 Fix any CRITICAL issues surfaced by cross-artifact review
- [ ] 1.4 Commit all change artifacts: `chore: create reliable-dual-arm-publish change artifacts (proposal, specs, design, tasks)`

## 2. Triple-publish in `_gz_publish` [SEQUENTIAL]

- [ ] 2.1 **RED** — In `test_motion_backed_e2e.py`, write a test that asserts `subprocess.run` is called exactly 3 times when `_gz_publish` is invoked once; run it and confirm it fails
- [ ] 2.2 **RED** — Write a test that asserts `time.sleep(0.150)` is called twice between the three `subprocess.run` calls; confirm it fails
- [ ] 2.3 **RED** — Write a test that asserts no `subprocess.Popen` is used in `_gz_publish` (only `subprocess.run`); confirm it fails
- [ ] 2.4 **GREEN** — In `testing_backend.py:_gz_publish`, replace `subprocess.Popen(...)` with `subprocess.run(...)` × 3 with `time.sleep(0.150)` between calls
- [ ] 2.5 **REFACTOR** — Confirm all three tests pass; run `pytest test_motion_backed_e2e.py -k "gz_publish" -x`; commit: `feat: triple-publish in _gz_publish with 150ms gaps`

## 3. RunStepExecutor E-STOP support [PARALLEL with 4]

- [ ] 3.1 **RED** — In `test_run_step_executor.py`, write a test that constructs `RunStepExecutor` with `estop_check=lambda: True` and verifies `execute()` returns `terminal_status="estop_aborted"` with `pick_completed=False`; confirm it fails
- [ ] 3.2 **RED** — Write a parametrized test covering all 6 phase boundaries (after each sleep): set `estop_check` to fire after the Nth sleep and assert `estop_aborted` is returned; confirm all 6 cases fail
- [ ] 3.3 **RED** — Write a test that when E-STOP fires mid-animation on arm2, zeros are published to `/joint3_copy_cmd`, `/joint4_copy_cmd`, `/joint5_copy_cmd` (the arm2 topics); confirm it fails
- [ ] 3.4 **RED** — Write a test that constructing `RunStepExecutor` without `estop_check` defaults to never aborting (run completes normally); confirm it fails only if param is missing
- [ ] 3.5 **GREEN** — Add `estop_check: Optional[Callable[[], bool]] = None` param to `RunStepExecutor.__init__`; store as `self._estop_check`; after each `self._sleep_fn()` call in `execute()`, check `self._estop_check()` and if True, publish zeros to all 3 arm topics and return `{"terminal_status": "estop_aborted", "pick_completed": False, "executed_in_gazebo": False}`
- [ ] 3.6 **REFACTOR** — Run `pytest test_run_step_executor.py -x`; confirm all new + existing tests pass; commit: `feat: add estop_check to RunStepExecutor with estop_aborted outcome`

## 4. RunController parallel animation [PARALLEL with 3]

- [ ] 4.1 **RED** — In `test_run_controller.py`, write a test that for a paired step, both `executor.execute()` calls are started within 50ms of each other (use threading timestamps injected via a recording sleep_fn); confirm it fails
- [ ] 4.2 **RED** — Write a test that step reports for a paired step are appended to the reporter in sorted arm-id order even if arm2's executor returns before arm1's; confirm it fails
- [ ] 4.3 **RED** — Write a test that a solo step (only one arm active) still produces a single step report correctly with no threading change; confirm it still passes (this is a guard test)
- [ ] 4.6 **RED** — Write a test that mode logic (candidate joints, peer-state exchange) runs and produces `applied` joints before any `executor.execute()` call is dispatched (use a recording executor that captures call order vs. candidate computation order); confirm it fails
- [ ] 4.4 **GREEN** — In `RunController.run()`, replace the sequential `for arm_id in arm_steps` executor loop with a `ThreadPoolExecutor(max_workers=2)` block: submit all active arms' `execute()` calls, then collect `future.result()` in sorted `arm_id` order before calling `self._reporter.add_step()`
- [ ] 4.5 **REFACTOR** — Run `pytest test_run_controller.py -x`; confirm all new + existing tests pass; commit: `feat: parallel dual-arm animation in RunController via ThreadPoolExecutor`

## 5. testing_backend.py integration [SEQUENTIAL]

- [ ] 5.1 **RED** — In `test_motion_backed_e2e.py`, write a test via `TestClient` that POSTing `/api/run/start` twice in a row results in a cleared E-STOP flag at the start of the second run (i.e., a prior E-STOP does not bleed into the next run); confirm it fails
- [ ] 5.2 **RED** — Write a test that POSTing `/api/estop` sets `_estop_event` (inspect via a test endpoint or monkeypatch); confirm it fails
- [ ] 5.3 **RED** — Write a test that when a run is in progress, a concurrent POST to `/api/estop` receives an HTTP 200 response (i.e., the event loop is not blocked); use `asyncio.to_thread` + `asyncio.gather` in the test to exercise concurrency; confirm it fails
- [ ] 5.4 **RED** — Write a test that when `_estop_event` is pre-set before `/api/run/start`, the run report includes at least one step with `terminal_status="estop_aborted"`; confirm it fails
- [ ] 5.9 **RED** — Write a test (in `test_run_controller.py`) that when E-STOP fires at step 3 of a 3-step run, step reports for steps 1 and 2 retain their original `terminal_status` values (`completed`, `blocked`, etc.); confirm it fails
- [ ] 5.5 **GREEN** — Add `_estop_event = threading.Event()` at module level in `testing_backend.py`
- [ ] 5.6 **GREEN** — In `/api/estop` handler, add `_estop_event.set()` after `estop_node.execute_estop()`
- [ ] 5.7 **GREEN** — In `/api/run/start`: (a) call `_estop_event.clear()` before creating executor; (b) pass `estop_check=_estop_event.is_set` to `RunStepExecutor`; (c) change `summary = controller.run()` to `summary = await asyncio.to_thread(controller.run)`
- [ ] 5.8 **REFACTOR** — Run `pytest test_motion_backed_e2e.py -x -k "not test_run_report_markdown"`; confirm all new + existing tests pass; commit: `feat: wire E-STOP threading.Event and asyncio.to_thread in testing_backend`

## 6. Final verification [SEQUENTIAL]

- [ ] 6.1 Run full test suite: `pytest pragati_ros2/src/vehicle_arm_sim/web_ui/ -k "not test_run_report_markdown" -q`; confirm no regressions
- [ ] 6.2 Verify test count is at baseline + new tests (baseline: 378 passed)
- [ ] 6.3 Dispatch `openspec-verify-change` subagent; fix any CRITICAL issues found
