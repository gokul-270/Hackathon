# Spec: Faster Pick Animation

## Purpose

Defines the reduced timing constants for pick animation so each arm-step completes in approximately 2.75 s instead of ~5.5 s, and the reduced publish retry delay.

## Requirements

### Requirement: Pick animation completes in approximately 2.75 s per arm-step

Animation sleep constants SHALL be halved from their previous values so that each
pick cycle (j4 → j3 → j5 extend → j5 retract → j3 home → j4 home) completes in
approximately 2.75 s under nominal conditions, down from ~5.5 s.

New timing constants:
- `_T_J4 = 0.4 s` (was 0.8 s)
- `_T_J3 = 0.4 s` (was 0.8 s)
- `_T_J5_EXTEND = 0.7 s` (was 1.4 s)
- `_T_J5_RETRACT = 0.4 s` (was 0.8 s)
- `_T_J3_HOME = 0.4 s` (was 0.8 s)
- `_T_J4_HOME = 0.45 s` (was 0.9 s)

#### Scenario: single arm-step completes in under 3 s
- **WHEN** an arm executes one allowed step with the new timing constants and a no-op sleep_fn replaced by time.sleep
- **THEN** total elapsed wall-clock time is approximately 2.75 s (sum of all sleep constants)

#### Scenario: reduced timing does not change step outcome
- **WHEN** an arm executes an allowed step with the new constants
- **THEN** terminal_status is "completed" and pick_completed is True
- **AND** executed_in_gazebo is True

### Requirement: Joint publish retry delay reduced to 50 ms

The inter-attempt sleep between triple-publish retries SHALL be reduced from 150 ms
to 50 ms, saving 0.2 s of overhead per joint command (new: 2 gaps × 50 ms = 0.1 s
per command; was: 2 gaps × 150 ms = 0.3 s).

#### Scenario: publish retry uses 50 ms gap
- **WHEN** `_gz_publish` sends a joint command with 3 attempts
- **THEN** it sleeps 50 ms between attempt 1→2 and between attempt 2→3
