# Dual-Arm Hackathon User Stories And MoSCoW Scope

**Date:** 2026-03-28
**Status:** Planning
**Scope:** User stories, acceptance intent, and scope prioritization for the dual-arm collision-avoidance hackathon demo

## Primary User Stories

### Story 1: Select Mode Before Run

As a demo operator, I want to choose one collision-avoidance mode before starting a run so that I
can compare how each strategy behaves under the same target sequence.

### Story 2: Replay The Same Scenario Across Modes

As a demo operator, I want the same scenario JSON file to be reused for every mode so that the
comparison is fair and repeatable.

### Story 3: Execute Paired Targets Simultaneously

As a reviewer, I want paired arm targets to execute simultaneously so that the demo shows the real
collision risk in the overlap zone.

### Story 3A: Compute Joints In Separate Arm Nodes

As a reviewer, I want each arm to run in its own node and compute its own `j4`, `j3`, and `j5`
values from camera/cotton points so that the hackathon system matches the intended distributed
dual-arm architecture.

### Story 3B: Exchange Peer Arm State

As a reviewer, I want each arm node to publish its current and candidate joints to the other arm so
that collision logic can use live peer-arm state when making decisions.

### Story 4: Continue Solo Targets Safely

As a reviewer, I want the remaining arm to continue its leftover targets while the other arm returns
to a safe home pose so that uneven target counts are still handled cleanly.

### Story 5: Measure True Collision Outcome

As a reviewer, I want a runtime collision monitor that is separate from the planner so that I can
trust the reported collision and near-collision results.

### Story 6: Compare Strategies Side-By-Side

As a hackathon judge, I want structured metrics and a readable report so that I can understand why
the recommended strategy is better than both unrestricted motion and the old baseline.

## Supporting Stories

### Story 7: Remove Picked Cotton

As a demo operator, I want successfully picked cotton bowls to disappear from Gazebo so that the
scene reflects the current state of the run.

### Story 8: Reset Between Runs

As a demo operator, I want the world to reset and the `Start` button to become available when the
sequence finishes so that I can quickly rerun the same scenario under another mode.

### Story 9: Export Results

As a teammate, I want the run summary in JSON and Markdown so that I can use JSON for analysis and
Markdown for hackathon presentation updates.

## MoSCoW Prioritization

### Must Have

- dual-arm Gazebo world with opposing arms
- one active mode per run
- UI mode selection before `Start`
- mode lock after `Start`
- scenario JSON with many camera-point targets for both arms
- both arm nodes read the same scenario JSON once at run start
- simultaneous execution for paired targets
- solo-tail execution when one arm has remaining targets
- finished arm returns to safe home pose during solo-tail phase
- central step synchronization controller
- separate `arm1` and `arm2` runtime nodes
- per-arm runtime joint computation from camera/cotton points
- peer-state exchange between arms
- local collision validation before motion publish
- `unrestricted` mode
- `baseline_j5_block_skip` mode
- at least two improved switchable modes
- runtime collision truth monitor independent from planner logic
- successful picks remove cotton bowls from the world
- automatic run completion and reset when scenario file is exhausted
- JSON summary output
- Markdown comparison output

### Should Have

- per-step metrics tagging by mode name
- per-step peer-state tagging by `step_id`
- near-collision threshold in addition to hard collision threshold
- workspace utilization metric
- total run time metric
- comparison table across all four modes
- recommended deployment mode and parameter notes
- fixed wait timeout per pick
- alternating-turn overlap arbitration

### Could Have

- UI summary card showing current run status and active mode
- scenario progress display such as `step X of N`
- export button in UI
- parameter override fields for collision thresholds
- replay of the last run without reselecting the file

### Won't Have For This Hackathon

- dynamic mode switching in the middle of a run
- full mesh-on-mesh collision analysis
- distributed multi-RPi inter-arm coordination
- production-grade field deployment tooling
- automatic tuning of strategy parameters during the demo

## Acceptance Intent

The demo is successful if all four modes can be run against the same scenario JSON, the metrics make
the difference between the modes visible, and the final report clearly supports a recommended mode
for near-term field deployment.

## Open Review Items For Teammate Sync

- confirm the scenario JSON schema for both arms' camera-point target lists
- confirm how cotton spawn/update hooks connect to the current Gazebo setup
- confirm where the arm-specific point-to-joint conversion already exists
- confirm whether the UI already has a suitable mode selector or needs a small addition
