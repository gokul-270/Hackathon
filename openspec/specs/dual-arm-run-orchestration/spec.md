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
