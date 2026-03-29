## Overview

Phase 2 fixes the runtime correctness gaps that remain after the UI flow is connected. The goal is to
ensure the parser and controller share the same scenario contract, overlap wait behaves according to
the intended policy, report text names the actual winner, and truth-monitor outputs are consistent
with the thresholds being claimed.

## User Journey

```text
Operator runs scenario from UI
  -> parser accepts intended paired-step scenario format
  -> controller advances only on correct terminal states
  -> wait mode really waits before skipping
  -> final report names the actual winning mode
```

## Scope

### Must Have
- parser/controller contract alignment
- correct paired-step support
- real wait-before-skip behavior
- correct recommendation text
- consistent truth-monitor semantics

### Should Have
- improved regression coverage for all corrected behaviors

### Could Have
- clearer debug output for runtime state transitions

### Won't Have
- true distributed transport refactor
