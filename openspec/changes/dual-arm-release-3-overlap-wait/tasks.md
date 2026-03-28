## Execution Plan

| Group | Depends On | Can Parallelize With |
| --- | --- | --- |
| 1 | - | 2, 3, 4 |
| 2 | - | 1, 3, 4 |
| 3 | - | 1, 2, 4 |
| 4 | - | 1, 2, 3 |
| 5 | 1, 2, 3, 4 | - |

### Group 1: [PARALLEL] Overlap-zone state

- [ ] Write failing tests for overlap-zone occupancy and contention detection
- [ ] Run the tests and verify failure
- [ ] Implement the minimal overlap-zone state model
- [ ] Run the tests and commit when green

### Group 2: [PARALLEL] Wait-mode policy

- [ ] Write failing tests for alternating-turn arbitration and timeout-driven skip
- [ ] Run the tests and verify failure
- [ ] Implement the wait-mode policy with fixed timeout per pick
- [ ] Run the tests and commit when green

### Group 3: [PARALLEL] Final reporting

- [ ] Write failing tests for blocked+skipped summary merging and recommendation logic
- [ ] Run the tests and verify failure
- [ ] Implement the final report summary and recommendation rules
- [ ] Run the tests and commit when green

### Group 4: [PARALLEL] Contention scenario pack

- [ ] Write failing validation tests for contention-heavy wait scenarios
- [ ] Run the tests and verify failure
- [ ] Create the minimal contention scenario pack
- [ ] Validate the scenarios and commit when green

### Group 5: [SEQUENTIAL] Release 3 integration

- [ ] Write failing end-to-end tests for `overlap_zone_wait`
- [ ] Run the tests and verify failure
- [ ] Integrate Groups 1-4 into the Release 2 platform
- [ ] Verify all four modes run end-to-end on the same scenario set
- [ ] Commit Release 3 integration when green
