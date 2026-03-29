## Overview

Release 2 adds `geometry_block` to the working Release 1 platform. The new mode uses a two-stage
geometry check: a quick end-effector distance screen and a better geometry/link-level check. If the
second stage deems the motion unsafe, the pick is blocked immediately. The release also introduces
Markdown comparison reporting and scenario packs that make the geometry mode visibly different from
both unrestricted replay and the old J5 baseline.

## End-To-End Behavior

- everything from Release 1 remains working
- `geometry_block` becomes available as Mode 2
- the same scenario can be replayed across:
  - `unrestricted`
  - `baseline_j5_block_skip`
  - `geometry_block`
- JSON and Markdown comparison outputs are produced

## Release Features

- `geometry-stage1-screen`
- `geometry-stage2-check`
- `geometry-mode-integration`
- `markdown-report`
- `geometry-scenario-pack`

## Geometry Model

### Stage 1
- quick end-effector distance screen
- fast safe/risky split

### Stage 2
- better geometry/link-level unsafe-case check
- unsafe -> block immediately

## MoSCoW

### Must Have
- geometry stage 1
- geometry stage 2
- `geometry_block` integrated into mode layer
- Markdown report for three-mode comparison
- reusable overlap-heavy scenarios

### Should Have
- clear report explanation of how geometry mode differs from baseline

### Could Have
- extra debug telemetry for geometry decisions

### Won't Have
- overlap wait mode
