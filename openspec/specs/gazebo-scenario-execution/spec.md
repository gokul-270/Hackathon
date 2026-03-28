# Spec: Gazebo Scenario Execution

## Purpose

Defines how the system drives real Gazebo arm motion during a scenario run, including which steps execute motion and how step advancement is gated on terminal outcomes.

## Requirements

### Requirement: Execute allowed scenario steps in Gazebo

The system SHALL publish real Gazebo arm motion for each scenario-run arm-step that the active mode allows to execute.

#### Scenario: Allowed arm-step spawns cotton and runs timed animation
- **WHEN** `/api/run/start` executes a step whose arm outcome is allowed by the active mode
- **THEN** the system spawns a cotton model at the step's camera position in Gazebo
- **AND** the system publishes the arm's motion sequence to Gazebo using the same timed animation as the manual pick (j4 → j3 → j5 → retract → home, ~5.5 s total)
- **AND** the system removes the cotton model after the animation completes

#### Scenario: Blocked arm-step does not spawn cotton or publish pick motion
- **WHEN** the active mode blocks an arm-step
- **THEN** the system records a blocked terminal outcome for that arm-step
- **AND** it does not spawn cotton for that arm-step
- **AND** it does not publish the pick-motion sequence for that blocked arm-step

#### Scenario: Skipped arm-step does not spawn cotton or publish pick motion
- **WHEN** overlap wait times out for an arm-step
- **THEN** the system records a skipped terminal outcome for that arm-step
- **AND** it does not spawn cotton for that arm-step
- **AND** it does not publish the pick-motion sequence for that skipped arm-step

### Requirement: Controller advances only after active arm outcomes are terminal

The system SHALL wait for each active arm in the current step to reach a terminal outcome before advancing to the next step.

#### Scenario: Paired step runs both arms in parallel
- **WHEN** both arms are active for the same `step_id`
- **THEN** the system runs both arm animations in parallel
- **AND** the controller waits until both arm outcomes are terminal before advancing

#### Scenario: Solo-tail step advances after the single active arm completes
- **WHEN** only one arm is active for the current `step_id`
- **THEN** the controller advances after that arm reaches a terminal outcome

### Requirement: Executor confirms physical completion before marking pick as complete

The system SHALL only mark a pick as completed after the full timed animation has run and the cotton model has been removed.

#### Scenario: pick_completed reflects confirmed animation, not attempted publish
- **WHEN** the timed animation for an arm-step runs to completion and cotton is removed
- **THEN** the executor returns `pick_completed = True` and `executed_in_gazebo = True`
- **AND** if the publish or spawn fails, `pick_completed` remains `False`
