## MODIFIED Requirements

### Requirement: Execute allowed scenario steps in Gazebo

The system SHALL publish real Gazebo arm motion for each scenario-run arm-step that the active mode allows to execute.

#### Scenario: All allowed cotton bowls are spawned before any arm motion begins
- **WHEN** `/api/run/start` is called
- **THEN** the system spawns cotton models for ALL allowed arm-steps before publishing any arm motion
- **AND** each cotton model is placed at the step's camera position in Gazebo
- **AND** arm1 cotton bowls SHALL use white color (RGBA 1 1 1 1)
- **AND** arm2 cotton bowls SHALL use yellow color (RGBA 1 1 0 1)

#### Scenario: Cotton bowl is removed only after its own pick animation completes
- **WHEN** the pick animation for a specific arm-step completes
- **THEN** the system removes only the cotton model for that arm-step
- **AND** cotton bowls for other arm-steps that have not yet been picked remain visible

#### Scenario: Blocked arm-step does not spawn cotton or publish pick motion
- **WHEN** the active mode blocks an arm-step
- **THEN** the system records a blocked terminal outcome for that arm-step
- **AND** it does not spawn cotton for that arm-step during the pre-spawn phase
- **AND** it does not publish the pick-motion sequence for that blocked arm-step

#### Scenario: Skipped arm-step does not spawn cotton or publish pick motion
- **WHEN** overlap wait times out for an arm-step
- **THEN** the system records a skipped terminal outcome for that arm-step
- **AND** it does not spawn cotton for that arm-step during the pre-spawn phase
- **AND** it does not publish the pick-motion sequence for that skipped arm-step

## ADDED Requirements

### Requirement: Cotton bowl color identifies the picking arm

The system SHALL spawn cotton bowls with a color that identifies which arm will pick them.

#### Scenario: arm1 cotton bowl is white
- **WHEN** an allowed arm-step is assigned to `arm1`
- **THEN** the spawned cotton bowl SHALL have RGBA color `1 1 1 1` (white)

#### Scenario: arm2 cotton bowl is yellow
- **WHEN** an allowed arm-step is assigned to `arm2`
- **THEN** the spawned cotton bowl SHALL have RGBA color `1 1 0 1` (yellow)
