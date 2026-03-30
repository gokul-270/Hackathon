# C4 Component Diagram — Run All Modes Comparison

## Level 2: Container Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Testing Web UI (Browser)                      │
│                                                                      │
│  ┌────────────────────┐   ┌──────────────────────────────────────┐  │
│  │  "Run All Modes"   │──▶│  setupRunAllModes() — JS handler     │  │
│  │   Button (HTML)    │   │  - resolves scenario (file/preset)   │  │
│  └────────────────────┘   │  - POST /api/run/start-all-modes     │  │
│                           │  - renders comparison table in modal  │  │
│  ┌────────────────────┐   └──────────────┬───────────────────────┘  │
│  │  Comparison Modal  │◀─────────────────┘                          │
│  │  - colour table    │                                              │
│  │  - recommendation  │   HTTP POST / GET                            │
│  │  - download links  │──────────────────────────────────────────────┤
│  └────────────────────┘                                              │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   FastAPI Backend (port 8081)                         │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  POST /api/run/start-all-modes                                │   │
│  │  ┌─────────────────────────────────────────────────────────┐  │   │
│  │  │  for mode in [0, 1, 2, 3, 4]:                           │  │   │
│  │  │    controller = RunController(mode, executor=None)       │  │   │
│  │  │    controller.load_scenario(scenario)                    │  │   │
│  │  │    summary = controller.run()  ← dry-run, no Gazebo     │  │   │
│  │  │    summaries.append(summary)                             │  │   │
│  │  └─────────────────────────────────────────────────────────┘  │   │
│  │                         │                                      │   │
│  │                         ▼                                      │   │
│  │  ┌─────────────────────────────────────────────────────────┐  │   │
│  │  │  MarkdownReporter.generate(summaries)                   │  │   │
│  │  │  → comparison table + recommendation                    │  │   │
│  │  └─────────────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  GET /api/run/report/all-modes/json      → 5 summaries JSON         │
│  GET /api/run/report/all-modes/markdown  → comparison markdown       │
└──────────────────────────────────────────────────────────────────────┘
```

## Level 3: Component Interactions

```
Browser                   FastAPI Backend             Existing Modules
───────                   ──────────────             ────────────────

  "Run All Modes" click
        │
        ▼
  POST /api/run/start-all-modes
  {scenario, arm_pair,    ──────▶  AllModesStartRequest
   enable_phi_comp}                        │
                                           ▼
                                  ┌─ mode 0 ─────────────┐
                                  │  RunController(0)     │──▶ BaselineMode
                                  │  .load_scenario()     │──▶ ArmRuntime
                                  │  .run() → summary_0   │──▶ TruthMonitor
                                  └───────────────────────┘──▶ JsonReporter
                                           │
                                  ┌─ mode 1 ─────────────┐
                                  │  RunController(1)     │──▶ (same)
                                  │  .run() → summary_1   │
                                  └───────────────────────┘
                                           │
                                       ... (modes 2-4)
                                           │
                                           ▼
                                  MarkdownReporter.generate(
                                    [summary_0..summary_4]
                                  )
                                           │
                                           ▼
                                  {status, summaries[5],
                                   comparison_markdown,
  ◀────────────────────────────    recommendation}
        │
        ▼
  renderComparisonTable()
  → modal with colour table
```
