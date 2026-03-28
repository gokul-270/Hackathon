## Execution Plan

| Group | Depends On | Can Parallelize With |
| --- | --- | --- |
| 1 | - | 2, 3 |
| 2 | - | 1, 3 |
| 3 | - | 1, 2 |
| 4 | 1, 2, 3 | - |

### Group 1: [PARALLEL] Parser/controller contract alignment

- [ ] Write failing tests for paired-step scenario parsing and controller execution
- [ ] Run the tests and verify failure
- [ ] Implement the minimal contract alignment between parser and controller
- [ ] Run the tests and commit when green

### Group 2: [PARALLEL] Wait-mode corrections

- [ ] Write failing tests that prove wait mode waits before skipping
- [ ] Run the tests and verify failure
- [ ] Implement one consistent timeout model and fix the wait behavior
- [ ] Run the tests and commit when green

### Group 3: [PARALLEL] Recommendation/truth corrections

- [ ] Write failing tests for winner-specific report text and threshold-consistent truth output
- [ ] Run the tests and verify failure
- [ ] Implement the minimal reporting and truth-monitor corrections
- [ ] Run the tests and commit when green

### Group 4: [SEQUENTIAL] Phase 2 correctness integration

- [ ] Write failing end-to-end tests covering the corrected flow
- [ ] Run the tests and verify failure
- [ ] Integrate Groups 1-3 into the working UI-driven replay flow
- [ ] Verify the reported run results are trustworthy
- [ ] Commit Phase 2 when green
