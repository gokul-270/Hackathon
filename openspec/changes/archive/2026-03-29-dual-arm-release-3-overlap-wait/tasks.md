## Execution Plan

| Group | Depends On | Can Parallelize With |
| --- | --- | --- |
| 1 | - | 2, 3, 4 |
| 2 | - | 1, 3, 4 |
| 3 | - | 1, 2, 4 |
| 4 | - | 1, 2, 3 |
| 5 | 1, 2, 3, 4 | - |

### Group 1: [PARALLEL] Overlap-zone state

- [x] Write failing tests for overlap-zone occupancy and contention detection
- [x] Run the tests and verify failure
- [x] Implement the minimal overlap-zone state model
- [x] Run the tests and commit when green

### Group 2: [PARALLEL] Wait-mode policy

- [x] Write failing tests for alternating-turn arbitration and timeout-driven skip
- [x] Run the tests and verify failure
- [x] Implement the wait-mode policy with fixed timeout per pick
- [x] Run the tests and commit when green

### Group 3: [PARALLEL] Final reporting

- [x] Write failing tests for blocked+skipped summary merging and recommendation logic
- [x] Run the tests and verify failure
- [x] Implement the final report summary and recommendation rules
- [x] Run the tests and commit when green

### Group 4: [PARALLEL] Contention scenario pack

- [x] Write failing validation tests for contention-heavy wait scenarios
- [x] Run the tests and verify failure
- [x] Create the minimal contention scenario pack
- [x] Validate the scenarios and commit when green

### Group 5: [SEQUENTIAL] Release 3 integration

- [x] Write failing end-to-end tests for `overlap_zone_wait`
- [x] Run the tests and verify failure
- [x] Integrate Groups 1-4 into the Release 2 platform
- [x] Verify all four modes run end-to-end on the same scenario set
- [x] Commit Release 3 integration when green
