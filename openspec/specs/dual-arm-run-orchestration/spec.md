## ADDED Requirements

### Requirement: Synchronize Dual-Arm Replay Steps

The system SHALL synchronize paired steps through a central controller and keep solo-tail execution
safe by parking the finished arm at a safe home pose.

#### Scenario: Paired step advances only after both active arms are terminal
- **GIVEN** both arms are active for a step
- **WHEN** one arm finishes before the other
- **THEN** the controller waits until both active arms are terminal before advancing

### Requirement: Replay Shared Scenario JSON

Both arm nodes SHALL read the same scenario JSON once at run start and process only their own arm
data.

#### Scenario: Shared scenario file loaded in both nodes
- **WHEN** the operator starts a run
- **THEN** both arm nodes load the same scenario JSON
