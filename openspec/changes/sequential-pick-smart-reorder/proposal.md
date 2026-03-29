## Why

The current Mode 3 (`overlap_zone_wait`) immediately skips the loser arm at every contention step (timeout=0 in production), wasting picks that could succeed if dispatched sequentially. Replacing it with **Sequential Pick** recovers those lost picks by dispatching winner-then-loser at contention steps. Adding **Mode 4 (Smart Reorder)** eliminates contention entirely by reordering cotton targets before the run starts, enabling fully parallel execution with zero skips.

## What Changes

- **BREAKING**: Remove `overlap_zone_wait` (Mode 3) constant, `WaitModePolicy` class, and all `"overlap_zone_wait"` string references. Replace with `sequential_pick` / `SEQUENTIAL_PICK`.
- **New Mode 3 -- Sequential Pick**: At contention steps (j4 gap < 0.10 m), dispatch winner arm first, wait for completion, then dispatch loser arm. Non-contention steps stay parallel. Turn alternates between arms.
- **New Mode 4 -- Smart Reorder**: Before execution, a scheduler rearranges cotton picking order for both arms to maximize the minimum j4 gap across all paired steps, eliminating contention so all steps run in parallel.
- Extend markdown reporter from four-mode to five-mode comparison support.
- Add Mode 4 option to the UI mode dropdown; rename Mode 3 label.
- Extend backend validation from modes 0-3 to 0-4.

## Capabilities

### New Capabilities

- `sequential-pick-policy`: Contention resolution policy for Mode 3 -- detects contention (j4 gap < 0.10 m), alternates winner turn, dispatches winner arm first then loser arm sequentially.
- `smart-reorder-scheduler`: Pre-run cotton target reordering optimizer for Mode 4 -- rearranges step order to maximize minimum j4 gap across all paired steps.

### Modified Capabilities

- `collision-avoidance-modes`: Replace `OVERLAP_ZONE_WAIT = 3` with `SEQUENTIAL_PICK = 3`, add `SMART_REORDER = 4`, update dispatch logic in `apply_with_skip`.
- `dual-arm-run-orchestration`: Sequential Pick mode uses two-phase dispatch (winner first, wait, loser second) at contention steps instead of parallel ThreadPoolExecutor.
- `collision-comparison-reporting`: Support five-mode comparison reports -- heading, table format, recommendation logic, mode name strings.
- `ui-run-flow`: Rename Mode 3 dropdown from "Overlap Zone Wait" to "Sequential Pick". Add Mode 4 "Smart Reorder" option. Backend accepts mode=4.

## Impact

- **Files modified**: ~25 files (9 source, ~16 test files)
- **Core source**: `baseline_mode.py`, `wait_mode_policy.py` (replaced), `overlap_zone_state.py` (kept for threshold), `run_controller.py`, `testing_backend.py`, `markdown_reporter.py`, `json_reporter.py`, `arm_runtime.py`, `testing_ui.html`
- **APIs**: POST `/api/run/start` accepts mode=4; error message changes from "must be 0-3" to "must be 0-4"
- **No new dependencies or endpoints**

## Non-goals

- Changing Modes 0, 1, or 2 behavior
- Modifying the executor animation pipeline or timing
- Adding new API endpoints
- Changing the contention threshold (stays at 0.10 m)
- Changing the `OverlapZoneState` detection logic (reused as-is)
