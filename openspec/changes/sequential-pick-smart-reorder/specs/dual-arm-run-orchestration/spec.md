## MODIFIED Requirements

### Requirement: Synchronize Dual-Arm Replay Steps

The system SHALL synchronize paired steps through a central controller and keep solo-tail execution
safe by parking the finished arm at a safe home pose. For paired steps in modes 0, 1, 2, and 4 the controller SHALL
execute both arms' `executor.execute()` calls concurrently using a `ThreadPoolExecutor(max_workers=2)`.
For mode 3 (sequential_pick) at contention steps (j4 gap < 0.10 m), the controller SHALL use two-phase dispatch: execute the winner arm first, wait for completion, then execute the loser arm.
Non-contention steps in mode 3 SHALL use parallel dispatch as in other modes.
Mode logic, peer-state exchange, and truth-monitor observation SHALL remain sequential (executed
before the animation phase). Step report results SHALL be collected in ascending arm-id
order to ensure deterministic ordering regardless of dispatch order.

#### Scenario: Paired step advances only after both active arms are terminal

- **GIVEN** both arms are active for a step
- **WHEN** one arm finishes before the other
- **THEN** the controller waits until both active arms are terminal before advancing

#### Scenario: Paired step runs both animations concurrently in non-contention modes

- **GIVEN** both arms are active for a step
- **WHEN** the controller executes the step in mode 0, 1, 2, or 4
- **THEN** both `executor.execute()` calls are submitted to a ThreadPoolExecutor simultaneously

#### Scenario: Mode logic runs before animation dispatch

- **GIVEN** a paired step with both arms active
- **WHEN** the step executes
- **THEN** candidate joint computation, peer-state exchange, and baseline mode logic complete sequentially
- **AND** only then does animation dispatch begin

#### Scenario: Sequential pick contention step dispatches winner then loser

- **GIVEN** both arms are active for a step in mode 3 (sequential_pick)
- **AND** the j4 gap between the arms is less than 0.10 m
- **WHEN** the controller executes the step
- **THEN** the winner arm's executor.execute() is called first and completes
- **AND** only after the winner completes does the loser arm's executor.execute() begin

#### Scenario: Sequential pick non-contention step uses parallel dispatch

- **GIVEN** both arms are active for a step in mode 3 (sequential_pick)
- **AND** the j4 gap between the arms is 0.10 m or greater
- **WHEN** the controller executes the step
- **THEN** both executor.execute() calls run in parallel via ThreadPoolExecutor

#### Scenario: Mode 4 reorders steps before execution loop

- **GIVEN** the operator selects mode 4 (smart_reorder)
- **WHEN** the RunController begins execution
- **THEN** the SmartReorderScheduler reorders the step map before the first step executes
- **AND** all steps use parallel dispatch since reordering minimizes contention
