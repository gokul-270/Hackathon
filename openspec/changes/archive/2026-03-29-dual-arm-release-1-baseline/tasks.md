## Execution Plan

| Group | Depends On | Can Parallelize With |
| --- | --- | --- |
| 1 | - | 2, 3, 4, 5 |
| 2 | - | 1, 3, 4, 5 |
| 3 | - | 1, 2, 4, 5 |
| 4 | - | 1, 2, 3, 5 |
| 5 | - | 1, 2, 3, 4 |
| 6 | 1, 2, 3, 4, 5 | - |

### Group 1: [PARALLEL] Scenario JSON contract

- [x] Write failing parser/validation tests for shared scenario JSON
- [x] Run the tests and verify failure
- [x] Implement minimal parser and validation rules
- [x] Run the tests and verify pass
- [x] Commit when green

### Group 2: [PARALLEL] Distributed arm runtime

- [x] Write failing tests for per-arm runtime loading and own-arm filtering
- [x] Run the tests and verify failure
- [x] Implement minimal separate arm-node runtime flow
- [x] Add peer-state publication with current/candidate joints
- [x] Run the tests and commit when green

### Group 3: [PARALLEL] Baseline mode layer

- [x] Write failing tests for `unrestricted` and `baseline_j5_block_skip`
- [x] Run the tests and verify failure
- [x] Implement the minimal baseline mode interface
- [x] Run the tests and commit when green

### Group 4: [PARALLEL] Truth monitor MVP

- [x] Write failing tests for near-collision and collision truth recording
- [x] Run the tests and verify failure
- [x] Implement the MVP truth monitor from peer-state inputs
- [x] Run the tests and commit when green

### Group 5: [PARALLEL] JSON reporting

- [x] Write failing tests for per-step and per-run JSON output
- [x] Run the tests and verify failure
- [x] Implement minimal JSON reporting
- [x] Run the tests and commit when green

### Group 6: [SEQUENTIAL] Release 1 integration

- [x] Write failing end-to-end tests for synchronized paired and solo-tail execution
- [x] Run the tests and verify failure
- [x] Implement the central run controller and integrate Groups 1-5
- [x] Verify `unrestricted` and `baseline_j5_block_skip` run end-to-end
- [x] Commit Release 1 integration when green
