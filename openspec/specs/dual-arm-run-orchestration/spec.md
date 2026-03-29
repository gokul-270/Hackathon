# Spec: Dual-Arm Run Orchestration

## Purpose

Defines how the run controller orchestrates two robot arms through a shared collision avoidance scenario, including step synchronization, solo-tail handling, arm pair configuration, and upfront cotton spawning.

## Requirements

### Requirement: Synchronize Dual-Arm Replay Steps

The system SHALL synchronize paired steps through a central controller and keep solo-tail execution
safe by parking the finished arm at a safe home pose. For paired steps, the controller SHALL
execute both arms' `executor.execute()` calls concurrently using a `ThreadPoolExecutor(max_workers=2)`.
Mode logic, peer-state exchange, and truth-monitor observation SHALL remain sequential (executed
before the parallel animation phase). Step report results SHALL be collected in ascending arm-id
order to ensure deterministic ordering regardless of thread completion order.

#### Scenario: Paired step advances only after both active arms are terminal
- **GIVEN** both arms are active for a step
- **WHEN** one arm finishes before the other
- **THEN** the controller waits until both active arms are terminal before advancing

#### Scenario: Paired step runs both animations concurrently

- **GIVEN** both arms are active for a step
- **WHEN** the controller executes the step
- **THEN** both `executor.execute()` calls are submitted to a ThreadPoolExecutor simultaneously
- **AND** total elapsed time for the step is approximately the time for ONE arm animation (~7.3 s), not two in sequence

#### Scenario: Mode logic runs before parallel animation

- **GIVEN** a paired step with both arms active
- **WHEN** the step executes
- **THEN** candidate joint computation, peer-state exchange, and baseline mode logic complete sequentially
- **AND** only then do both arm animations start in parallel

### Requirement: Deterministic step report ordering

The controller SHALL collect step report entries in sorted ascending arm-id order
(e.g., arm1 before arm2, arm2 before arm3) regardless of which thread finishes first.
This ensures that run reports are reproducible and comparable across runs.

#### Scenario: Step reports are in arm-id order for paired steps

- **WHEN** a paired step completes with arm1 and arm2 both active
- **THEN** the arm1 step report is appended to the reporter before the arm2 step report
- **AND** this order holds even if arm2's executor.execute() returns before arm1's

#### Scenario: Step reports order is unaffected by thread scheduling

- **WHEN** two consecutive runs execute the same paired scenario
- **THEN** the step_reports list has the same arm_id sequence in both run summaries

### Requirement: Replay Shared Scenario JSON

Both arm nodes SHALL read the same scenario JSON once at run start and process only their own arm
data.

#### Scenario: Shared scenario file loaded in both nodes
- **WHEN** the operator starts a run
- **THEN** both arm nodes load the same scenario JSON

### Requirement: Configurable arm pair replaces hardcoded arm1+arm2

The RunController SHALL accept an `arm_pair` parameter specifying which two arms participate
in a run. The first arm is the primary (replaces "arm1" scenario slots) and the second is the
secondary (replaces "arm2" scenario slots). The default SHALL be ("arm1", "arm2").

#### Scenario: Default arm pair produces unchanged behaviour

- **GIVEN** RunController instantiated with no arm_pair argument
- **WHEN** a scenario with arm1 and arm2 steps is run
- **THEN** arm1 steps execute on arm1 and arm2 steps execute on arm2

#### Scenario: arm_pair=("arm1","arm3") remaps arm2 slots to arm3

- **GIVEN** RunController instantiated with arm_pair=("arm1","arm3")
- **WHEN** a scenario with arm_id="arm2" steps is loaded
- **THEN** those steps are executed by arm3

#### Scenario: arm_pair=("arm2","arm3") remaps arm1 to arm2 and arm2 to arm3

- **GIVEN** RunController instantiated with arm_pair=("arm2","arm3")
- **WHEN** a scenario with arm_id="arm1" and arm_id="arm2" steps is loaded
- **THEN** arm1 steps are executed by arm2 and arm2 steps are executed by arm3

### Requirement: RunController emits SSE events during execution

The RunController SHALL emit enriched SSE events during step execution, including `cotton_reached`
after successful picks, `contention_detected` for Mode 3 contention steps, `dispatch_order` at
every dispatch decision, and `reorder_applied` after Mode 4 reordering. All events flow through
the existing `RunEventBus` via `self._emit()`.

#### Scenario: enriched events emitted during dual-arm run

- **WHEN** a dual-arm run executes with any collision avoidance mode (0–4)
- **THEN** the RunController emits `step_start` (with cam position), `dispatch_order`,
  `cotton_reached` (on completed picks), and `step_complete` events for each step,
  plus mode-specific events (`contention_detected` for Mode 3, `reorder_applied` for Mode 4)

### Requirement: Dual-arm run applies phi compensation

The dual-arm run path SHALL apply phi compensation to J3 values computed by
`ArmRuntime.compute_candidate_joints()`. The `RunStartRequest` model SHALL
include an `enable_phi_compensation: bool = True` field. When enabled,
`phi_compensation(j3, j5)` SHALL be called on the candidate joints before
they are passed to mode logic and execution.

#### Scenario: Dual-arm run uses compensated J3 by default

- **GIVEN** a dual-arm run is started via `POST /api/run/start` without
  specifying `enable_phi_compensation`
- **WHEN** `ArmRuntime.compute_candidate_joints()` returns raw joints
- **THEN** `phi_compensation(j3, j5)` is applied to the j3 value
- **AND** the compensated j3 is used for mode logic and published to `/joint3_cmd`

#### Scenario: Compensation disabled via request parameter

- **GIVEN** a dual-arm run is started with `enable_phi_compensation: false`
- **WHEN** joints are computed for each step
- **THEN** the raw j3 from `polar_decompose()` is used without compensation

#### Scenario: UI passes phi compensation state to run endpoint

- **GIVEN** the user has the "Phi Compensation" checkbox checked in the UI
- **WHEN** the user starts a dual-arm run
- **THEN** the `POST /api/run/start` request body includes
  `enable_phi_compensation: true`

#### Scenario: Phi compensation checkbox default matches endpoint default

- **GIVEN** the testing UI is loaded fresh
- **WHEN** the user inspects the "Phi Compensation" checkbox
- **THEN** it is checked by default (matching the endpoint default of `true`)
