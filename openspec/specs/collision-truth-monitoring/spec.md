## ADDED Requirements

### Requirement: Record Near-Collision And Collision Truth

The system SHALL record near-collision and collision outcomes independently from planner decisions.

#### Scenario: Truth monitor records minimum distance during step
- **WHEN** a step is executing
- **THEN** the truth monitor records actual minimum distance and threshold crossings
