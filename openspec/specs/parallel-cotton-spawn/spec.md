# Spec: Parallel Cotton Spawn

## Purpose

Defines how all cotton models for a run are spawned concurrently before any arm execution begins, using a thread pool for parallel Gazebo service calls.

## Requirements

### Requirement: All run cottons are spawned concurrently before execution begins

The system SHALL spawn all cotton models for a run using a `ThreadPoolExecutor`,
issuing all `gz service /world/*/create` calls in parallel rather than sequentially.
All spawn calls SHALL complete before the first arm thread begins executing any step.

#### Scenario: N cottons spawned with concurrent calls
- **GIVEN** a scenario with 8 cotton positions (arm1: 3, arm2: 5)
- **WHEN** the run starts
- **THEN** all 8 spawn_fn calls are submitted to a thread pool simultaneously
- **AND** the first arm animation does not start until all 8 spawns have returned

#### Scenario: spawn failures do not block other spawns
- **WHEN** one spawn_fn call raises an exception
- **THEN** the remaining spawn calls still complete
- **AND** the failed cotton model name is recorded as an empty string in cotton_models

### Requirement: Cotton model names are recorded per (step_index, arm_id) key

After parallel spawn, the system SHALL store each returned model name in a dict
keyed by `(step_index, arm_id)` so each arm thread can look up its pre-spawned
cotton model when executing that step.

#### Scenario: arm thread looks up its pre-spawned cotton
- **WHEN** arm1 executes step index 1
- **THEN** it retrieves the model name stored at key (1, arm1) from cotton_models
- **AND** passes it to executor.execute() as cotton_model
