Feature: Mode 2 — Geometry Block (Two-Stage Check)
  Mode 2 uses a two-stage geometry evaluation:
    Stage 1: lateral j4 gap < 0.12m → risky (proceed to Stage 2)
    Stage 2: lateral j4 gap < 0.06m AND combined j5 > 0.5 → unsafe (zero j5)
  If Stage 1 is safe, Stage 2 is skipped entirely.

  # -------------------------------------------------------------------
  # Stage 1 SAFE — j4 gap >= 0.12m, Stage 2 skipped
  # -------------------------------------------------------------------

  Scenario: Joints unchanged when stage-1 gap is 0.15m (safe)
    Given the collision avoidance mode is 2 (geometry_block)
    And arm1 has joints j3=1.0 j4=0.100 j5=0.5
    And arm2 has joints j3=0.8 j4=0.250 j5=0.4
    When the algorithm is applied for arm1
    Then j5 is not zeroed
    And the returned joints are j3=1.0 j4=0.100 j5=0.5

  Scenario: Joints unchanged when stage-1 gap is exactly 0.12m (boundary safe)
    Given the collision avoidance mode is 2 (geometry_block)
    And arm1 has joints j3=1.0 j4=0.100 j5=0.5
    And arm2 has joints j3=0.8 j4=0.220 j5=0.4
    When the algorithm is applied for arm1
    Then j5 is not zeroed

  Scenario: Joints unchanged when stage-1 gap is 0.50m (well separated)
    Given the collision avoidance mode is 2 (geometry_block)
    And arm1 has joints j3=1.0 j4=0.100 j5=0.5
    And arm2 has joints j3=0.8 j4=0.600 j5=0.4
    When the algorithm is applied for arm1
    Then j5 is not zeroed

  # -------------------------------------------------------------------
  # Stage 1 RISKY + Stage 2 UNSAFE — j5 zeroed
  # -------------------------------------------------------------------

  Scenario: j5 zeroed when stage-1 risky and stage-2 unsafe
    Given the collision avoidance mode is 2 (geometry_block)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.4
    And arm2 has joints j3=0.8 j4=0.310 j5=0.3
    When the algorithm is applied for arm1
    Then j5 is zeroed
    And j3 is unchanged at 1.0
    And j4 is unchanged at 0.300

  Scenario: j5 zeroed when j4 gap is 0.01m and combined j5 is 0.9
    Given the collision avoidance mode is 2 (geometry_block)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And arm2 has joints j3=0.8 j4=0.310 j5=0.5
    When the algorithm is applied for arm1
    Then j5 is zeroed

  Scenario: j5 zeroed when j4 gap is exactly 0.0m and combined j5 is 0.8
    Given the collision avoidance mode is 2 (geometry_block)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And arm2 has joints j3=0.8 j4=0.300 j5=0.3
    When the algorithm is applied for arm1
    Then j5 is zeroed

  Scenario: j5 zeroed when j4 gap is 0.059m (just under stage-2 lateral) and combined j5 is 0.6
    Given the collision avoidance mode is 2 (geometry_block)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.4
    And arm2 has joints j3=0.8 j4=0.359 j5=0.3
    When the algorithm is applied for arm1
    Then j5 is zeroed

  # -------------------------------------------------------------------
  # Stage 1 RISKY + Stage 2 SAFE — joints unchanged
  # -------------------------------------------------------------------

  Scenario: Joints unchanged when stage-1 risky but stage-2 lateral gap >= 0.06m
    Given the collision avoidance mode is 2 (geometry_block)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And arm2 has joints j3=0.8 j4=0.370 j5=0.5
    When the algorithm is applied for arm1
    Then j5 is not zeroed

  Scenario: Joints unchanged when stage-1 risky but combined j5 <= 0.5
    Given the collision avoidance mode is 2 (geometry_block)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.2
    And arm2 has joints j3=0.8 j4=0.310 j5=0.2
    When the algorithm is applied for arm1
    Then j5 is not zeroed

  Scenario: Joints unchanged when stage-2 lateral gap exactly 0.06m (boundary safe)
    Given the collision avoidance mode is 2 (geometry_block)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And arm2 has joints j3=0.8 j4=0.360 j5=0.5
    When the algorithm is applied for arm1
    Then j5 is not zeroed

  Scenario: Joints unchanged when combined j5 exactly 0.5 (boundary safe)
    Given the collision avoidance mode is 2 (geometry_block)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.25
    And arm2 has joints j3=0.8 j4=0.310 j5=0.25
    When the algorithm is applied for arm1
    Then j5 is not zeroed

  # -------------------------------------------------------------------
  # No peer — always safe
  # -------------------------------------------------------------------

  Scenario: Joints unchanged when no peer arm is active
    Given the collision avoidance mode is 2 (geometry_block)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And no peer arm is active
    When the algorithm is applied for arm1
    Then j5 is not zeroed

  Scenario: Joints unchanged when peer arm is present but idle
    Given the collision avoidance mode is 2 (geometry_block)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And the peer arm is present but idle
    When the algorithm is applied for arm1
    Then j5 is not zeroed

  # -------------------------------------------------------------------
  # j5 edge values
  # -------------------------------------------------------------------

  Scenario: j5 already zero is not modified even in unsafe zone
    Given the collision avoidance mode is 2 (geometry_block)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.0
    And arm2 has joints j3=0.8 j4=0.310 j5=0.6
    When the algorithm is applied for arm1
    Then the returned j5 is 0.0

  Scenario: Both arms zero j5 combined extension is 0.0 — stage-2 safe
    Given the collision avoidance mode is 2 (geometry_block)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.0
    And arm2 has joints j3=0.8 j4=0.310 j5=0.0
    When the algorithm is applied for arm1
    Then j5 is not zeroed
