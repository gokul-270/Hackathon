## Overview

Release 3 adds `overlap_zone_wait` to the working three-mode platform. The new mode models overlap
contention explicitly, resolves conflicts with alternating-turn priority, waits a fixed number of
seconds per pick, and skips that pick if the timeout expires. The release also finalizes the
comparison report so all four modes can be replayed and recommended using safety first and success
second.

## End-To-End Behavior

- everything from Release 2 remains working
- `overlap_zone_wait` becomes available as Mode 3
- same scenario can be replayed across all four modes
- timeout never stalls the whole run; it skips the conflicting pick and continues
- final JSON and Markdown outputs recommend a mode

## Release Features

- `overlap-zone-state`
- `wait-mode-policy`
- `wait-mode-integration`
- `final-reporting`
- `contention-scenario-pack`

## Wait Policy

- alternating-turn priority
- fixed seconds per pick timeout
- timeout -> skipped pick
- future enhancement remains `closer-target-wins`, but not in this release

## Recommendation Rule

1. zero actual collisions first
2. then highest successful picks

Summary combines:
- blocked picks
- skipped picks

## MoSCoW

### Must Have
- overlap-zone state tracking
- alternating-turn wait arbitration
- fixed timeout and skip
- four-mode comparison output
- final recommendation

### Should Have
- clear visibility of skipped picks in reports

### Could Have
- richer contention debugging traces

### Won't Have
- closer-target-wins arbitration
