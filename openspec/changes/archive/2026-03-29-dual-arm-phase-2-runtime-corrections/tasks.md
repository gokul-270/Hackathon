## Execution Plan

| Group | Depends On | Can Parallelize With |
| --- | --- | --- |
| 1 | - | 2, 3 |
| 2 | - | 1, 3 |
| 3 | - | 1, 2 |
| 4 | 1, 2, 3 | - |

### Group 1: [PARALLEL] Parser/controller contract alignment

- [x] Write failing tests for paired-step scenario parsing and controller execution
- [x] Run the tests and verify failure
- [x] Implement the minimal contract alignment between parser and controller
- [x] Run the tests and commit when green

### Group 2: [PARALLEL] Wait-mode corrections

- [x] Write failing tests that prove wait mode waits before skipping
- [x] Run the tests and verify failure
- [x] Implement one consistent timeout model and fix the wait behavior
- [x] Run the tests and commit when green

### Group 3: [PARALLEL] Recommendation/truth corrections

- [x] Write failing tests for winner-specific report text and threshold-consistent truth output
- [x] Run the tests and verify failure
- [x] Implement the minimal reporting and truth-monitor corrections
- [x] Run the tests and commit when green

### Group 4: [SEQUENTIAL] Phase 2 correctness integration

- [x] Write failing end-to-end tests covering the corrected flow
- [x] Run the tests and verify failure
- [x] Integrate Groups 1-3 into the working UI-driven replay flow
- [x] Verify the reported run results are trustworthy
- [x] Commit Phase 2 when green
