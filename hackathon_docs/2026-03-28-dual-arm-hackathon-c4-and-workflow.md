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
|    - file with many target pairs                             |
|    - arm1 targets                                            |
|    - arm2 targets                                            |
|                                                              |
| 3. Per-arm motion container                                  |
|    - target -> joint conversion                              |
|    - local collision validation                              |
|    - mode-aware decision                                     |
|                                                              |
| 4. Runtime collision truth container                         |
|    - actual minimum-distance monitoring                      |
|    - collision / near-collision detection                    |
|                                                              |
| 5. Metrics and report container                              |
|    - per-step logging                                        |
|    - per-mode summary                                        |
|    - JSON + Markdown outputs                                 |
+--------------------------------------------------------------+
```

## C3: Components

```text
                    +----------------------+
                    | UI / run controller  |
                    | mode select          |
                    | start / reset        |
                    +----------+-----------+
                               |
                               v
                    +----------------------+
                    | scenario reader      |
                    | many target pairs    |
                    +----------+-----------+
                               |
             +-----------------+-----------------+
             |                                   |
             v                                   v
   +----------------------+           +----------------------+
   | arm1 pick pipeline   |           | arm2 pick pipeline   |
   +----------------------+           +----------------------+
   | target -> joints     |           | target -> joints     |
   | local validator      |<--------->| local validator      |
   | mode switch          |           | mode switch          |
   | joint publisher      |           | joint publisher      |
   +----------+-----------+           +-----------+----------+
              |                                   |
              +----------------+------------------+
                               |
                               v
                    +----------------------+
                    | runtime monitor      |
                    | true min distance    |
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
4. System reads the full scenario file
5. System validates file contents
6. For each sequence step:
      a. load paired targets or solo target
      b. spawn/update cotton bowls in Gazebo
      c. compute candidate joint values
      d. run local collision validation
      e. allow / clamp / wait / block
      f. publish joint commands
      g. Gazebo executes motion
      h. runtime monitor records actual minimum distance
      i. metrics logger stores outcome
      j. successful pick removes cotton bowl
7. After all steps finish, world resets
8. Start button becomes available again
9. Same file can be replayed under next mode
```

## Mode Model

Exactly one mode is active at a time.

```text
Mode 0 -> unrestricted
Mode 1 -> baseline_j5_block_skip
Mode 2 -> geometry_soft_clamp
Mode 3 -> overlap_zone_wait
```

Rules:

- mode is chosen before `Start`
- mode is locked during the run
- both arms use the same active mode for the whole run
- the same scenario file is replayed across all modes for fair comparison

## Sequence Behavior

```text
If both arms have a target at index i:
    run simultaneously

If one arm has no target at index i:
    finished arm returns to safe home pose
    remaining arm continues solo
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

- [ ] confirm the scenario file location and file format
- [ ] confirm how arm1 targets are exposed to the run controller
- [ ] confirm how arm2 targets are exposed to the run controller
- [ ] confirm how current cotton bowls are spawned or updated in Gazebo
- [ ] confirm how picked cotton bowls are removed after successful picks
- [ ] confirm where candidate target-to-joint conversion already exists for each arm
- [ ] confirm how to read the other arm's current state inside local validation
- [ ] confirm the safe home pose used when an arm becomes idle
- [ ] confirm the collision and near-collision thresholds used by the runtime truth monitor
- [ ] confirm the output location for JSON and Markdown reports

## Suggested Review Focus

The teammate review should answer three questions:

1. Does this workflow match the actual cotton-spawn and target-feed pipeline?
2. Are any missing interfaces needed between target generation and local validation?
3. Is the solo-tail behavior with safe-home fallback acceptable for the demo?
