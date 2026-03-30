## Execution Plan

| Group | Depends On | Can Parallelize With |
|-------|-----------|---------------------|
| 1. Backend Tests (RED) | — | — |
| 2. Backend Endpoint (GREEN) | 1 | — |
| 3. Backend Refactor | 2 | — |
| 4. Frontend HTML | — | 5, 6 |
| 5. Frontend CSS | — | 4, 6 |
| 6. Frontend JS | 2 (needs endpoint) | 4, 5 |
| 7. Integration Verification | 1-6 | — |

## 1. Backend Tests (RED) [SEQUENTIAL]

- [x] 1.1 Create `test_run_all_modes_backend.py` with autouse fixture suppressing Gazebo side-effects (same pattern as `test_ui_run_flow_backend.py`)
- [x] 1.2 Write test: `POST /api/run/start-all-modes` returns HTTP 200 with valid payload
- [x] 1.3 Write test: response contains `status: "complete"`
- [x] 1.4 Write test: response contains `summaries` list with exactly 5 entries
- [x] 1.5 Write test: summary mode names cover all 5 modes (`unrestricted`, `baseline_j5_block_skip`, `geometry_block`, `sequential_pick`, `smart_reorder`)
- [x] 1.6 Write test: response contains `comparison_markdown` with "Comparison Report"
- [x] 1.7 Write test: response contains `recommendation` naming a valid mode
- [x] 1.8 Write test: invalid `arm_pair` returns HTTP 422
- [x] 1.9 Write test: `GET /api/run/report/all-modes/json` returns 200 after completed run with 5 summaries
- [x] 1.10 Write test: `GET /api/run/report/all-modes/json` returns 404 before any run
- [x] 1.11 Write test: `GET /api/run/report/all-modes/markdown` returns 200 with "Comparison Report" and "Recommendation"
- [x] 1.12 Run tests and confirm all FAIL (RED phase)

## 2. Backend Endpoint (GREEN) [SEQUENTIAL]

- [x] 2.1 Add `AllModesStartRequest` Pydantic model to `testing_backend.py` (fields: `scenario`, `arm_pair`, `enable_phi_compensation`)
- [x] 2.2 Add `_current_all_modes_result` global variable (initially `None`)
- [x] 2.3 Implement `POST /api/run/start-all-modes` endpoint: validate arm_pair, loop modes 0-4 creating `RunController(mode, executor=None)`, collect summaries, generate comparison markdown via `MarkdownReporter`, extract recommendation via regex, store result, return response
- [x] 2.4 Implement `GET /api/run/report/all-modes/json` endpoint: return summaries or 404
- [x] 2.5 Implement `GET /api/run/report/all-modes/markdown` endpoint: return comparison markdown as text/plain or 404
- [x] 2.6 Run tests and confirm all 11 PASS (GREEN phase)

## 3. Backend Refactor [SEQUENTIAL]

- [x] 3.1 Review endpoint code for duplication with existing `/api/run/start`, extract shared validation if beneficial
- [x] 3.2 Run all backend tests (new + existing `test_ui_run_flow_backend.py`) to confirm no regressions

## 4. Frontend HTML [PARALLEL with 5, 6]

- [x] 4.1 Add "Run All Modes" button (`id="run-all-modes-btn"`) below the existing Start Run button row in `testing_ui.html`
- [x] 4.2 Add status text span (`id="run-all-modes-status"`) next to the button
- [x] 4.3 Add modal overlay div (`id="all-modes-modal"`) with close button, table container, recommendation text area, and download links

## 5. Frontend CSS [PARALLEL with 4, 6]

- [x] 5.1 Add `.modal-overlay` and `.modal-content` styles (fixed overlay, centred white-on-dark content box, close button)
- [x] 5.2 Add `.comparison-table` styles (full-width, border-collapse, header row)
- [x] 5.3 Add `.cell-green`, `.cell-red`, `.cell-amber` cell colour classes
- [x] 5.4 Add `.row-best` highlighted row style (gold left border, subtle background)
- [x] 5.5 Add `.btn-all-modes` button style and spinner animation for loading state

## 6. Frontend JS [PARALLEL with 4, 5]

- [x] 6.1 Add `setupRunAllModes()` function: resolve scenario (file input priority over preset), POST to `/api/run/start-all-modes`, show spinner during request
- [x] 6.2 Add `renderComparisonTable(summaries, recommendation)` function: build HTML table with 5 rows, apply colour classes per cell, highlight recommended row
- [x] 6.3 Add `openModal()` / `closeModal()` functions: show/hide modal overlay, close on button click and overlay click
- [x] 6.4 Wire download links in modal to `/api/run/report/all-modes/json` and `/api/run/report/all-modes/markdown`
- [x] 6.5 Call `setupRunAllModes()` from `init()`

## 7. Integration Verification [SEQUENTIAL]

- [x] 7.1 Run all backend tests (`pytest test_run_all_modes_backend.py test_ui_run_flow_backend.py test_markdown_reporter.py`)
- [x] 7.2 Verify no regressions in existing test suite
- [x] 7.3 Git commit when all tests are green
