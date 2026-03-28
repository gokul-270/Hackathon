## Why

Even after the UI flow works and the runtime behavior is corrected, the implementation still behaves
more like an in-process replay library than the originally intended dual-arm runtime architecture.
This phase is needed if the team wants the system shape to match the spec more closely with cleaner
runtime separation and more realistic peer-state exchange.

## What Changes

- Refactor the current in-process arm runtimes toward cleaner separate runtime units.
- Introduce real peer-state transport rather than only local object passing if required by the target
  architecture.
- Wire the hackathon runtime flow into launch/runtime startup as needed.
- Strengthen the truth/geometry model if the current heuristic remains too weak.

## Capabilities

### New Capabilities
- `architecture-alignment`: runtime structure closer to the intended distributed dual-arm system

### Modified Capabilities
- `peer-state-exchange`: move toward real runtime transport instead of only in-process handoff
- `dual-arm-run-orchestration`: improve runtime separation and startup integration
- `collision-truth-monitoring`: strengthen monitoring model if required

## Impact

- Affects launch/runtime wiring and internal architecture, not just UI or tests.
- Useful if the hackathon needs architectural credibility beyond a replay-only implementation.

## Non-goals

- changing the user-facing flow already completed in earlier phases
