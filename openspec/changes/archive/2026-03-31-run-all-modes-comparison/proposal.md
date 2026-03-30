## Why

The testing UI requires operators to manually run each collision avoidance mode (0-4) one at a time, compare results by hand, and decide which mode is most effective for a given scenario. The `MarkdownReporter` five-mode comparison engine is implemented and tested but never exposed through any UI or backend endpoint. A single "Run All Modes" button that dry-runs all 5 modes against the selected scenario, displays a colourful comparison table in a modal, and recommends the best mode will eliminate this manual repetition.

## What Changes

- New backend endpoint `POST /api/run/start-all-modes` that dry-runs all 5 collision avoidance modes (no Gazebo motion) using the existing no-op executor path in `RunController`, collects 5 run summaries, and feeds them to `MarkdownReporter.generate()` for comparison and recommendation.
- New report download endpoints `GET /api/run/report/all-modes/json` and `GET /api/run/report/all-modes/markdown` exposing per-mode summaries and the comparison markdown.
- New "Run All Modes" button in the Scenario Run section of the testing UI, placed below the existing "Start Run" button.
- New modal popup displaying a colourful HTML comparison table (green/red/amber cell colouring based on collision counts) with the recommended mode row highlighted, recommendation text, and download links for JSON and Markdown reports.

## Non-goals

- Changing the existing single-mode "Start Run" flow — it remains untouched.
- Running all modes with live Gazebo joint motion — the all-modes run is a dry-run (collision logic only) for speed.
- Adding new collision avoidance modes beyond the existing 5 (modes 0-4).
- Modifying any collision avoidance logic or thresholds.

## Capabilities

### New Capabilities

- `all-modes-dry-run`: Backend dry-run of all 5 collision avoidance modes against a single scenario, returning per-mode summaries, a comparison markdown report, and a recommended mode.
- `all-modes-comparison-ui`: Frontend button, modal popup with colourful comparison table, recommendation display, and report download links for the all-modes dry-run feature.

### Modified Capabilities

_(none — existing specs for `ui-run-flow` and `collision-comparison-reporting` are not modified; the new feature is purely additive)_

## Impact

- **Backend** (`testing_backend.py`): 3 new endpoints, 1 new request model, 1 new global state variable (~80 lines added).
- **Frontend** (`testing_ui.html`, `testing_ui.js`, `testing_ui.css`): New button, modal DOM structure, JS handler, and CSS styles (~230 lines added across 3 files).
- **Dependencies**: Reuses existing `RunController`, `RunStepExecutor`, `MarkdownReporter` — no new package dependencies.
- **Performance**: Dry-run of 5 modes completes in under 1 second (no Gazebo sleep/publish). Zero impact on existing single-mode run flow.
