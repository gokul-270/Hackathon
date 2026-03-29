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

The UI SHALL provide a direct start action that triggers the backend to run the selected scenario as a motion-backed Gazebo execution for the selected mode.

#### Scenario: Start button triggers backend run
- **WHEN** the operator presses Start Run
- **THEN** the backend starts the replay controller for the selected mode and scenario
- **AND** the controller drives Gazebo arm motion for allowed arm-steps during the run

### Requirement: Access Final Reports From The UI

The UI SHALL expose the JSON and Markdown outputs of a completed run, including explicit arm completion outcomes.

#### Scenario: Reports available after run completion
- **WHEN** a replay run completes
- **THEN** the UI allows the operator to access both JSON and Markdown reports
- **AND** those reports include explicit completion-aware run results
