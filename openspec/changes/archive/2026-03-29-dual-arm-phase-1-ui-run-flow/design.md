## Overview

Phase 1 makes the existing dual-arm replay flow usable from the testing UI. The UI gains controls for
mode selection and scenario JSON input, the backend exposes run-control/report endpoints, and the
existing replay/reporting logic is connected so the user can run a scenario and access a final report
without manual Python or test harness steps.

## User Journey

```text
Open UI
  -> choose mode
  -> load/select scenario JSON
  -> press Start Run
  -> backend starts controller
  -> run status updates in UI
  -> run completes
  -> JSON + Markdown reports are available
```

## C4

```text
                   +----------------------+
                   | UI                   |
                   | mode/file/start      |
                   +----------+-----------+
                              |
                              v
                   +----------------------+
                   | FastAPI Backend      |
                   | run/report API       |
                   +----------+-----------+
                              |
                              v
                   +----------------------+
                   | RunController        |
                   | existing replay core |
                   +----------+-----------+
                              |
                              v
                   +----------------------+
                   | Reports              |
                   | JSON + Markdown      |
                   +----------------------+
```

## Scope

### Must Have
- mode selector in UI
- scenario JSON load/select control
- start-run action in UI
- backend endpoint to run a scenario
- backend endpoint to fetch status
- backend endpoints to fetch JSON and Markdown reports
- report summary visible or linked in UI

### Should Have
- clear run progress state
- clean reset after completion

### Could Have
- nicer report rendering inside the page

### Won't Have
- architecture refactor
- deeper correctness repairs beyond what is needed to make the flow usable
