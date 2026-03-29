## MODIFIED Requirements

### Requirement: Execute allowed scenario steps in Gazebo

The system SHALL publish real Gazebo arm motion for each scenario-run arm-step that
the active mode allows to execute. All cotton models SHALL be spawned upfront at run
start using parallel concurrent calls (see parallel-cotton-spawn spec) before any
arm thread begins executing. Blocked and skipped steps leave their cotton model
visible. Each joint command SHALL be published 3 times with 50 ms gaps (reduced
from 150 ms). The timed animation totals approximately 3.35 s per arm-step
(2.75 s sleep + 6 commands × 2 gaps × 0.05 s = 0.6 s overhead). An arm-step MAY
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

## MODIFIED Requirements

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
