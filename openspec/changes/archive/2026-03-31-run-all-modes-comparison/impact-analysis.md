## Before / After Behavior

| Item | Before (current) | After |
|------|-----------------|-------|
| Comparing collision avoidance modes | Operator manually runs each mode 1-by-1 via "Start Run", compares results by hand | One-click "Run All Modes" button dry-runs all 5 modes in <50ms, displays colourful comparison table in modal |
| `MarkdownReporter` usage | Class implemented and tested but never called from any endpoint | Called by `POST /api/run/start-all-modes` to generate comparison markdown and recommendation |
| Mode comparison report download | Not available | JSON and Markdown downloads via `GET /api/run/report/all-modes/json` and `/markdown` |
| Mode recommendation | Operator decides manually | Automatic recommendation extracted from `MarkdownReporter` output, highlighted in gold in modal table |
| Global state for all-modes results | Does not exist | New `_current_all_modes_result` global stores latest all-modes run result |

## Performance Impact

| Item | CPU | Memory | Latency |
|------|-----|--------|---------|
| 5-mode dry-run loop | 5 × RunController with no-op executor, ~5-10ms each | ~5 run summaries in memory (~2KB total) | <50ms total (no Gazebo I/O, no sleep) |
| `MarkdownReporter.generate()` | String formatting only, negligible | ~1KB markdown output | <1ms |
| Modal DOM rendering (frontend) | 5-row HTML table build, negligible | ~2KB DOM nodes | Instant |
| Report download endpoints | Return cached result, no computation | None beyond stored result | <1ms |

## Unchanged Behavior

- All existing SSE event types (`cotton_spawn`, `step_start`, `step_complete`, `run_complete`) — fields unchanged
- `/api/run/start` POST — single-mode run flow completely untouched
- `/api/run/status` GET — unchanged
- `/api/run/report/json` and `/api/run/report/markdown` — single-mode report endpoints unchanged
- `_current_run_result` global — separate from new `_current_all_modes_result`, no interaction
- RunController dispatch logic — no behavior changes
- RunStepExecutor — no changes
- Collision avoidance modes 0–4 logic — no changes
- MarkdownReporter class — no modifications (only called, not changed)
- JsonReporter class — no modifications (only called, not changed)
- Existing "Start Run" button and UI flow — completely untouched

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Dry-run results differ from Gazebo-backed run | Low | Collision detection is mathematical (FK chain + J4 gap), not physics-based. Both paths use identical RunController logic. |
| `MarkdownReporter` format changes break recommendation regex | Low | Existing `test_markdown_reporter.py` (17 tests) validates format. New `test_run_all_modes_backend.py` also verifies extraction. |
| Large scenario slows dry-run beyond acceptable latency | Very low | 100 steps × 5 modes = 500 FK computations at ~0.1ms each = <50ms. No I/O in loop. |
| New global state leaks between single-mode and all-modes runs | None | Separate globals (`_current_run_result` vs `_current_all_modes_result`) with no shared mutation. |
| Modal popup interferes with existing UI interactions | None | Standard modal overlay pattern. Close button + overlay click dismiss. No DOM changes to existing elements. |

## Blast Radius

- **Files modified:** 3
  - `pragati_ros2/src/vehicle_arm_sim/web_ui/testing_backend.py` — ~80 lines added (3 endpoints, 1 model, 1 global)
  - `pragati_ros2/src/vehicle_arm_sim/web_ui/testing_ui.html` — ~50 lines added (button row, modal DOM)
  - `pragati_ros2/src/vehicle_arm_sim/web_ui/testing_ui.css` — ~150 lines added (modal, table, colour classes)
  - `pragati_ros2/src/vehicle_arm_sim/web_ui/testing_ui.js` — ~170 lines added (5 functions, init wiring)
- **New files:** 1
  - `pragati_ros2/src/vehicle_arm_sim/web_ui/test_run_all_modes_backend.py` — 10 new tests
- **Packages affected:** `vehicle_arm_sim` web UI only
- **New dependencies:** None — reuses existing `RunController`, `MarkdownReporter`, `json_reporter`
