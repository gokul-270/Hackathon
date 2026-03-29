# C4 Diagram: fix-second-run-freeze

## Context (Level 1)

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Testing Environment                          │
│                                                                      │
│   ┌────────────┐          ┌──────────────────────────────────────┐  │
│   │            │  HTTP    │         Testing Backend              │  │
│   │  Browser   │◄────────►│  (FastAPI, testing_backend.py)       │  │
│   │  (UI)      │  SSE     │                                      │  │
│   └────────────┘          │  ┌──────────────┐  ┌─────────────┐  │  │
│                           │  │ RunEventBus  │  │RunController│  │  │
│                           │  │(run_event_   │◄─│(run_        │  │  │
│                           │  │  bus.py)     │  │controller.py│  │  │
│                           │  └──────────────┘  └─────────────┘  │  │
│                           └──────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

## Container (Level 2) — SSE Lifecycle

```
Browser (testing_ui.js)
│
│  1. GET /api/run/events  (EventSource)
│─────────────────────────────────────────────────────────────►│
│                                              testing_backend.py
│                                              │
│                                              │  2. _event_bus.reset()   [FIX]
│                                              │  3. gen = _event_bus.subscribe()
│                                              │
│  4. POST /api/run/start
│─────────────────────────────────────────────────────────────►│
│                                              │
│                                              │  5. _event_bus.reset()  (defensive)
│                                              │  6. controller.run()
│                                              │     └─► _event_bus.emit(step_start)
│◄─────── data: {"type":"step_start",...} ─────│
│                                              │     └─► _event_bus.emit(run_complete)
│◄─────── data: {"type":"run_complete",...} ───│
│                                              │  7. _event_bus.close()
│  (stream closes)                             │
```

## Component (Level 3) — RunEventBus internals

```
RunEventBus
┌──────────────────────────────────────────────────┐
│  _queue: deque                                   │
│  _closed: bool                                   │
│  _lock: threading.Condition                      │
│                                                  │
│  emit(event)                                     │
│    append to _queue                              │
│    notify_all()                                  │
│                                                  │
│  subscribe() → Generator                        │
│    cursor = 0                                    │
│    loop:                                         │
│      wait while queue empty AND not closed       │
│      yield queued events                         │
│      if closed: return                           │
│                                                  │
│  close()                                         │
│    _closed = True                                │
│    notify_all()                                  │
│                                                  │
│  reset()                                         │
│    queue.clear()                                 │
│    _closed = False          ◄── key: re-arms bus │
└──────────────────────────────────────────────────┘
```
