## Execution Plan

| Group | Depends On | Can Parallelize With |
| --- | --- | --- |
| 1 | - | 2, 3, 4 |
| 2 | - | 1, 3, 4 |
| 3 | - | 1, 2, 4 |
| 4 | - | 1, 2, 3 |
| 5 | 1, 2, 3, 4 | - |

### Group 1: [PARALLEL] Geometry Stage 1 screen

- [ ] Write failing tests for the quick end-effector distance screen
- [ ] Run the tests and verify failure
- [ ] Implement the minimal Stage 1 geometry screen
- [ ] Run the tests and commit when green

### Group 2: [PARALLEL] Geometry Stage 2 check

- [ ] Write failing tests for unsafe geometry/link-level cases
- [ ] Run the tests and verify failure
- [ ] Implement the minimal Stage 2 geometry check
- [ ] Run the tests and commit when green

### Group 3: [PARALLEL] Markdown reporting

- [ ] Write failing tests for three-mode Markdown comparison output
- [ ] Run the tests and verify failure
- [ ] Implement the Markdown report
- [ ] Run the tests and commit when green

### Group 4: [PARALLEL] Geometry scenario pack

- [ ] Write failing validation tests for overlap-heavy geometry scenarios
- [ ] Run the tests and verify failure
- [ ] Create the minimal scenario pack for geometry comparison
- [ ] Validate the scenarios and commit when green

### Group 5: [SEQUENTIAL] Release 2 integration

- [ ] Write failing end-to-end tests for `geometry_block`
- [ ] Run the tests and verify failure
- [ ] Integrate Groups 1-4 into the Release 1 platform
- [ ] Verify unrestricted, baseline, and geometry modes run end-to-end
- [ ] Commit Release 2 integration when green
