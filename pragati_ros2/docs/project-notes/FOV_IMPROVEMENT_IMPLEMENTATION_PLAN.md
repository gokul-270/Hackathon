# Joint4 Multi-Position Picking - Implementation Plan

**Date:** January 29, 2026  
**Status:** 🔵 Planning Phase  
**Target:** February 25, 2026 Field Trial  
**Related:** [FOV_IMPROVEMENT_TASKS.md](./FOV_IMPROVEMENT_TASKS.md) - Design rationale and theory

---

## Executive Summary

This document provides a comprehensive implementation plan for the Joint4 multi-position picking feature to recover border cotton detections. The feature enables the camera to scan multiple left/right positions (±100mm, ±50mm, center) to increase field-of-view coverage and reduce border_skip rejections.

**Key Decisions:**
- **Configuration-driven:** Fully controllable via YAML, no code changes needed to adjust positions
- **5 positions:** [-100mm, -50mm, 0mm, +50mm, +100mm] for maximum coverage
- **Phase 1 approach:** Fixed positions, no re-detection (simpler, faster)
- **Early exit optimization:** Skip remaining positions if all cotton already picked
- **Estimated cycle time:** ~3.8-4.5s per pick (vs ~2.0s baseline), acceptable for ~60% more coverage

---

## 1. Configuration System Design

### 1.1 YAML Configuration Schema

Add to `/src/yanthra_move/config/production.yaml` after line 173 (after `joint4_init` section):

```yaml
# ═══════════════════════════════════════════════════════════════
# JOINT4 MULTI-POSITION PICKING (FOV Enhancement)
# Reference: docs/project-notes/FOV_IMPROVEMENT_IMPLEMENTATION_PLAN.md
# ═══════════════════════════════════════════════════════════════
joint4_multiposition:
  # Master enable/disable - set to false to revert to single-position behavior
  # SAFETY: Only enable after completing safety verification (SAFETY-1 through SAFETY-9)
  enabled: false  # Default: disabled until safety verified
  
  # List of J4 positions to scan in meters (left/right from center)
  # Phase 1: Full range with 50mm increments for maximum coverage
  # Examples:
  #   Conservative:  [-0.050, 0.000, 0.050]
  #   Balanced:      [-0.075, 0.000, 0.075]
  #   Maximum:       [-0.100, -0.050, 0.000, 0.050, 0.100]
  #   Fine-grained:  [-0.100, -0.075, -0.050, -0.025, 0, 0.025, 0.050, 0.075, 0.100]
  # Must all be within motor_control joint4 limits: [-0.125, 0.175]
  positions: [-0.100, -0.050, 0.000, 0.050, 0.100]  # 5 positions, 50mm increment
  
  # Safety limits (extra margin from mechanical limits)
  # motor_control physical limits: [-0.125, 0.175]
  # These provide 25mm safety margin on left, 75mm on right
  safe_min: -0.100  # meters
  safe_max: 0.100   # meters
  
  # Timing parameters
  j4_settling_time: 0.100  # seconds - wait after J4 move for TF to stabilize
  detection_settling_time: 0.050  # seconds - additional wait before triggering detection
  
  # Re-detection strategy (Phase 1: disabled for simplicity)
  redetect_after_pick: false  # Re-detect after each pick at current J4 position
  redetect_interval: 1  # If redetect enabled: re-detect after every N picks
  
  # Performance optimization
  early_exit_enabled: true  # Skip remaining positions if no cotton found
  early_exit_threshold: 0  # Skip remaining if this many or fewer cotton remain
  max_cycle_time: 20.0  # seconds - abort multi-position if cycle exceeds this
  max_positions_per_cycle: 10  # Safety limit to prevent infinite loops
  
  # Recovery behavior on J4 movement failure
  # Options: "skip_position", "abort_cycle", "fallback_single"
  on_j4_failure: "skip_position"
  
  # Logging and diagnostics
  enable_timing_stats: true  # Log detailed timing breakdown per cycle
  enable_position_stats: true  # Log detections/picks per J4 position
  log_level: "info"  # "debug", "info", "warn"
```

### 1.2 C++ Configuration Struct

Add to `src/yanthra_move/include/yanthra_move/motion_controller.hpp`:

```cpp
/**
 * @brief Configuration for Joint4 multi-position picking feature
 * Enables scanning multiple J4 positions to increase FOV coverage
 * Reference: docs/project-notes/FOV_IMPROVEMENT_IMPLEMENTATION_PLAN.md
 */
struct Joint4MultiPositionConfig {
    bool enabled = false;
    std::vector<double> positions;  // J4 positions in meters
    double safe_min = -0.100;
    double safe_max = 0.100;
    double j4_settling_time = 0.100;
    double detection_settling_time = 0.050;
    bool redetect_after_pick = false;
    int redetect_interval = 1;
    bool early_exit_enabled = true;
    int early_exit_threshold = 0;
    double max_cycle_time = 20.0;
    int max_positions_per_cycle = 10;
    std::string on_j4_failure = "skip_position";
    bool enable_timing_stats = true;
    bool enable_position_stats = true;
    std::string log_level = "info";
    
    // Runtime state
    int current_position_index = 0;
    double current_j4_position = 0.0;
    std::chrono::steady_clock::time_point cycle_start_time;
};

/**
 * @brief Statistics for multi-position picking performance analysis
 */
struct MultiPositionStats {
    int positions_attempted = 0;
    int positions_successful = 0;
    int positions_skipped = 0;
    int total_detections = 0;
    int total_picks_successful = 0;
    int total_picks_failed = 0;
    std::vector<double> time_per_position_ms;
    std::map<double, int> detections_per_position;
    std::map<double, int> picks_per_position;
    double total_cycle_time_ms = 0.0;
    
    void reset() {
        positions_attempted = 0;
        positions_successful = 0;
        positions_skipped = 0;
        total_detections = 0;
        total_picks_successful = 0;
        total_picks_failed = 0;
        time_per_position_ms.clear();
        detections_per_position.clear();
        picks_per_position.clear();
        total_cycle_time_ms = 0.0;
    }
};
```

---

## 2. Implementation Gaps & Resolutions

### GAP-1: No Configuration System ✅ RESOLVED
- **Issue:** Hardcoded positions in design document
- **Resolution:** Complete YAML configuration system with runtime updates
- **Impact:** Can adjust positions without recompiling

### GAP-2: No Border Detection Integration ⏳ DEFERRED
- **Issue:** Border detections are discarded, not used to trigger J4 movement
- **Resolution:** Defer "smart border mode" to Phase 2 (post-Feb trial)
- **Rationale:** Fixed positions simpler and lower risk for initial deployment

### GAP-3: Safety Verification Not Documented ✅ RESOLVED
- **Issue:** No procedure for verifying collision clearance
- **Resolution:** Section 4 provides detailed safety checklist
- **Requirement:** MUST complete before enabling feature

### GAP-4: TF Settling Time Not Configurable ✅ RESOLVED
- **Issue:** Hardcoded settling delays
- **Resolution:** Two configurable delays: `j4_settling_time` (100ms) + `detection_settling_time` (50ms)
- **Rationale:** Can tune for different robots/field conditions

### GAP-5: Re-Detection Strategy Not Clear ✅ RESOLVED
- **Issue:** Three options presented, none chosen
- **Resolution:** Phase 1 = NO re-detection (simpler), configurable for Phase 2
- **Rationale:** Gather field data first, optimize later

### GAP-6: No Failure Handling for J4 Movement ✅ RESOLVED
- **Issue:** J4 movement failures not handled
- **Resolution:** Configurable behavior via `on_j4_failure` parameter
- **Options:** skip_position (continue), abort_cycle (stop), fallback_single (revert to single-position)

### GAP-7: Cycle Time Impact Not Estimated ✅ RESOLVED
- **Issue:** Performance impact unknown
- **Resolution:** Section 8 provides detailed analysis
- **Estimate:** ~3.8-4.5s per pick (75-125% slower) for ~60% more coverage
- **Optimization:** Early exit skips positions if no cotton

### GAP-8: No Integration with Existing Detection Flow ✅ RESOLVED
- **Issue:** Where to add multi-position logic
- **Resolution:** New method `executeMultiPositionCycle()` in `motion_controller.cpp`
- **Integration:** Called from `executePickCycle()` when `enabled=true`

### GAP-9: Cotton Tracking Not Implemented ✅ NOT NEEDED
- **Issue:** No tracking between re-detections
- **Resolution:** Detect-pick-at-each-position approach = no tracking needed
- **Rationale:** No merging of detections across positions

### GAP-10: No Metrics/Logging for Effectiveness ✅ RESOLVED
- **Issue:** Cannot measure if feature helps
- **Resolution:** Comprehensive `MultiPositionStats` struct
- **Metrics:** Detections/picks per position, timing breakdown, coverage improvement

---

## 3. Detailed Task List

### 🔴 MUST-HAVE for Feb 25 Field Trial

#### Task Group 1: Safety Verification (CRITICAL - Must Complete First)

**Owner:** Field team (manual verification)  
**Estimated Time:** 2-4 hours  
**Blocking:** ALL implementation tasks

- [ ] **SAFETY-1:** Power on arm in lab, move J4 to -0.050m manually via `/joint4_position_controller/command`, observe for collisions
- [ ] **SAFETY-2:** Move J4 to +0.050m manually, verify no collision
- [ ] **SAFETY-3:** Test at J3 = 0° (horizontal), verify clearance
- [ ] **SAFETY-4:** Test at J3 = -30° (tilted down), verify clearance (worst case during picking)
- [ ] **SAFETY-5:** Test at J3 = -60° (max tilt), verify clearance
- [ ] **SAFETY-6:** Move J4 to -0.100m, verify clearance (Phase 1 minimum)
- [ ] **SAFETY-7:** Move J4 to +0.100m, verify clearance (Phase 1 maximum)
- [ ] **SAFETY-8:** Document actual safe range in verification report, update `safe_min/safe_max` if needed
- [ ] **SAFETY-9:** Take photos/video of arm at extreme positions for reference

**Acceptance Criteria:**
- ✅ Zero collisions observed at any test position
- ✅ Clearance margin documented and verified
- ✅ Safe range confirmed: [-0.100, +0.100] meters

---

#### Task Group 2: Configuration System (Foundation)

**Owner:** Implementation team  
**Estimated Time:** 4-6 hours  
**Dependencies:** None

- [ ] **CONFIG-1:** Add `joint4_multiposition` section to `/src/yanthra_move/config/production.yaml`
  - Add after line 173 (after `joint4_init` section)
  - Use complete YAML schema from Section 1.1
  - Set `enabled: false` by default

- [ ] **CONFIG-2:** Add `Joint4MultiPositionConfig` struct to `motion_controller.hpp`
  - Add struct definition from Section 1.2
  - Add member variable: `Joint4MultiPositionConfig multipos_config_;`
  - Add member variable: `MultiPositionStats multipos_stats_;`

- [ ] **CONFIG-3:** Add parameter loading in `motion_controller.cpp` (in `loadMotionParameters()` method)
  ```cpp
  // Load Joint4 multi-position configuration
  multipos_config_.enabled = loadParamBool("joint4_multiposition/enabled", false);
  multipos_config_.positions = loadParamDoubleArray("joint4_multiposition/positions", 
                                                     {-0.100, -0.050, 0.0, 0.050, 0.100});
  multipos_config_.safe_min = loadParamDouble("joint4_multiposition/safe_min", -0.100);
  multipos_config_.safe_max = loadParamDouble("joint4_multiposition/safe_max", 0.100);
  // ... (load all other parameters)
  ```

- [ ] **CONFIG-4:** Add configuration validation
  ```cpp
  // Validate positions are within safe range
  for (double pos : multipos_config_.positions) {
      if (pos < multipos_config_.safe_min || pos > multipos_config_.safe_max) {
          RCLCPP_ERROR("Position %.3f outside safe range [%.3f, %.3f] - DISABLING feature", 
                       pos, multipos_config_.safe_min, multipos_config_.safe_max);
          multipos_config_.enabled = false;
          break;
      }
  }
  
  // Validate against motor_control limits
  if (multipos_config_.safe_min < joint4_limits_.min || 
      multipos_config_.safe_max > joint4_limits_.max) {
      RCLCPP_ERROR("Safe range [%.3f, %.3f] exceeds motor limits [%.3f, %.3f]",
                   multipos_config_.safe_min, multipos_config_.safe_max,
                   joint4_limits_.min, joint4_limits_.max);
      multipos_config_.enabled = false;
  }
  ```

- [ ] **CONFIG-5:** Add configuration logging at startup
  ```cpp
  RCLCPP_INFO(node_->get_logger(), "📸 Joint4 Multi-Position Config:");
  RCLCPP_INFO(node_->get_logger(), "   Enabled: %s", multipos_config_.enabled ? "YES" : "NO");
  if (multipos_config_.enabled) {
      std::string positions_str = "";
      for (double pos : multipos_config_.positions) {
          positions_str += std::to_string(static_cast<int>(pos * 1000)) + "mm ";
      }
      RCLCPP_INFO(node_->get_logger(), "   Positions: %s", positions_str.c_str());
      RCLCPP_INFO(node_->get_logger(), "   Safe range: [%.3fm, %.3fm]", 
                  multipos_config_.safe_min, multipos_config_.safe_max);
      RCLCPP_INFO(node_->get_logger(), "   Settling times: J4=%.0fms, Detection=%.0fms",
                  multipos_config_.j4_settling_time * 1000,
                  multipos_config_.detection_settling_time * 1000);
      RCLCPP_INFO(node_->get_logger(), "   Early exit: %s (threshold=%d)",
                  multipos_config_.early_exit_enabled ? "enabled" : "disabled",
                  multipos_config_.early_exit_threshold);
  }
  ```

**Acceptance Criteria:**
- ✅ YAML config loads without errors
- ✅ Invalid configurations are rejected with clear error messages
- ✅ Feature can be enabled/disabled via YAML change (no recompile)
- ✅ All parameters logged at startup for verification

---

#### Task Group 3: Core Multi-Position Logic (Implementation)

**Owner:** Implementation team  
**Estimated Time:** 10-14 hours  
**Dependencies:** CONFIG tasks complete

- [ ] **CORE-1:** Create `executeMultiPositionCycle()` method in `motion_controller.cpp`
  - Method signature: `PickCycleResult executeMultiPositionCycle()`
  - Returns: Same `PickCycleResult` struct as single-position
  - Add method declaration to `motion_controller.hpp`

- [ ] **CORE-2:** Implement main multi-position loop with J4 scanning

- [ ] **CORE-3:** Implement `moveJoint4Safe()` with validation and error handling

- [ ] **CORE-4:** Implement settling delays (`waitForJ4Settling()`, `waitForDetectionSettling()`)

- [ ] **CORE-5:** Implement `detectAndPickAtCurrentPosition()` - detect and pick all cotton at current J4 position

- [ ] **CORE-6:** Implement early exit logic (`shouldExitEarly()`)

- [ ] **CORE-7:** Integrate into main pick cycle - modify `executePickCycle()` to branch based on `enabled` flag

**Acceptance Criteria:**
- ✅ Multi-position loop executes all configured positions
- ✅ J4 moves to each position with proper settling delays
- ✅ Detection service called at each position
- ✅ All detected cotton picked at each position before moving to next
- ✅ J4 returns to home (0) after cycle completes
- ✅ Early exit works when no cotton found

---

#### Task Group 4: Error Handling & Recovery (Robustness)

**Owner:** Implementation team  
**Estimated Time:** 4-6 hours  
**Dependencies:** CORE tasks complete

- [ ] **ERROR-1:** Implement J4 failure handling (`handleJ4Failure()`) with configurable recovery behavior

- [ ] **ERROR-2:** Implement cycle timeout detection (`hasCycleTimedOut()`)

- [ ] **ERROR-3:** Add position limit watchdog to prevent infinite loops

- [ ] **ERROR-4:** Handle detection service failures gracefully

**Acceptance Criteria:**
- ✅ J4 movement failures don't crash the system
- ✅ Cycle timeout prevents infinite loops
- ✅ Position limit watchdog catches configuration errors
- ✅ Detection failures logged and handled gracefully
- ✅ Recovery behavior configurable via YAML

---

#### Task Group 5: Logging & Metrics (Observability - MUST-HAVE)

**Owner:** Implementation team  
**Estimated Time:** 3-4 hours  
**Dependencies:** CORE tasks complete

- [ ] **LOG-1:** Implement `logMultiPositionStats()` for cycle summary with per-position breakdown

- [ ] **LOG-2:** Add per-position timing breakdown (if detailed timing enabled)

- [ ] **LOG-3:** Add session-level counters (accumulate across multiple cycles for comparison)

**Acceptance Criteria:**
- ✅ Each cycle logs summary with detections/picks per position
- ✅ Timing breakdown shows cycle time impact
- ✅ Session stats accumulate for comparison analysis
- ✅ Logs are readable and actionable in field conditions

---

#### Task Group 6: Testing & Validation (Quality Assurance - MUST-HAVE)

**Owner:** QA + Field team  
**Estimated Time:** 6-8 hours  
**Dependencies:** CORE, ERROR, LOG tasks complete

- [ ] **TEST-1:** Unit test for config validation (automated)
  - Invalid positions (outside safe range) → should disable feature
  - Empty positions array → should use defaults or disable
  - safe_min > safe_max → should disable

- [ ] **TEST-2:** Simulation test with mocked hardware
  - Verify correct sequence: move → settle → detect → pick

- [ ] **TEST-3:** Lab test - Motion only (NO COTTON)
  - Enable multi-position, trigger cycle
  - Verify J4 moves to all positions and returns to home

- [ ] **TEST-4:** Lab test - With cotton targets
  - Place cotton at positions requiring different J4 values
  - Compare multi-position vs single-position coverage

- [ ] **TEST-5:** Lab test - Error conditions
  - Test J4 movement timeout, detection failures
  - Verify error handling works

- [ ] **TEST-6:** Lab test - Performance baseline
  - Measure cycle times with 3 positions vs 5 positions

**Acceptance Criteria:**
- ✅ All unit tests pass
- ✅ Lab tests with 5 positions complete successfully
- ✅ No collisions during any test
- ✅ Error handling verified
- ✅ Performance overhead documented and acceptable

---

### 🟡 NICE-TO-HAVE (Post-Feb Trial)

#### Task Group 7: Advanced Features (Phase 2)

**Owner:** TBD  
**Estimated Time:** TBD  
**Priority:** LOW (only if Phase 1 successful)

- [ ] **ADV-1:** Implement smart border detection mode (adaptive J4 movement based on border detections)
- [ ] **ADV-2:** Add re-detection after each pick support
- [ ] **ADV-3:** Implement adaptive position selection based on first detection
- [ ] **ADV-4:** Add dry-run mode for testing without picking
- [ ] **ADV-5:** Export metrics to ROS2 diagnostics topic for real-time monitoring
- [ ] **ADV-6:** Add runtime parameter updates (change positions without restart)

---

## 4. Safety Verification Procedures

### Pre-Implementation Checklist

**CRITICAL:** Complete ALL safety checks before enabling feature in code. Any collision risk must be resolved before proceeding.

#### Manual Testing Procedure

1. **Setup:**
   - Power on arm system in lab environment
   - Ensure emergency stop accessible
   - Clear workspace of obstructions
   - Have camera/video ready to document

2. **Initial Position (J4 = 0, J3 = 0):**
   ```bash
   # Move J4 to center manually
   ros2 topic pub --once /joint4_position_controller/command std_msgs/Float64 "data: 0.0"
   # Wait for movement to complete
   # Observe: Arm should be at center position, no unexpected movement
   ```

3. **Conservative Range Tests (±50mm):**
   ```bash
   # Test left position
   ros2 topic pub --once /joint4_position_controller/command std_msgs/Float64 "data: -0.050"
   # ✅ Verify: No collision, smooth movement, stable at position
   # ❌ Abort if: Any contact, unexpected vibration, motor strain
   
   # Test right position
   ros2 topic pub --once /joint4_position_controller/command std_msgs/Float64 "data: 0.050"
   # ✅ Verify: No collision, smooth movement, stable at position
   ```

4. **Maximum Range Tests (±100mm):**
   ```bash
   # Test left extreme
   ros2 topic pub --once /joint4_position_controller/command std_msgs/Float64 "data: -0.100"
   # ✅ Verify: Adequate clearance (>25mm from any structure)
   # Measure actual clearance with ruler/calipers
   
   # Test right extreme
   ros2 topic pub --once /joint4_position_controller/command std_msgs/Float64 "data: 0.100"
   # ✅ Verify: Adequate clearance (>25mm from any structure)
   ```

5. **J3 Angle Variation Tests:**
   ```bash
   # Set J3 to picking position (tilted down ~30°)
   ros2 topic pub --once /joint3_position_controller/command std_msgs/Float64 "data: -0.0833"
   
   # Repeat J4 tests at ±50mm and ±100mm
   # This is CRITICAL - picking position has different clearances
   
   # Set J3 to maximum tilt (~60°)
   ros2 topic pub --once /joint3_position_controller/command std_msgs/Float64 "data: -0.1667"
   
   # Repeat J4 tests again
   ```

6. **Documentation:**
   - Record clearance measurements at all test positions
   - Take photos/videos of arm at extreme positions
   - Note any positions with marginal clearance (<50mm)
   - Update `safe_min/safe_max` if actual safe range differs from [-0.100, +0.100]

#### Safety Verification Report Template

```markdown
# Joint4 Multi-Position Safety Verification Report

**Date:** [Date]
**Tester:** [Name]
**Location:** [Lab/Field]

## Test Results

| J3 Angle | J4 Position | Clearance (mm) | Status | Notes |
|----------|-------------|----------------|--------|-------|
| 0°       | -100mm      | [measured]     | ✅/❌  |       |
| 0°       | -50mm       | [measured]     | ✅/❌  |       |
| 0°       | +50mm       | [measured]     | ✅/❌  |       |
| 0°       | +100mm      | [measured]     | ✅/❌  |       |
| -30°     | -100mm      | [measured]     | ✅/❌  |       |
| -30°     | -50mm       | [measured]     | ✅/❌  |       |
| -30°     | +50mm       | [measured]     | ✅/❌  |       |
| -30°     | +100mm      | [measured]     | ✅/❌  |       |
| -60°     | -100mm      | [measured]     | ✅/❌  |       |
| -60°     | +100mm      | [measured]     | ✅/❌  |       |

## Minimum Clearances Observed
- Left side (J4 < 0): [X] mm at [position]
- Right side (J4 > 0): [Y] mm at [position]

## Recommended Safe Range
Based on tests, recommend:
- `safe_min: [value]` (current: -0.100)
- `safe_max: [value]` (current: 0.100)

## Approval
- [ ] Safe for conservative range (±50mm)
- [ ] Safe for full range (±100mm)
- [ ] Restrictions/modifications needed: [describe]

**Approved by:** [Name/Date]
```

---

## 5. Testing & Validation

### 5.1 Lab Testing Sequence

**Prerequisites:** Safety verification complete, config system implemented

#### Test 1: Feature Enable/Disable
```bash
# Test 1a: Verify feature disabled by default
grep "enabled:" src/yanthra_move/config/production.yaml
# Expected: enabled: false

# Launch system, check logs
ros2 launch yanthra_move yanthra_move.launch.py
# Expected log: "Joint4 Multi-Position Config: Enabled: NO"

# Test 1b: Enable feature
# Edit production.yaml: enabled: true
# Restart system
# Expected log: "Joint4 Multi-Position Config: Enabled: YES"
# Expected log: "Positions: -100mm -50mm 0mm 50mm 100mm"
```

#### Test 2: Motion Without Cotton
```bash
# Trigger cycle with no cotton present
ros2 topic pub --once /start_switch/command std_msgs/msg/Bool "data: true"

# Expected behavior:
# - J4 moves to -100mm → detects nothing → moves to -50mm → etc.
# - Cycle completes in ~1-2 seconds (no picks)
# - J4 returns to 0mm
# - Log shows: "No cotton detected at J4=..."

# Measure cycle time for baseline
```

#### Test 3: Single Cotton at Each Position
```bash
# Place cotton target at position requiring J4=-100mm
# Trigger cycle
# Expected: Cotton picked, remaining positions may be skipped (early exit)

# Place cotton at center (J4=0)
# Trigger cycle
# Expected: Cotton picked at center position

# Place cotton at J4=+100mm
# Trigger cycle
# Expected: All positions scanned, cotton picked at +100mm position
```

#### Test 4: Multiple Cotton Across Positions
```bash
# Place 3 cotton: one at -100mm, one at 0mm, one at +100mm
# Trigger multi-position cycle
# Expected: All 3 picked

# For comparison: Disable multi-position (enabled: false)
# Place same 3 cotton
# Trigger single-position cycle
# Expected: Only center cotton picked (demonstrates improvement)
```

#### Test 5: Error Handling
```bash
# Test 5a: J4 movement timeout
# Method: Temporarily block J4 motor (software or hardware)
# Expected: Error logged, position skipped (or cycle aborted depending on config)

# Test 5b: Detection service unavailable
# Method: Kill cotton_detection node during cycle
# Expected: Error logged, position skipped, cycle continues

# Test 5c: Cycle timeout
# Method: Set max_cycle_time: 5.0, add delays to exceed timeout
# Expected: Cycle aborts, J4 returns to home, error logged
```

### 5.2 Field Testing Protocol (Feb 25)

#### Phase 1: Baseline Collection (Disabled)
```yaml
# Config: enabled: false
# Duration: 1 hour
# Collect:
# - Pick success rate
# - Border_skip count from detection logs
# - Cycle time per pick
# - Total cotton detected vs picked
```

#### Phase 2: Multi-Position Enabled (Conservative)
```yaml
# Config: enabled: true, positions: [-0.050, 0, 0.050]
# Duration: 1 hour
# Collect same metrics as Phase 1
# Compare: Pick rate improvement, border_skip reduction, cycle time increase
```

#### Phase 3: Multi-Position Full Coverage (If Phase 2 successful)
```yaml
# Config: enabled: true, positions: [-0.100, -0.050, 0, 0.050, 0.100]
# Duration: 1 hour
# Collect same metrics
# Decide: Is additional coverage worth the cycle time increase?
```

### 5.3 Success Metrics

#### Lab Success Criteria
- ✅ Zero collisions during all tests
- ✅ J4 moves to all configured positions
- ✅ Detection service called at each position
- ✅ Cotton at extreme positions (±100mm) successfully picked
- ✅ Early exit works when enabled
- ✅ Error handling graceful (no crashes)

#### Field Success Criteria (Feb 25)
- ✅ Pick success rate improves by ≥10% vs baseline
- ✅ `border_skip` count reduced by ≥30%
- ✅ Cycle time increase ≤75% (i.e., <4.2s per pick)
- ✅ Zero collisions or safety incidents
- ✅ System stable for ≥2 hours continuous operation
- ✅ Feature can be disabled in field if issues arise

---

## 6. Phased Rollout Plan

### Phase 0: Preparation (Week 1)
**Duration:** 2-4 hours  
**Goal:** Verify safety and feasibility

- [ ] Complete safety verification (SAFETY-1 through SAFETY-9)
- [ ] Document safe range
- [ ] Review plan with team
- [ ] **Decision Gate:** Safe to proceed? If yes → Phase 1, If no → adjust or abort

### Phase 1: Implementation (Week 1-2)
**Duration:** 4-6 days (29-43 hours estimated)  
**Goal:** Working implementation ready for lab testing

- [ ] Complete CONFIG tasks (4-6 hours)
- [ ] Complete CORE tasks (10-14 hours)
- [ ] Complete ERROR tasks (4-6 hours)
- [ ] Complete LOG tasks (3-4 hours)
- [ ] Complete TEST-1 and TEST-2 (unit + simulation) (4-6 hours)
- [ ] **Milestone:** Code complete, builds successfully, unit tests pass

### Phase 2: Lab Validation (Week 2)
**Duration:** 1-2 days (6-8 hours)  
**Goal:** Validate in controlled environment

- [ ] Complete TEST-3: Motion without cotton
- [ ] Complete TEST-4: Cotton at different positions
- [ ] Complete TEST-5: Error conditions
- [ ] Complete TEST-6: Performance baseline
- [ ] Document results
- [ ] **Decision Gate:** Lab tests pass? If yes → Phase 3, If no → debug and repeat

### Phase 3: Field Trial (Feb 25)
**Duration:** 1 day (4-6 hours active testing)  
**Goal:** Validate effectiveness in real conditions

- [ ] Deploy to field with `enabled: false` (baseline)
- [ ] Collect 1 hour baseline data
- [ ] Enable feature with 3 positions (conservative)
- [ ] Collect 1 hour comparison data
- [ ] If successful: Enable 5 positions (full coverage)
- [ ] Collect 1 hour full-coverage data
- [ ] **Decision Gate:** Improves pick rate? If yes → keep enabled, If no → investigate or disable

### Phase 4: Optimization (Post-Feb)
**Duration:** TBD  
**Goal:** Enhance feature based on field learnings

- [ ] Analyze field data
- [ ] Tune parameters (positions, settling times, early exit)
- [ ] Consider smart border mode (DETECT tasks)
- [ ] Consider re-detection support (ADV tasks)
- [ ] Document findings and recommendations

---

## 7. Risk Assessment & Mitigation

| Risk | Likelihood | Impact | Mitigation | Owner |
|------|------------|--------|------------|-------|
| **Collision at ±100mm** | MEDIUM | HIGH (arm damage) | Safety verification MUST complete first, start with ±50mm | Field team |
| **Cycle time too slow** | HIGH | MEDIUM (productivity loss) | Configurable positions, early exit optimization, cycle time limit | Implementation |
| **TF not stable after J4 move** | MEDIUM | HIGH (picking accuracy) | Conservative settling times (150ms total), make configurable | Implementation |
| **Feature breaks existing functionality** | LOW | HIGH (field trial failure) | Master enable/disable, extensive lab testing | QA |
| **No improvement in pick rate** | MEDIUM | LOW (wasted effort) | Detailed metrics to understand why, can disable easily | Field team |
| **Configuration errors in field** | MEDIUM | MEDIUM (cycle aborts) | Validation at startup, clear error messages, fallback to single-position | Implementation |
| **J4 motor timeout/failure** | LOW | MEDIUM (incomplete coverage) | Error handling with skip_position default, logs for diagnosis | Implementation |

---

## 8. Performance Analysis

### 8.1 Cycle Time Breakdown

#### Single-Position Baseline (Current)
```
Detection:          70ms
Approach (J3+J4+J5): 800ms
EE + Pick:          400ms
Retract:            600ms
Compressor drop:    500ms
--------------------------------
TOTAL:              ~2370ms (2.4s per pick)
```

#### Multi-Position (3 positions: -50, 0, +50mm)
```
Position 1 (-50mm):
  J4 move:          200ms
  TF settling:      100ms
  Detection settling: 50ms
  Detection:        70ms
  Pick (if cotton): 2000ms (approach + pick + retract)
  
Position 2 (0mm):
  J4 move:          200ms
  Settling:         150ms
  Detection:        70ms
  Pick (if cotton): 2000ms
  
Position 3 (+50mm):
  J4 move:          200ms
  Settling:         150ms
  Detection:        70ms
  Pick (if cotton): 2000ms
  
J4 return home:     200ms
--------------------------------
Best case (no cotton): ~1660ms (just movements + detections)
Worst case (cotton at all): ~8660ms (8.7s per cycle)
Average case (cotton at 1 position): ~3660ms (3.7s per cycle)
```

#### Multi-Position (5 positions: full coverage)
```
5 × (J4 move + settling + detection) = 5 × 420ms = 2100ms overhead
+ picks at positions with cotton
--------------------------------
Best case (no cotton): ~2300ms
Worst case (cotton at all 5): ~12100ms (12.1s per cycle)
Average case (cotton at 2 positions): ~6500ms (6.5s per cycle)
```

### 8.2 Performance Optimization: Early Exit

With early exit enabled (default):
- If cotton picked at first position → skip remaining positions (saves ~1500ms for 5-position)
- If no cotton at first 2 positions → likely none at remaining (can add heuristic)

### 8.3 Coverage vs Cycle Time Tradeoff

| Configuration | Positions | Estimated Coverage | Avg Cycle Time | Overhead |
|---------------|-----------|-------------------|----------------|----------|
| Single (baseline) | 1 | 100% (reference) | 2.4s | 0% |
| Conservative | 3 (±50mm) | ~130-140% | 3.7s | +54% |
| Balanced | 3 (±75mm) | ~140-150% | 3.7s | +54% |
| Maximum | 5 (±100mm) | ~160-170% | 6.5s | +171% |

**Recommendation:** Start with 5 positions for maximum coverage. Field data will show if cycle time is acceptable or if reduction to 3 positions is needed.

---

## 9. Open Questions & Decisions Made

### Q1: Re-detection strategy?
**Decision:** Phase 1 = NO re-detection (simpler)
- Configurable via `redetect_after_pick: false`
- Can enable later if field data shows plant movement is significant

### Q2: Border detection integration priority?
**Decision:** Defer smart border mode to Phase 2 (post-Feb)
- Fixed positions simpler and sufficient for Phase 1
- Border_skip count reduction will indicate if smart mode needed

### Q3: Starting distance for Feb trial?
**Decision:** Full coverage (5 positions: ±100mm with 50mm increment)
- Safety verification will confirm ±100mm is safe
- Can easily reduce to 3 positions if cycle time too slow in field
- Array-based config makes adjustment trivial

### Q4: Performance budget - acceptable cycle time increase?
**Decision:** Up to 75% increase acceptable (~4.2s vs 2.4s baseline)
- Justification: 60% more coverage for 75% more time = net positive
- Early exit optimization keeps no-cotton cycles fast (~2.3s)
- Cycle time limit (20s) prevents runaway scenarios

### Q5: Integration point - where to add multi-position logic?
**Decision:** New method in `motion_controller.cpp`
- `executeMultiPositionCycle()` called from `executePickCycle()`
- Clean separation: enable/disable doesn't affect existing code

### Q6: What if feature doesn't improve pick rate?
**Decision:** Detailed metrics will diagnose WHY
- Possible reasons: cotton distribution, cycle time impact, TF/detection issues
- Action: Disable and analyze logs, may need smart border mode instead
- No regression risk: can always fall back to single-position

---

## 10. Success Criteria

### Lab Success (Pre-Field)
- ✅ Safety verification complete, no collisions
- ✅ Feature enables/disables via YAML change only
- ✅ Arm completes 5-position cycle smoothly
- ✅ Detection called at each position
- ✅ Cotton at extreme positions (±100mm) picked successfully
- ✅ J4 returns to home after cycle
- ✅ Error handling tested (timeout, detection failure)
- ✅ Logs clear and informative
- ✅ Code review approved

### Field Success (Feb 25 Trial)
- ✅ **Primary:** Pick success rate improves by ≥10% vs single-position baseline
- ✅ **Primary:** `border_skip` count reduced by ≥30%
- ✅ **Secondary:** Cycle time increase ≤75% (≤4.2s per pick avg)
- ✅ **Secondary:** System uptime >2 hours with feature enabled
- ✅ **Critical:** Zero collisions or safety incidents
- ✅ **Critical:** Feature can be disabled remotely if issues arise

### Long-Term Success (Post-Feb)
- ✅ Feature remains enabled in production (not disabled due to issues)
- ✅ Operators report increased cotton collection
- ✅ Maintenance: No unexpected wear on J4 motor
- ✅ Data shows consistent 10-20% pick rate improvement over time

---

## 11. Additional Features & Suggestions

### Dry-Run Mode (Phase 2+)
```yaml
joint4_multiposition:
  dry_run: true  # Move and detect, but don't pick (testing mode)
```
**Use cases:**
- Field testing without disturbing plants
- Collect detection data to analyze cotton distribution
- Verify J4 movements in production environment without risk

### Adaptive Position Selection (Phase 3+)
```yaml
joint4_multiposition:
  adaptive: true
  # Analyze first detection (at center) to decide which positions to scan
  # If all cotton centered → skip edge positions (save time)
  # If cotton at left edge → scan [-100, -50, 0] only
  # If cotton at right edge → scan [0, 50, 100] only
```

### Position Randomization (Research)
```yaml
joint4_multiposition:
  randomize_order: true  # Randomize position order per cycle
```
**Use case:** Collect unbiased field data to determine if position order affects results

### Per-Plant Variation (Advanced)
```yaml
joint4_multiposition:
  use_previous_plant_data: true
  # Remember which positions had cotton on previous plant
  # Prioritize those positions on next plant (same row likely similar)
```

---

## 12. Implementation File Structure

### Files to Modify

1. **`/src/yanthra_move/config/production.yaml`**
   - Add `joint4_multiposition` section (after line 173)

2. **`/src/yanthra_move/include/yanthra_move/motion_controller.hpp`**
   - Add `Joint4MultiPositionConfig` struct
   - Add `MultiPositionStats` struct
   - Add method declarations for multi-position cycle

3. **`/src/yanthra_move/src/core/motion_controller.cpp`**
   - Add method implementations
   - Modify `executePickCycle()` to branch based on `enabled` flag

4. **`/src/yanthra_move/src/yanthra_move_system_parameters.cpp`** (or wherever param loading happens)
   - Add parameter loading for all `joint4_multiposition/*` params

### Files to Create (Optional)

5. **`/docs/project-notes/JOINT4_MULTIPOSITION_SAFETY_VERIFICATION.md`**
   - Safety verification report (from Section 4)
   - Photos/measurements
   - Approved safe ranges

6. **`/docs/project-notes/JOINT4_MULTIPOSITION_FIELD_RESULTS.md`**
   - Feb 25 field trial results
   - Performance metrics
   - Lessons learned
   - Recommendations for Phase 2

---

## 13. Reference Documentation

- **Design Rationale:** [FOV_IMPROVEMENT_TASKS.md](./FOV_IMPROVEMENT_TASKS.md)
  - Section 2.2: Joint4 Multi-Position Picking (design theory)
  - Section 2.3: Smart Border Handling (Phase 2 feature)
  - Section 6.1-6.9: Kinematic analysis and TF handling
- **Field Trial Reports:**
  - [FIELD_VISIT_REPORT_JAN_2026.md](./FIELD_VISIT_REPORT_JAN_2026.md) - 16 border cottons rejected
  - [FEBRUARY_FIELD_TRIAL_PLAN_2026.md](./FEBRUARY_FIELD_TRIAL_PLAN_2026.md) - Overall Feb plan
- **Motor Control:**
  - `/src/motor_control_ros2/config/production.yaml` - Joint4 limits: [-0.125, 0.175]
- **Detection:**
  - `/src/cotton_detection_ros2/src/cotton_detection_node_detection.cpp` - Border filter (line 126-134)

---

## 14. Timeline & Milestones

| Date | Milestone | Tasks | Status |
|------|-----------|-------|--------|
| Feb 3 | Safety Verification Complete | SAFETY-1 to SAFETY-9 | ⬜ |
| Feb 7 | Config System Complete | CONFIG-1 to CONFIG-5 | ⬜ |
| Feb 12 | Core Implementation Complete | CORE-1 to CORE-7, ERROR-1 to ERROR-4 | ⬜ |
| Feb 14 | Logging & Unit Tests Complete | LOG-1 to LOG-3, TEST-1, TEST-2 | ⬜ |
| Feb 18 | Lab Testing Complete | TEST-3 to TEST-6 | ⬜ |
| Feb 20 | Code Review & Final QA | All MUST-HAVE tasks verified | ⬜ |
| Feb 22-24 | Integration & Pre-Field Prep | Deploy to RPi, final checks | ⬜ |
| **Feb 25** | **Field Trial** | Phase 3 testing protocol | ⬜ |
| Feb 28 | Results Analysis & Report | Document findings, Phase 2 decisions | ⬜ |

---

## Appendix A: Quick Reference Commands

### Enable/Disable Feature
```bash
# Edit config
nano /path/to/yanthra_move/config/production.yaml
# Change: enabled: true/false

# Restart system
ros2 launch yanthra_move yanthra_move.launch.py
```

### Manually Move J4 (Testing)
```bash
# Move to specific position
ros2 topic pub --once /joint4_position_controller/command std_msgs/Float64 "data: -0.050"

# Subscribe to J4 feedback
ros2 topic echo /joint4/feedback
```

### Monitor Multi-Position Logs
```bash
# Watch logs in real-time
ros2 launch yanthra_move yanthra_move.launch.py | grep "Multi-Position\|J4="

# Save logs to file
ros2 launch yanthra_move yanthra_move.launch.py 2>&1 | tee multipos_test.log
```

### Change Positions Without Restart (If runtime updates implemented)
```bash
# Set new positions dynamically
ros2 param set /yanthra_move joint4_multiposition.positions "[-0.075, 0.0, 0.075]"
```

---

**Document Version:** 1.0  
**Last Updated:** January 29, 2026  
**Next Review:** After Feb 25 field trial

---
