# Spec: Smart Reorder Scheduler

## Purpose

Defines how the smart reorder scheduler rearranges cotton picking order before execution to maximize the minimum j4 gap across paired steps, reducing collision risk without runtime intervention.

## Requirements

### Requirement: Reorder Cotton Targets To Maximize Minimum J4 Gap

The smart reorder scheduler SHALL rearrange the cotton picking order for both arms before execution starts to maximize the minimum absolute j4 gap across all paired steps.

#### Scenario: Scheduler produces reordered step map

- **GIVEN** a scenario with N paired steps for arm1 and N paired steps for arm2
- **WHEN** the scheduler reorders the steps
- **THEN** it returns a new step map where step_ids are reassigned to the optimal pairing
- **AND** every original step is preserved (no steps lost or duplicated)

#### Scenario: Reordering improves minimum j4 gap

- **GIVEN** a scenario where the original step order has a minimum j4 gap of G1
- **WHEN** the scheduler reorders the steps
- **THEN** the resulting minimum j4 gap G2 is greater than or equal to G1

#### Scenario: Reordering handles already-optimal order

- **GIVEN** a scenario where the original step order already maximizes the minimum j4 gap
- **WHEN** the scheduler reorders the steps
- **THEN** the step order is unchanged or equivalently optimal

### Requirement: Compute J4 Values From FK For Each Cotton Target

The scheduler SHALL compute the j4 joint value for each cotton target using the forward kinematics chain, without executing any arm motion.

#### Scenario: J4 computed from cam_z using FK formula

- **GIVEN** a cotton target with cam_z value C
- **WHEN** the scheduler computes the j4 value
- **THEN** the result equals 0.1005 minus C (the FK linear formula at j4_pos=0.0)

### Requirement: Handle Unequal Step Counts Between Arms

The scheduler SHALL handle scenarios where one arm has more steps than the other by only reordering the paired portion and leaving solo-tail steps unchanged.

#### Scenario: Solo tail steps preserved after reorder

- **GIVEN** arm1 has 5 steps and arm2 has 3 steps
- **WHEN** the scheduler reorders the steps
- **THEN** the first 3 step_ids are reordered for optimal pairing
- **AND** arm1's remaining 2 solo steps retain their relative order after the paired steps

### Requirement: Fall Back To Greedy For Large Step Counts

The scheduler SHALL use brute-force permutation search for step counts of 8 or fewer per arm and SHALL fall back to a greedy assignment algorithm for step counts greater than 8.

#### Scenario: Brute-force used for small scenario

- **GIVEN** a scenario with 5 steps per arm
- **WHEN** the scheduler runs
- **THEN** it evaluates all permutations to find the globally optimal pairing

#### Scenario: Greedy fallback used for large scenario

- **GIVEN** a scenario with 10 steps per arm
- **WHEN** the scheduler runs
- **THEN** it uses greedy assignment without evaluating all permutations
- **AND** the result still improves or maintains the minimum j4 gap

### Requirement: Integrate With RunController At Run Start

The scheduler SHALL be invoked by RunController before the step execution loop when mode is SMART_REORDER (4). The reordered step map SHALL replace the original step map for execution.

#### Scenario: Mode 4 triggers reorder before execution

- **GIVEN** the operator selects mode 4 (smart_reorder)
- **WHEN** the RunController begins a run
- **THEN** the scheduler reorders the step map before any step is executed
- **AND** the rest of the run proceeds with the reordered step map using parallel dispatch
