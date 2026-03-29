## ADDED Requirements

### Requirement: Cotton removed for unreachable and skipped steps
The system SHALL remove any cotton ball that was spawned for a step even when
that step is subsequently determined to be unreachable or skipped. If no cotton
was spawned (e.g. the step was skipped before spawn), no removal attempt is made.

#### Scenario: Cotton spawned before reachability failure is removed
- **WHEN** a cotton ball has been spawned for a step
- **AND** the step is later determined unreachable during execution
- **THEN** `_gz_remove_model()` is called for that cotton ball's model name

#### Scenario: No removal attempt when cotton was never spawned
- **WHEN** a step is skipped before cotton spawn
- **THEN** no `_gz_remove_model()` call is made for that step
