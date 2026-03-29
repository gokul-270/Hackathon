## Execution Plan

| Group | Depends On | Can Parallelize With |
| --- | --- | --- |
| 1 | - | 2, 3 |
| 2 | - | 1, 3 |
| 3 | - | 1, 2 |
| 4 | 1, 2, 3 | - |

### Group 1: [PARALLEL] UI controls

- [x] Write failing UI tests for mode select, scenario load/select, and Start Run controls
- [x] Run the tests and verify failure
- [x] Implement the minimal UI controls in `testing_ui.html` and `testing_ui.js`
- [x] Run the tests and commit when green

### Group 2: [PARALLEL] Backend run/report endpoints

- [x] Write failing backend tests for run start, status, JSON report, and Markdown report endpoints
- [x] Run the tests and verify failure
- [x] Implement the minimal endpoints in `testing_backend.py`
- [x] Run the tests and commit when green

### Group 3: [PARALLEL] Replay/report integration

- [x] Write failing integration tests for invoking `RunController` and fetching generated reports
- [x] Run the tests and verify failure
- [x] Integrate the backend with the existing controller and reporters
- [x] Run the tests and commit when green

### Group 4: [SEQUENTIAL] Phase 1 end-to-end UI flow

- [x] Write failing end-to-end tests for scenario run from the UI
- [x] Run the tests and verify failure
- [x] Integrate Groups 1-3 into one visible UI flow
- [x] Verify one scenario can be run end-to-end from the UI with report access
- [x] Commit Phase 1 when green
