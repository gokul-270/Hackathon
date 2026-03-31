# Spec: UI Run Flow

## Purpose

Defines the operator-facing run workflow in the UI — loading a scenario, starting replay, and accessing post-run reports.
## Requirements
### Requirement: Load Scenario JSON From The UI

The UI SHALL allow the operator to choose or load a scenario JSON for a run.

#### Scenario: Operator selects scenario before start
- **WHEN** the operator prepares a run
- **THEN** the UI provides a way to choose or load the scenario JSON used for replay

### Requirement: Start Replay From The UI

The UI SHALL provide a direct start action that triggers the backend to run the selected
scenario as a motion-backed Gazebo execution for the selected mode. The mode dropdown SHALL
offer five modes (0-4). Mode 3 SHALL be labeled "Sequential Pick" and mode 4 SHALL be
labeled "Smart Reorder". **A second or subsequent Start action SHALL produce a fully
functional SSE event stream and live log updates identical to the first run.**

#### Scenario: Start button triggers backend run

- **WHEN** the operator presses Start Run
- **THEN** the backend starts the replay controller for the selected mode and scenario
- **AND** the controller drives Gazebo arm motion for allowed arm-steps during the run

#### Scenario: Mode dropdown offers five modes

- **WHEN** the operator views the mode dropdown
- **THEN** it contains options for mode 0 (Unrestricted), mode 1 (Baseline J5 Block/Skip),
  mode 2 (Geometry Block), mode 3 (Sequential Pick), and mode 4 (Smart Reorder)

#### Scenario: Mode 3 labeled Sequential Pick

- **WHEN** the operator views the mode dropdown
- **THEN** the option with value 3 reads "3 — Sequential Pick"

#### Scenario: Mode 4 labeled Smart Reorder

- **WHEN** the operator views the mode dropdown
- **THEN** the option with value 4 reads "4 — Smart Reorder"

#### Scenario: Second consecutive run is not frozen

- **WHEN** the operator completes one run and presses Start Run a second time
- **THEN** the log begins receiving events for the new run
- **AND** the Start button is not unresponsive

#### Scenario: SSE log events appear on second run

- **WHEN** a second run starts after a previous run has completed
- **THEN** step_start events appear in the UI log before the run completes

### Requirement: Access Final Reports From The UI

The UI SHALL expose the JSON and Markdown outputs of a completed run, including explicit arm completion outcomes.

#### Scenario: Reports available after run completion
- **WHEN** a replay run completes
- **THEN** the UI allows the operator to access both JSON and Markdown reports
- **AND** those reports include explicit completion-aware run results

### Requirement: Arm pair selection in run UI

The UI SHALL provide an arm pair selector in the Scenario Run panel. The selected pair
SHALL be included in the run start request sent to the backend.

#### Scenario: Arm pair dropdown present in Scenario Run panel

- **WHEN** the operator views the Scenario Run section of the UI
- **THEN** an "Arm Pair" dropdown is visible above the Mode dropdown
- **AND** the dropdown offers options: "arm1 + arm2", "arm1 + arm3", "arm2 + arm3"
- **AND** "arm1 + arm2" is selected by default

#### Scenario: Selected arm pair sent in run start request

- **WHEN** the operator selects "arm1 + arm3" from the arm pair dropdown
- **AND** presses Start Run
- **THEN** the frontend sends `arm_pair: ["arm1", "arm3"]` in the POST /api/run/start body

### Requirement: Frontend SSE handler formats all event types

The frontend SSE `onmessage` handler SHALL format and display all SSE event types including the
4 new types (`cotton_reached`, `contention_detected`, `dispatch_order`, `reorder_applied`) and
the enhanced `step_start` (with cam position). Unrecognized event types SHALL be silently ignored.

#### Scenario: cotton_reached displayed in log

- **WHEN** a `cotton_reached` SSE event is received
- **THEN** the log displays a line in the format:
  `"{arm_id} reached cotton (step:{step_id}, x:{cam_x}, y:{cam_y}, z:{cam_z})"`

#### Scenario: contention_detected displayed in log

- **WHEN** a `contention_detected` SSE event is received
- **THEN** the log displays a line in the format:
  `"Contention at step {step_id}: {winner_arm} wins, {loser_arm} waits (gap={j4_gap}m)"`

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
- **THEN** the log displays:
  `"Step {step_id} {arm_id} starting -> target (x:{cam_x}, y:{cam_y}, z:{cam_z})"`

### Requirement: Backend Accepts Mode 4 In Run Start Request

The backend SHALL accept mode values 0 through 4 in POST /api/run/start. Mode values outside this range SHALL return HTTP 422 with an error message indicating the valid range is 0-4.

#### Scenario: Mode 4 accepted by backend

- **WHEN** the operator sends POST /api/run/start with mode 4
- **THEN** the backend returns HTTP 200 and executes the run with smart_reorder mode

#### Scenario: Invalid mode rejected with updated error

- **WHEN** the operator sends POST /api/run/start with mode 99
- **THEN** the backend returns HTTP 422 with detail containing "must be 0-4"

