# Spec: Gazebo Scenario Execution

## Purpose

Defines how the system drives real Gazebo arm motion during a scenario run, including which steps execute motion and how step advancement is gated on terminal outcomes.

## Requirements

### Requirement: Execute allowed scenario steps in Gazebo

The system SHALL publish real Gazebo arm motion for each scenario-run arm-step that the active mode allows to execute.

#### Scenario: Allowed arm-step publishes Gazebo motion during run
- **WHEN** `/api/run/start` executes a step whose arm outcome is allowed by the active mode
- **THEN** the system publishes the arm's motion sequence to Gazebo from the scenario-run path

#### Scenario: Blocked arm-step does not publish pick motion
- **WHEN** the active mode blocks an arm-step
- **THEN** the system records a blocked terminal outcome for that arm-step
- **AND** it does not publish the pick-motion sequence for that blocked arm-step

### Requirement: Controller advances only after active arm outcomes are terminal

The system SHALL wait for each active arm in the current step to reach a terminal outcome before advancing to the next step.

#### Scenario: Paired step waits for both arm outcomes
- **WHEN** both arms are active for the same `step_id`
- **THEN** the controller waits until both arm outcomes are terminal before advancing

#### Scenario: Solo-tail step advances after the single active arm completes
- **WHEN** only one arm is active for the current `step_id`
- **THEN** the controller advances after that arm reaches a terminal outcome
