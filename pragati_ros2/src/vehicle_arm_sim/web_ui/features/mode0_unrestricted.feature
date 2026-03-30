Feature: Mode 0 — Unrestricted (No Collision Avoidance)
  Mode 0 passes all joints through without any modification.
  No j4 gap check, no j5 blocking, no contention detection.
  Both arms always execute in parallel regardless of proximity.

  # -------------------------------------------------------------------
  # Basic passthrough
  # -------------------------------------------------------------------

  Scenario: Joints pass through unchanged when no peer is present
    Given the collision avoidance mode is 0 (unrestricted)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And no peer arm is active
    When the algorithm is applied for arm1
    Then the returned joints are j3=1.0 j4=0.300 j5=0.5
    And skipped is false

  Scenario: Joints pass through unchanged when peer is active and overlapping
    Given the collision avoidance mode is 0 (unrestricted)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And arm2 has joints j3=0.8 j4=0.310 j5=0.4
    When the algorithm is applied for arm1
    Then the returned joints are j3=1.0 j4=0.300 j5=0.5
    And skipped is false

  Scenario: Joints pass through when peer is idle (candidate_joints is None)
    Given the collision avoidance mode is 0 (unrestricted)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And the peer arm is present but idle
    When the algorithm is applied for arm1
    Then the returned joints are j3=1.0 j4=0.300 j5=0.5

  # -------------------------------------------------------------------
  # j4 gap has no effect in Mode 0
  # -------------------------------------------------------------------

  Scenario: j4 gap of 0.01m (far below any threshold) does NOT block j5
    Given the collision avoidance mode is 0 (unrestricted)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And arm2 has joints j3=0.8 j4=0.310 j5=0.4
    When the algorithm is applied for arm1
    Then j5 is not zeroed

  Scenario: j4 gap of exactly 0.0m does NOT block j5
    Given the collision avoidance mode is 0 (unrestricted)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And arm2 has joints j3=0.8 j4=0.300 j5=0.4
    When the algorithm is applied for arm1
    Then j5 is not zeroed

  # -------------------------------------------------------------------
  # j5 edge values
  # -------------------------------------------------------------------

  Scenario: Zero j5 passes through as zero (not modified)
    Given the collision avoidance mode is 0 (unrestricted)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.0
    And arm2 has joints j3=0.8 j4=0.300 j5=0.4
    When the algorithm is applied for arm1
    Then the returned joints are j3=1.0 j4=0.300 j5=0.0

  Scenario: Large j5 extension passes through unchanged
    Given the collision avoidance mode is 0 (unrestricted)
    And arm1 has joints j3=1.0 j4=0.300 j5=1.0
    And arm2 has joints j3=0.8 j4=0.300 j5=1.0
    When the algorithm is applied for arm1
    Then the returned joints are j3=1.0 j4=0.300 j5=1.0
