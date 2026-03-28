## Why

The current implementation contains several correctness gaps that weaken confidence in the demo flow.
The scenario parser and controller do not fully agree on paired-step handling, wait mode does not yet
behave as intended, and final recommendation/report wording is not fully trustworthy. This phase is
needed to make the replayed outcomes correct and defensible.

## What Changes

- Align the scenario parser and controller around one paired-step contract.
- Fix terminal-state and step-advance behavior where needed.
- Make overlap wait actually wait before skipping, with one consistent timeout model.
- Make recommendation/report text reflect the actual winning mode.
- Tighten truth-monitor semantics and related tests.

## Capabilities

### New Capabilities
- `runtime-correctness`: correctness-focused behavior for parser, wait mode, and step lifecycle

### Modified Capabilities
- `dual-arm-run-orchestration`: align parser/controller semantics and terminal-state handling
- `collision-avoidance-modes`: correct wait-mode behavior
- `collision-comparison-reporting`: correct final recommendation wording
- `collision-truth-monitoring`: tighten threshold semantics and expectations

## Impact

- Affects scenario parsing, step lifecycle, wait policy, reporting, and truth-monitor behavior.
- Makes the Phase 1 UI flow trustworthy enough for demo and evaluation.

## Non-goals

- full architecture refactor into true distributed nodes
