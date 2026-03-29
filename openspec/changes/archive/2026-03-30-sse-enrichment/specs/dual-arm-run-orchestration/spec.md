## MODIFIED Requirements

### Requirement: RunController emits SSE events during execution
The RunController SHALL emit enriched SSE events during step execution, including `cotton_reached` after successful picks, `contention_detected` for Mode 3 contention steps, `dispatch_order` at every dispatch decision, and `reorder_applied` after Mode 4 reordering. All events flow through the existing `RunEventBus` via `self._emit()`.

#### Scenario: enriched events emitted during dual-arm run
- **WHEN** a dual-arm run executes with any collision avoidance mode (0–4)
- **THEN** the RunController emits `step_start` (with cam position), `dispatch_order`, `cotton_reached` (on completed picks), and `step_complete` events for each step, plus mode-specific events (`contention_detected` for Mode 3, `reorder_applied` for Mode 4)
