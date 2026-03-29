## ADDED Requirements

### Requirement: cotton_reached event emitted after successful pick
The system SHALL emit a `cotton_reached` SSE event after each arm completes a pick cycle with `pick_completed: True`. The event SHALL include `arm_id`, `step_id`, `cam_x`, `cam_y`, and `cam_z` fields matching the scenario step's camera-frame coordinates.

#### Scenario: cotton_reached emitted on completed pick
- **WHEN** an arm executes a step and the executor returns `pick_completed: True`
- **THEN** a `cotton_reached` event is emitted with the arm's `arm_id`, `step_id`, and `cam_x`, `cam_y`, `cam_z` matching the scenario step

#### Scenario: cotton_reached not emitted on skipped step
- **WHEN** an arm's step is skipped (executor returns `pick_completed: False`)
- **THEN** no `cotton_reached` event is emitted for that arm/step

#### Scenario: cotton_reached not emitted on blocked step
- **WHEN** an arm's step is blocked (executor returns `terminal_status: "blocked"`)
- **THEN** no `cotton_reached` event is emitted for that arm/step

#### Scenario: cotton_reached order reflects sequential dispatch in Mode 3
- **WHEN** Mode 3 dispatches a contention step sequentially (winner first, loser second)
- **THEN** the winner arm's `cotton_reached` event is emitted before the loser arm's `cotton_reached` event

### Requirement: contention_detected event emitted for Mode 3 contention steps
The system SHALL emit a `contention_detected` SSE event when Mode 3 (Sequential Pick) detects contention at a step where both arms are active and their j4 gap is below 0.10m. The event SHALL include `step_id`, `winner_arm`, `loser_arm`, and `j4_gap`.

#### Scenario: contention_detected emitted at contention step
- **WHEN** Mode 3 processes a step where both arms are active and j4 gap < 0.10m
- **THEN** a `contention_detected` event is emitted with the correct `winner_arm`, `loser_arm`, and `j4_gap` values

#### Scenario: contention_detected not emitted when gap is safe
- **WHEN** Mode 3 processes a step where both arms are active but j4 gap >= 0.10m
- **THEN** no `contention_detected` event is emitted for that step

#### Scenario: contention_detected not emitted in other modes
- **WHEN** Modes 0, 1, 2, or 4 process a step
- **THEN** no `contention_detected` event is emitted regardless of j4 gap

### Requirement: dispatch_order event emitted at every dispatch decision
The system SHALL emit a `dispatch_order` SSE event at every dispatch decision point. The event SHALL include `step_id`, `order` (either `"sequential"` or `"parallel"`), and `sequence` (list of arm_ids in execution order).

#### Scenario: sequential dispatch_order for Mode 3 contention
- **WHEN** Mode 3 detects contention and dispatches sequentially
- **THEN** a `dispatch_order` event is emitted with `order: "sequential"` and `sequence` listing the winner arm first, loser arm second

#### Scenario: parallel dispatch_order for non-contention steps
- **WHEN** any mode dispatches arms in parallel (no contention or modes 0/1/2/4)
- **THEN** a `dispatch_order` event is emitted with `order: "parallel"` and `sequence` listing both arm_ids in sorted order

#### Scenario: dispatch_order for single-arm step
- **WHEN** only one arm is active at a step (solo step)
- **THEN** a `dispatch_order` event is emitted with `order: "parallel"` and `sequence` containing only that arm_id

### Requirement: reorder_applied event emitted for Mode 4
The system SHALL emit a `reorder_applied` SSE event after SmartReorderScheduler completes step reordering in Mode 4. The event SHALL include `original_step_count`, `reordered_step_count`, and `min_j4_gap`.

#### Scenario: reorder_applied emitted in Mode 4
- **WHEN** Mode 4 (Smart Reorder) completes step reordering before execution begins
- **THEN** a `reorder_applied` event is emitted with the correct step counts and the minimum j4 gap achieved by the reorder

#### Scenario: reorder_applied not emitted in other modes
- **WHEN** Modes 0, 1, 2, or 3 run
- **THEN** no `reorder_applied` event is emitted

### Requirement: step_start event includes camera position
The existing `step_start` SSE event SHALL include `cam_x`, `cam_y`, and `cam_z` fields from the scenario step, in addition to the existing `arm_id`, `step_id`, `target_j3`, `target_j4`, `target_j5`, and `mode` fields.

#### Scenario: step_start contains cam coordinates
- **WHEN** a `step_start` event is emitted for any arm at any step
- **THEN** the event includes `cam_x`, `cam_y`, and `cam_z` fields matching the scenario step's camera-frame coordinates
