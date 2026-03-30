Feature: Mode 1 — Baseline J5 Block/Skip (Cosine Reach Limit)
  Mode 1 zeros j5 (blocks the pick extension) when the peer arm is active
  and the arm's candidate j5 exceeds the cosine-derived horizontal reach limit:
    J5_limit = 0.20 / cos(|j3|)
  j3 and j4 are never modified.

  # -------------------------------------------------------------------
  # Collision detected — j5 exceeds cosine limit
  # -------------------------------------------------------------------

  Scenario: j5 blocked when arm is vertical and extension exceeds 0.20m
    Given the collision avoidance mode is 1 (baseline_j5_block_skip)
    And arm1 has joints j3=0.0 j4=0.100 j5=0.25
    And arm2 has joints j3=0.0 j4=0.200 j5=0.1
    When the algorithm is applied for arm1
    Then j5 is zeroed
    And j3 is unchanged at 0.0
    And j4 is unchanged at 0.100

  Scenario: j5 blocked when tilted 30 degrees and j5 exceeds cosine limit
    Given the collision avoidance mode is 1 (baseline_j5_block_skip)
    And arm1 has joints j3=0.5236 j4=0.100 j5=0.24
    And arm2 has joints j3=0.0 j4=0.200 j5=0.1
    When the algorithm is applied for arm1
    Then j5 is zeroed

  Scenario: large j5 is zeroed when horizontal reach exceeds limit
    Given the collision avoidance mode is 1 (baseline_j5_block_skip)
    And arm1 has joints j3=0.0 j4=0.100 j5=0.45
    And arm2 has joints j3=0.0 j4=0.200 j5=0.1
    When the algorithm is applied for arm1
    Then j5 is zeroed

  # -------------------------------------------------------------------
  # No collision — j5 within cosine limit
  # -------------------------------------------------------------------

  Scenario: j5 unchanged when arm is vertical and extension is within 0.20m
    Given the collision avoidance mode is 1 (baseline_j5_block_skip)
    And arm1 has joints j3=0.0 j4=0.100 j5=0.19
    And arm2 has joints j3=0.0 j4=0.200 j5=0.1
    When the algorithm is applied for arm1
    Then j5 is not zeroed
    And the returned joints are j3=0.0 j4=0.100 j5=0.19

  Scenario: j5 unchanged at boundary when extension equals limit exactly
    Given the collision avoidance mode is 1 (baseline_j5_block_skip)
    And arm1 has joints j3=0.0 j4=0.100 j5=0.20
    And arm2 has joints j3=0.0 j4=0.200 j5=0.1
    When the algorithm is applied for arm1
    Then j5 is not zeroed

  Scenario: j5 unchanged when tilted 30 degrees and j5 within cosine limit
    Given the collision avoidance mode is 1 (baseline_j5_block_skip)
    And arm1 has joints j3=0.5236 j4=0.100 j5=0.22
    And arm2 has joints j3=0.0 j4=0.200 j5=0.1
    When the algorithm is applied for arm1
    Then j5 is not zeroed

  Scenario: j5 unchanged at near-vertical tilt where cosine limit is very large
    Given the collision avoidance mode is 1 (baseline_j5_block_skip)
    And arm1 has joints j3=0.89 j4=0.100 j5=0.30
    And arm2 has joints j3=0.0 j4=0.200 j5=0.1
    When the algorithm is applied for arm1
    Then j5 is not zeroed

  # -------------------------------------------------------------------
  # No peer — always safe
  # -------------------------------------------------------------------

  Scenario: j5 unchanged when no peer arm is active
    Given the collision avoidance mode is 1 (baseline_j5_block_skip)
    And arm1 has joints j3=0.0 j4=0.100 j5=0.45
    And no peer arm is active
    When the algorithm is applied for arm1
    Then j5 is not zeroed
    And the returned joints are j3=0.0 j4=0.100 j5=0.45

  Scenario: j5 unchanged when peer arm is present but idle
    Given the collision avoidance mode is 1 (baseline_j5_block_skip)
    And arm1 has joints j3=0.0 j4=0.100 j5=0.45
    And the peer arm is present but idle
    When the algorithm is applied for arm1
    Then j5 is not zeroed

  # -------------------------------------------------------------------
  # j5 edge values
  # -------------------------------------------------------------------

  Scenario: j5 already zero remains zero
    Given the collision avoidance mode is 1 (baseline_j5_block_skip)
    And arm1 has joints j3=0.0 j4=0.100 j5=0.0
    And arm2 has joints j3=0.0 j4=0.200 j5=0.1
    When the algorithm is applied for arm1
    Then the returned j5 is 0.0
