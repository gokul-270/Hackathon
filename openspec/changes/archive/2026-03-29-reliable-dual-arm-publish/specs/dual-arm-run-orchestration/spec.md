## MODIFIED Requirements

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

## ADDED Requirements

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
