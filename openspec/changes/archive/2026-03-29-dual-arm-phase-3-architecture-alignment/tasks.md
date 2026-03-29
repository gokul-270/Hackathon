## Execution Plan

| Group | Depends On | Can Parallelize With |
| --- | --- | --- |
| 1 | - | 2, 3 |
| 2 | - | 1, 3 |
| 3 | - | 1, 2 |
| 4 | 1, 2, 3 | - |

### Group 1: [PARALLEL] Runtime separation

- [x] Write failing tests or launch checks for separated runtime responsibilities
- [x] Run them and verify failure
- [x] Implement the minimal separation needed for arm/runtime roles
- [x] Run checks and commit when green

### Group 2: [PARALLEL] Peer-state transport alignment

- [x] Write failing tests/checks for explicit peer-state transport
- [x] Run them and verify failure
- [x] Implement the chosen transport path for peer-state exchange
- [x] Run checks and commit when green

### Group 3: [PARALLEL] Launch/runtime integration

- [x] Write failing integration checks for launch/runtime hookup
- [x] Run them and verify failure
- [x] Integrate the hackathon runtime flow into startup/launch
- [x] Run checks and commit when green

### Group 4: [SEQUENTIAL] Phase 3 architecture integration

- [x] Write failing end-to-end checks for the aligned runtime architecture
- [x] Run them and verify failure
- [x] Integrate Groups 1-3 and verify the launched system matches the intended architecture more closely
- [x] Commit Phase 3 when green
