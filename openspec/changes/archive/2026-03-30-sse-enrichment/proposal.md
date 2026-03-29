## Why

The SSE event stream from RunController currently emits generic `step_start` and `step_complete` events that look identical regardless of which collision avoidance mode is running. There is no way for Playwright E2E tests (or the operator watching the UI log) to verify that Mode 3 (Sequential Pick) actually dispatches arms sequentially at contention steps, or that Mode 4 (Smart Reorder) actually reordered the steps before execution. We need richer events so that mode-specific behavior is observable and verifiable from the frontend.

## What Changes

- Add `cotton_reached` event — emitted after each arm completes a pick, includes arm_id and cam position (x, y, z). Lets Playwright verify cotton pick order and target positions.
- Add `contention_detected` event — emitted in Mode 3 when both arms contest a step, includes winner/loser arm IDs and j4 gap distance.
- Add `dispatch_order` event — emitted at every dispatch decision point, indicates "sequential" or "parallel" and the arm execution sequence.
- Add `reorder_applied` event — emitted in Mode 4 after SmartReorderScheduler completes, includes step count and achieved min j4 gap.
- Enhance existing `step_start` event — add `cam_x`, `cam_y`, `cam_z` fields from the scenario step.
- Add frontend formatting for all 4 new event types and updated `step_start` in the SSE `onmessage` handler.
- Playwright E2E verification of all 5 modes (0–4) against `contention_pack` scenario, asserting mode-specific log lines.

## Capabilities

### New Capabilities
- `run-event-enrichment`: Four new SSE event types (`cotton_reached`, `contention_detected`, `dispatch_order`, `reorder_applied`) and one enhanced event (`step_start` with cam position), emitted by RunController and formatted by the frontend SSE handler.

### Modified Capabilities
- `dual-arm-run-orchestration`: RunController gains new `_emit()` calls at dispatch decision points and after executor returns.
- `ui-run-flow`: Frontend `onmessage` handler gains formatting for 4 new event types and enhanced `step_start`.

## Impact

- **Files modified:** `run_controller.py` (add ~30 lines of `_emit()` calls), `testing_ui.js` (add ~20 lines of event formatting)
- **Files added:** None (events use existing `RunEventBus` infrastructure)
- **Tests added:** ~6 new tests in `test_run_controller.py` for new events
- **APIs:** No new endpoints. Existing `/api/run/events` SSE stream carries new event types. Clients that don't recognize the new types silently ignore them (no breaking change).
- **Dependencies:** None new. Uses existing `RunEventBus`, `SequentialPickPolicy`, `SmartReorderScheduler`.
