## ADDED Requirements

### Requirement: Record explicit per-arm terminal outcome

The system SHALL record an explicit terminal outcome for every arm-step in a scenario run.

#### Scenario: Successful arm-step is marked completed
- **WHEN** an allowed arm-step finishes its motion-backed execution
- **THEN** the step report stores `terminal_status = "completed"`
- **AND** the step report stores `pick_completed = true`

#### Scenario: Blocked arm-step is marked blocked
- **WHEN** mode logic prevents pick execution for an arm-step
- **THEN** the step report stores `terminal_status = "blocked"`
- **AND** the step report stores `pick_completed = false`

#### Scenario: Wait-timeout arm-step is marked skipped
- **WHEN** overlap wait times out for an arm-step
- **THEN** the step report stores `terminal_status = "skipped"`
- **AND** the step report stores `pick_completed = false`

### Requirement: Summarize completed picks in run outputs

The system SHALL expose completed-pick counts in run-level outputs.

#### Scenario: JSON summary includes completed-pick totals
- **WHEN** a scenario run completes
- **THEN** the JSON summary includes total completed picks across all arm-steps

#### Scenario: Markdown summary includes completed-pick totals
- **WHEN** a scenario run completes
- **THEN** the Markdown summary includes completed-pick totals alongside blocked and skipped information
