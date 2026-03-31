Feature: Mode 3 — Sequential Pick (Contention Arbitration)
  Mode 3 detects contention when both arms are extending (j5 > 0) and the
  j4 gap is below 0.110m. On contention, the winner arm is dispatched first,
  then the loser. Winner alternates each contention step (arm1 first, then arm2).
  Both arms always receive unmodified joints — dispatch order is the intervention.

  # -------------------------------------------------------------------
  # Contention detected — j4 gap BELOW 0.110m, both arms extending
  # -------------------------------------------------------------------

  Scenario: Contention detected when j4 gap is 0.05m and both arms extend
    Given the collision avoidance mode is 3 (sequential_pick)
    And arm1 has joints j3=1.0 j4=0.050 j5=0.3
    And arm2 has joints j3=0.8 j4=-0.030 j5=0.4
    When the policy evaluates contention for step 0
    Then contention is detected
    And joints are returned unchanged

  Scenario: Contention detected when j4 gap is 0.01m
    Given the collision avoidance mode is 3 (sequential_pick)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And arm2 has joints j3=0.8 j4=-0.310 j5=0.4
    When the policy evaluates contention for step 0
    Then contention is detected

  Scenario: Contention detected when j4 gap is exactly 0.0m
    Given the collision avoidance mode is 3 (sequential_pick)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And arm2 has joints j3=0.8 j4=-0.300 j5=0.4
    When the policy evaluates contention for step 0
    Then contention is detected

  Scenario: Contention detected when j4 gap is 0.109m (just below threshold)
    Given the collision avoidance mode is 3 (sequential_pick)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And arm2 has joints j3=0.8 j4=-0.409 j5=0.4
    When the policy evaluates contention for step 0
    Then contention is detected

  # -------------------------------------------------------------------
  # No contention — j4 gap AT or ABOVE 0.110m
  # -------------------------------------------------------------------

  Scenario: No contention when j4 gap is 0.15m (above threshold)
    Given the collision avoidance mode is 3 (sequential_pick)
    And arm1 has joints j3=1.0 j4=0.100 j5=0.5
    And arm2 has joints j3=0.8 j4=-0.250 j5=0.4
    When the policy evaluates contention for step 0
    Then no contention is detected
    And joints are returned unchanged

  Scenario: No contention when j4 gap is exactly 0.110m (boundary — at threshold)
    Given the collision avoidance mode is 3 (sequential_pick)
    And arm1 has joints j3=1.0 j4=0.050 j5=0.5
    And arm2 has joints j3=0.8 j4=-0.160 j5=0.4
    When the policy evaluates contention for step 0
    Then no contention is detected

  Scenario: No contention when j4 gap is 0.50m (well separated)
    Given the collision avoidance mode is 3 (sequential_pick)
    And arm1 has joints j3=1.0 j4=0.100 j5=0.5
    And arm2 has joints j3=0.8 j4=-0.600 j5=0.4
    When the policy evaluates contention for step 0
    Then no contention is detected

  # -------------------------------------------------------------------
  # No contention — j5 not extending
  # -------------------------------------------------------------------

  Scenario: No contention when own arm j5 is zero (not extending)
    Given the collision avoidance mode is 3 (sequential_pick)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.0
    And arm2 has joints j3=0.8 j4=-0.310 j5=0.4
    When the policy evaluates contention for step 0
    Then no contention is detected

  Scenario: No contention when peer arm j5 is zero (not extending)
    Given the collision avoidance mode is 3 (sequential_pick)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And arm2 has joints j3=0.8 j4=-0.310 j5=0.0
    When the policy evaluates contention for step 0
    Then no contention is detected

  Scenario: No contention when both arms j5 is zero
    Given the collision avoidance mode is 3 (sequential_pick)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.0
    And arm2 has joints j3=0.8 j4=-0.310 j5=0.0
    When the policy evaluates contention for step 0
    Then no contention is detected

  # -------------------------------------------------------------------
  # No peer — always safe
  # -------------------------------------------------------------------

  Scenario: No contention when no peer arm is active
    Given the collision avoidance mode is 3 (sequential_pick)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And no peer arm is active
    When the policy evaluates contention for step 0 with no peer
    Then no contention is detected
    And skipped is false

  # -------------------------------------------------------------------
  # Winner/loser turn alternation
  # -------------------------------------------------------------------

  Scenario: arm1 wins the first contention step
    Given the collision avoidance mode is 3 (sequential_pick)
    And a fresh sequential pick policy
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And arm2 has joints j3=0.8 j4=-0.310 j5=0.4
    When arm1 is evaluated for contention at step 0
    Then arm1 is the winner

  Scenario: arm2 is the loser at the first contention step
    Given the collision avoidance mode is 3 (sequential_pick)
    And a fresh sequential pick policy
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And arm2 has joints j3=0.8 j4=-0.310 j5=0.4
    When arm1 is evaluated for contention at step 0
    And arm2 is evaluated for contention at step 0
    Then arm2 is the loser

  Scenario: Winner alternates to arm2 on second contention step
    Given the collision avoidance mode is 3 (sequential_pick)
    And a fresh sequential pick policy
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And arm2 has joints j3=0.8 j4=-0.310 j5=0.4
    When arm1 wins step 0 and arm2 loses step 0
    And arm1 is evaluated for contention at step 1
    Then arm1 is the loser at step 1

  Scenario: Winner alternates back to arm1 on third contention step
    Given the collision avoidance mode is 3 (sequential_pick)
    And a fresh sequential pick policy
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And arm2 has joints j3=0.8 j4=-0.310 j5=0.4
    When three contention steps are processed
    Then the winners alternate as arm1 arm2 arm1

  # -------------------------------------------------------------------
  # Joints always pass through unchanged (policy does NOT modify)
  # -------------------------------------------------------------------

  Scenario: Winner arm receives unmodified joints
    Given the collision avoidance mode is 3 (sequential_pick)
    And a fresh sequential pick policy
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And arm2 has joints j3=0.8 j4=-0.310 j5=0.4
    When arm1 is evaluated for contention at step 0
    Then the returned joints for arm1 are j3=1.0 j4=0.300 j5=0.5

  Scenario: Loser arm also receives unmodified joints
    Given the collision avoidance mode is 3 (sequential_pick)
    And a fresh sequential pick policy
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And arm2 has joints j3=0.8 j4=-0.310 j5=0.4
    When arm1 is evaluated for contention at step 0
    And arm2 is evaluated for contention at step 0
    Then the returned joints for arm2 are j3=0.8 j4=-0.310 j5=0.4

  Scenario: Skipped is always false even during contention
    Given the collision avoidance mode is 3 (sequential_pick)
    And a fresh sequential pick policy
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And arm2 has joints j3=0.8 j4=-0.310 j5=0.4
    When arm1 is evaluated for contention at step 0
    Then skipped is false
