## MODIFIED Requirements

### Requirement: Start Replay From The UI

The UI SHALL provide a direct start action that triggers the backend to run the selected scenario as a motion-backed Gazebo execution for the selected mode. The mode dropdown SHALL offer five modes (0-4). Mode 3 SHALL be labeled "Sequential Pick" and mode 4 SHALL be labeled "Smart Reorder".

#### Scenario: Start button triggers backend run

- **WHEN** the operator presses Start Run
- **THEN** the backend starts the replay controller for the selected mode and scenario
- **AND** the controller drives Gazebo arm motion for allowed arm-steps during the run

#### Scenario: Mode dropdown offers five modes

- **WHEN** the operator views the mode dropdown
- **THEN** it contains options for mode 0 (Unrestricted), mode 1 (Baseline J5 Block/Skip), mode 2 (Geometry Block), mode 3 (Sequential Pick), and mode 4 (Smart Reorder)

#### Scenario: Mode 3 labeled Sequential Pick

- **WHEN** the operator views the mode dropdown
- **THEN** the option with value 3 reads "3 — Sequential Pick"

#### Scenario: Mode 4 labeled Smart Reorder

- **WHEN** the operator views the mode dropdown
- **THEN** the option with value 4 reads "4 — Smart Reorder"

## ADDED Requirements

### Requirement: Backend Accepts Mode 4 In Run Start Request

The backend SHALL accept mode values 0 through 4 in POST /api/run/start. Mode values outside this range SHALL return HTTP 422 with an error message indicating the valid range is 0-4.

#### Scenario: Mode 4 accepted by backend

- **WHEN** the operator sends POST /api/run/start with mode 4
- **THEN** the backend returns HTTP 200 and executes the run with smart_reorder mode

#### Scenario: Invalid mode rejected with updated error

- **WHEN** the operator sends POST /api/run/start with mode 99
- **THEN** the backend returns HTTP 422 with detail containing "must be 0-4"
