## Why

The baseline replay platform can prove the distributed workflow and the existing conservative blocker,
but it cannot yet show a smarter collision-avoidance strategy. The second release needs to add a
geometry-aware blocking mode that improves the comparison story while still keeping the system fully
demoable end-to-end.

## What Changes

- Add `geometry_block` as the first improved strategy.
- Add a two-stage geometry check with a quick screen and a better unsafe-case check.
- Add Markdown comparison reporting for three-mode replay.
- Add overlap-heavy scenario packs that make the geometry behavior measurable.

## Capabilities

### New Capabilities
- `collision-avoidance-modes`: add `geometry_block` as a switchable strategy
- `collision-comparison-reporting`: add Markdown comparison output and three-mode recommendation flow

### Modified Capabilities
- `collision-truth-monitoring`: use truth-monitor outputs in the three-mode comparison loop

## Impact

- Extends the release-1 runtime platform with the first improved collision strategy.
- Adds richer comparison outputs needed for hackathon judging.

## Non-goals

- Overlap-zone wait arbitration
- Final four-mode recommendation
