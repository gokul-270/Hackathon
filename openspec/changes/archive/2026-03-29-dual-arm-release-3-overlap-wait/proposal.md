## Why

The geometry-aware blocker adds one improved strategy, but the hackathon deliverable calls for at
least two improved strategies. The third release needs to add an overlap-zone wait mode that shows a
coordination-based alternative, completes the four-mode comparison, and produces the final field
recommendation.

## What Changes

- Add `overlap_zone_wait` as the second improved strategy.
- Add overlap-zone state tracking, alternating-turn arbitration, and fixed timeout per pick.
- Add skip behavior after timeout so the run stays unblocked.
- Finalize reporting and recommendation logic across all four modes.
- Add contention-heavy scenario packs that make wait behavior visible.

## Capabilities

### New Capabilities
- `collision-avoidance-modes`: add `overlap_zone_wait` as a switchable strategy
- `collision-comparison-reporting`: finalize four-mode recommendation and blocked/skipped summary logic

### Modified Capabilities
- `collision-truth-monitoring`: consume truth-monitor outputs in the final four-mode recommendation

## Impact

- Completes the hackathon comparison set with a coordination-based alternative.
- Adds deterministic wait/skip behavior so contention does not stall the run.

## Non-goals

- Closer-target-wins arbitration in this release
- Full production tuning automation
