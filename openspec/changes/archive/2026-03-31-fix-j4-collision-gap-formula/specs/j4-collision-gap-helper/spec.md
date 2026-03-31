## ADDED Requirements

### Requirement: Centralized J4 collision gap computation
The system SHALL provide a `j4_collision_gap(j4_a, j4_b)` function in `collision_math.py` that returns `abs(j4_a + j4_b)` to compute the lateral gap between two opposite-facing arms.

#### Scenario: Same-sign J4 values produce large gap
- **WHEN** both arms have positive J4 values (e.g., j4_a=0.10, j4_b=0.10)
- **THEN** the gap SHALL be abs(0.10 + 0.10) = 0.20

#### Scenario: Opposite-sign J4 values produce small gap
- **WHEN** arms have opposite J4 signs (e.g., j4_a=0.10, j4_b=-0.10)
- **THEN** the gap SHALL be abs(0.10 + (-0.10)) = 0.00

#### Scenario: Gap is symmetric
- **WHEN** j4_collision_gap(a, b) is called
- **THEN** the result SHALL equal j4_collision_gap(b, a)

#### Scenario: Both zero produces zero gap
- **WHEN** both J4 values are 0.0
- **THEN** the gap SHALL be 0.0
