## Execution Plan

| Group | Depends On | Can Parallelize With |
|-------|-----------|---------------------|
| 1. Backend SSE Events | — | 2 |
| 2. Frontend SSE Formatting | — | 1 |
| 3. Playwright E2E Verification | 1, 2 | — |

## 1. Backend SSE Events [SEQUENTIAL]

Add 4 new SSE event emissions and enhance 1 existing event in `run_controller.py`. TDD: write failing tests first, then implement, then refactor.

- [x] 1.1 Write failing test `test_step_start_includes_cam_position`: assert `step_start` event contains `cam_x`, `cam_y`, `cam_z` fields.
- [x] 1.2 Enhance `step_start` emit (line 364) to include `cam_x`, `cam_y`, `cam_z` from `args["step"]`. Run test — GREEN.
- [x] 1.3 Write failing test `test_cotton_reached_event_emitted`: Mode 0 run with completed pick emits `cotton_reached` with correct `arm_id`, `step_id`, `cam_x`, `cam_y`, `cam_z`.
- [x] 1.4 Write failing test `test_cotton_reached_not_emitted_on_skip`: skipped step does not emit `cotton_reached`.
- [x] 1.5 Implement `cotton_reached` emit after each `execute()` return when `pick_completed` is True. Run tests — GREEN.
- [x] 1.6 Write failing test `test_contention_detected_event_emitted`: Mode 3 run with contention step emits `contention_detected` with `winner_arm`, `loser_arm`, `j4_gap`.
- [x] 1.7 Write failing test `test_contention_detected_not_emitted_safe_gap`: Mode 3 run with safe gap does not emit `contention_detected`.
- [x] 1.8 Implement `contention_detected` emit after `step_has_contention` is True. Compute j4 gap from `candidates`. Run tests — GREEN.
- [x] 1.9 Write failing test `test_dispatch_order_sequential`: Mode 3 contention step emits `dispatch_order` with `order="sequential"`, `sequence=[winner, loser]`.
- [x] 1.10 Write failing test `test_dispatch_order_parallel`: Mode 0 step emits `dispatch_order` with `order="parallel"`.
- [x] 1.11 Implement `dispatch_order` emit at start of each dispatch path. Run tests — GREEN.
- [x] 1.12 Write failing test `test_reorder_applied_event_emitted`: Mode 4 run emits `reorder_applied` with `original_step_count`, `reordered_step_count`, `min_j4_gap`.
- [x] 1.13 Write failing test `test_reorder_applied_not_emitted_other_modes`: Mode 0 run does not emit `reorder_applied`.
- [x] 1.14 Implement `reorder_applied` emit after Mode 4 step_map rebuild. Compute min_j4_gap from rebuilt step_map using FK. Run tests — GREEN.
- [x] 1.15 Run full test suite (`python3 -m pytest -k "not test_run_report_markdown"`) — all tests pass. Commit.

## 2. Frontend SSE Formatting [PARALLEL with 1]

Add formatting for 4 new event types and enhance `step_start` in `testing_ui.js` onmessage handler.

- [x] 2.1 Modify `step_start` handler to display: `"Step {step_id} {arm_id} starting -> target (x:{cam_x}, y:{cam_y}, z:{cam_z})"`.
- [x] 2.2 Add `cotton_reached` handler: `"{arm_id} reached cotton (step:{step_id}, x:{cam_x}, y:{cam_y}, z:{cam_z})"`.
- [x] 2.3 Add `contention_detected` handler: `"Contention at step {step_id}: {winner_arm} wins, {loser_arm} waits (gap={j4_gap}m)"`.
- [x] 2.4 Add `dispatch_order` handler: sequential → `"Step {step_id}: sequential dispatch [{arm1} -> {arm2}]"`, parallel → `"Step {step_id}: parallel dispatch [{arm1}, {arm2}]"`.
- [x] 2.5 Add `reorder_applied` handler: `"Reorder applied: {step_count} steps, min j4 gap={min_j4_gap}m"`.
- [x] 2.6 Run full test suite to confirm no regressions. Commit with Group 1.

## 3. Playwright E2E Verification [SEQUENTIAL]

Start Gazebo server, start backend, run all 5 modes via Playwright, assert SSE log content.

- [ ] 3.1 Start Gazebo server (`gz sim -s`) and backend on port 8081.
- [ ] 3.2 Navigate Playwright to UI, verify mode dropdown has 5 options.
- [ ] 3.3 Mode 0 (Unrestricted): select mode, load `contention_pack`, start run, wait for completion. Assert: `parallel dispatch` present, `cotton_reached` with correct positions present, NO `Contention`, NO `sequential dispatch`, NO `Reorder`.
- [ ] 3.4 Mode 1 (Baseline J5): same flow. Assert: `parallel dispatch` present, NO `Contention`, NO `sequential dispatch`, NO `Reorder`.
- [ ] 3.5 Mode 2 (Geometry Block): same flow. Assert: `parallel dispatch` present, NO `Contention`, NO `sequential dispatch`, NO `Reorder`.
- [ ] 3.6 Mode 3 (Sequential Pick): same flow. Assert: `Contention at step` present, `sequential dispatch` present at contention steps, `parallel dispatch` at non-contention steps, `cotton_reached` in winner-first order at contention steps, NO `Reorder`.
- [ ] 3.7 Mode 4 (Smart Reorder): same flow. Assert: `Reorder applied` present with min gap, `parallel dispatch` present, `cotton_reached` with reordered positions, NO `Contention`, NO `sequential dispatch`.
- [ ] 3.8 Take screenshot evidence of each mode's log output.
- [ ] 3.9 Final commit if any fixes needed. Update tasks.md.
