# C4 Architecture Diagram: Independent Arm Run

## System Context

```
┌─────────────────────────────────────────────────────────────────┐
│  User (browser / curl)                                          │
│  POST /api/run/start { mode, scenario, arm_pair }               │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  testing_backend.py  (FastAPI HTTP layer)                       │
│  - validates request                                            │
│  - creates RunController + RunStepExecutor                      │
│  - calls controller.run() via asyncio.to_thread()               │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  RunController.run()                                            │
│                                                                 │
│  Phase 1: Parallel Cotton Spawn                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  ThreadPoolExecutor  (max_workers = N cottons)           │  │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐   ┌─────────┐     │  │
│  │  │spawn(0) │ │spawn(1) │ │spawn(2) │...│spawn(N) │     │  │
│  │  └────┬────┘ └────┬────┘ └────┬────┘   └────┬────┘     │  │
│  │       └───────────┴───────────┴─────────────┘           │  │
│  │                    gz service /world/*/create             │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  Phase 2: Independent Arm Threads                               │
│  ┌─────────────────────┐     ┌─────────────────────┐          │
│  │  Arm1 Thread         │     │  Arm2 Thread         │          │
│  │  for step in steps:  │     │  for step in steps:  │          │
│  │    compute FK        │     │    compute FK        │          │
│  │    publish state ───────────▶                     │          │
│  │               ◀────────────── publish state       │          │
│  │    read peer         │     │    read peer         │          │
│  │    mode logic        │     │    mode logic        │          │
│  │    executor.execute()│     │    executor.execute()│          │
│  │    reporter.add_step │     │    reporter.add_step │          │
│  └──────────┬──────────┘     └──────────┬──────────┘          │
│             │                           │                       │
│             └────────────┬──────────────┘                       │
│                          ▼                                       │
│              Both threads joined → return summary               │
└─────────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Shared Thread-Safe State                                        │
│                                                                 │
│  ┌──────────────────────┐   ┌──────────────────────┐           │
│  │  LocalPeerTransport  │   │  JsonReporter         │           │
│  │  _mailbox: dict      │   │  _steps: list         │           │
│  │  _lock: Lock  ←────────── _lock: Lock            │           │
│  └──────────────────────┘   └──────────────────────┘           │
│                                                                 │
│  ┌──────────────────────┐                                       │
│  │  TruthMonitor         │                                       │
│  │  _records: dict       │                                       │
│  │  _lock: Lock          │                                       │
│  └──────────────────────┘                                       │
└─────────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Gazebo (gz topic / gz service)                                  │
│  - joint commands via gz topic (arm1: /joint*_cmd)              │
│  - joint commands via gz topic (arm2: /joint*_copy_cmd)         │
│  - cotton spawn/remove via gz service /world/*/create|remove    │
└─────────────────────────────────────────────────────────────────┘
```

## Key Data Flows

| Flow | Source | Destination | Thread safety |
|------|--------|-------------|---------------|
| Candidate joints publish | Arm thread | LocalPeerTransport | Lock |
| Peer state read | Arm thread | LocalPeerTransport | Lock |
| Step report write | Arm thread | JsonReporter | Lock |
| Truth observe | Arm thread | TruthMonitor | Lock |
| Cotton model name | RunController | cotton_models dict (read-only after spawn) | No lock needed |
