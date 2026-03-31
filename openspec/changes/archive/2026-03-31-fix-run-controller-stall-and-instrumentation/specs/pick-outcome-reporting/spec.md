## MODIFIED Requirements

### Requirement: Record explicit per-arm terminal outcome
The system SHALL record and surface the per-arm `terminal_status` for every step
in both the run report and the SSE `step_complete` event. The UI `step_complete`
SSE handler SHALL display the actual `terminal_status` value (e.g. `ok`,
`unreachable`, `skipped`) instead of a static "complete" label.

#### Scenario: Unreachable step shows correct status in UI
- **WHEN** a step completes with `terminal_status = "unreachable"`
- **THEN** the `step_complete` SSE payload contains `terminal_status: "unreachable"`
- **AND** the UI displays "unreachable" (not "complete") for that step

#### Scenario: Successful step shows ok status in UI
- **WHEN** a step completes with `terminal_status = "ok"`
- **THEN** the UI displays "ok" or "complete" for that step
