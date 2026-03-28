## Execution Plan

| Group | Depends On | Can Parallelize With |
| --- | --- | --- |
| 1 | - | 2, 3, 4 |
| 2 | - | 1, 3, 4 |
| 3 | - | 1, 2, 4 |
| 4 | - | 1, 2, 3 |
| 5 | 1, 2, 3, 4 | - |

### Group 1: [PARALLEL] Geometry Stage 1 screen

- [x] Write failing tests for the quick end-effector distance screen
- [x] Run the tests and verify failure
- [x] Implement the minimal Stage 1 geometry screen
- [x] Run the tests and commit when green

### Group 2: [PARALLEL] Geometry Stage 2 check

- [x] Write failing tests for unsafe geometry/link-level cases
- [x] Run the tests and verify failure
- [x] Implement the minimal Stage 2 geometry check
- [x] Run the tests and commit when green

### Group 3: [PARALLEL] Markdown reporting

- [x] Write failing tests for three-mode Markdown comparison output
- [x] Run the tests and verify failure
- [x] Implement the Markdown report
- [x] Run the tests and commit when green

### Group 4: [PARALLEL] Geometry scenario pack

- [x] Write failing validation tests for overlap-heavy geometry scenarios
- [x] Run the tests and verify failure
- [x] Create the minimal scenario pack for geometry comparison
- [x] Validate the scenarios and commit when green

### Group 5: [SEQUENTIAL] Release 2 integration

- [x] Write failing end-to-end tests for `geometry_block`
- [x] Run the tests and verify failure
- [x] Integrate Groups 1-4 into the Release 1 platform
- [x] Verify unrestricted, baseline, and geometry modes run end-to-end
- [x] Commit Release 2 integration when green
