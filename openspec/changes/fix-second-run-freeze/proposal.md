## Why

After a scenario run completes, pressing Start again causes the UI to appear frozen: the
Start button receives no feedback and the log emits no events. The root cause is a race in
the global `RunEventBus` lifecycle — the SSE subscriber attaches to an already-closed bus
before `/api/run/start` resets it, so the SSE stream closes immediately and the new run's
events are never delivered.

## What Changes

- `RunEventBus.subscribe()` SHALL NOT silently return on a closed bus; instead the bus SHALL
  be auto-reset so that a new subscriber always receives a live stream.
- Alternatively, `/api/run/events` SHALL reset the bus before subscribing, eliminating the
  race window between SSE open and `/api/run/start`.
- A failing integration test SHALL be added that reproduces the two-run SSE freeze before
  the fix and passes after.

## Capabilities

### New Capabilities

- `sse-run-lifecycle`: SSE stream correctness across consecutive runs — the `/api/run/events`
  endpoint SHALL deliver all events for every run regardless of how many prior runs have
  completed.

### Modified Capabilities

- `ui-run-flow`: The requirement for "Start Replay From The UI" SHALL be extended to cover
  **consecutive** runs — a second Start SHALL produce a fully functional SSE stream and
  live log updates identical to the first run.

## Impact

- `run_event_bus.py` — `RunEventBus` class (`subscribe`, `reset`, `close`)
- `testing_backend.py` — `/api/run/events` SSE handler (lines ~1227-1251) and
  `/api/run/start` handler (lines ~1253-1339)
- `test_ui_run_flow_integration.py` — new test covering SSE lifecycle across two runs
- `test_run_event_bus.py` — new unit tests for `RunEventBus` subscribe-after-close behaviour

## Non-goals

- No UI changes — the freeze is entirely backend-side.
- No changes to event payload schemas or SSE event types.
- No changes to run logic, modes, or arm selection.
