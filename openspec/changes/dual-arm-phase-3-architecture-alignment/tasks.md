## Execution Plan

| Group | Depends On | Can Parallelize With |
| --- | --- | --- |
| 1 | - | 2, 3 |
| 2 | - | 1, 3 |
| 3 | - | 1, 2 |
| 4 | 1, 2, 3 | - |

### Group 1: [PARALLEL] Runtime separation

- [ ] Write failing tests or launch checks for separated runtime responsibilities
- [ ] Run them and verify failure
- [ ] Implement the minimal separation needed for arm/runtime roles
- [ ] Run checks and commit when green

### Group 2: [PARALLEL] Peer-state transport alignment

- [ ] Write failing tests/checks for explicit peer-state transport
- [ ] Run them and verify failure
- [ ] Implement the chosen transport path for peer-state exchange
- [ ] Run checks and commit when green

### Group 3: [PARALLEL] Launch/runtime integration

- [ ] Write failing integration checks for launch/runtime hookup
- [ ] Run them and verify failure
- [ ] Integrate the hackathon runtime flow into startup/launch
- [ ] Run checks and commit when green

### Group 4: [SEQUENTIAL] Phase 3 architecture integration

- [ ] Write failing end-to-end checks for the aligned runtime architecture
- [ ] Run them and verify failure
- [ ] Integrate Groups 1-3 and verify the launched system matches the intended architecture more closely
- [ ] Commit Phase 3 when green
