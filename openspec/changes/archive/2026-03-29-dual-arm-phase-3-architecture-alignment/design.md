## Overview

Phase 3 brings the runtime shape closer to the intended dual-arm architecture. Instead of keeping the
core logic only as in-process replay objects, this phase separates runtime responsibilities more
cleanly, improves peer-state exchange fidelity, and integrates the hackathon flow more directly into
the launched simulation environment.

## C4

```text
                 +----------------------+
                 | UI / Backend         |
                 +----------+-----------+
                            |
                            v
                 +----------------------+
                 | Run Controller Unit   |
                 +----+-------------+----+
                      |             |
                      v             v
             +---------------+  +---------------+
             | Arm1 Runtime   |  | Arm2 Runtime   |
             | separate unit  |  | separate unit  |
             +-------+--------+  +--------+-------+
                     |                    |
                     +--------+  +--------+
                              v  v
                       +------------------+
                       | Peer transport    |
                       +------------------+
```

## Scope

### Must Have
- cleaner runtime separation
- explicit peer-state transport model
- launch/runtime integration for the hackathon flow

### Should Have
- stronger truth-monitor/runtime geometry fidelity

### Could Have
- deeper ROS-native refactoring if needed

### Won't Have
- redesigning the already agreed user-facing flow
