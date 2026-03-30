Feature: Mode 4 — Smart Reorder (Pre-Run Step Rearrangement)
  Mode 4 rearranges cotton picking order BEFORE execution to maximize the
  minimum j4 gap across paired steps. Per-step mode logic is pure passthrough.
  FK formula: j4 = 0.1005 - cam_z.

  # -------------------------------------------------------------------
  # Per-step passthrough (algorithm does nothing at step level)
  # -------------------------------------------------------------------

  Scenario: Joints pass through unchanged during step execution
    Given the collision avoidance mode is 4 (smart_reorder)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And arm2 has joints j3=0.8 j4=0.310 j5=0.4
    When the algorithm is applied for arm1
    Then the returned joints are j3=1.0 j4=0.300 j5=0.5
    And skipped is false

  Scenario: Joints pass through unchanged when no peer is active
    Given the collision avoidance mode is 4 (smart_reorder)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And no peer arm is active
    When the algorithm is applied for arm1
    Then the returned joints are j3=1.0 j4=0.300 j5=0.5

  Scenario: Joints pass through with peer idle
    Given the collision avoidance mode is 4 (smart_reorder)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And the peer arm is present but idle
    When the algorithm is applied for arm1
    Then the returned joints are j3=1.0 j4=0.300 j5=0.5

  # -------------------------------------------------------------------
  # FK formula: j4 = 0.1005 - cam_z
  # -------------------------------------------------------------------

  Scenario: j4 computed correctly from cam_z = 0.10
    Given a smart reorder scheduler
    When j4 is computed from cam_z 0.10
    Then the j4 value is 0.0005

  Scenario: j4 computed correctly from cam_z = 0.05
    Given a smart reorder scheduler
    When j4 is computed from cam_z 0.05
    Then the j4 value is 0.0505

  Scenario: j4 computed correctly from cam_z = 0.0
    Given a smart reorder scheduler
    When j4 is computed from cam_z 0.0
    Then the j4 value is 0.1005

  # -------------------------------------------------------------------
  # Reordering preserves all steps (no data lost or duplicated)
  # -------------------------------------------------------------------

  Scenario: Reorder preserves all step data
    Given a smart reorder scheduler
    And a paired scenario "preserves" with steps (0,arm1,0.10) (0,arm2,0.05) (1,arm1,0.05) (1,arm2,0.10)
    When the scheduler reorders the steps
    Then all original steps are present in the result
    And no steps are duplicated

  # -------------------------------------------------------------------
  # Reordering improves or maintains minimum j4 gap
  # -------------------------------------------------------------------

  Scenario: Reorder improves minimum j4 gap for a bad initial pairing
    Given a smart reorder scheduler
    And a paired scenario "improves" with steps (0,arm1,0.10) (0,arm2,0.10) (1,arm1,0.05) (1,arm2,0.05)
    When the scheduler reorders the steps
    Then the new minimum j4 gap is greater than or equal to the original

  Scenario: Already optimal order is not degraded
    Given a smart reorder scheduler
    And a paired scenario "optimal" with steps (0,arm1,0.02) (0,arm2,0.08) (1,arm1,0.08) (1,arm2,0.02)
    When the scheduler reorders the steps
    Then the new minimum j4 gap is greater than or equal to the original

  # -------------------------------------------------------------------
  # Unequal step counts — solo tail preserved
  # -------------------------------------------------------------------

  Scenario: Solo tail steps preserved when arm1 has more steps
    Given a smart reorder scheduler
    And arm1 has 3 steps and arm2 has 2 steps
    When the scheduler reorders the steps
    Then the result has 3 total step IDs
    And arm1 solo tail step is present after paired steps

  # -------------------------------------------------------------------
  # Brute-force vs greedy algorithm selection
  # -------------------------------------------------------------------

  Scenario: Brute-force used for 5 steps per arm
    Given a smart reorder scheduler
    And a scenario with 5 paired steps per arm
    When the scheduler reorders the steps
    Then the result is globally optimal

  Scenario: Greedy fallback used for 10 steps per arm
    Given a smart reorder scheduler
    And a scenario with 10 paired steps per arm
    When the scheduler reorders the steps
    Then the minimum j4 gap is improved or maintained

  # -------------------------------------------------------------------
  # Single step and empty arm edge cases
  # -------------------------------------------------------------------

  Scenario: Single paired step passes through unchanged
    Given a smart reorder scheduler
    And a paired scenario "single" with steps (0,arm1,0.10) (0,arm2,0.05)
    When the scheduler reorders the steps
    Then the result has 1 total step ID

  Scenario: Empty arm produces solo-only step map
    Given a smart reorder scheduler
    And arm1 has 3 steps and arm2 has 0 steps
    When the scheduler reorders the steps
    Then the result has 3 total step IDs
    And all steps are solo arm1 steps
