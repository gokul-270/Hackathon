## Why

The simulation stack can compute cotton-picking motions and drive a merged arm simulation, but it
does not yet provide a repeatable distributed dual-arm experiment baseline. The first release needs
to prove that the same scenario can be replayed end-to-end with separate arm nodes, synchronized step
control, baseline avoidance logic, and machine-readable outputs before more advanced strategies are
added.

## What Changes

- Add a distributed dual-arm replay baseline where both arm nodes read the same scenario JSON and
  compute candidate joints from camera/cotton points.
- Add a central run controller that synchronizes paired steps, handles solo-tail execution, and resets
  the world after the scenario completes.
- Add peer-state exchange so each arm publishes current and candidate joints with step-aware status.
- Add the initial mode layer with `unrestricted` and `baseline_j5_block_skip`.
- Add a runtime truth monitor MVP and JSON reporting for end-to-end baseline comparison.

## Capabilities

### New Capabilities
- `dual-arm-run-orchestration`: central controller, step synchronization, and run lifecycle management
- `peer-state-exchange`: arm-to-arm publication of current and candidate joints with step-aware status
- `collision-truth-monitoring`: independent near-collision and collision measurement during execution
- `collision-comparison-reporting`: per-step and per-run JSON outputs for baseline comparison

### Modified Capabilities
- `cam-coord-sequence-player`: extend the existing camera-coordinate flow from single-sequence control
  to dual-arm scenario replay and step-synchronized execution

## Impact

- Affects `pragati_ros2/src/vehicle_arm_sim/` runtime control and hackathon experiment flow.
- Introduces the first shared contracts for scenario JSON, peer-state packets, and baseline reporting.
- Creates the minimum stable platform that later releases build on.

## Non-goals

- Geometry-aware blocking
- Overlap-zone wait arbitration
- Markdown comparison reporting
