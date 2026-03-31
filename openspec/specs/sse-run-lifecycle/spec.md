# sse-run-lifecycle Specification

## Purpose
TBD - created by archiving change fix-second-run-freeze. Update Purpose after archive.
## Requirements
### Requirement: SSE stream resets cleanly for each run

The `/api/run/events` endpoint SHALL reset the `RunEventBus` before subscribing so that
every connection — including connections opened after a previous run completed and closed
the bus — receives a fully live event stream.

#### Scenario: Second run SSE receives all events

- **WHEN** a first run completes (bus is closed)
- **AND** the UI opens a new `GET /api/run/events` connection
- **AND** `POST /api/run/start` is called for the second run
- **THEN** the second SSE stream delivers all `step_start` and `run_complete` events for
  that run without closing prematurely

#### Scenario: SSE stream closes after run_complete event

- **WHEN** the run controller emits a `run_complete` event
- **THEN** the SSE stream for that run closes cleanly without error

#### Scenario: RunEventBus reset clears closed state and re-arms for new events

- **WHEN** `RunEventBus.reset()` is called on a closed bus
- **THEN** a subsequent `subscribe()` on that bus blocks waiting for new events rather than
  returning immediately

#### Scenario: RunEventBus subscribe on open bus yields only new events

- **WHEN** `RunEventBus.subscribe()` is called on a freshly reset bus
- **AND** an event is emitted after the subscribe call
- **THEN** the subscriber receives that event

