Feature: Cross-Mode Algorithm Comparison
  Verifies behaviour across all five modes on the same scenario data,
  ensuring mode numbering, naming, and relative safety guarantees hold.

  # -------------------------------------------------------------------
  # Mode constants and naming
  # -------------------------------------------------------------------

  Scenario: Mode constant UNRESTRICTED is 0
    Then the BaselineMode.UNRESTRICTED constant equals 0

  Scenario: Mode constant BASELINE_J5_BLOCK_SKIP is 1
    Then the BaselineMode.BASELINE_J5_BLOCK_SKIP constant equals 1

  Scenario: Mode constant GEOMETRY_BLOCK is 2
    Then the BaselineMode.GEOMETRY_BLOCK constant equals 2

  Scenario: Mode constant SEQUENTIAL_PICK is 3
    Then the BaselineMode.SEQUENTIAL_PICK constant equals 3

  Scenario: Mode constant SMART_REORDER is 4
    Then the BaselineMode.SMART_REORDER constant equals 4

  Scenario: Unknown mode raises ValueError
    Given the collision avoidance mode is 99 (unknown)
    And arm1 has joints j3=1.0 j4=0.300 j5=0.5
    And no peer arm is active
    When the algorithm is applied and an error is expected
    Then a ValueError is raised with message containing "Unknown mode"

  # -------------------------------------------------------------------
  # All five modes complete a full run without error
  # -------------------------------------------------------------------

  Scenario: Mode 0 completes a full run
    Given a contention scenario with both arms at cam_z 0.10
    And the run mode is 0
    When RunController executes the full run
    Then the run completes without error
    And the summary mode name is "unrestricted"

  Scenario: Mode 1 completes a full run
    Given a contention scenario with both arms at cam_z 0.10
    And the run mode is 1
    When RunController executes the full run
    Then the run completes without error
    And the summary mode name is "baseline_j5_block_skip"

  Scenario: Mode 2 completes a full run
    Given a contention scenario with both arms at cam_z 0.10
    And the run mode is 2
    When RunController executes the full run
    Then the run completes without error
    And the summary mode name is "geometry_block"

  Scenario: Mode 3 completes a full run
    Given a contention scenario with both arms at cam_z 0.10
    And the run mode is 3
    When RunController executes the full run
    Then the run completes without error
    And the summary mode name is "sequential_pick"

  Scenario: Mode 4 completes a full run
    Given a contention scenario with both arms at cam_z 0.10
    And the run mode is 4
    When RunController executes the full run
    Then the run completes without error
    And the summary mode name is "smart_reorder"

  # -------------------------------------------------------------------
  # Relative collision safety: Mode 0 >= all blocking modes
  # -------------------------------------------------------------------

  Scenario: Mode 0 has at least as many collisions as Mode 1
    Given a contention scenario with both arms at cam_z 0.10
    When mode 0 and mode 1 both run on the same scenario
    Then mode 0 collision count is greater than or equal to mode 1

  Scenario: Mode 0 has at least as many collisions as Mode 2
    Given a contention scenario with both arms at cam_z 0.10
    When mode 0 and mode 2 both run on the same scenario
    Then mode 0 collision count is greater than or equal to mode 2

  Scenario: Mode 0 has at least as many collisions as Mode 3
    Given a contention scenario with both arms at cam_z 0.10
    When mode 0 and mode 3 both run on the same scenario
    Then mode 0 collision count is greater than or equal to mode 3

  Scenario: Mode 0 has at least as many collisions as Mode 4
    Given a contention scenario with both arms at cam_z 0.10
    When mode 0 and mode 4 both run on the same scenario
    Then mode 0 collision count is greater than or equal to mode 4

  # -------------------------------------------------------------------
  # Step reports produced for all modes
  # -------------------------------------------------------------------

  Scenario: Each mode produces step reports for both arms
    Given a contention scenario with both arms at cam_z 0.10
    When all five modes run on the same scenario
    Then each run has step reports for arm1 and arm2

  # -------------------------------------------------------------------
  # Threshold comparison across modes
  # -------------------------------------------------------------------

  Scenario: Mode 1 blocks when j5 exceeds cosine limit but Mode 3 is safe (large j4 gap)
    Given arms with j3=0.0 j4=0.300 j5=0.25 vs j3=0.0 j4=-0.450 j5=0.4
    When mode 1 and mode 3 are both applied
    Then mode 1 blocks j5 (j5 exceeds cosine limit)
    And mode 3 does NOT detect contention (j4 gap >= 0.10m)

  Scenario: Both Mode 1 and Mode 3 trigger when j5 exceeds limit and j4 gap is small
    Given arms with j3=0.0 j4=0.300 j5=0.25 vs j3=0.0 j4=-0.360 j5=0.4
    When mode 1 and mode 3 are both applied
    Then mode 1 blocks j5 (j5 exceeds cosine limit)
    And mode 3 detects contention (j4 gap < 0.10m)

  Scenario: Neither Mode 1 nor Mode 3 triggers when j5 is safe and j4 gap is large
    Given arms with j3=0.0 j4=0.300 j5=0.19 vs j3=0.0 j4=-0.450 j5=0.4
    When mode 1 and mode 3 are both applied
    Then mode 1 does NOT block (j5 within cosine limit)
    And mode 3 does NOT detect contention (j4 gap >= 0.10m)
