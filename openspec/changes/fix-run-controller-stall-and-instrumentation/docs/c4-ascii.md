# C4 Context / Container Diagram (ASCII)

## Level 1 – System Context

```
┌──────────────────────────────────────────────────────────┐
│                    Simulation Operator                    │
│                       (Browser)                          │
└────────────────────────────┬─────────────────────────────┘
                             │  HTTP / SSE
                             ▼
┌──────────────────────────────────────────────────────────┐
│             Vehicle Arm Sim Web UI                        │
│         (Flask + SocketIO  testing_backend.py)           │
│                                                          │
│  ┌──────────────────────────────────────────────────┐    │
│  │              Run Controller                       │    │
│  │           run_controller.py                       │    │
│  │  - reachability check (fk_chain.py)               │    │
│  │  - ThreadPoolExecutor dispatch                    │    │
│  │  - step_complete / run_complete emit              │    │
│  └──────────────────┬───────────────────────────────┘    │
│                     │                                    │
│  ┌──────────────────▼───────────────────────────────┐    │
│  │            Run Step Executor                      │    │
│  │         run_step_executor.py                      │    │
│  │  - per-arm joint publish                          │    │
│  │  - cotton spawn / remove                          │    │
│  └──────────────────┬───────────────────────────────┘    │
│                     │  gz topic pub                      │
└─────────────────────┼──────────────────────────────────-─┘
                      │
                      ▼
┌──────────────────────────────────────────────────────────┐
│                   Gazebo Simulator                        │
│           (external process / ROS2 bridge)               │
└──────────────────────────────────────────────────────────┘
```

## Level 2 – Container: Run Controller internals

```
run_controller.py
─────────────────────────────────────────────────
  execute_run(scenario)
    │
    ├─ for each ScenarioStep
    │    │
    │    ├─ [reachability check] ──► fk_chain.py
    │    │       │
    │    │       ├─ UNREACHABLE ──► emit step_complete(unreachable)  ← ADD LOG
    │    │       │
    │    │       └─ REACHABLE
    │    │             │
    │    │             ├─ ThreadPoolExecutor.submit()               ← ADD LOG
    │    │             │         │
    │    │             │         └─ run_step_executor.py
    │    │             │                 │
    │    │             │                 └─ gz publish / cotton ops
    │    │             │
    │    │             ├─ executor future.result()                  ← ADD LOG
    │    │             │
    │    │             └─ emit step_complete(ok)                    ← ADD LOG
    │
    └─ build run summary                                            ← ADD LOG
         │
         └─ return → testing_backend.py
                        │
                        ├─ emit run_complete                        ← ADD LOG
                        └─ _event_bus.close()                      ← ADD LOG
```
