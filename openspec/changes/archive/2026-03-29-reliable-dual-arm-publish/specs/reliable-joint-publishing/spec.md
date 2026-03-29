## REMOVED Requirements

### Requirement: Retry-based joint publishing
**Reason**: `_publish_joint_gz` (the retry-based function this requirement described) was removed
in a prior refactor. The run path now uses `_gz_publish` with triple-publish for reliability.
**Migration**: Use triple-publish in `_gz_publish` (see ADDED Requirements below).

### Requirement: Observable publishing failures
**Reason**: Removed with `_publish_joint_gz`. Triple-publish is fire-and-succeed; individual
subprocess failures are not surfaced because Gazebo does not expose per-publish ACKs.
**Migration**: No replacement. If all three publishes fail, the joint simply does not move —
observable from the simulation view.

### Requirement: Per-arm joint publishing mutex
**Reason**: Removed with `_publish_joint_gz`. The run path uses a single worker thread per arm
step (via `ThreadPoolExecutor`), eliminating concurrent same-arm publish races.
**Migration**: No replacement needed. Thread isolation is enforced by the execution model.

## ADDED Requirements

### Requirement: Triple-publish for run-path joint commands

The `_gz_publish` function used in `/api/run/start` SHALL publish each joint command exactly
3 times via `subprocess.run()` (blocking), with a 150 ms sleep between successive publishes.
This matches the frontend triple-publish reliability pattern.

#### Scenario: Each joint command is published three times

- **WHEN** `_gz_publish(topic, value)` is called
- **THEN** `subprocess.run(["gz", "topic", ...])` is called 3 times with the same topic and value
- **AND** each call completes (blocking) before the next sleep begins

#### Scenario: 150 ms gap between publishes

- **WHEN** `_gz_publish` issues the first publish
- **THEN** 150 ms elapses before the second publish
- **AND** 150 ms elapses before the third publish

#### Scenario: Blocking subprocess prevents orphaned processes

- **WHEN** `_gz_publish` is invoked
- **THEN** each `subprocess.run()` call waits for the process to exit before proceeding
- **AND** no zombie `gz topic` processes remain after the function returns
