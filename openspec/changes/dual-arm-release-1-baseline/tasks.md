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

- [ ] Write failing parser/validation tests for shared scenario JSON
- [ ] Run the tests and verify failure
- [ ] Implement minimal parser and validation rules
- [ ] Run the tests and verify pass
- [ ] Commit when green

### Group 2: [PARALLEL] Distributed arm runtime

- [ ] Write failing tests for per-arm runtime loading and own-arm filtering
- [ ] Run the tests and verify failure
- [ ] Implement minimal separate arm-node runtime flow
- [ ] Add peer-state publication with current/candidate joints
- [ ] Run the tests and commit when green

### Group 3: [PARALLEL] Baseline mode layer

- [ ] Write failing tests for `unrestricted` and `baseline_j5_block_skip`
- [ ] Run the tests and verify failure
- [ ] Implement the minimal baseline mode interface
- [ ] Run the tests and commit when green

### Group 4: [PARALLEL] Truth monitor MVP

- [ ] Write failing tests for near-collision and collision truth recording
- [ ] Run the tests and verify failure
- [ ] Implement the MVP truth monitor from peer-state inputs
- [ ] Run the tests and commit when green

### Group 5: [PARALLEL] JSON reporting

- [ ] Write failing tests for per-step and per-run JSON output
- [ ] Run the tests and verify failure
- [ ] Implement minimal JSON reporting
- [ ] Run the tests and commit when green

### Group 6: [SEQUENTIAL] Release 1 integration

- [ ] Write failing end-to-end tests for synchronized paired and solo-tail execution
- [ ] Run the tests and verify failure
- [ ] Implement the central run controller and integrate Groups 1-5
- [ ] Verify `unrestricted` and `baseline_j5_block_skip` run end-to-end
- [ ] Commit Release 1 integration when green
