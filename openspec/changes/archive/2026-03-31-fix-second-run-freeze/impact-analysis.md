# Impact Analysis: fix-second-run-freeze

## Before / After Behavior

| Item | Before (current) | After |
|------|-----------------|-------|
| Second `GET /api/run/events` on a closed bus | `subscribe()` returns immediately; SSE stream closes before any events | `reset()` is called first; `subscribe()` blocks until events arrive |
| UI on second Start press | Log receives no events; button appears frozen | Log receives all step and completion events, identical to first run |
| First run SSE behavior | Unchanged — bus is open when SSE connects | Unchanged |
| `_event_bus.reset()` in `/api/run/start` | Canonical reset point | Becomes a defensive guard (reset already done by SSE open) |
| `_event_bus.close()` in `/api/run/start` | Signals subscriber to stop after `run_complete` | Unchanged |
| E-STOP path | Bus closed via `close()` after E-STOP | Unchanged |

## Performance Impact

| Item | CPU | Memory | Latency |
|------|-----|--------|---------|
| `reset()` in SSE handler | +1 lock acquisition per SSE connect (~μs) | No change | Negligible |
| Overall SSE stream | No change | No change | No change |

## Unchanged Behavior

- All SSE event payload schemas (`step_start`, `cotton_reached`, `contention_detected`,
  `dispatch_order`, `reorder_applied`, `run_complete`) — no change.
- All HTTP API endpoints, HTTP status codes, request/response bodies — no change.
- ROS2 topics, services, and parameters — no change.
- Launch files and shell scripts — no change.
- E-STOP integration path — no change.
- Single-run (first run) SSE behavior — no change.
- `RunEventBus` public API signatures (`emit`, `subscribe`, `close`, `reset`) — no change.

> **Note:** The *call-site ordering* of `reset()` changes: the canonical reset moves from
> `/api/run/start` to `/api/run/events`. `/api/run/start` retains a defensive `reset()` call.
> Observable behavior of a single run is identical; the change only affects correctness across
> consecutive runs.

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| `reset()` in SSE open wipes events emitted before SSE connects | Very low — browser connects before pressing Start | `/api/run/start` also calls `reset()` as guard; events are only emitted after start |
| Two concurrent SSE opens both call `reset()` | Very low — UI only opens one SSE at a time | Single-subscriber design; no multi-client fan-out |
| Removing the canonical role of `reset()` from start causes confusion | Low | Design doc documents the intentional ordering |

## Blast Radius

| Area | Files Touched | Approx. Lines Changed |
|------|--------------|----------------------|
| Backend fix | `testing_backend.py` | ~1 line added in `_generator()` |
| Unit tests | `test_run_event_bus.py` | ~30 lines (2 new tests) |
| Integration tests | `test_ui_run_flow_integration.py` | ~40 lines (1 new test) |
| OpenSpec artifacts | `proposal.md`, `design.md`, `specs/`, `tasks.md`, `impact-analysis.md` | N/A |
| **Total code change** | 2 files | ~71 lines |
