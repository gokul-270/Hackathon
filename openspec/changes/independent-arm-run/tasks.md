## Execution Plan

| Group | Depends On | Can Parallelize With |
|-------|-----------|---------------------|
| 1 | — | 2, 3 |
| 2 | — | 1, 3 |
| 3 | — | 1, 2 |
| 4 | 1 | — |
| 5 | 2, 3 | — |
| 6 | 4, 5 | — |
| 7 | 6 | — |

---

## 1. Faster Pick Animation + Publish Delay [PARALLEL with 2, 3]

- [x] 1.1 **RED** Write `test_animation_timing_constants_are_halved` in `test_run_step_executor.py` — assert `_T_J4==0.4`, `_T_J3==0.4`, `_T_J5_EXTEND==0.7`, `_T_J5_RETRACT==0.4`, `_T_J3_HOME==0.4`, `_T_J4_HOME==0.45`; confirm test fails
- [x] 1.2 **GREEN** Halve all six timing constants in `run_step_executor.py` (lines 40–45); confirm test passes
- [x] 1.3 **RED** Write `test_gz_publish_retry_delay_is_50ms` in `test_motion_backed_e2e.py` — patch `time.sleep` and assert it is called with 0.05, not 0.15; confirm test fails
- [x] 1.4 **GREEN** Change inter-attempt sleep in `testing_backend.py` `_gz_publish` from `0.150` to `0.050`; confirm test passes
- [x] 1.5 **REFACTOR** Run full test suite; commit `fix: halve animation timing and publish retry delay`

## 2. Per-Arm Cotton Colour [PARALLEL with 1, 3]

- [x] 2.1 **RED** Write `test_arm1_cotton_sdf_is_red` and `test_arm2_cotton_sdf_is_blue` in `test_testing_backend.py` (or `test_run_controller.py`) — assert SDF string contains correct `<ambient>` and `<diffuse>` values per arm_id; confirm tests fail
- [x] 2.2 **GREEN** Add `_ARM_COTTON_COLOURS` dict and `{ambient}`/`{diffuse}` placeholders to `_COTTON_SDF_TEMPLATE` in `testing_backend.py`; pass arm-specific colours from `_run_spawn_cotton()`; confirm tests pass
- [x] 2.3 **RED** Write `test_arm3_cotton_sdf_fallback_is_white` — assert unknown arm_id gets white colour; confirm fails
- [x] 2.4 **GREEN** Add white fallback in `_run_spawn_cotton()`; confirm test passes
- [x] 2.5 **REFACTOR** Run full test suite; commit `feat: per-arm cotton colours (arm1=red, arm2=blue)`

## 3. Parallel Cotton Spawn [PARALLEL with 1, 2]

- [x] 3.1 **RED** Write `test_parallel_spawn_submits_all_cottons_concurrently` in `test_run_controller.py` — use a mock spawn_fn with a threading.Event and assert all N calls are in-flight before any returns; confirm test fails
- [x] 3.2 **GREEN** Replace sequential spawn loop in `RunController.run()` (lines 171–175) with `ThreadPoolExecutor` parallel dispatch; confirm test passes
- [x] 3.3 **RED** Write `test_parallel_spawn_all_complete_before_execution` — assert spawn_fn is called for all steps before executor.execute() is ever called; confirm fails
- [x] 3.4 **GREEN** Ensure futures are all `.result()`-ed before the arm execution phase; confirm test passes
- [x] 3.5 **REFACTOR** Run full test suite; commit `feat: parallel upfront cotton spawn`

## 4. Thread-Safe Transport and Reporter [SEQUENTIAL after 1]

- [ ] 4.1 **RED** Write `test_peer_transport_is_thread_safe` — two threads simultaneously publish 1000 times each, assert no data corruption; confirm test fails (or passes trivially — verify Lock is absent first)
- [ ] 4.2 **GREEN** Add `threading.Lock` to `LocalPeerTransport.publish()` and `receive()` in `peer_transport.py`; confirm test passes
- [ ] 4.3 **RED** Write `test_json_reporter_add_step_is_thread_safe` — two threads each add 500 steps concurrently, assert all 1000 appear in final summary; confirm test fails without lock
- [ ] 4.4 **GREEN** Add `threading.Lock` to `JsonReporter.add_step()` in `json_reporter.py`; confirm test passes
- [ ] 4.5 **RED** Write `test_truth_monitor_observe_is_thread_safe` — two threads call observe() concurrently, assert no exception and records are intact; confirm test passes/fails appropriately
- [ ] 4.6 **GREEN** Add `threading.Lock` to `TruthMonitor.observe()` in `truth_monitor.py`; confirm test passes
- [ ] 4.7 **REFACTOR** Run full test suite; commit `fix: thread-safe peer transport, reporter, and truth monitor`

## 5. Independent Arm Loop in RunController [SEQUENTIAL after 2, 3]

- [ ] 5.1 **RED** Write `test_arm1_does_not_wait_for_arm2_between_steps` — give arm1 3 steps, arm2 5 steps, use a slow sleep_fn for arm2 only; assert arm1 finishes its steps without delay from arm2; confirm test fails
- [ ] 5.2 **RED** Write `test_run_returns_after_all_arms_terminal` — arm1 fast, arm2 slow; assert run() total time matches the slower arm
- [ ] 5.3 **RED** Write `test_step_reports_contain_all_steps_from_both_arms` — arm1: 3 steps, arm2: 5 steps; assert `len(step_reports) == 8`
- [ ] 5.4 **RED** Write `test_independent_arms_publish_and_read_peer_state` — assert each arm thread calls `transport.publish()` once per step
- [ ] 5.5 Confirm all 4 new tests fail (RED confirmed)
- [ ] 5.6 **GREEN** Rewrite `RunController.run()` execution phase: extract `_run_arm_thread(arm_id, steps, ...)` helper; dispatch both arm threads via `ThreadPoolExecutor(max_workers=2)`; join both before returning summary
- [ ] 5.7 Confirm all 4 new tests pass; run full test suite and fix any regressions
- [ ] 5.8 **REFACTOR** Clean up; commit `feat: independent per-arm execution threads in RunController`

## 6. New Asymmetric Scenario Files [SEQUENTIAL after 4, 5]

- [ ] 6.1 **RED** Write `test_geometry_pack_has_asymmetric_arm_counts` — load `geometry_pack.json`, assert arm1 has 3 steps and arm2 has 5 steps; confirm test fails (current file has equal counts)
- [ ] 6.2 **RED** Write `test_geometry_pack_contains_colliding_and_safe_steps` — assert at least 1 step_id has j4 gap < 0.05 m and at least 1 has j4 gap > 0.08 m when both arms are active; confirm fails
- [ ] 6.3 **GREEN** Replace `geometry_pack.json` with asymmetric scenario: arm1 steps 0–2, arm2 steps 0–4, mixing colliding (cam_z close) and safe (cam_z far) positions; confirm tests pass
- [ ] 6.4 **RED** Write equivalent tests for `contention_pack.json` (asymmetric counts + collision/safe mix); confirm tests fail
- [ ] 6.5 **GREEN** Replace `contention_pack.json` with a distinct asymmetric scenario; confirm tests pass
- [ ] 6.6 **REFACTOR** Run full test suite; commit `chore: replace scenario files with asymmetric independent-arm scenarios`

## 7. Integration + Impact Analysis [SEQUENTIAL after 6]

- [ ] 7.1 Write `impact-analysis.md` in the change directory covering before/after behaviour, performance impact, unchanged behaviour, risk assessment, and blast radius
- [ ] 7.2 Run full test suite `python3 -m pytest . -q -k "not test_run_report_markdown"` — confirm all tests pass (expected ≥ 408 + new tests)
- [ ] 7.3 Cross-artifact review: verify every spec scenario in this change has a corresponding test task above; fix any gaps
- [ ] 7.4 Commit all artifact files: `chore: create independent-arm-run change artifacts`
