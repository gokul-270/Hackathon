# Dual-Arm Hackathon C4 And Workflow Confirmation

**Date:** 2026-03-28
**Status:** Planning
**Scope:** C4-style diagrams and workflow confirmation points for teammate review

## C1: System Context

```text
          +-------------------------------------------+
          | Dual-Arm Cotton Picking Hackathon System  |
          +-------------------------------------------+
                 |                  |                |
                 v                  v                v
          Gazebo simulation   Avoidance modes   Metrics/report
                 |
                 v
      Two arms face each other across cotton row
```

## C2: Containers

```text
+--------------------------------------------------------------+
| 1. Dual-arm simulation container                             |
|    - Gazebo world                                            |
|    - two arms in opposite positions                          |
|    - cotton bowls in overlap zone                            |
|                                                              |
| 2. Scenario input container                                  |
|    - scenario JSON with camera/cotton points                 |
|    - read by both arm nodes                                  |
|    - arm1 targets                                            |
|    - arm2 targets                                            |
|                                                              |
| 3. Run-control container                                     |
|    - mode lock per run                                       |
|    - central step synchronization                            |
|                                                              |
| 4. Per-arm motion container                                  |
|    - camera point -> joint conversion                        |
|    - peer-state publish/subscribe                            |
|    - local collision validation                              |
|    - mode-aware decision                                     |
|                                                              |
| 5. Runtime collision truth container                         |
|    - actual minimum-distance monitoring                      |
|    - collision / near-collision detection                    |
|                                                              |
| 6. Metrics and report container                              |
|    - per-step logging                                        |
|    - per-mode summary                                        |
|    - JSON + Markdown outputs                                 |
+--------------------------------------------------------------+
```

## C3: Components

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
   | local validator      |           | local validator      |
   | local mode decision  |           | local mode decision  |
   | joint publisher      |           | joint publisher      |
   +----------+-----------+           +-----------+----------+
              |                                   |
              +----------------+------------------+
                               |
                               v
                    +----------------------+
                    | runtime monitor      |
                    | reads peer-state     |
                    | collision truth      |
                    +----------+-----------+
                               |
                               v
                    +----------------------+
                    | metrics + report     |
                    +----------------------+
```

## C4: Runtime Workflow

```text
1. Operator selects mode in UI
2. Operator presses Start
3. System locks the mode for this run
4. Both arm nodes read the same scenario JSON file once
5. Central controller validates file contents and activates step 1
6. For each active sequence step:
      a. arm1 reads its own target for the active step
      b. arm2 reads its own target for the active step
      c. spawn/update cotton bowls in Gazebo
      d. each arm computes candidate `j4`, `j3`, `j5` values
      e. each arm publishes peer state with `step_id`, `status`, `current_joints`, `candidate_joints`
      f. each arm receives the peer arm state
      g. each arm applies the selected mode locally
      h. allow / wait / block
      i. Gazebo executes allowed motion
      j. runtime monitor records actual minimum distance
      k. metrics logger stores outcome
      l. successful pick removes cotton bowl
      m. controller waits until all active arms are terminal before advancing
7. After all steps finish, world resets
8. Start button becomes available again
9. Same file can be replayed under next mode
```

## Mode Model

Exactly one mode is active at a time.

```text
Mode 0 -> unrestricted
Mode 1 -> baseline_j5_block_skip
Mode 2 -> geometry_block
Mode 3 -> overlap_zone_wait
```

Rules:

- mode is chosen before `Start`
- mode is locked during the run
- both arms use the same active mode for the whole run
- both arm nodes read the same scenario JSON once at run start
- the same scenario JSON is replayed across all modes for fair comparison

## Sequence Behavior

```text
If both arms have a target at index i:
    run simultaneously

If one arm has no target at index i:
    finished arm returns to safe home pose
    remaining arm continues solo

Step completes only when all active arms are terminal.
```

Example:

```text
arm1 = 4 targets
arm2 = 7 targets

1 -> arm1[1] + arm2[1]
2 -> arm1[2] + arm2[2]
3 -> arm1[3] + arm2[3]
4 -> arm1[4] + arm2[4]
5 -> arm2[5], arm1 idle at home pose
6 -> arm2[6], arm1 idle at home pose
7 -> arm2[7], arm1 idle at home pose
```

## Workflow Confirmation Checklist

Use this with the teammate working on cotton spawning and target generation.

- [ ] confirm the scenario JSON location and file format
- [ ] confirm how arm1 targets are exposed to the run controller
- [ ] confirm how arm2 targets are exposed to the run controller
- [ ] confirm how current cotton bowls are spawned or updated in Gazebo
- [ ] confirm how picked cotton bowls are removed after successful picks
- [ ] confirm where candidate point-to-joint conversion already exists for each arm
- [ ] confirm the peer-state topic contract for current and candidate joints
- [ ] confirm the safe home pose used when an arm becomes idle
- [ ] confirm the collision and near-collision thresholds used by the runtime truth monitor
- [ ] confirm the output location for JSON and Markdown reports

## Peer-State Contract

Each arm publishes a peer-state packet with at least:

```text
arm_id
step_id
status
timestamp
current_joints
candidate_joints
```

Recommended status values:

```text
idle
ready
waiting
moving
blocked
skipped
done
```

## Wait-Mode Rule

`overlap_zone_wait` uses:

- alternating-turn priority
- fixed seconds per pick timeout
- timeout -> skip that specific pick and continue

## Recommendation Rule

Final mode recommendation uses:

1. zero actual collisions first
2. then highest successful picks

Summary reporting combines:

- blocked picks
- skipped picks

## Suggested Review Focus

The teammate review should answer three questions:

1. Does this workflow match the actual cotton-spawn and target-feed pipeline?
2. Are any missing interfaces needed between target generation and local validation?
3. Is the solo-tail behavior with safe-home fallback acceptable for the demo?
