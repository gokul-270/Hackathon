## Overview

Release 1 establishes the distributed dual-arm replay platform. Both arm nodes read the same scenario
JSON once at run start, compute their own candidate `j4`, `j3`, and `j5` values from camera/cotton
points, exchange peer state, and execute under either `unrestricted` or `baseline_j5_block_skip`.
A central controller advances steps only when all active arms are terminal, while a runtime truth
monitor records near-collision and collision outcomes independently from planner logic.

## Architecture

```text
                    +----------------------+
                    | UI                   |
                    | mode select          |
                    | start / reset        |
                    +----------+-----------+
                               |
                               v
                    +----------------------+
                    | central run          |
                    | controller           |
                    | step sync            |
                    +----------+-----------+
                               |
             +-----------------+-----------------+
             |                                   |
             v                                   v
   +----------------------+           +----------------------+
   | arm1 node            |           | arm2 node            |
   +----------------------+           +----------------------+
   | read same JSON       |           | read same JSON       |
   | camera point->joints |           | camera point->joints |
   | publish peer state   |<--------->| publish peer state   |
   | baseline mode logic  |           | baseline mode logic  |
   | joint publisher      |           | joint publisher      |
   +----------+-----------+           +-----------+----------+
              |                                   |
              +----------------+------------------+
                               |
                               v
                    +----------------------+
                    | truth monitor MVP    |
                    | JSON reporting       |
                    +----------------------+
```

## End-To-End Behavior

- load the same scenario JSON in both arm nodes
- run paired steps simultaneously
- run solo-tail steps with finished arm at safe home pose
- support `unrestricted` and `baseline_j5_block_skip`
- generate JSON outputs after replay

## Capabilities

### Scenario JSON
- shared file read by both arms
- camera/cotton points only
- no precomputed expected joints

### Peer-State Contract

```text
arm_id
step_id
status
timestamp
current_joints
candidate_joints
```

### Modes

```text
Mode 0 -> unrestricted
Mode 1 -> baseline_j5_block_skip
```

## MoSCoW

### Must Have
- scenario JSON replay
- distributed arm nodes
- central step synchronization
- peer-state exchange
- unrestricted mode
- baseline mode
- truth monitor MVP
- JSON reporting

### Should Have
- per-step traceability by `step_id`
- stable safe-home handling for solo-tail steps

### Could Have
- richer UI summaries

### Won't Have
- geometry-aware blocking
- overlap wait arbitration
