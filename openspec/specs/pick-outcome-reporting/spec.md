# Spec: Pick Outcome Reporting

## Purpose

Defines how the system records and exposes the outcome of each arm-step pick during a scenario run, including explicit terminal status and summary counts.

## Requirements

### Requirement: Record explicit per-arm terminal outcome

The system SHALL record an explicit terminal outcome for every arm-step in a scenario run.

#### Scenario: Successful arm-step is marked completed
- **WHEN** an allowed arm-step's full timed animation runs to completion and cotton is removed
- **THEN** the step report stores `terminal_status = "completed"`
- **AND** the step report stores `pick_completed = true`
- **AND** the step report stores `executed_in_gazebo = true`

#### Scenario: Blocked arm-step is marked blocked
- **WHEN** mode logic prevents pick execution for an arm-step
- **THEN** the step report stores `terminal_status = "blocked"`
- **AND** the step report stores `pick_completed = false`
- **AND** the step report stores `executed_in_gazebo = false`

#### Scenario: Skipped arm-step is marked skipped
- **WHEN** overlap wait times out for an arm-step
- **THEN** the step report stores `terminal_status = "skipped"`
- **AND** the step report stores `pick_completed = false`
- **AND** the step report stores `executed_in_gazebo = false`

#### Scenario: Failed animation does not produce a completed pick
- **WHEN** the Gazebo animation or spawn fails for an arm-step
- **THEN** `pick_completed` remains `false`
- **AND** `executed_in_gazebo` remains `false`

### Requirement: Summarize completed picks in run outputs

The system SHALL expose completed-pick counts in run-level outputs.

#### Scenario: JSON summary includes completed-pick totals
- **WHEN** a scenario run completes
- **THEN** the JSON summary includes total completed picks across all arm-steps
- **AND** a completed pick is only counted when the full animation confirmed completion

#### Scenario: Markdown summary includes completed-pick totals
- **WHEN** a scenario run completes
- **THEN** the Markdown summary includes completed-pick totals alongside blocked and skipped information
