# Three Motor Setup Guide - MG6010 Integration

## Overview

You're transitioning from the old ODrive-based system to the new MG6010 motor system. This guide will help you set up three MG6010 motors for the Pragati robot arm.

---

## Current System Architecture

### Original ODrive Mapping (Legacy)
| Joint | Function | ODrive ID | CAN ID | Axis |
|-------|----------|-----------|--------|------|
| joint2 | L2 (Linear actuator) | 1 | 0x003 | 1 |
| joint3 | Base (Phi - vertical rotation) | 0 | 0x001 | 1 |
| joint4 | Upper Arm (Theta - horizontal rotation) | 1 | 0x002 | 0 |
| joint5 | End Effector (Linear) | 0 | 0x000 | 0 |

### New MG6010 Mapping (Recommended)
| Joint | Function | Motor Node ID | CAN ID | Notes |
|-------|----------|---------------|--------|-------|
| joint3 | Base (Phi) | 1 | 0x141 | Primary rotation |
| joint4 | Upper Arm (Theta) | 2 | 0x142 | Secondary rotation |
| joint5 | End Effector (Linear) | 3 | 0x143 | Linear actuator |

**Note:** joint2 (L2) will remain on the legacy system or be migrated later.

---

## Physical Setup

### 1. Motor ID Configuration

Each MG6010 motor needs a unique Node ID (1-32). You can set this using:

#### Method A: Via CAN (if motor responds)
```bash
# Set motor node ID (example for setting ID to 1)
cansend can0 140#A600010000000000
# Format: 0x140 (base) + A6 (set ID command) + 00 01 (new ID = 1)
```

#### Method B: Via Motor Configuration Tool
- Use the LK-TECH motor configuration software
- Connect via USB or CAN
- Set Node ID for each motor

### 2. Physical Wiring

**CAN Bus Topology:**
```
Raspberry Pi (CAN0)
    |
    |--- 120Ω termination
    |
    +-- Motor 1 (Node ID: 1, Joint3 - Base)
    |
    +-- Motor 2 (Node ID: 2, Joint4 - Upper Arm)  
    |
    +-- Motor 3 (Node ID: 3, Joint5 - End Effector)
    |
    |--- 120Ω termination
```

**Power:**
- All motors: **48V DC** (rated voltage)
- Connect to common 48V power supply
- Ensure adequate current capacity (≥20A for 3 motors)

**Safety:**
- ⚠️ **Critical**: Verify voltage is 48V before powering motors
- Install emergency stop switch
- Verify CAN termination resistors (120Ω at each end)

---

## Software Configuration

### Step 1: Create Multi-Motor Configuration File

Create `/home/uday/Downloads/pragati_ros2/src/motor_control_ros2/config/mg6010_three_motors.yaml`:

```yaml
# Three Motor Configuration - MG6010
# Motors for joint3, joint4, joint5

# ==============================================================================
# CAN Bus Configuration
# ==============================================================================
can_interface:
  ros__parameters:
    interface_name: "can0"
    bitrate: 500000
    
# ==============================================================================
# Motor 1: Joint3 (Base - Phi rotation)
# ==============================================================================
joint3_motor:
  ros__parameters:
    # Identification
    node_id: 1
    can_id: 0x141
    joint_name: "joint3"
    
    # Motor specs
    motor_model: "MG6010E-i6"
    rated_voltage: 48.0
    rated_current: 5.5
    max_current: 15.0
    gear_ratio: 6.0
    
    # Control parameters (from production.yaml)
    transmission_factor: 0.870047022
    direction: -1
    position_offset: 0.890118
    
    # PID gains
    position_kp: 35.0
    position_ki: 0.0
    position_kd: 0.0
    velocity_kp: 20.0
    
    # Limits
    position_limit_min: -3.14159
    position_limit_max: 6.28318
    velocity_limit: 50.0
    current_limit: 15.0
    
    # Homing
    homing_position: 1.4108

# ==============================================================================
# Motor 2: Joint4 (Upper Arm - Theta rotation)
# ==============================================================================
joint4_motor:
  ros__parameters:
    # Identification
    node_id: 2
    can_id: 0x142
    joint_name: "joint4"
    
    # Motor specs
    motor_model: "MG6010E-i6"
    rated_voltage: 48.0
    rated_current: 5.5
    max_current: 15.0
    gear_ratio: 6.0
    
    # Control parameters (from production.yaml)
    transmission_factor: 14.28571
    direction: -1
    position_offset: -0.200
    
    # PID gains
    position_kp: 100.0
    position_ki: 0.0
    position_kd: 0.0
    velocity_kp: 20.0
    
    # Limits
    position_limit_min: -3.14159
    position_limit_max: 6.28318
    velocity_limit: 60.0
    current_limit: 10.0
    
    # Homing
    homing_position: 3.19159

# ==============================================================================
# Motor 3: Joint5 (End Effector - Linear)
# ==============================================================================
joint5_motor:
  ros__parameters:
    # Identification
    node_id: 3
    can_id: 0x143
    joint_name: "joint5"
    
    # Motor specs
    motor_model: "MG6010E-i6"
    rated_voltage: 48.0
    rated_current: 5.5
    max_current: 15.0
    gear_ratio: 6.0
    
    # Control parameters (from production.yaml)
    transmission_factor: 25.477
    direction: -1
    position_offset: -0.330
    
    # PID gains
    position_kp: 35.0
    position_ki: 0.0
    position_kd: 0.0
    velocity_kp: 20.0
    
    # Limits
    position_limit_min: 0.162  # min_length
    position_limit_max: 0.601  # max_length
    velocity_limit: 133.0
    current_limit: 15.0
    
    # Homing
    homing_position: 0.001

# ==============================================================================
# Safety Configuration
# ==============================================================================
safety_monitor:
  ros__parameters:
    enable_safety_monitoring: true
    enable_position_limits: true
    enable_velocity_limits: true
    enable_temperature_monitoring: true
    enable_voltage_monitoring: true
    
    temperature_warning: 65.0
    temperature_critical: 70.0
    
    voltage_warning_low: 44.0
    voltage_critical_low: 40.0
    voltage_warning_high: 52.0
    voltage_critical_high: 55.0
```

### Step 2: Update Launch File

The launch file should already support multiple motors through the hardware interface. Verify `pragati_complete.launch.py` loads the new config.

---

## Testing Procedure

### Phase 1: Individual Motor Testing

Test each motor individually before integrating all three.

#### Test Motor 1 (Joint3):
```bash
# Ensure CAN is up
sudo ip link set can0 type can bitrate 500000 restart-ms 100 berr-reporting on
sudo ip link set can0 up

# Test single motor
ros2 run motor_control_ros2 mg6010_test_node --ros-args \
    -p node_id:=1 \
    -p can_id:=0x141 \
    -p interface_name:=can0 \
    -p mode:=status
```

#### Test Motor 2 (Joint4):
```bash
ros2 run motor_control_ros2 mg6010_test_node --ros-args \
    -p node_id:=2 \
    -p can_id:=0x142 \
    -p interface_name:=can0 \
    -p mode:=status
```

#### Test Motor 3 (Joint5):
```bash
ros2 run motor_control_ros2 mg6010_test_node --ros-args \
    -p node_id:=3 \
    -p can_id:=0x143 \
    -p interface_name:=can0 \
    -p mode:=status
```

### Phase 2: Multi-Motor Testing

Once individual motors work, test all three together:

```bash
# Terminal 1: Monitor CAN traffic
candump can0

# Terminal 2: Launch system with three motors
ros2 launch yanthra_move pragati_complete.launch.py \
    use_simulation:=false \
    motor_config:=mg6010_three_motors.yaml
```

### Phase 3: Validation Script

Run the updated validation script:

```bash
cd /home/ubuntu/pragati_ws
./scripts/validation/system/run_table_top_validation_v2.sh
```

---

## Troubleshooting

### Issue: Motors not responding
**Check:**
1. CAN bus is UP: `ip -details link show can0`
2. Correct bitrate (500000): `ip -details link show can0 | grep bitrate`
3. CAN termination (120Ω at both ends)
4. Motor power (48V)
5. Motor node IDs are unique

**Debug:**
```bash
# Monitor all CAN traffic
candump can0

# Send status query to motor 1
cansend can0 141#9A00000000000000

# Check if motor responds (should see 0x141 replies)
```

### Issue: CAN bus errors
```bash
# Check error counters
ip -details -statistics link show can0

# If bus-off, restart:
sudo ip link set can0 down
sudo ip link set can0 up
```

### Issue: Wrong motor moves
- Verify node IDs match configuration
- Check CAN ID calculation: `CAN_ID = 0x140 + node_id`
- Verify direction parameter (1 or -1)

### Issue: Position doesn't match expected
- Check transmission_factor matches your motor/gearbox
- Verify encoder resolution (18-bit = 262,144 counts/rev)
- Check position_offset for homing

---

## Migration Checklist

- [ ] Set unique Node IDs on all three motors (1, 2, 3)
- [ ] Verify 48V power supply capacity (≥20A)
- [ ] Install CAN termination resistors (120Ω)
- [ ] Test CAN communication with each motor individually
- [ ] Create `mg6010_three_motors.yaml` configuration
- [ ] Test motors individually with `mg6010_test_node`
- [ ] Verify motor directions match expected rotation
- [ ] Test all three motors together
- [ ] Run validation script
- [ ] Update system documentation

---

## Quick Reference Commands

```bash
# CAN Setup
sudo ip link set can0 type can bitrate 500000 restart-ms 100 berr-reporting on
sudo ip link set can0 up

# Monitor CAN
candump can0

# Status query (Node ID 1)
cansend can0 141#9A00000000000000

# Motor ON (Node ID 1)
cansend can0 141#8800000000000000

# Motor OFF (Node ID 1)
cansend can0 141#8000000000000000

# Check joint states
ros2 topic echo /joint_states

# List motor services
ros2 service list | grep motor
```

---

## Next Steps After Three-Motor Setup

1. **Calibration**: Run homing sequence for all joints
2. **Integration Testing**: Full system validation with cotton detection
3. **Performance Tuning**: Adjust PID gains if needed
4. **Joint2 Migration**: Plan migration of joint2 (L2) to MG6010
5. **Production Deploy**: Move to full field operation

---

## Support Resources

- **MG6010 Manual**: LK-TECH CAN Protocol V2.35
- **Motor Specs**: `config/mg6010_test.yaml`
- **Validation Script**: `scripts/validation/system/run_table_top_validation_v2.sh`
- **Status Documentation**: `src/motor_control_ros2/MOTOR_CONTROL_STATUS.md`

---

**Last Updated**: 2025-10-10
**Author**: Agent Mode
**System**: Pragati ROS2 - MG6010 Motor Integration
