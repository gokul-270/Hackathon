## Why

The current codebase contains replay logic, mode logic, and reporting utilities, but the intended
hackathon flow is not accessible from the UI. There is no visible way to load a scenario JSON, start
the distributed dual-arm replay, or fetch the final report from the testing interface. This phase is
needed to turn the existing backend/library work into a usable end-to-end demo flow.

## What Changes

- Add UI controls to select a mode, choose/load a scenario JSON, and start the run.
- Add backend endpoints that invoke the existing replay controller and expose run status.
- Add JSON and Markdown report retrieval endpoints and UI display/download hooks.
- Connect the existing `RunController`, `JsonReporter`, and `MarkdownReporter` to the testing UI flow.

## Capabilities

### New Capabilities
- `ui-run-flow`: end-to-end UI flow for mode selection, scenario start, status, and report access

### Modified Capabilities
- `collision-comparison-reporting`: expose generated reports to the UI/backend flow
- `dual-arm-run-orchestration`: expose controller lifecycle through backend-triggered execution

## Impact

- Affects `pragati_ros2/src/vehicle_arm_sim/web_ui/testing_ui.html`, `testing_ui.js`, and
  `testing_backend.py`.
- Integrates existing replay/reporting modules into the visible hackathon workflow.

## Non-goals

- Fixing deeper parser/runtime correctness issues
- Reworking the architecture into true distributed nodes
