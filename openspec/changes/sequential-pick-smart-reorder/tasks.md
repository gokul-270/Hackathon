## Execution Plan

| Group | Depends On | Can Parallelize With |
|-------|-----------|---------------------|
| 1. Rename Constants & Strings | — | — |
| 2. Sequential Pick Policy | 1 | 3 |
| 3. Smart Reorder Scheduler | 1 | 2 |
| 4. BaselineMode Integration | 1, 2, 3 | — |
| 5. RunController Orchestration | 4 | 6, 7 |
| 6. Reporting Extensions | 1 | 5, 7 |
| 7. UI & Backend Validation | 1 | 5, 6 |
| 8. Test Suite Migration | 1, 4 | 6, 7 |
| 9. E2E Verification & Playwright | 1–8 | — |

## 1. Rename Constants & Strings [SEQUENTIAL]

Replace all `overlap_zone_wait` / `OVERLAP_ZONE_WAIT` references with `sequential_pick` / `SEQUENTIAL_PICK` across source and test files. No behavior change — pure rename. Commit when green.

- [x] 1.1 In `baseline_mode.py`: rename constant `OVERLAP_ZONE_WAIT = 3` to `SEQUENTIAL_PICK = 3`. Update all internal references.
- [x] 1.2 In `run_controller.py`: rename `_MODE_NAMES` entry from `"overlap_zone_wait"` to `"sequential_pick"` for key 3. Add entry `4: "smart_reorder"`.
- [x] 1.3 In `testing_backend.py`: update `valid_modes` from `{0, 1, 2, 3}` to `{0, 1, 2, 3, 4}`. Update error message from `"must be 0-3"` to `"must be 0-4"`.
- [x] 1.4 In `json_reporter.py`: update mode type comment from overlap_zone_wait to sequential_pick/smart_reorder. Update skipped comment if present.
- [x] 1.5 Rename file `wait_mode_policy.py` to `sequential_pick_policy.py` (empty the old class, write stub `SequentialPickPolicy` with pass-through `apply` method that preserves the old interface signature).
- [x] 1.6 Update all import references from `wait_mode_policy` to `sequential_pick_policy` in `baseline_mode.py` and any other importing files.
- [x] 1.7 Bulk-rename string `"overlap_zone_wait"` to `"sequential_pick"` in all 16 test files. Update test names/docstrings referencing old Mode 3.
- [x] 1.8 Run full test suite (`python3 -m pytest -k "not test_run_report_markdown"`) — all 446+ tests must pass. TDD: this is a rename-only commit, tests should pass with no behavior change. Commit.

## 2. Sequential Pick Policy [PARALLEL with 3]

Implement `SequentialPickPolicy` with contention detection, turn alternation, and winner/loser designation. Pure unit — no RunController changes yet.

- [x] 2.1 Write failing tests in `test_sequential_pick_policy.py` (new file replacing `test_wait_mode_policy.py`): contention detected when j4 gap < 0.10 and both j5 > 0; no contention when gap >= 0.10; no contention when peer j5 == 0; no contention when no peer; arm1 wins first contention; turn alternates; turn locked within same step_id; winner gets unmodified joints; loser gets unmodified joints with loser flag.
- [x] 2.2 Run tests — confirm RED (all new tests fail).
- [x] 2.3 Implement `SequentialPickPolicy` in `sequential_pick_policy.py`: `__init__` initializes turn state. `apply(step_id, arm_id, own_joints, peer_joints)` returns `(applied_joints, skipped, is_contention, is_winner)`. Contention: `|own_j4 - peer_j4| < 0.10` AND both j5 > 0 AND peer exists.
- [x] 2.4 Run tests — confirm GREEN. Refactor if needed. Commit.

## 3. Smart Reorder Scheduler [PARALLEL with 2]

Implement `SmartReorderScheduler` — pure algorithm, no RunController wiring yet.

- [x] 3.1 Write failing tests in `test_smart_reorder_scheduler.py` (new file): reorder produces valid step map with all steps preserved; reorder improves min j4 gap over original; handles already-optimal order; j4 computed from cam_z using FK formula (0.1005 - cam_z); handles unequal step counts (solo tail preserved); brute-force for N <= 8; greedy fallback for N > 8.
- [x] 3.2 Run tests — confirm RED.
- [x] 3.3 Implement `SmartReorderScheduler` in `smart_reorder_scheduler.py` (new file): `reorder(step_map, arm1_steps, arm2_steps)` computes j4 for each step via FK, finds optimal pairing via brute-force permutations (N <= 8) or greedy (N > 8), returns reordered step_map.
- [x] 3.4 Run tests — confirm GREEN. Refactor if needed. Commit.

## 4. BaselineMode Integration [SEQUENTIAL]

Wire SequentialPickPolicy and SmartReorder passthrough into BaselineMode dispatch.

- [ ] 4.1 Write failing tests in existing `test_baseline_mode.py` or appropriate test file: `apply_with_skip` delegates to sequential pick policy when mode == 3; `apply_with_skip` passes through unchanged when mode == 4 (smart_reorder); mode constant `SMART_REORDER == 4` exists.
- [ ] 4.2 Run tests — confirm RED.
- [ ] 4.3 In `baseline_mode.py`: add `SMART_REORDER = 4`. Update `__init__` to create `SequentialPickPolicy` instead of `WaitModePolicy`. Add dispatch branch in `apply_with_skip` for mode 3 → sequential pick, mode 4 → passthrough. Remove old `_apply_overlap_zone_wait` method.
- [ ] 4.4 Run full test suite — confirm GREEN. Commit.

## 5. RunController Orchestration [SEQUENTIAL]

Add two-phase dispatch for Mode 3 contention steps and pre-run reorder for Mode 4.

- [ ] 5.1 Write failing tests: Mode 3 contention step dispatches winner arm first then loser arm sequentially (verify call order); Mode 3 non-contention step dispatches both in parallel; Mode 4 calls SmartReorderScheduler.reorder() before step loop; Mode 4 steps run in parallel after reorder.
- [ ] 5.2 Run tests — confirm RED.
- [ ] 5.3 In `run_controller.py`: import `SmartReorderScheduler`. Before step loop, if mode == SMART_REORDER, call `scheduler.reorder()` to replace step_map. In dispatch section, if mode == SEQUENTIAL_PICK and contention detected (from policy result), dispatch winner arm `executor.execute()` first, await result, then dispatch loser arm. Else use parallel ThreadPoolExecutor dispatch as before.
- [ ] 5.4 Run full test suite — confirm GREEN. Refactor. Commit.

## 6. Reporting Extensions [PARALLEL with 5, 7]

Extend markdown reporter for five-mode support. Update mode name strings.

- [ ] 6.1 Write failing tests: five run summaries produce "Five-Mode" heading; four summaries still produce "Four-Mode" heading; all five mode names appear in five-mode table; Blocked+Skipped column present for >= 4 modes; recommendation works with five modes.
- [ ] 6.2 Run tests — confirm RED.
- [ ] 6.3 In `markdown_reporter.py`: update heading logic — `five_mode = len(runs) >= 5`, use "Five-Mode" when true. Ensure mode name `sequential_pick` and `smart_reorder` are handled. Table format unchanged (Blocked+Skipped column for >= 4 modes already works).
- [ ] 6.4 Run tests — confirm GREEN. Commit.

## 7. UI & Backend Validation [PARALLEL with 5, 6]

Update mode dropdown and backend mode validation.

- [ ] 7.1 Write failing tests: UI dropdown has 5 options (modes 0-4); mode 3 labeled "Sequential Pick"; mode 4 labeled "Smart Reorder"; backend accepts mode 4; backend rejects mode 99 with "must be 0-4".
- [ ] 7.2 Run tests — confirm RED.
- [ ] 7.3 In `testing_ui.html`: rename mode 3 option from "Overlap Zone Wait" to "Sequential Pick". Add mode 4 option "Smart Reorder". Update any supporting JS if needed.
- [ ] 7.4 In `testing_backend.py`: confirm `valid_modes = {0, 1, 2, 3, 4}` and error message says "must be 0-4" (should already be done in Group 1, verify).
- [ ] 7.5 Run tests — confirm GREEN. Commit.

## 8. Test Suite Migration [PARALLEL with 6, 7]

Rewrite/update the 16 test files that reference old Mode 3 behavior. Adapt mode lists, assertions, and test scenarios for five-mode support.

- [ ] 8.1 Rewrite `test_overlap_zone_wait_e2e.py` → `test_sequential_pick_e2e.py`: new E2E tests verifying Mode 3 sequential pick behavior (contention steps dispatch sequentially, non-contention parallel, no skips, turn alternation visible in reports).
- [ ] 8.2 Delete or empty `test_wait_mode_policy.py` (replaced by `test_sequential_pick_policy.py` in Group 2).
- [ ] 8.3 Update `test_phase2_runtime_correctness_e2e.py`: replace OZW-dedicated tests with sequential pick tests; update all four-mode lists to five-mode; update `mode_names` set.
- [ ] 8.4 Update `test_final_reporting.py`: replace `"overlap_zone_wait"` strings with `"sequential_pick"`; update four-mode lists to include `"smart_reorder"`; update recommendation test.
- [ ] 8.5 Update `test_markdown_reporter.py`: replace OZW winner string with `"sequential_pick"`.
- [ ] 8.6 Update `test_ui_run_flow_e2e.py`: change `range(4)` to `range(5)`; update mode 3 assertion.
- [ ] 8.7 Update `test_ui_run_flow_integration.py`: update mode names dict (lines 74-79) to include sequential_pick and smart_reorder.
- [ ] 8.8 Update `test_ui_run_flow_ui.py`: update `value="3"` assertion text to "Sequential Pick"; add mode 4 assertion.
- [ ] 8.9 Update `test_ui_run_flow_backend.py`: verify mode 4 acceptance boundary test exists.
- [ ] 8.10 Update `test_phase3_architecture_alignment_e2e.py`: update four-mode list on line 225 to five-mode.
- [ ] 8.11 Update `test_contention_scenario_pack.py`: update docstring reference.
- [ ] 8.12 Update `test_run_summary_output.py`: replace OZW string with sequential_pick.
- [ ] 8.13 Update `test_outcome_reporting.py`: replace OZW string with sequential_pick.
- [ ] 8.14 Update `test_motion_backed_e2e.py`: change `range(4)` to `range(5)`.
- [ ] 8.15 Update `test_run_controller.py`: update mode references for new Mode 3/4.
- [ ] 8.16 Run full test suite — confirm GREEN (all 446+ tests pass, plus new tests). Commit.

## 9. E2E Verification & Playwright [SEQUENTIAL]

Full system verification — run all tests and verify the UI in a browser.

- [ ] 9.1 Run full test suite: `python3 -m pytest -k "not test_run_report_markdown"` — all tests green.
- [ ] 9.2 Start the backend server and open the UI in Playwright.
- [ ] 9.3 Verify mode dropdown shows 5 options (0-4) with correct labels.
- [ ] 9.4 Run a scenario in Mode 3 (Sequential Pick) — verify SSE log shows sequential dispatch at contention steps.
- [ ] 9.5 Run a scenario in Mode 4 (Smart Reorder) — verify SSE log shows reordered steps and parallel dispatch.
- [ ] 9.6 Take screenshot evidence of five-mode dropdown and run results.
- [ ] 9.7 Final commit if any Playwright-driven fixes were needed.
