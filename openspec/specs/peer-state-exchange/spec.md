## ADDED Requirements

### Requirement: Publish Current And Candidate Joints

Each arm node SHALL publish its current and candidate joints with step-aware status so the peer arm
can consume them for local decisions.

#### Scenario: Peer-state packet published per active step
- **WHEN** an arm computes a candidate motion for the active step
- **THEN** it publishes a peer-state packet including current and candidate joints
