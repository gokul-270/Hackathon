## MODIFIED Requirements

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
