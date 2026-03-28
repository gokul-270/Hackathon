## Why

The current dual-arm run flow computes candidate joints and produces reports, but it does not drive Gazebo arm motion during `/api/run/start` and it does not record an explicit per-arm "pick completed" result. This leaves the hackathon demo misaligned with the planned workflow and makes the report less trustworthy as a demo artifact.

## What Changes

- Add a motion-execution bridge so scenario runs publish real Gazebo arm commands from the replay controller path.
- Add explicit per-arm terminal outcomes for each run step, including `completed`, `blocked`, and `skipped`.
- Add `pick_completed` and completed-pick totals to JSON and Markdown run reports.
- Update the UI/backend run flow contract so run completion reflects motion-backed execution, not report-only replay.
- Add regression tests that prove `/api/run/start` triggers execution and emits completion-aware reports.

## Capabilities

### New Capabilities
- `gazebo-scenario-execution`: Execute allowed scenario-run steps as real Gazebo arm motion from the run controller path.
- `pick-outcome-reporting`: Record explicit per-arm terminal outcomes and completed-pick metrics for scenario runs.

### Modified Capabilities
- `ui-run-flow`: Starting a run now triggers motion-backed execution and completion-aware reporting.
- `collision-comparison-reporting`: Run summaries now include explicit completed-pick outcomes instead of only inferred blocked/skipped counts.

## Impact

- Affected code: `pragati_ros2/src/vehicle_arm_sim/web_ui/run_controller.py`, `pragati_ros2/src/vehicle_arm_sim/web_ui/testing_backend.py`, `pragati_ros2/src/vehicle_arm_sim/web_ui/json_reporter.py`, `pragati_ros2/src/vehicle_arm_sim/web_ui/markdown_reporter.py`, and related tests.
- Affected behavior: `/api/run/start`, `/api/run/report/json`, and `/api/run/report/markdown` will reflect motion-backed execution and explicit completion state.
- Systems touched: Gazebo command publishing, run orchestration, reporting, and backend test coverage.

## Non-goals

- Full simulator-feedback truth as the primary report source in this change.
- Dynamic mode switching during a run.
- Generalized scenario-to-cotton model mapping beyond the current run/report integration scope.
