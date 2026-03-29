## Before / After Behavior

| Item | Before (current) | After |
|------|-----------------|-------|
| `step_start` event | Contains `arm_id`, `step_id`, `target_j3/j4/j5`, `mode` | Also contains `cam_x`, `cam_y`, `cam_z` from scenario step |
| Cotton pick completion | No SSE event emitted | `cotton_reached` event emitted with `arm_id`, `step_id`, `cam_x/y/z` |
| Mode 3 contention detection | Silent — only affects dispatch order | `contention_detected` event emitted with `winner_arm`, `loser_arm`, `j4_gap` |
| Dispatch decision | Silent — executor called with no observable signal | `dispatch_order` event emitted with `order` ("sequential"/"parallel") and `sequence` |
| Mode 4 reorder | Silent — step_map rebuilt with no observable signal | `reorder_applied` event emitted with step counts and `min_j4_gap` |
| UI log — step start | `"Step 1 starting"` | `"Step 1 arm1 starting -> target (x:0.650, y:-0.001, z:0.050)"` |
| UI log — cotton pick | Nothing | `"arm1 reached cotton (step:1, x:0.650, y:-0.001, z:0.050)"` |
| UI log — contention | Nothing | `"Contention at step 1: arm1 wins, arm2 waits (gap=0.005m)"` |
| UI log — dispatch | Nothing | `"Step 1: sequential dispatch [arm1 -> arm2]"` or `"Step 1: parallel dispatch [arm1, arm2]"` |
| UI log — reorder | Nothing | `"Reorder applied: 6 steps, min j4 gap=0.142m"` |
| Playwright verification | Cannot verify mode-specific behavior | All 5 modes (0–4) verifiable via log content assertions |

## Performance Impact

| Item | CPU | Memory | Latency |
|------|-----|--------|---------|
| New `_emit()` calls (4 per step) | +4 dict allocations per step, negligible | ~400 bytes per step in EventBus deque | None — emits are non-blocking (deque append + notify) |
| Frontend log lines | None | +4 log lines per step, capped at 200 lines | None |
| Mode 4 min_j4_gap computation | 1 loop over step_map (N iterations), O(N) | None | <1ms for N<=20 steps |

## Unchanged Behavior

- All existing SSE event types (`cotton_spawn`, `step_complete`, `run_complete`) — fields unchanged
- `/api/run/events` SSE endpoint — no protocol changes
- `/api/run/start` POST — no changes
- RunController dispatch logic — no behavior changes (only observability added)
- SequentialPickPolicy — no changes
- SmartReorderScheduler — no changes
- RunStepExecutor — no changes
- JsonReporter / MarkdownReporter — no changes
- Collision avoidance modes 0–4 — behavior unchanged

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| New emit calls add noise to test assertions | Low — tests use specific event type filters | Tests assert specific event `type` fields, not raw event count |
| Frontend log grows faster, harder to read | Low — 200-line cap already in place | No change needed |
| `cotton_reached` emitted even when Gazebo not running (test mode) | None — only emitted when `pick_completed: True`, which requires executor to return completed status | No mitigation needed |

## Blast Radius

- **Files modified:** 2
  - `pragati_ros2/src/vehicle_arm_sim/web_ui/run_controller.py` — ~35 lines added
  - `pragati_ros2/src/vehicle_arm_sim/web_ui/testing_ui.js` — ~25 lines added
- **Test files modified:** 1
  - `pragati_ros2/src/vehicle_arm_sim/web_ui/test_run_controller.py` — ~8 new tests
- **New files:** 0
- **Packages affected:** `vehicle_arm_sim` web UI only
