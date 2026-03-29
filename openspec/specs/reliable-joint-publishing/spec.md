# Spec: Reliable Joint Publishing

## Purpose

Defines how the system reliably publishes joint commands to Gazebo during scenario execution, ensuring each command reaches the simulator without leaving orphaned processes.

## Requirements

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
