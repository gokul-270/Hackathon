# Spec: Gazebo Scenario Execution (delta)

## Purpose

Changes to cotton spawn timing: all cotton is spawned upfront at run start rather than
per-step. Blocked and skipped steps no longer suppress cotton visibility.

## MODIFIED Requirements

### Requirement: Execute allowed scenario steps in Gazebo

The system SHALL publish real Gazebo arm motion for each scenario-run arm-step that the active mode allows to execute. All cotton models SHALL be spawned upfront at run start (before the execution loop). Blocked and skipped steps leave their cotton model visible (no removal).

#### Scenario: All cotton spawned before execution begins

- **GIVEN** a scenario with N steps
- **WHEN** the operator starts a run
- **THEN** spawn_fn is called N times before any step executor is invoked
- **AND** each executor receives the pre-spawned cotton model name

#### Scenario: Allowed arm-step uses pre-spawned cotton and runs timed animation
- **WHEN** `/api/run/start` executes a step whose arm outcome is allowed by the active mode
- **THEN** the system uses the pre-spawned cotton model at the step's camera position in Gazebo
- **AND** the system publishes the arm's motion sequence to Gazebo using the same timed animation as the manual pick (j4 → j3 → j5 → retract → home, ~5.5 s total)
- **AND** the system removes the cotton model after the animation completes

#### Scenario: Blocked arm-step leaves cotton visible and does not publish pick motion
- **WHEN** the active mode blocks an arm-step
- **THEN** the system records a blocked terminal outcome for that arm-step
- **AND** it does NOT remove the pre-spawned cotton for that arm-step
- **AND** it does not publish the pick-motion sequence for that blocked arm-step

#### Scenario: Skipped arm-step leaves cotton visible and does not publish pick motion
- **WHEN** overlap wait times out for an arm-step
- **THEN** the system records a skipped terminal outcome for that arm-step
- **AND** it does NOT remove the pre-spawned cotton for that arm-step
- **AND** it does not publish the pick-motion sequence for that skipped arm-step
