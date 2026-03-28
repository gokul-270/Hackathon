# Velocity-Based Steering Implementation Checklist

**Target Date:** February 25, 2026  
**Days Remaining:** 22 days  
**Status:** 📋 Planning Complete → Ready for Implementation  

---

## Pre-Implementation Requirements

### Critical Measurements Needed ⚠️

- [ ] **Wheel positions measured** (required for velocity-based algorithm)
  ```
  Front wheel:  x = ____m,  y = ____m  (from base_link center)
  Rear left:    x = ____m,  y = ____m
  Rear right:   x = ____m,  y = ____m
  ```
  **Method:** Tape measure from vehicle center point
  **Accuracy:** ±10mm
  **Owner:** [TBD]
  **Deadline:** Before Day 1

- [ ] **Get Gazebo setup from colleague**
  - [ ] Gazebo world files
  - [ ] Robot URDF/SDF model
  - [ ] Test scripts
  - [ ] Drift measurement data (CSV/plots)
  **Owner:** Udaya
  **Contact:** Vasanth
  **Deadline:** Before Feb 10 (Day 9)

- [ ] **Choose switching method**
  - [ ] Option A: Config file (restart required)
  - [ ] Option B: ROS2 parameter (dynamic) ← RECOMMENDED
  - [ ] Option C: Service call (programmatic)
  - [ ] Option D: Launch argument (testing)
  **Decision:** [TBD]
  **Deadline:** Before Feb 8 (Day 5)

---

## Week 1: Core Implementation (Feb 3-9)

### Day 1-2: Velocity Kinematics Module

**File:** `src/vehicle_control/hardware/velocity_kinematics.py`

- [ ] Create new file
- [ ] Define `VelocityKinematicsController` class
- [ ] Implement `compute_wheel_kinematics()` method
  ```python
  def compute_wheel_kinematics(self, vx, omega, wheel_x, wheel_y):
      vix = vx - omega * wheel_y
      viy = omega * wheel_x
      angle = atan2(viy, vix)
      speed = sqrt(vix² + viy²) / wheel_radius
      return angle, speed
  ```
- [ ] Add `compute_wheel_commands()` wrapper method
- [ ] Add error handling and validation
- [ ] Add comprehensive logging
- [ ] Create basic unit tests

**Files to reference:**
- `C:\Users\udayakumar\Downloads\velocitybasedIK.py` (lines 115-155)

**Owner:** [TBD]  
**Estimated:** 16 hours

---

### Day 3: Differential Velocities for Ackermann

**File:** `src/vehicle_control/hardware/advanced_steering.py`

- [ ] Add new method: `calculate_differential_velocities()`
  ```python
  def calculate_differential_velocities(self, vx, omega, angles):
      turn_radius = vx / omega
      left_radius = abs(turn_radius - wheel_center_distance)
      right_radius = abs(turn_radius + wheel_center_distance)
      # Calculate speed ratios...
      return speeds_dict
  ```
- [ ] Import math functions if needed
- [ ] Add logging for velocity calculations
- [ ] Handle edge cases (straight driving, pure rotation)
- [ ] Unit tests for differential calculations

**Files to reference:**
- `C:\Users\udayakumar\Downloads\ackerman.py` (lines 214-262)

**Owner:** [TBD]  
**Estimated:** 8 hours

---

### Day 4: Configuration Updates

**File:** `src/vehicle_control/config/production.yaml`

- [ ] Add steering algorithm selection:
  ```yaml
  steering:
    algorithm: "ackermann"  # or "velocity_based"
  ```
- [ ] Add differential drive section:
  ```yaml
  differential_drive:
    enabled: true
  ```
- [ ] Add wheel positions section:
  ```yaml
  wheel_positions:
    front: {x: 0.75, y: 0.0}
    rear_left: {x: -0.75, y: 0.9}
    rear_right: {x: -0.75, y: -0.9}
  ```
  **USE ACTUAL MEASUREMENTS!**
- [ ] Document all new parameters
- [ ] Create `ackermann_mode.yaml` example
- [ ] Create `velocity_based_mode.yaml` example

**Owner:** [TBD]  
**Estimated:** 4 hours

---

### Day 5-6: Dual-Mode Integration

**File:** `src/vehicle_control/integration/vehicle_control_node.py`

**Changes needed:**

- [ ] Add imports:
  ```python
  from ..hardware.velocity_kinematics import VelocityKinematicsController
  ```

- [ ] In `__init__()`:
  ```python
  # Load algorithm choice
  self.steering_algorithm = self.config['steering']['algorithm']
  
  # Initialize both controllers
  self.velocity_controller = VelocityKinematicsController(...)
  
  self.logger.info(f"Steering algorithm: {self.steering_algorithm}")
  ```

- [ ] Add algorithm selection method:
  ```python
  def _process_steering_command(self, vx, omega):
      if self.steering_algorithm == "ackermann":
          return self._process_ackermann(vx, omega)
      elif self.steering_algorithm == "velocity_based":
          return self._process_velocity_based(vx, omega)
      else:
          self.logger.error("Unknown algorithm")
          return None
  ```

- [ ] Implement `_process_ackermann()`:
  ```python
  def _process_ackermann(self, vx, omega):
      # Convert to steering angle
      if abs(vx) > 0.01:
          steering_angle = atan(wheelbase * omega / vx)
      else:
          steering_angle = 0.0
      
      # Calculate angles
      angles = self.ackermann_controller.calculate_three_wheel_ackermann_angles(
          steering_angle
      )
      
      # Calculate differential velocities (NEW!)
      speeds = self.ackermann_controller.calculate_differential_velocities(
          vx, omega, angles
      )
      
      return {'angles': angles, 'speeds': speeds}
  ```

- [ ] Implement `_process_velocity_based()`:
  ```python
  def _process_velocity_based(self, vx, omega):
      return self.velocity_controller.compute_wheel_commands(vx, omega)
  ```

- [ ] Add runtime parameter handling:
  ```python
  # ROS2 parameter callback for algorithm switching
  def _on_parameter_change(self, params):
      for param in params:
          if param.name == 'steering.algorithm':
              self.steering_algorithm = param.value
              self.logger.info(f"Switched to {self.steering_algorithm} mode")
  ```

- [ ] Add comparison logging
- [ ] Add algorithm validation on startup
- [ ] Update existing `_send_drive_velocity()` calls

**Owner:** [TBD]  
**Estimated:** 16 hours

---

## Week 2: Testing & Validation (Feb 10-16)

### Day 7-8: Unit Tests

**File:** `tests/test_velocity_kinematics.py`

- [ ] `test_straight_driving()` - vx=1.0, omega=0
  - Verify: all angles=0, all speeds equal
- [ ] `test_left_turn()` - vx=1.0, omega=0.5
  - Verify: angle signs correct, speed ratios correct
- [ ] `test_right_turn()` - vx=1.0, omega=-0.5
  - Verify: mirror of left turn
- [ ] `test_pure_rotation()` - vx=0, omega=0.5
  - Verify: pivot mode angles
- [ ] `test_velocity_consistency()` 
  - Verify: inner wheel slower, outer faster
- [ ] `test_asymmetric_positions()`
  - Verify: handles offset wheel positions
- [ ] `test_algorithm_switching()`
  - Verify: parameter change works

- [ ] Run all tests: `pytest tests/test_velocity_kinematics.py -v`
- [ ] Verify coverage: `pytest --cov=vehicle_control --cov-report=html`
- [ ] Target: >90% coverage

**Owner:** [TBD]  
**Estimated:** 16 hours

---

### Day 9-11: Gazebo Simulation Testing

**Prerequisites:**
- [ ] Gazebo installed and working
- [ ] Colleague's world/model files obtained
- [ ] Test scenarios ported

**Test Scenarios:**

- [ ] **Scenario 1: Straight Line (100m)**
  - [ ] Run with algorithm="ackermann"
  - [ ] Measure lateral drift
  - [ ] Run with algorithm="velocity_based"
  - [ ] Measure lateral drift
  - [ ] Compare results
  - Target: velocity_based ≤ ackermann drift

- [ ] **Scenario 2: Circle Pattern (10m radius, 5 loops)**
  - [ ] Ackermann mode
  - [ ] Velocity-based mode
  - [ ] Measure closed-loop error (should return to start)
  - Target: <50mm final error

- [ ] **Scenario 3: Figure-8 Pattern**
  - [ ] Both algorithms
  - [ ] Visualize trajectories
  - [ ] Measure cumulative drift
  - [ ] Generate comparison plots

- [ ] **Scenario 4: Random Waypoints**
  - [ ] 10 waypoints in 50m x 50m area
  - [ ] Both algorithms
  - [ ] Measure: avg error, max error, completion time

**Metrics to collect:**
- [ ] Position error over time (CSV export)
- [ ] Closed-loop path error
- [ ] Wheel scrubbing indicators
- [ ] Turn radius accuracy
- [ ] Computational performance

**Deliverable:**
- [ ] Comparison report with plots
- [ ] Decision recommendation

**Owner:** [TBD]  
**Estimated:** 24 hours

---

### Day 12: Comparison Dashboard (Optional)

**File:** `tools/algorithm_comparator.py`

- [ ] Create ROS2 node for monitoring
- [ ] Display current algorithm
- [ ] Show real-time velocity commands
- [ ] Plot drift measurement
- [ ] Add switch button/service
- [ ] Log data for analysis

**Owner:** [TBD]  
**Estimated:** 8 hours (optional)

---

## Week 3: Hardware Testing (Feb 17-23)

### Day 13-14: Bench Testing (No Movement)

**Environment:** Vehicle on stands/rollers

**Tests:**

- [ ] **Steering angle verification**
  - [ ] Set vx=1.0, omega=0.5 (left turn)
  - [ ] Verify steering motors move to correct angles
  - [ ] Check: front wheel angle differs between algorithms
  - [ ] Visual inspection or encoder readback

- [ ] **Motor command range check**
  - [ ] Run full range of (vx, omega) commands
  - [ ] Verify: no limit violations
  - [ ] Check: commands within ±90° steering limits

- [ ] **Velocity command consistency**
  - [ ] Both algorithms
  - [ ] Log actual motor speeds
  - [ ] Verify: differential speeds present

- [ ] **Safety limit validation**
  - [ ] Extreme commands (high omega)
  - [ ] Verify: safety clipping works
  - [ ] Check: E-stop interrupts both algorithms

- [ ] **Algorithm switching**
  - [ ] Switch via parameter: `ros2 param set ...`
  - [ ] Verify: smooth transition
  - [ ] Check: no motor jumps or errors

**Success criteria:**
- [ ] No motor limit violations
- [ ] Clean algorithm switching
- [ ] Commands match simulation
- [ ] All safety checks pass

**Owner:** [TBD]  
**Estimated:** 16 hours

---

### Day 15-16: Controlled Movement Testing

**Environment:** Open space (parking lot or field)

**Tests:**

- [ ] **Straight driving**
  - [ ] Both algorithms
  - [ ] 50m distance
  - [ ] Verify: wheel speeds identical
  - [ ] Measure: lateral deviation

- [ ] **Gentle turns**
  - [ ] vx=0.5 m/s, omega=±0.2 rad/s
  - [ ] Both algorithms
  - [ ] Compare: motor currents (scrubbing indicator)
  - [ ] Visual: tire marks (scrubbing)

- [ ] **Sharp turns**
  - [ ] vx=0.5 m/s, omega=±0.5 rad/s
  - [ ] Both algorithms
  - [ ] Check: reduced scrubbing with differential

- [ ] **Pivot mode**
  - [ ] vx=0, omega=0.5 rad/s
  - [ ] Verify: turns in place
  - [ ] Check: all wheels coordinated

- [ ] **Speed ramps**
  - [ ] 0 → 1.0 m/s acceleration
  - [ ] Verify: smooth, no jerks

- [ ] **Emergency stop**
  - [ ] From various (vx, omega) states
  - [ ] Both algorithms
  - [ ] Verify: safe stops

**Data collection:**
- [ ] Motor currents (logged)
- [ ] Actual vs commanded positions
- [ ] Velocity tracking accuracy
- [ ] Algorithm switch latency

**Success criteria:**
- [ ] Both algorithms run without errors
- [ ] Differential velocities reduce currents
- [ ] No jerky transitions
- [ ] Safe stops from all conditions

**Owner:** [TBD]  
**Estimated:** 16 hours

---

### Day 17-18: Field Validation with GPS

**Environment:** Open field

**Equipment:**
- [ ] GPS logger (1Hz minimum)
- [ ] Ground truth markers
- [ ] Data logging active

**Test 1: GPS Straight Line**
- [ ] Distance: 100m
- [ ] Algorithm: Ackermann (3 runs)
- [ ] Algorithm: Velocity-based (3 runs)
- [ ] Measure: lateral deviation from ideal line
- [ ] Target: <10cm RMS error

**Test 2: GPS Circle**
- [ ] Radius: 10m
- [ ] 5 complete circles
- [ ] Both algorithms (separate runs)
- [ ] Measure: closed-loop error (return to start)
- [ ] Target: <50mm final position error

**Test 3: Figure-8 Pattern**
- [ ] Both algorithms
- [ ] Measure: path repeatability (3 runs each)
- [ ] Compare: drift accumulation

**Test 4: Row-Following Simulation**
- [ ] Set up straight line markers (50m)
- [ ] Follow line with both algorithms
- [ ] Measure: tracking accuracy
- [ ] Target: stay within ±10cm of line

**Data to collect:**
- [ ] GPS tracks (GPX/CSV)
- [ ] Planned vs actual paths
- [ ] Error statistics (mean, max, RMS)
- [ ] Motor data (currents, positions)

**Success criteria:**
- [ ] Velocity-based ≤ Ackermann drift (ideally better)
- [ ] Both algorithms < 50mm cumulative drift
- [ ] No unexpected behaviors
- [ ] Ready for Feb 25 field trial

**Owner:** [TBD]  
**Estimated:** 16 hours

---

## Week 4: Final Prep (Feb 24-25)

### Day 19: Documentation

- [ ] **Update operator manual**
  - [ ] How to switch algorithms
  - [ ] When to use each mode
  - [ ] Troubleshooting guide

- [ ] **Create quick reference card**
  - [ ] Algorithm switch command
  - [ ] Expected behavior differences
  - [ ] Fallback procedure

- [ ] **Record video demonstrations**
  - [ ] Algorithm switching
  - [ ] Performance comparison
  - [ ] Troubleshooting examples

- [ ] **Training session**
  - [ ] Train operators on new features
  - [ ] Practice algorithm switching
  - [ ] Q&A session

**Owner:** [TBD]  
**Estimated:** 8 hours

---

### Day 20: Contingency Buffer

- [ ] Fix any Week 3 issues
- [ ] Fine-tune parameters
- [ ] Final validation run
- [ ] Backup all configuration files
- [ ] Prepare rollback plan
- [ ] **DECISION MEETING: Choose primary algorithm for Feb 25**

---

### Day 21-22: Feb 25 Prep

- [ ] **System health check**
  - [ ] All motors working
  - [ ] GPS functional
  - [ ] Logging configured
  - [ ] Battery charged

- [ ] **Configuration deployment**
  - [ ] Deploy chosen algorithm
  - [ ] Set fallback options
  - [ ] Verify parameter persistence

- [ ] **Pre-deployment checklist**
  - [ ] Test all modes one final time
  - [ ] Verify emergency stops
  - [ ] Check communication systems
  - [ ] Load spare configurations

- [ ] **Briefing**
  - [ ] Team sync on algorithm choice
  - [ ] Review fallback procedures
  - [ ] Assign roles for Feb 25

**Ready for Feb 25 Field Trial!**

---

## Decision Framework for Feb 25

### Decision Point: Feb 20 (Day 20)

**Based on Week 3 test results:**

| Test Results | Primary Algorithm | Fallback |
|--------------|------------------|----------|
| ✅ Velocity-based: drift <20mm, no issues | Velocity-based | Ackermann |
| ✅ Velocity-based: drift 20-50mm, stable | Velocity-based | Ackermann |
| ⚠️ Velocity-based: occasional issues | Ackermann + diff vel | Original |
| ❌ Velocity-based: hardware problems | Ackermann + diff vel | Original |
| ❌ Both new modes have issues | Original (same speed) | N/A |

**Switching procedure:**
```bash
# To switch to Ackermann
ros2 param set /vehicle_control steering.algorithm "ackermann"

# To switch to Velocity-based
ros2 param set /vehicle_control steering.algorithm "velocity_based"

# To check current algorithm
ros2 param get /vehicle_control steering.algorithm
```

---

## Rollback Plans

### Level 1: Switch to Ackermann Mode
**When:** Velocity-based has issues in field
**Action:** 
```bash
ros2 param set /vehicle_control steering.algorithm "ackermann"
```
**Time:** Instant (no restart)
**Risk:** Low (proven differential velocities)

### Level 2: Revert to Original Implementation
**When:** Both new algorithms have issues
**Action:**
```bash
# Restore backup configuration
cp production.yaml.backup production.yaml
ros2 service call /vehicle_control/restart
```
**Time:** ~30 seconds
**Risk:** Very low (known baseline)

### Level 3: Full Code Revert
**When:** System-level integration issues
**Action:**
```bash
git revert [implementation-commit-hash]
colcon build --packages-select vehicle_control
# Redeploy
```
**Time:** ~5 minutes
**Risk:** None (last resort, back to known good state)

---

## Key Contacts

| Role | Name | Contact |
|------|------|---------|
| **Project Lead** | Udaya | [contact] |
| **Implementation Owner** | Vasanth | [contact] |
| **Contributors** | Gokul | [contact] |
| **Gazebo Expert** | Vasanth | [contact] |
| **Field Trial Lead** | Udaya | [contact] |

---

## Critical Path Items (Blockers)

### Must Have Before Starting:
1. ⚠️ **Wheel position measurements** (required for velocity-based)
2. ⚠️ **Gazebo setup from colleague** (required for simulation testing)
3. ⚠️ **Switching method decision** (required for integration)

### Must Have Before Hardware Testing (Day 13):
4. ⚠️ **All unit tests passing** (>90% coverage)
5. ⚠️ **Gazebo validation complete** (comparison data)

### Must Have Before Feb 25:
6. ⚠️ **Decision on primary algorithm** (Feb 20)
7. ⚠️ **Operator training complete** (Day 19)
8. ⚠️ **Fallback procedures tested** (Day 20)

---

## Success Metrics

### Minimum Success (Must Achieve):
- ✅ Ackermann + differential velocities working in hardware
- ✅ Drift reduced to <50mm per 10m circle
- ✅ Safe algorithm switching demonstrated
- ✅ Fallback to original implementation available

### Target Success (Should Achieve):
- ✅ Velocity-based validated in simulation
- ✅ Drift reduced to <20mm per 10m circle  
- ✅ Both algorithms tested in field
- ✅ Quantitative comparison data collected

### Stretch Success (Nice to Have):
- ✅ Velocity-based deployed as primary for Feb 25
- ✅ Autonomous navigation validated
- ✅ Performance improvement documented

---

**Document Status:** ✅ Ready for Implementation  
**Last Updated:** February 3, 2026  
**Next Review:** After Week 1 (Feb 10)  
**Lead:** Udaya  
**Owner:** Vasanth  
**Contributors:** Gokul  
**Tracking:** Use this checklist for daily standup updates
