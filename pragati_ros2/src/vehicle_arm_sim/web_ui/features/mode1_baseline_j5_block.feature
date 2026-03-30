Feature: Mode 1 — Baseline J5 Block/Skip
  Mode 1 zeros j5 (blocks the pick extension) when the peer arm is active
  and the lateral j4 gap is below 0.05m. j3 and j4 are never modified.

  # -------------------------------------------------------------------
  # Collision detected — j4 gap BELOW 0.05m threshold
  # -------------------------------------------------------------------

  Scenario: j5 blocked when j4 gap is 0.040m (below 0.05m)
    Given the collision avoidance mode is 1 (baseline_j5_block_skip)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And arm2 has joints j3=0.8 j4=0.340 j5=0.4
    When the algorithm is applied for arm1
    Then j5 is zeroed
    And j3 is unchanged at 1.0
    And j4 is unchanged at 0.300

  Scenario: j5 blocked when j4 gap is 0.01m (well below threshold)
    Given the collision avoidance mode is 1 (baseline_j5_block_skip)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And arm2 has joints j3=0.8 j4=0.310 j5=0.4
    When the algorithm is applied for arm1
    Then j5 is zeroed

  Scenario: j5 blocked when j4 gap is exactly 0.0m (identical positions)
    Given the collision avoidance mode is 1 (baseline_j5_block_skip)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And arm2 has joints j3=0.8 j4=0.300 j5=0.4
    When the algorithm is applied for arm1
    Then j5 is zeroed

  Scenario: j5 blocked when j4 gap is 0.049m (just below threshold)
    Given the collision avoidance mode is 1 (baseline_j5_block_skip)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And arm2 has joints j3=0.8 j4=0.349 j5=0.4
    When the algorithm is applied for arm1
    Then j5 is zeroed

  Scenario: j5 blocked when arm2 j4 is less than arm1 j4 (negative gap)
    Given the collision avoidance mode is 1 (baseline_j5_block_skip)
    And arm1 has joints j3=1.0 j4=0.340 j5=0.5
    And arm2 has joints j3=0.8 j4=0.300 j5=0.4
    When the algorithm is applied for arm1
    Then j5 is zeroed

  # -------------------------------------------------------------------
  # No collision — j4 gap AT or ABOVE 0.05m threshold
  # -------------------------------------------------------------------

  Scenario: j5 unchanged when j4 gap is 0.060m (above 0.05m)
    Given the collision avoidance mode is 1 (baseline_j5_block_skip)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And arm2 has joints j3=0.8 j4=0.360 j5=0.4
    When the algorithm is applied for arm1
    Then j5 is not zeroed
    And the returned joints are j3=1.0 j4=0.300 j5=0.5

  Scenario: j5 unchanged when j4 gap is exactly 0.05m (boundary — at threshold)
    Given the collision avoidance mode is 1 (baseline_j5_block_skip)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And arm2 has joints j3=0.8 j4=0.351 j5=0.4
    When the algorithm is applied for arm1
    Then j5 is not zeroed

  Scenario: j5 unchanged when j4 gap is 0.200m (well above threshold)
    Given the collision avoidance mode is 1 (baseline_j5_block_skip)
    And arm1 has joints j3=1.0 j4=0.100 j5=0.5
    And arm2 has joints j3=0.8 j4=0.300 j5=0.4
    When the algorithm is applied for arm1
    Then j5 is not zeroed

  # -------------------------------------------------------------------
  # No peer — always safe
  # -------------------------------------------------------------------

  Scenario: j5 unchanged when no peer arm is active
    Given the collision avoidance mode is 1 (baseline_j5_block_skip)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And no peer arm is active
    When the algorithm is applied for arm1
    Then j5 is not zeroed
    And the returned joints are j3=1.0 j4=0.300 j5=0.5

  Scenario: j5 unchanged when peer arm is present but idle
    Given the collision avoidance mode is 1 (baseline_j5_block_skip)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And the peer arm is present but idle
    When the algorithm is applied for arm1
    Then j5 is not zeroed

  # -------------------------------------------------------------------
  # j5 edge values
  # -------------------------------------------------------------------

  Scenario: j5 already zero remains zero even below threshold
    Given the collision avoidance mode is 1 (baseline_j5_block_skip)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.0
    And arm2 has joints j3=0.8 j4=0.310 j5=0.4
    When the algorithm is applied for arm1
    Then the returned j5 is 0.0

  Scenario: Large j5 is zeroed when below threshold
    Given the collision avoidance mode is 1 (baseline_j5_block_skip)
    And arm1 has joints j3=1.0 j4=0.300 j5=1.0
    And arm2 has joints j3=0.8 j4=0.310 j5=0.4
    When the algorithm is applied for arm1
    Then j5 is zeroed
