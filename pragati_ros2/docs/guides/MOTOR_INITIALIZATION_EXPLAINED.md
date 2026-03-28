# Motor Initialization Process Explained

## Overview

When you start the `mg6010_controller_node`, it **automatically performs motor initialization (homing)** for all configured motors before accepting position commands.

---

## Initialization Flow

### 1. Node Startup
```bash
ros2 run motor_control_ros2 mg6010_controller_node \
  --ros-args --params-file src/motor_control_ros2/config/mg6010_three_motors.yaml
```

### 2. Configuration Loading

The node reads from `mg6010_three_motors.yaml`:
```yaml
motor_ids: [1, 2, 3]              # CAN IDs for 3 motors
joint_names: [joint3, joint4, joint5]
transmission_factors: [6.0, 480.1, 480.1]
directions: [1, 1, 1]

# HOMING POSITIONS (in MOTOR degrees, not joint angles)
homing_positions:
  - 4200.0   # joint3: 700° output × 6 (internal gear) = 4200° motor
  - 18000.0  # joint4: 3000° output × 6 = 18000° motor
  - 12000.0  # joint5: 2000° output × 6 = 12000° motor
```

### 3. CAN Interface Initialization
```
✅ CAN interface initialized: can0 @ 500000 baud
```

### 4. Motor Initialization Loop

For **each motor** (joint3, joint4, joint5):

```
╔═══════════════════════════════════════╗
║  Homing Sequence: joint3              ║
╚═══════════════════════════════════════╝

[1/4] Reading current motor position...
      Current position: 0.123 rad (7.0°)

[2/4] Entering multi-loop angle mode 1 (closed-loop control)...
      ✓ Motor entered closed-loop mode at current position

[3/4] Moving to motor zero position (0.0 rad)...
      ✓ Moving to motor zero...
      [Motor physically moves to 0°]
      Current position: 0.001 rad (0.1°)

[4/4] Moving to arm homing position: 4200.0° (73.304 rad)...
      ✓ Moving to homing position...
      [Motor physically moves to homing position]
      Final position: 73.298 rad (4199.8°)

✅ Homing sequence completed for joint3
```

This repeats for joint4 and joint5.

### 5. ROS 2 Interface Setup
```
✅ Initialized 3 / 3 motors
Publishing: /joint_states
Services: /enable_motors, /disable_motors
📥 Subscribed to: /joint3_position_controller/command
📥 Subscribed to: /joint4_position_controller/command
📥 Subscribed to: /joint5_position_controller/command
✅ ROS 2 interface ready (control loop, joint_states, services)
```

### 6. Ready for Commands
Now the node is **waiting for position commands** from yanthra_move!

---

## What Happens During Homing

### Physical Motor Movement

1. **Motor reads current encoder position** via CAN
2. **Enters closed-loop control** (enables position holding)
3. **Moves to zero** (motor's internal zero reference)
   - Motors will **physically move** during this step
   - You will **HEAR and SEE** movement
4. **Moves to homing position** (configured per-joint)
   - Motors move to predefined safe starting position
   - Arm should be in known configuration

### Why Homing is Important

- ✅ **Establishes zero reference** for all motors
- ✅ **Ensures known starting position** for safety
- ✅ **Calibrates encoder offsets** if needed
- ✅ **Verifies motor communication** before operation

---

## Expected Startup Logs

```
[mg6010_controller_node] ╔═══════════════════════════════════════════════════════╗
[mg6010_controller_node] ║    MG6010 Multi-Motor Controller (ROS 2 Interface)    ║
[mg6010_controller_node] ╚═══════════════════════════════════════════════════════╝
[mg6010_controller_node] 
[mg6010_controller_node] Configuration:
[mg6010_controller_node]   CAN Interface: can0
[mg6010_controller_node]   Baud Rate: 500000
[mg6010_controller_node]   Motor Count: 3
[mg6010_controller_node]   Test Mode: multi_motor
[mg6010_controller_node]   Control Frequency: 10.0 Hz
[mg6010_controller_node] 
[mg6010_controller_node] ✅ CAN interface initialized
[mg6010_controller_node]   joint3: transmission_factor=6.000, direction=1
[mg6010_controller_node]   joint4: transmission_factor=480.100, direction=1
[mg6010_controller_node]   joint5: transmission_factor=480.100, direction=1
[mg6010_controller_node] ✅ Motor 1 initialized: joint3
[mg6010_controller_node] 
[mg6010_controller_node] ╔═══════════════════════════════════════╗
[mg6010_controller_node] ║  Homing Sequence: joint3              ║
[mg6010_controller_node] ╚═══════════════════════════════════════╝
[mg6010_controller_node] [1/4] Reading current motor position...
[mg6010_controller_node]       Current position: 0.123 rad (7.0°)
[mg6010_controller_node] [2/4] Entering multi-loop angle mode 1 (closed-loop control)...
[mg6010_controller_node]       ✓ Motor entered closed-loop mode
[mg6010_controller_node] [3/4] Moving to motor zero position (0.0 rad)...
[mg6010_controller_node]       ✓ Moving to motor zero...
[mg6010_controller_node]       Current position: 0.001 rad (0.1°)
[mg6010_controller_node] [4/4] Moving to arm homing position: 4200.0° (73.304 rad)...
[mg6010_controller_node]       ✓ Moving to homing position...
[mg6010_controller_node]       Final position: 73.298 rad (4199.8°)
[mg6010_controller_node] ✅ Homing sequence completed for joint3
[mg6010_controller_node] 
[mg6010_controller_node] [... same for joint4 and joint5 ...]
[mg6010_controller_node] 
[mg6010_controller_node] ✅ Initialized 3 / 3 motors
[mg6010_controller_node] Publishing: /joint_states
[mg6010_controller_node] 📥 Subscribed to: /joint3_position_controller/command
[mg6010_controller_node] 📥 Subscribed to: /joint4_position_controller/command
[mg6010_controller_node] 📥 Subscribed to: /joint5_position_controller/command
[mg6010_controller_node] ✅ ROS 2 interface ready (control loop, joint_states, services)
```

---

## Troubleshooting

### Motors Don't Move During Homing

**Check:**
```bash
# Verify CAN interface is up
ip link show can0

# Check for CAN traffic
candump can0
```

**Solution:** 
- Motors should be powered (24V)
- CAN termination resistors in place
- CAN interface configured and UP

### Homing Fails or Times Out

**Possible causes:**
- Motor not responding on CAN bus
- Wrong CAN ID configured
- Motor in error state
- Encoder not calibrated

**Solution:**
```bash
# Check motor status with single-motor test
ros2 run motor_control_ros2 mg6010_test_node \
  --ros-args -p interface_name:=can0 -p motor_id:=1 -p mode:=status
```

### Homing Positions Look Wrong

Homing positions in the YAML are **motor angles** (including internal 1:6 gear), not joint angles.

**Conversion:**
```
motor_angle_deg = output_angle_deg × internal_gear_ratio
motor_angle_deg = output_angle_deg × 6.0

Example:
- Joint output wants 700°
- Motor angle = 700° × 6 = 4200° (in config)
```

---

## Summary

✅ **Homing happens automatically** when mg6010_controller_node starts  
✅ **Motors physically move** to zero, then to homing position  
✅ **Takes ~10-15 seconds** for 3 motors (including delays)  
✅ **Must complete successfully** before accepting position commands  
✅ **Configured via YAML** (`mg6010_three_motors.yaml`)  

After homing completes, the node is ready to receive position commands from yanthra_move!
