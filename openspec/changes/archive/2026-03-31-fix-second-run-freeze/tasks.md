## Execution Plan

| Group | Depends On | Can Parallelize With |
|-------|-----------|----------------------|
| 1. RED — Unit tests | — | 2 |
| 2. RED — Integration test | — | 1 |
| 3. GREEN — Fix | 1, 2 | — |
| 4. REFACTOR + verify | 3 | — |
| 5. Artifacts + commit | 4 | — |

---

## 1. RED — Unit tests for RunEventBus [PARALLEL with 2]

- [ ] 1.1 In `test_run_event_bus.py`, add test `test_subscribe_after_close_returns_immediately`
      — call `close()` then `subscribe()` and assert the generator yields nothing without
      blocking (confirms current behaviour that the fix must not break for E-STOP path;
      covers spec scenario "RunEventBus subscribe on open bus yields only new events").
- [ ] 1.2 Add test `test_subscribe_after_reset_blocks_until_emit` — call `close()`, then
      `reset()`, then `subscribe()` in a thread, assert the thread is blocked, then `emit()`
      an event, assert it is received (covers spec scenario "RunEventBus reset clears closed
      state and re-arms for new events").
- [ ] 1.3 Add test `test_sse_stream_closes_after_run_complete` — emit a `run_complete` event
      on the bus then call `close()`; assert `subscribe()` drains and returns (covers spec
      scenario "SSE stream closes after run_complete event").
- [ ] 1.4 Run `python3 -m pytest test_run_event_bus.py -x` — confirm 1.2 FAILS (bus not
      yet re-armed by reset in SSE handler).

## 2. RED — Integration regression test [PARALLEL with 1]

- [ ] 2.1 In `test_ui_run_flow_integration.py`, add test
      `test_second_run_sse_receives_events` that:
      1. Opens `GET /api/run/events`, calls `POST /api/run/start` (run 1), collects all
         events until `run_complete`.
      2. Opens a new `GET /api/run/events` connection (simulating the browser reconnecting).
      3. Calls `POST /api/run/start` for run 2.
      4. Asserts that the second SSE stream delivers a `run_complete` event (not empty).
      (Covers spec scenarios "Second run SSE receives all events",
      "Second consecutive run is not frozen", "SSE log events appear on second run".)
- [ ] 2.2 Add test `test_start_fires_before_sse_opens` — call `POST /api/run/start` for
      run 2 before opening `GET /api/run/events`; assert that when SSE is opened it still
      delivers the `run_complete` event (covers edge case: start fires before SSE opens).
- [ ] 2.3 Run `python3 -m pytest test_ui_run_flow_integration.py::test_second_run_sse_receives_events -x`
      — confirm it FAILS (second SSE stream closes immediately, no events).

## 3. GREEN — Move reset to SSE handler [SEQUENTIAL]

- [ ] 3.1 In `testing_backend.py`, inside the `_generator()` coroutine of
      `GET /api/run/events`, add `_event_bus.reset()` as the first line before
      `gen = _event_bus.subscribe()`.
- [ ] 3.2 Keep the existing `_event_bus.reset()` call in `POST /api/run/start` as a
      defensive guard (no removal needed).
- [ ] 3.3 Run `python3 -m pytest test_run_event_bus.py test_ui_run_flow_integration.py -x`
      — confirm all tests GREEN.
- [ ] 3.4 Run the full test suite:
      `python3 -m pytest test_run_event_bus.py test_ui_run_flow_integration.py test_ui_run_flow_backend.py test_testing_backend.py -v`
      — confirm no regressions.

## 4. REFACTOR + verify [SEQUENTIAL]

- [ ] 4.1 Review `_generator()` in `testing_backend.py` — confirm code is clean, no
      dead code, docstring updated if needed.
- [ ] 4.2 Re-run full test suite — confirm still GREEN.
- [ ] 4.3 Verify `impact-analysis.md` is present and up to date.

## 5. Artifacts commit [SEQUENTIAL]

- [ ] 5.1 `git add` all change artifacts (proposal.md, design.md, specs/, tasks.md,
      impact-analysis.md, docs/).
- [ ] 5.2 Commit: `chore: create fix-second-run-freeze change artifacts (proposal, specs, design, tasks)`.
- [ ] 5.3 `git add` implementation files and tests.
- [ ] 5.4 Commit: `fix: reset SSE event bus on /api/run/events to prevent second-run freeze`.
