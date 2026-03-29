# Spec: Gazebo Scenario Execution

## Purpose

Defines how the system drives real Gazebo arm motion during a scenario run, including which steps execute motion and how step advancement is gated on terminal outcomes.

## Requirements

### Requirement: Execute allowed scenario steps in Gazebo

The system SHALL publish real Gazebo arm motion for each scenario-run arm-step that
the active mode allows to execute. All cotton models SHALL be spawned upfront at run
start using parallel concurrent calls (see parallel-cotton-spawn spec) before any
arm thread begins executing. Blocked and skipped steps leave their cotton model
visible. Each joint command SHALL be published 3 times with 50 ms gaps (reduced
from 150 ms). The timed animation totals approximately 3.35 s per arm-step
(2.75 s sleep + 6 commands x 2 gaps x 0.05 s = 0.6 s overhead). An arm-step MAY
also terminate early with `estop_aborted` if the server-side E-STOP flag is set
mid-animation.

#### Scenario: All cotton spawned concurrently before execution begins
- **GIVEN** a scenario with N steps across both arms
- **WHEN** the operator starts a run
- **THEN** all N spawn_fn calls are submitted concurrently to a thread pool
- **AND** all spawns complete before any arm thread begins executing

#### Scenario: Allowed arm-step uses pre-spawned cotton and runs timed animation
- **WHEN** `/api/run/start` executes a step whose arm outcome is allowed by the active mode
- **THEN** the system uses the pre-spawned cotton model at the step's camera position
- **AND** publishes the arm's motion sequence with the new timing (~3.35 s total)
- **AND** removes the cotton model after the animation completes

#### Scenario: Blocked arm-step leaves cotton visible and does not publish pick motion
- **WHEN** the active mode blocks an arm-step
- **THEN** the system records a blocked terminal outcome
- **AND** does NOT remove the pre-spawned cotton
- **AND** does not publish the pick-motion sequence

#### Scenario: E-STOP mid-animation produces estop_aborted outcome
- **WHEN** the E-STOP flag is set while an arm-step animation is in progress
- **THEN** the executor detects the flag at the next phase boundary
- **AND** publishes zeros to all three joints
- **AND** returns `terminal_status = "estop_aborted"` with `pick_completed = False`

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

### Requirement: Scenario files support asymmetric arm cotton counts

Scenario JSON files SHALL support asymmetric step lists where arm1 and arm2 have
different numbers of steps. The arm_id field on each step entry determines which
arm executes that step; there is no requirement for both arms to have an entry at
every step_id. A step_id that appears for only one arm is a solo step for that arm.

#### Scenario: arm1 has 3 steps, arm2 has 5 steps — all execute
- **GIVEN** a scenario where arm1 has step_ids 0,1,2 and arm2 has step_ids 0,1,2,3,4
- **WHEN** the run completes
- **THEN** arm1 executes exactly 3 picks and arm2 executes exactly 5 picks

#### Scenario: scenario mixes colliding and safe cotton positions
- **GIVEN** a scenario where some (step_id, arm_pair) combinations have j4 gap < 0.05 m and others > 0.08 m
- **WHEN** the run executes in unrestricted mode
- **THEN** all steps execute regardless of j4 distance
- **AND** the truth monitor records both near-collision and safe observations

#### Scenario: solo arm2 steps execute after arm1 is done
- **GIVEN** arm1 has finished all 3 steps and arm2 still has steps 3 and 4 remaining
- **WHEN** arm2 executes step 3
- **THEN** peer_state for arm1 is None (no recent publish) and arm2 executes solo
