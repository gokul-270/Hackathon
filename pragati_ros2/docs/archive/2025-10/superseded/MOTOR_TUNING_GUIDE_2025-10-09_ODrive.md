# Pragati Robot Motor Tuning Guide

**Version:** 1.0  
**Date:** October 9, 2025  
**Target System:** Pragati ROS2 Cotton-Picking Robot  
**Tier:** 3.3 - Motor Tuning Procedures  
**Related:** [CALIBRATION_GUIDE.md](./CALIBRATION_GUIDE.md)

---

## Table of Contents

1. [Introduction](#introduction)
2. [Prerequisites](#prerequisites)
3. [Quick Tuning Checklist](#quick-tuning-checklist)
4. [Understanding Motor Control](#understanding-motor-control)
5. [PID Tuning Procedures](#pid-tuning-procedures)
6. [Velocity Control Tuning](#velocity-control-tuning)
7. [Position Control Tuning](#position-control-tuning)
8. [Advanced Tuning](#advanced-tuning)
9. [Parameter Reference](#parameter-reference)
10. [Troubleshooting](#troubleshooting)
11. [Emergency Procedures](#emergency-procedures)

---

## Introduction

This guide provides step-by-step procedures for tuning the ODrive motor controllers used in the Pragati cotton-picking robot. Proper motor tuning is essential for:

- **Smooth motion** - Eliminating oscillations and jerky movements
- **Accuracy** - Achieving precise positioning for cotton picking
- **Stability** - Preventing runaway conditions and vibrations  
- **Performance** - Optimizing speed and responsiveness
- **Safety** - Reducing mechanical stress and wear

### When to Tune

Motor tuning should be performed:

- ✅ **Initial setup** - During first-time system commissioning
- ✅ **After hardware changes** - Motor, encoder, or gearbox replacement
- ✅ **Performance issues** - Oscillations, overshoot, or sluggish response
- ✅ **Load changes** - Significant changes to end effector weight
- ✅ **Maintenance** - Part of quarterly preventive maintenance

### Safety Warning

⚠️ **CRITICAL SAFETY INFORMATION** ⚠️

- Incorrect tuning parameters can cause:
  - High-speed uncontrolled motion
  - Excessive motor heating  
  - Mechanical damage to joints
  - Instability and oscillations
  
- **ALWAYS have emergency stop within reach**
- **Start with conservative (low) gain values**
- **Increase gains gradually in small increments**
- **Monitor motor temperature during tuning**

---

## Prerequisites

### Hardware Requirements

- ✅ Pragati robot with all ODrive controllers powered
- ✅ Emergency stop button functional and within reach
- ✅ Clear workspace (minimum 2m x 2m)
- ✅ Thermal camera or infrared thermometer (optional but recommended)
- ✅ Safety barriers or warning signs if operating in shared space

### Software Requirements

- ✅ ROS2 environment sourced:
  ```bash
  source ~/Downloads/pragati_ros2/install/setup.bash
  ```

- ✅ ODrive motor control package built and running:
  ```bash
  ros2 launch yanthra_move pragati_complete.launch.py
  ```

- ✅ ODrive utilities installed (if direct USB tuning needed):
  ```bash
  python3 -m pip install --user odrive
  ```

### Knowledge Requirements

- Basic understanding of PID control concepts
- Familiarity with ROS2 service calls and parameter system
- Ability to interpret joint motion behavior (oscillations, overshoot, etc.)

---

## Quick Tuning Checklist

For experienced operators needing a quick reference:

| Step | Action | Typical Range | Verification |
|------|--------|---------------|--------------|
| 1 | Set velocity controller **P-gain** | 0.1 - 1.0 | No oscillation at constant velocity |
| 2 | Set velocity controller **I-gain** | 0.01 - 0.1 | Reaches target velocity without steady-state error |
| 3 | Set position controller **P-gain** | 5.0 - 50.0 | Reaches target position smoothly |
| 4 | Adjust **velocity limit** | 0.5 - 5.0 rad/s | Safe maximum speed for joint |
| 5 | Configure **acceleration limit** | 1.0 - 10.0 rad/s² | Smooth acceleration profile |
| 6 | Test **full range motion** | - | No oscillation, overshoot < 2% |
| 7 | **Save configuration** | - | Persist to ODrive NVM |

**Estimated Time:** 45-90 minutes per joint (first time), 15-30 minutes for fine-tuning

---

## Understanding Motor Control

### ODrive Control Hierarchy

The ODrive uses a cascaded control loop architecture:

```
Position Setpoint 
    ↓
┌──────────────────────┐
│ Position Controller  │ (P-only)
│   Output: Velocity   │
└──────────────────────┘
    ↓
┌──────────────────────┐
│ Velocity Controller  │ (PI)
│   Output: Current    │
└──────────────────────┘
    ↓
┌──────────────────────┐
│ Current Controller   │ (PI, runs at 8kHz)
│   Output: Voltage    │
└──────────────────────┘
    ↓
 Motor PWM
```

### Control Modes

Pragati uses different control modes for different joints:

| Joint | Control Mode | Reason |
|-------|--------------|--------|
| Joint 2 (vertical prismatic) | Position Control | Precise height positioning |
| Joint 3 (phi - vertical revolute) | Position Control | Accurate angle control |
| Joint 4 (theta - horizontal revolute) | Position Control | Precise horizontal angle |
| Joint 5 (prismatic end effector) | Velocity Control | Smooth extension/retraction |

### Key Concepts

**P-Gain (Proportional)**
- Determines response strength to position/velocity error
- Higher P = faster response, but risk of oscillation
- Too low = sluggish, doesn't reach target
- Too high = overshoot, ringing, instability

**I-Gain (Integral)**
- Eliminates steady-state error over time
- Higher I = faster error elimination
- Too high = overshoot, slow settling
- Generally 10-100x smaller than P-gain

**D-Gain (Derivative)**
- Dampens oscillations (ODrive typically doesn't expose this for position/velocity loops)
- Used internally in current control loop

---

## PID Tuning Procedures

### Method 1: Manual Tuning (Recommended for First-Time)

This method gives you hands-on understanding of how each parameter affects motion.

#### Step 1: Prepare the System

1. **Launch system in safe mode:**
   ```bash
   ros2 launch yanthra_move pragati_complete.launch.py \
     continuous_operation:=false \
     simulation_mode:=false
   ```

2. **Verify motor is enabled and homed:**
   ```bash
   # Home the joint you'll be tuning (example: joint 3)
   ros2 service call /motor/home_joint motor_control_ros2/srv/JointHoming \
     "{homing_required: true, joint_id: 3}"
   ```

3. **Check current parameters:**
   ```bash
   ros2 param get /motor_controller joint3_pos_gain
   ros2 param get /motor_controller joint3_vel_gain
   ros2 param get /motor_controller joint3_vel_integrator_gain
   ```

#### Step 2: Start with Safe Baseline

1. **Set conservative initial values:**
   ```bash
   # Position loop gain (start low)
   ros2 param set /motor_controller joint3_pos_gain 10.0
   
   # Velocity loop P-gain (start low)
   ros2 param set /motor_controller joint3_vel_gain 0.2
   
   # Velocity loop I-gain (start very low)
   ros2 param set /motor_controller joint3_vel_integrator_gain 0.02
   ```

2. **Test small motion:**
   ```bash
   # Send a small position command (e.g., 0.1 radians)
   ros2 topic pub --once /joint3_position_controller/command std_msgs/msg/Float64 "{data: 0.1}"
   ```

3. **Observe behavior:**
   - Does it move smoothly?
   - Does it reach the target position?
   - Is there overshoot or oscillation?
   - How long does it take to settle?

#### Step 3: Tune Velocity Controller

The velocity controller is the inner loop and should be tuned first.

**3a. Tune Velocity P-Gain**

1. **Command constant velocity:**
   ```bash
   # For velocity control testing, temporarily switch control mode
   # (or use velocity commands if your joint supports it)
   ros2 topic pub /joint3_velocity_command std_msgs/msg/Float64 "{data: 0.5}"
   ```

2. **Increase vel_gain gradually:**
   ```bash
   # Start: 0.2, then try 0.3, 0.4, 0.5...
   ros2 param set /motor_controller joint3_vel_gain 0.3
   ```

3. **Stop when you observe:**
   - ✅ **Good:** Smooth acceleration to target velocity
   - ❌ **Too high:** Oscillation or high-frequency vibration
   - ❌ **Too low:** Very slow to reach target velocity

4. **Back off 20-30% from oscillation threshold:**
   ```bash
   # If oscillation started at 0.8, use 0.6 (25% reduction)
   ros2 param set /motor_controller joint3_vel_gain 0.6
   ```

**3b. Tune Velocity I-Gain**

1. **Set I-gain to 10% of P-gain:**
   ```bash
   # If vel_gain = 0.6, start with vel_integrator_gain = 0.06
   ros2 param set /motor_controller joint3_vel_integrator_gain 0.06
   ```

2. **Test steady-state accuracy:**
   - Does velocity reach exactly the commanded value?
   - Is there steady-state error (velocity slightly off target)?

3. **Increase I-gain if steady-state error exists:**
   ```bash
   # Try 0.08, 0.10, etc.
   ros2 param set /motor_controller joint3_vel_integrator_gain 0.08
   ```

4. **Stop increasing if:**
   - ✅ Steady-state error eliminated
   - ❌ Overshoot or slow settling appears

#### Step 4: Tune Position Controller

Now tune the outer position control loop.

1. **Set position P-gain conservatively:**
   ```bash
   ros2 param set /motor_controller joint3_pos_gain 15.0
   ```

2. **Test step response:**
   ```bash
   # Command a position step (0.5 radians)
   ros2 topic pub --once /joint3_position_controller/command std_msgs/msg/Float64 "{data: 0.5}"
   ```

3. **Observe settling behavior:**
   - Rise time (how fast it moves toward target)
   - Overshoot (how much it exceeds target)
   - Settling time (how long until motion stops)

4. **Increase pos_gain gradually:**
   ```bash
   # Try 20.0, 25.0, 30.0, ...
   ros2 param set /motor_controller joint3_pos_gain 25.0
   ```

5. **Optimal tuning criteria:**
   - ✅ Rise time: < 1-2 seconds for full range motion
   - ✅ Overshoot: < 2-5% of step size
   - ✅ Settling time: < 0.5 seconds
   - ✅ No oscillation or ringing

6. **Final position gain:**
   ```bash
   # Example final value (will vary by joint)
   ros2 param set /motor_controller joint3_pos_gain 22.0
   ```

#### Step 5: Set Velocity and Acceleration Limits

Safety limits prevent dangerous high-speed motion.

1. **Configure velocity limit:**
   ```bash
   # Maximum safe velocity (radians/second or meters/second)
   # Revolute joints: typically 1.0 - 3.0 rad/s
   # Prismatic joints: typically 0.5 - 2.0 m/s
   ros2 param set /motor_controller joint3_vel_limit 2.0
   ```

2. **Configure acceleration limit:**
   ```bash
   # Maximum acceleration (rad/s² or m/s²)
   ros2 param set /motor_controller joint3_accel_limit 5.0
   ```

3. **Test with full range motion:**
   ```bash
   # Move from minimum to maximum position
   ros2 topic pub --once /joint3_position_controller/command std_msgs/msg/Float64 "{data: -0.8}"
   # Wait for arrival
   sleep 3
   ros2 topic pub --once /joint3_position_controller/command std_msgs/msg/Float64 "{data: 0.8}"
   ```

4. **Verify:**
   - Motion is smooth
   - Acceleration is not excessively abrupt
   - No overshoot at endpoints

#### Step 6: Save Configuration

1. **Persist parameters to ODrive non-volatile memory:**
   ```bash
   ros2 service call /motor/save_configuration motor_control_ros2/srv/SaveConfiguration "{}"
   ```

2. **Backup parameters to file:**
   ```bash
   ros2 param dump /motor_controller \
     --output-dir ~/.ros/config/motor_tuning/ \
     --print motor_tuning_joint3_$(date +%Y%m%d).yaml
   ```

3. **Document in maintenance log:**
   ```
   Date: 2025-10-09
   Joint: Joint 3 (phi - vertical revolute)
   Tuner: [Your Name]
   Final Parameters:
     - pos_gain: 22.0
     - vel_gain: 0.6
     - vel_integrator_gain: 0.08
     - vel_limit: 2.0 rad/s
     - accel_limit: 5.0 rad/s²
   Notes: Tuned after end effector weight increased by 200g
   ```

---

### Method 2: Ziegler-Nichols Tuning (Advanced)

For users familiar with control theory, the Ziegler-Nichols method provides a systematic approach.

#### Z-N Procedure

1. **Set I-gain and D-gain to zero**
2. **Increase P-gain until sustained oscillation occurs** (critical gain Kc)
3. **Measure oscillation period** (Tc)
4. **Calculate PID gains:**
   - P-gain = 0.6 × Kc
   - I-gain = 1.2 × Kc / Tc
   - D-gain = 0.075 × Kc × Tc

⚠️ **Warning:** This method can cause aggressive oscillations. Use only if you're experienced and have mechanical hard stops or software limits configured.

---

## Velocity Control Tuning

For joints primarily using velocity control (e.g., Joint 5 prismatic extension):

### Procedure

1. **Set position gains to zero** (disable position control loop)

2. **Tune velocity PI controller:**
   ```bash
   ros2 param set /motor_controller joint5_vel_gain 0.3
   ros2 param set /motor_controller joint5_vel_integrator_gain 0.03
   ```

3. **Test velocity commands:**
   ```bash
   # Forward velocity
   ros2 topic pub /joint5_velocity_command std_msgs/msg/Float64 "{data: 1.0}"
   
   # Stop
   ros2 topic pub /joint5_velocity_command std_msgs/msg/Float64 "{data: 0.0}"
   
   # Reverse velocity
   ros2 topic pub /joint5_velocity_command std_msgs/msg/Float64 "{data: -1.0}"
   ```

4. **Evaluate:**
   - Velocity tracking accuracy
   - Response time to velocity changes
   - Smoothness of acceleration/deceleration

5. **Adjust gains** using same procedure as position tuning:
   - Increase P until oscillation, then back off 20-30%
   - Set I to ~10% of P
   - Fine-tune to eliminate steady-state error

---

## Position Control Tuning

Detailed tuning for precise position control (Joints 2, 3, 4):

### Step-by-Step

1. **Initial Setup:**
   ```bash
   # Joint 2 example (vertical prismatic, heaviest load)
   ros2 param set /motor_controller joint2_pos_gain 20.0
   ros2 param set /motor_controller joint2_vel_gain 0.5
   ros2 param set /motor_controller joint2_vel_integrator_gain 0.05
   ros2 param set /motor_controller joint2_vel_limit 1.5  # m/s
   ros2 param set /motor_controller joint2_accel_limit 3.0  # m/s²
   ```

2. **Test different position targets:**
   ```bash
   # Near position (small step)
   ros2 topic pub --once /joint2_position_controller/command std_msgs/msg/Float64 "{data: 0.05}"
   
   # Medium position
   ros2 topic pub --once /joint2_position_controller/command std_msgs/msg/Float64 "{data: 0.3}"
   
   # Far position (large step)
   ros2 topic pub --once /joint2_position_controller/command std_msgs/msg/Float64 "{data: 0.8}"
   ```

3. **Measure performance:**
   ```bash
   # Monitor position tracking
   ros2 topic echo /joint_states
   
   # Record settling time, overshoot, steady-state error
   ```

4. **Iterate tuning** until performance goals met

---

## Advanced Tuning

### Current Limiting

Protect motors from overcurrent damage:

```bash
# Set current limit (Amps)
ros2 param set /motor_controller joint3_current_limit 20.0
```

### Bandwidth Tuning

For faster response (advanced users):

```bash
# Increase control loop bandwidth (Hz)
ros2 param set /motor_controller joint3_bandwidth 100.0
```

⚠️ Higher bandwidth can cause instability with mechanical compliance or sensor noise.

### Load Compensation

For joints with significant gravity loading:

```bash
# Feed-forward torque compensation
ros2 param set /motor_controller joint2_feedforward_torque 5.0  # Nm
```

### Anti-Windup

Prevent integrator windup during saturation:

```bash
# Integrator clamp (usually set automatically, but can override)
ros2 param set /motor_controller joint3_integrator_clamp 10.0
```

---

## Parameter Reference

### Joint 2 (Vertical Prismatic) - Typical Values

```yaml
joint2_pos_gain: 20.0 - 40.0  # Position P-gain
joint2_vel_gain: 0.4 - 0.8    # Velocity P-gain
joint2_vel_integrator_gain: 0.04 - 0.08  # Velocity I-gain
joint2_vel_limit: 1.0 - 2.0  # m/s
joint2_accel_limit: 2.0 - 5.0  # m/s²
joint2_current_limit: 15.0 - 25.0  # Amps
```

### Joint 3 (Phi - Vertical Revolute) - Typical Values

```yaml
joint3_pos_gain: 15.0 - 30.0  # Position P-gain
joint3_vel_gain: 0.3 - 0.7    # Velocity P-gain
joint3_vel_integrator_gain: 0.03 - 0.07  # Velocity I-gain
joint3_vel_limit: 1.5 - 3.0  # rad/s
joint3_accel_limit: 3.0 - 8.0  # rad/s²
joint3_current_limit: 12.0 - 20.0  # Amps
```

### Joint 4 (Theta - Horizontal Revolute) - Typical Values

```yaml
joint4_pos_gain: 15.0 - 30.0  # Position P-gain
joint4_vel_gain: 0.3 - 0.7    # Velocity P-gain
joint4_vel_integrator_gain: 0.03 - 0.07  # Velocity I-gain
joint4_vel_limit: 1.5 - 3.0  # rad/s
joint4_accel_limit: 3.0 - 8.0  # rad/s²
joint4_current_limit: 12.0 - 20.0  # Amps
```

### Joint 5 (Prismatic End Effector) - Typical Values

```yaml
joint5_pos_gain: 10.0 - 25.0  # Position P-gain (if used)
joint5_vel_gain: 0.2 - 0.5    # Velocity P-gain
joint5_vel_integrator_gain: 0.02 - 0.05  # Velocity I-gain
joint5_vel_limit: 0.5 - 1.5  # m/s
joint5_accel_limit: 2.0 - 6.0  # m/s²
joint5_current_limit: 10.0 - 18.0  # Amps
```

**Note:** These are starting points. Actual optimal values depend on:
- Mechanical system characteristics (inertia, friction, compliance)
- Load conditions (end effector weight)
- Performance requirements (speed vs. accuracy)
- Environmental factors (temperature, vibration)

---

## Troubleshooting

### Problem: Oscillation / Vibration

**Symptoms:**
- Joint vibrates or oscillates around target position
- High-frequency buzzing noise from motor
- Position never settles

**Solutions:**
1. **Reduce P-gain** (most common fix):
   ```bash
   # Reduce by 20-30%
   ros2 param set /motor_controller joint3_pos_gain 15.0  # was 20.0
   ```

2. **Reduce velocity loop gains:**
   ```bash
   ros2 param set /motor_controller joint3_vel_gain 0.4  # was 0.6
   ```

3. **Check mechanical issues:**
   - Loose couplings or mounts
   - Worn bearings
   - Belt tension (if applicable)

4. **Add mechanical damping** (hardware solution)

---

### Problem: Sluggish Response

**Symptoms:**
- Takes very long to reach target position
- Slow acceleration
- Fails to reach target (steady-state error)

**Solutions:**
1. **Increase P-gain:**
   ```bash
   ros2 param set /motor_controller joint3_pos_gain 25.0  # was 18.0
   ```

2. **Increase velocity limit:**
   ```bash
   ros2 param set /motor_controller joint3_vel_limit 2.5  # was 1.5
   ```

3. **Add/increase I-gain** (if steady-state error):
   ```bash
   ros2 param set /motor_controller joint3_vel_integrator_gain 0.08  # was 0.04
   ```

4. **Check for mechanical friction:**
   - Dry or worn bearings
   - Misalignment
   - Cable drag

---

### Problem: Overshoot

**Symptoms:**
- Joint overshoots target position
- Requires multiple oscillations to settle

**Solutions:**
1. **Reduce P-gain slightly:**
   ```bash
   ros2 param set /motor_controller joint3_pos_gain 18.0  # was 22.0
   ```

2. **Reduce velocity limit:**
   ```bash
   ros2 param set /motor_controller joint3_vel_limit 1.8  # was 2.5
   ```

3. **Increase acceleration limit** (counter-intuitive but helps):
   ```bash
   # Allows faster deceleration near target
   ros2 param set /motor_controller joint3_accel_limit 6.0  # was 4.0
   ```

4. **Add damping** (if available in your control mode)

---

### Problem: Motor Overheating

**Symptoms:**
- Motor housing temperature > 70°C
- Thermal protection triggering
- Loss of torque over time

**Solutions:**
1. **Reduce current limit:**
   ```bash
   ros2 param set /motor_controller joint3_current_limit 15.0  # was 20.0
   ```

2. **Check for:**
   - Excessive friction (mechanical binding)
   - Continuous high-speed operation
   - Inadequate cooling/ventilation

3. **Increase thermal limits** (only if motor rating allows):
   ```bash
   ros2 param set /motor_controller joint3_thermal_limit 80.0  # °C
   ```

4. **Duty cycle management:** Add pauses between operations

---

### Problem: Position Drift

**Symptoms:**
- Position slowly drifts over time
- Zero position changes after homing
- Inconsistent repeatability

**Solutions:**
1. **Check encoder:**
   - Verify encoder counts are stable when stationary
   - Check for electrical noise
   - Inspect encoder cabling

2. **Increase velocity I-gain** (reduces steady-state error):
   ```bash
   ros2 param set /motor_controller joint3_vel_integrator_gain 0.10  # was 0.06
   ```

3. **Recalibrate encoder:**
   ```bash
   ros2 service call /motor/encoder_calibrate motor_control_ros2/srv/EncoderCalibration \
     "{joint_id: 3, index_search: true, timeout: 20.0}"
   ```

4. **Check for mechanical play** (backlash, loose components)

---

### Problem: Erratic Motion

**Symptoms:**
- Unpredictable, jerky movements
- Different behavior each time
- Random errors or faults

**Solutions:**
1. **Check communication:**
   ```bash
   # Monitor CAN bus or serial errors
   ros2 topic echo /motor/diagnostics
   ```

2. **Verify power supply:**
   - Voltage stability (should be within ±5% of rated)
   - Current capacity adequate for peak loads
   - Proper grounding

3. **Software issues:**
   ```bash
   # Restart motor controller node
   ros2 lifecycle set /motor_controller shutdown
   ros2 lifecycle set /motor_controller configure
   ros2 lifecycle set /motor_controller activate
   ```

4. **EMI/RFI interference:**
   - Check cable routing
   - Add ferrite beads on motor cables
   - Separate power and signal cables

---

## Emergency Procedures

### Emergency Stop

**Physical E-Stop Button:**
- Press large red mushroom button on robot base
- Cuts power to all motors immediately
- Requires manual reset before operation can resume

**Software Emergency Stop:**
```bash
# Stop all motion immediately
ros2 service call /motor/emergency_stop std_srvs/srv/Trigger

# Or publish to stop topic
ros2 topic pub --once /emergency_stop std_msgs/msg/Bool "{data: true}"
```

---

### Motor Runaway Condition

If a motor runs away uncontrollably:

1. **Press physical E-stop** (fastest)
2. **Cut main power** if E-stop doesn't work
3. **After stopping:**
   ```bash
   # Disable all motors
   ros2 service call /motor/disable_all motor_control_ros2/srv/DisableMotors
   
   # Reset ODrive controller
   ros2 service call /motor/reboot motor_control_ros2/srv/Reboot
   ```

4. **Investigate cause:**
   - Check parameter values (especially gains)
   - Inspect for encoder issues
   - Review logs for error messages

5. **Before resuming:**
   - Load known-good configuration
   - Test with reduced gains
   - Verify encoder functionality

---

### Thermal Overload

If motors are overheating:

1. **Stop operation immediately**
2. **Let motors cool** (wait at least 15 minutes)
3. **Inspect for:**
   - Blocked ventilation
   - Continuous high-current operation
   - Mechanical binding causing excess load

4. **Reduce current limit temporarily:**
   ```bash
   ros2 param set /motor_controller joint3_current_limit 12.0  # was 18.0
   ```

5. **Monitor temperature:**
   ```bash
   ros2 topic echo /motor/temperature
   ```

---

### Configuration Corruption

If motor parameters seem incorrect or corrupted:

1. **Load factory defaults:**
   ```bash
   ros2 service call /motor/load_defaults motor_control_ros2/srv/LoadDefaults
   ```

2. **Restore from backup:**
   ```bash
   ros2 param load /motor_controller \
     ~/.ros/config/motor_tuning/motor_tuning_YYYYMMDD.yaml
   ```

3. **Re-home all joints:**
   ```bash
   for joint_id in 2 3 4 5; do
     ros2 service call /motor/home_joint motor_control_ros2/srv/JointHoming \
       "{homing_required: true, joint_id: $joint_id}"
     sleep 3
   done
   ```

4. **Verify motion with conservative parameters** before returning to full speed

---

## Best Practices

### Documentation

- **Record all parameter changes** in maintenance log
- **Document reasons** for tuning (e.g., "reduced overshoot from 8% to 2%")
- **Keep dated configuration backups** (at least 3 most recent)
- **Note environmental conditions** (temperature, humidity, load weight)

### Testing

- **Always test in safe mode first** (single-cycle, emergency stop accessible)
- **Test full range of motion** (minimum, maximum, and mid-range positions)
- **Test with representative loads** (actual end effector, cotton load if possible)
- **Verify repeatability** (10+ cycles to same position)

### Maintenance

- **Quarterly tuning review** - Check if performance has degraded
- **After mechanical work** - Re-tune affected joints
- **Monitor trends** - Track if gains need adjustment over time
- **Temperature logs** - Record motor temperatures during operation

---

## Related Documentation

- **[CALIBRATION_GUIDE.md](./CALIBRATION_GUIDE.md)** - Motor homing and encoder calibration
- **[HARDWARE_TEST_CHECKLIST.md](./HARDWARE_TEST_CHECKLIST.md)** - Pre-operation hardware verification
- **[TESTING_AND_VALIDATION_PLAN.md](./TESTING_AND_VALIDATION_PLAN.md)** - System-level testing procedures
- **ODrive Documentation** - https://docs.odriverobotics.com/ (for low-level tuning)

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-10-09 | System | Initial motor tuning guide created |

---

## Support

For assistance with motor tuning:

1. **Check troubleshooting section** above
2. **Review ODrive logs:** `/var/log/pragati/odrive_*.log`
3. **Consult ODrive community:** https://discourse.odriverobotics.com/
4. **Contact Pragati support** with:
   - Current parameter values
   - Description of problem behavior
   - Video of motion issue (if applicable)
   - Motor temperature readings
   - Recent maintenance history

---

**End of Motor Tuning Guide**
