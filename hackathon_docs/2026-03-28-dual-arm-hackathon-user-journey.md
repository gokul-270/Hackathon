# Dual-Arm Hackathon User Journey

**Date:** 2026-03-28
**Status:** Planning
**Scope:** End-to-end operator and system journey for the dual-arm collision-avoidance hackathon demo

## Goal

Create a repeatable dual-arm Gazebo experiment where the same camera-point scenario is replayed
across multiple collision-avoidance modes, then compared using safety and productivity metrics.

## Demo Story

The operator opens the UI, selects exactly one collision-avoidance mode, selects the full-sequence
scenario JSON, and starts the run. Both arm nodes read the same scenario file once at run start,
then each arm processes only its own camera-point targets. For every active step, each arm computes
its own candidate `j4`, `j3`, and `j5` values at runtime, publishes its current and candidate joints
to the peer arm, receives the peer arm state, and applies the selected mode locally. A central run
controller keeps both arms synchronized by step index, while a runtime truth monitor measures actual
arm-arm proximity separately from the planner logic. When the sequence finishes, the world resets,
the Start button becomes available again, and the same scenario can be replayed under the next mode
for fair comparison.

## User Journey

### Phase 0: Ready State

- Gazebo dual-arm world is available.
- `arm_left` and `arm_right` face each other across the cotton row.
- The scenario JSON exists and contains many camera-point targets for both arms.
- The UI is idle and the `Start` button is available.

### Phase 1: Configure Run

1. The operator opens the UI.
2. The operator selects one active mode for the run:
   - `unrestricted`
   - `baseline_j5_block_skip`
   - `geometry_block`
   - `overlap_zone_wait`
3. The operator selects or confirms the scenario JSON file.
4. The operator presses `Start`.
5. The system locks the selected mode for the duration of the run.

### Phase 2: Load Scenario

1. The central run controller starts the run.
2. Both arm nodes read the same scenario JSON file once.
3. The system validates:
   - file format is valid,
   - both arm target lists are readable,
   - camera-point values are inside expected workspace bounds.
4. The controller builds a synchronized run sequence.

## Sequence Rules

- If both arms have targets at the same step index, they run simultaneously.
- If one arm has remaining targets after the other finishes, the finished arm returns to a safe home
  pose and stays idle.
- The active arm continues processing its remaining solo targets.
- The controller advances to the next step only when all active arms have reached terminal state.

Example:

```text
arm1 targets = 4
arm2 targets = 7

Step 1 -> arm1[1] + arm2[1]  simultaneous
Step 2 -> arm1[2] + arm2[2]  simultaneous
Step 3 -> arm1[3] + arm2[3]  simultaneous
Step 4 -> arm1[4] + arm2[4]  simultaneous
Step 5 -> arm2[5] only       arm1 idle at safe home pose
Step 6 -> arm2[6] only       arm1 idle at safe home pose
Step 7 -> arm2[7] only       arm1 idle at safe home pose
```

### Phase 3: Execute Each Step

For each sequence step:

1. The controller activates the current paired step or solo step.
2. The cotton spawn manager spawns or updates the visible cotton bowls in Gazebo.
3. Each active arm reads its own current camera-point target from the already loaded scenario.
4. Each active arm computes candidate `j4`, `j3`, and `j5` values from its own target.
5. Each active arm publishes peer state containing:
   - `step_id`
   - `status`
   - `current_joints`
   - `candidate_joints`
6. Each active arm receives the peer arm state.
7. Each active arm runs local collision validation before publishing motion.
8. The selected mode decides whether to:
   - allow motion,
   - wait,
   - block.
9. Allowed commands are published to the respective arm joints.
10. Gazebo executes the motion.
11. The runtime truth monitor checks actual minimum arm-arm distance.
12. On successful pick without collision, the corresponding cotton bowl disappears.
13. Metrics for the step are logged.

### Phase 4: Complete Run

1. After all targets in the file are processed, the run ends.
2. The system finalizes the mode summary.
3. The world resets.
4. The `Start` button becomes available again.
5. The operator can select another mode and replay the same scenario file.

### Phase 5: Compare Modes

The operator repeats the same sequence file under all modes:

```text
Run 1 -> unrestricted
Run 2 -> baseline_j5_block_skip
Run 3 -> geometry_block
Run 4 -> overlap_zone_wait
```

The system then produces comparison outputs in:

- JSON for structured analysis
- Markdown for hackathon presentation and review

## Success Criteria

- One mode is active at a time.
- The selected mode is locked after `Start`.
- The same scenario JSON file is reused across modes.
- Both arm nodes read the same scenario JSON once at run start.
- Each arm computes its own `j4`, `j3`, and `j5` values at runtime.
- Each arm publishes `current_joints` and `candidate_joints` to the peer arm.
- Paired targets execute simultaneously.
- Remaining solo targets execute while the other arm stays in a safe home pose.
- Runtime collision truth is measured independently from planner decisions.
- Successful picks remove the cotton bowl from the scene.
- The world resets automatically when the file is fully processed.

## Metrics To Report

- total targets processed
- paired steps processed
- solo tail steps processed
- picks attempted
- picks completed
- picks blocked
- picks delayed
- picks clamped
- actual collisions
- near collisions
- minimum separation observed
- workspace utilization
- total run time
- recommended deployment mode
