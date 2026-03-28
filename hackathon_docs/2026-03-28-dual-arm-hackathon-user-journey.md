# Dual-Arm Hackathon User Journey

**Date:** 2026-03-28
**Status:** Planning
**Scope:** End-to-end operator and system journey for the dual-arm collision-avoidance hackathon demo

## Goal

Create a repeatable dual-arm Gazebo experiment where the same cotton target sequence is replayed
across multiple collision-avoidance modes, then compared using safety and productivity metrics.

## Demo Story

The operator opens the UI, selects exactly one collision-avoidance mode, selects the full-sequence
scenario file, and starts the run. The system reads both arms' cotton targets from the file,
processes paired steps simultaneously, then continues any remaining solo steps while the finished arm
returns to a safe home pose. A runtime truth monitor measures actual arm-arm proximity separately
from the planner's decision logic. When the sequence finishes, the world resets, the Start button
becomes available again, and the same scenario can be replayed under the next mode for fair
comparison.

## User Journey

### Phase 0: Ready State

- Gazebo dual-arm world is available.
- `arm_left` and `arm_right` face each other across the cotton row.
- The scenario file exists and contains many target pairs for both arms.
- The UI is idle and the `Start` button is available.

### Phase 1: Configure Run

1. The operator opens the UI.
2. The operator selects one active mode for the run:
   - `unrestricted`
   - `baseline_j5_block_skip`
   - `geometry_soft_clamp`
   - `overlap_zone_wait`
3. The operator selects or confirms the scenario file.
4. The operator presses `Start`.
5. The system locks the selected mode for the duration of the run.

### Phase 2: Load Scenario

1. The run controller reads the scenario file.
2. The system validates:
   - file format is valid,
   - both arm target lists are readable,
   - target values are inside expected workspace bounds.
3. The system builds a run sequence.

## Sequence Rules

- If both arms have targets at the same step index, they run simultaneously.
- If one arm has remaining targets after the other finishes, the finished arm returns to a safe home
  pose and stays idle.
- The active arm continues processing its remaining solo targets.

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

1. The system reads the current arm target pair or solo target.
2. The cotton spawn manager spawns or updates the visible cotton bowls in Gazebo.
3. Each active arm computes candidate joint values from its assigned cotton target.
4. Each active arm runs local collision validation before publishing motion.
5. The selected mode decides whether to:
   - allow motion,
   - clamp motion,
   - wait,
   - block.
6. Allowed commands are published to the respective arm joints.
7. Gazebo executes the motion.
8. The runtime truth monitor checks actual minimum arm-arm distance.
9. On successful pick without collision, the corresponding cotton bowl disappears.
10. Metrics for the step are logged.

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
Run 3 -> geometry_soft_clamp
Run 4 -> overlap_zone_wait
```

The system then produces comparison outputs in:

- JSON for structured analysis
- Markdown for hackathon presentation and review

## Success Criteria

- One mode is active at a time.
- The selected mode is locked after `Start`.
- The same scenario file is reused across modes.
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
