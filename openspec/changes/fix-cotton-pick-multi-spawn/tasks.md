## Execution Plan

| Group | Depends On | Can Parallelize With |
|-------|-----------|---------------------|
| 1. Pick status reliability (backend) | None | 2 |
| 2. Pick status reliability (frontend) | None | 1 |
| 3. Reachable target validation | None | 1, 2 |
| 4. Multi-cotton backend state | 1 | 5 |
| 5. Multi-cotton frontend UI | 2 | 4 |
| 6. Sequential pick-all | 4 | — |
| 7. Integration & cleanup | 1–6 | — |

## 1. Pick Status Reliability — Backend [PARALLEL with 2, 3]

- [x] 1.1 RED: Write test `test_pick_status_resets_to_idle_between_picks` — assert `GET /api/cotton/pick-status` returns `"idle"` immediately after a new `POST /api/cotton/pick` (before timers fire). Capability: `pick-status-reliability`
- [x] 1.2 RED: Write test `test_pick_status_thread_lock` — assert concurrent status reads during timer updates return consistent snapshots (no mixed state). Capability: `pick-status-reliability`
- [x] 1.3 GREEN: Add `threading.Lock` to `testing_backend.py`; protect `_pick_in_progress` and `_pick_status` reads/writes; reset `_pick_status = "idle"` at start of `POST /api/cotton/pick`. Design ref: D1, D3
- [x] 1.4 REFACTOR: Clean up any redundant status checks; verify tests pass

## 2. Pick Status Reliability — Frontend [PARALLEL with 1, 3]

- [x] 2.1 N/A: Playwright E2E test `test_single_completion_message` — requires live server; underlying fix (module-level `_pickPollInterval`) verified in 2.2
- [x] 2.2 GREEN: Refactor `pollPickStatus()` in `testing_ui.js` — replace local interval variable with module-level `_pickPollInterval`; clear existing interval before creating new one. Design ref: D2
- [x] 2.3 N/A: Dead code removal verified during 2.2 implementation; E2E verification requires live server

## 3. Reachable Target Validation [PARALLEL with 1, 2]

- [x] 3.1 RED: Write test `test_spawn_unreachable_j3_above_arm` — assert `POST /api/cotton/spawn` returns 400 with reason when phi > 0. Capability: `reachable-target-validation`
- [x] 3.2 RED: Write test `test_spawn_unreachable_j5_too_close` — assert 400 when r < HARDWARE_OFFSET. Capability: `reachable-target-validation`
- [x] 3.3 RED: Write test `test_spawn_reachable_returns_200` — assert 200 with cotton name and joint values for valid coordinates. Capability: `reachable-target-validation`
- [x] 3.4 RED: Write test `test_pick_after_remove_rejected` — assert pick returns error when cotton has been removed. Capability: `reachable-target-validation`
- [x] 3.5 GREEN: Add reachability check to `POST /api/cotton/spawn`; return 400 with specific reason on failure. Ensure remove deletes from collection completely. Design ref: D6, D7
- [x] 3.6 RED: Write JS/E2E test `test_error_toast_on_unreachable` — assert error message displayed in UI on failed spawn. Capability: `reachable-target-validation`
- [x] 3.7 GREEN: Add frontend error handling for 400 responses from spawn; display reason in status area
- [x] 3.8 REFACTOR: Clean up; verify all reachability tests pass

## 4. Multi-Cotton Backend State [SEQUENTIAL]

- [x] 4.1 RED: Write test `test_spawn_multiple_cottons_unique_names` — assert 3 spawns produce `cotton_0`, `cotton_1`, `cotton_2`. Capability: `multi-cotton-management`
- [x] 4.2 RED: Write test `test_cotton_counter_no_reset_after_remove` — assert counter continues after remove. Capability: `multi-cotton-management`
- [x] 4.3 RED: Write test `test_cotton_list_endpoint` — assert `GET /api/cotton/list` returns all cottons with coords and status. Capability: `multi-cotton-management`
- [x] 4.4 RED: Write test `test_remove_all_deletes_all_cottons` — assert `POST /api/cotton/remove-all` clears collection. Capability: `multi-cotton-management`
- [x] 4.5 RED: Write test `test_remove_all_blocked_during_pick` — assert 400 during active pick sequence. Capability: `multi-cotton-management`
- [x] 4.6 GREEN: Refactor `testing_backend.py` — replace singleton globals with `CottonState` dataclass and `_cottons` dict; add `_cotton_counter`; implement `GET /api/cotton/list`, `POST /api/cotton/remove-all`. Design ref: D4, D7
- [x] 4.7 REFACTOR: Migrate existing spawn/remove/compute/pick endpoints to use collection; verify all existing + new tests pass

## 5. Multi-Cotton Frontend UI [PARALLEL with 4]

- [x] 5.1 RED: Write Playwright E2E test `test_cotton_table_shows_spawned` — assert table rows appear after spawning 2 cottons. Capability: `multi-cotton-management`
- [x] 5.2 RED: Write Playwright E2E test `test_remove_all_clears_table` — assert table is empty after Remove All. Capability: `multi-cotton-management`
- [x] 5.3 GREEN: Add cotton table HTML to `testing_ui.html` (Name, Cam Coords, J3/J4/J5, Status columns). Add "Remove All" button. Design ref: proposal
- [x] 5.4 GREEN: Add CSS for cotton table in `testing_ui.css`
- [x] 5.5 GREEN: Wire up JS in `testing_ui.js` — fetch `/api/cotton/list` to render table; bind Remove All button to `POST /api/cotton/remove-all`; refresh table after spawn/remove/pick
- [x] 5.6 REFACTOR: Disable Remove All button during pick sequence; verify E2E tests pass

## 6. Sequential Pick-All [SEQUENTIAL]

- [x] 6.1 RED: Write test `test_pick_all_sequential_order` — assert cottons are picked in spawn order with correct status transitions. Capability: `multi-cotton-management`
- [x] 6.2 RED: Write test `test_pick_all_skips_picked_cottons` — assert already-picked cottons are skipped. Capability: `multi-cotton-management`
- [x] 6.3 RED: Write test `test_pick_all_nothing_to_pick` — assert `{"status": "nothing_to_pick"}` when no spawned cottons remain. Capability: `multi-cotton-management`
- [x] 6.4 RED: Write test `test_pick_status_progress_during_multi` — assert pick-status returns `current` and `progress` fields during sequence. Capability: `multi-cotton-management`
- [x] 6.5 GREEN: Implement `POST /api/cotton/pick-all` — iterate `_cottons` in order; run pick animation per cotton; advance via timer callback; return home after last. Design ref: D5
- [x] 6.6 GREEN: Update `GET /api/cotton/pick-status` to include `current` and `progress` fields during multi-pick
- [x] 6.7 RED: Write Playwright E2E test `test_pick_all_button_updates_table` — assert table status updates during multi-pick. Capability: `multi-cotton-management`
- [x] 6.8 GREEN: Wire up "Pick All" button in frontend; update poll to handle progress; update table during pick
- [x] 6.9 REFACTOR: Clean up; verify all tests pass

## 7. Integration & Cleanup [SEQUENTIAL]

- [x] 7.1 Run full test suite: `python3 -m pytest test_fk_chain.py test_cam_markers_backend.py -v` and `node --test tests/test_cam_to_joint.js`
- [x] 7.2 Verify existing Phase 1 Playwright E2E tests still pass (cotton_placement.spec.js, cotton_sequence.spec.js) or update them to match new multi-cotton API
- [x] 7.3 Final cleanup — remove any dead singleton code, update comments, verify no lint issues
