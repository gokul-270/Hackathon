# Spec: Gazebo Scenario Execution

## Purpose

Defines how the system drives real Gazebo arm motion during a scenario run, including which steps execute motion and how step advancement is gated on terminal outcomes.

## Requirements

### Requirement: Execute allowed scenario steps in Gazebo

The system SHALL publish real Gazebo arm motion for each scenario-run arm-step that the active mode allows to execute. All cotton models SHALL be spawned upfront at run start (before the execution loop). Blocked and skipped steps leave their cotton model visible (no removal). Each joint command SHALL be published 3 times with 150 ms gaps, making the timed animation approximately 7.3 s total per arm-step (up from 5.5 s before triple-publish). An arm-step MAY also terminate early with `estop_aborted` if the server-side E-STOP flag is set mid-animation.

#### Scenario: All cotton spawned before execution begins

- **GIVEN** a scenario with N steps
- **WHEN** the operator starts a run
- **THEN** spawn_fn is called N times before any step executor is invoked
- **AND** each executor receives the pre-spawned cotton model name

#### Scenario: Allowed arm-step uses pre-spawned cotton and runs timed animation
- **WHEN** `/api/run/start` executes a step whose arm outcome is allowed by the active mode
- **THEN** the system uses the pre-spawned cotton model at the step's camera position in Gazebo
- **AND** the system publishes the arm's motion sequence to Gazebo using the timed animation (j4 → j3 → j5 → retract → home, ~7.3 s total with triple-publish)
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

#### Scenario: E-STOP mid-animation produces estop_aborted outcome

- **WHEN** the server-side E-STOP flag is set while an arm-step animation is in progress
- **THEN** the executor detects the flag at the next phase boundary
- **AND** publishes zeros to all three joints for that arm
- **AND** returns `terminal_status = "estop_aborted"` with `pick_completed = False`
- **AND** does NOT remove the pre-spawned cotton (consistent with blocked/skipped behaviour)

### Requirement: Controller advances only after active arm outcomes are terminal

The system SHALL wait for each active arm in the current step to reach a terminal outcome before advancing to the next step. For paired steps, both arms' executor calls SHALL run concurrently (in parallel threads), and the controller SHALL collect both results before advancing.

#### Scenario: Paired step runs both arms in parallel
- **WHEN** both arms are active for the same `step_id`
- **THEN** the system starts both arm animations at the same time (parallel threads)
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
