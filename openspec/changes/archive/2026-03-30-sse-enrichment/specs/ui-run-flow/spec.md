## MODIFIED Requirements

### Requirement: Frontend SSE handler formats all event types
The frontend SSE `onmessage` handler SHALL format and display all SSE event types including the 4 new types (`cotton_reached`, `contention_detected`, `dispatch_order`, `reorder_applied`) and the enhanced `step_start` (with cam position). Unrecognized event types SHALL be silently ignored.

#### Scenario: cotton_reached displayed in log
- **WHEN** a `cotton_reached` SSE event is received
- **THEN** the log displays a line in the format: `"{arm_id} reached cotton (step:{step_id}, x:{cam_x}, y:{cam_y}, z:{cam_z})"`

#### Scenario: contention_detected displayed in log
- **WHEN** a `contention_detected` SSE event is received
- **THEN** the log displays a line in the format: `"Contention at step {step_id}: {winner_arm} wins, {loser_arm} waits (gap={j4_gap}m)"`

#### Scenario: dispatch_order displayed in log
- **WHEN** a `dispatch_order` SSE event with `order: "sequential"` is received
- **THEN** the log displays: `"Step {step_id}: sequential dispatch [{arm1} → {arm2}]"`

#### Scenario: dispatch_order parallel displayed in log
- **WHEN** a `dispatch_order` SSE event with `order: "parallel"` is received
- **THEN** the log displays: `"Step {step_id}: parallel dispatch [{arm1}, {arm2}]"`

#### Scenario: reorder_applied displayed in log
- **WHEN** a `reorder_applied` SSE event is received
- **THEN** the log displays: `"Reorder applied: {step_count} steps, min j4 gap={min_j4_gap}m"`

#### Scenario: enhanced step_start displayed with position
- **WHEN** a `step_start` SSE event is received
- **THEN** the log displays: `"Step {step_id} {arm_id} starting -> target (x:{cam_x}, y:{cam_y}, z:{cam_z})"`
