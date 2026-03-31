# Spec: Sequential Pick Policy

## Purpose

Defines the sequential pick contention detection, turn alternation, and joint pass-through logic used by Mode 3 (sequential_pick).
## Requirements
### Requirement: Detect Contention Between Arms At Paired Steps

The sequential pick policy SHALL detect contention when both arms are active at a paired step and the absolute j4 gap is less than 0.10 m.

#### Scenario: Contention detected when j4 gap below threshold

- **GIVEN** both arms are active at a paired step
- **WHEN** the absolute difference between own j4 and peer j4 is less than 0.10 m
- **AND** both arms have j5 greater than 0
- **THEN** the policy reports contention for that step

#### Scenario: No contention when j4 gap at or above threshold

- **GIVEN** both arms are active at a paired step
- **WHEN** the absolute difference between own j4 and peer j4 is 0.10 m or greater
- **THEN** the policy reports no contention and passes joints through unchanged

#### Scenario: No contention when peer is not extending

- **GIVEN** both arms are active at a paired step
- **WHEN** the j4 gap is below 0.10 m but the peer arm has j5 equal to 0
- **THEN** the policy reports no contention and passes joints through unchanged

#### Scenario: No contention when no peer is active

- **GIVEN** only one arm is active at a solo step
- **WHEN** the policy is applied with no peer joints
- **THEN** the policy passes joints through unchanged with skipped equal to False

### Requirement: Alternate Winner Turn Between Arms

The sequential pick policy SHALL alternate the winner arm across contention steps. The first contention step SHALL be won by arm1, the second by arm2, and so on.

#### Scenario: Arm1 wins first contention step

- **GIVEN** this is the first contention step in the run
- **WHEN** both arms contend at the same step
- **THEN** arm1 is designated the winner and arm2 is designated the loser

#### Scenario: Turn alternates after each contention step

- **GIVEN** arm1 won the previous contention step
- **WHEN** a new contention step is encountered
- **THEN** arm2 is designated the winner and arm1 is designated the loser

#### Scenario: Turn is locked for both arms within a single step

- **GIVEN** a contention step where arm1 and arm2 are both processed
- **WHEN** the policy is called for arm1 and then for arm2 at the same step_id
- **THEN** both calls see the same turn value so exactly one arm wins

### Requirement: Winner Arm Joints Pass Through Unchanged

The sequential pick policy SHALL pass the winner arm's candidate joints through without modification.

#### Scenario: Winner arm receives unmodified joints

- **GIVEN** contention is detected at a paired step
- **WHEN** the policy is applied for the winner arm
- **THEN** applied joints equal the candidate joints with no modifications
- **AND** skipped is False

### Requirement: Loser Arm Joints Pass Through For Deferred Dispatch

The sequential pick policy SHALL pass the loser arm's candidate joints through unchanged (not zeroed). The RunController is responsible for deferring the loser arm's dispatch — the policy itself does not block or skip the loser.

#### Scenario: Loser arm receives unmodified joints with contention flag

- **GIVEN** contention is detected at a paired step
- **WHEN** the policy is applied for the loser arm
- **THEN** applied joints equal the candidate joints with no modifications
- **AND** skipped is False
- **AND** the policy indicates this arm is the loser for this step

### Requirement: Contention detection uses opposite-facing J4 formula
The sequential pick policy SHALL compute J4 gap for contention detection using `j4_collision_gap(own_j4, peer_j4)` from `collision_math` instead of inline `abs(own_j4 - peer_j4)`.

#### Scenario: Contention gap computed with opposite-facing formula
- **WHEN** sequential pick policy evaluates own and peer J4 for contention
- **THEN** gap SHALL be `j4_collision_gap(own_j4, peer_j4)` which returns `abs(own_j4 + peer_j4)`

#### Scenario: No contention when arms are far apart
- **WHEN** own_j4=0.0 and peer_j4=-0.20 (arms far apart in world frame)
- **THEN** gap SHALL be abs(0.0 + (-0.20)) = 0.20 which exceeds the contention threshold

