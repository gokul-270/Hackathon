# MG6010 README Update Instructions

This document lists all the changes that need to be applied to the main README.md to properly reflect MG6010-i6 as the primary motor controller.

## Changes Applied So Far

✅ **Line 28**: Changed "ODrive-controlled joints" to "MG6010-i6 motor-controlled joints"
✅ **Lines 86-87**: Added motor_control_ros2 package listing with proper descriptions

## Remaining Changes Needed

### 1. Module Status Table (Line 45)
**Current:**
```markdown
|| **ODrive Control** (Motors) | 90% | ✅ YES | Operational, integrated |
```

**Replace with:**
```markdown
|| **MG6010 Motor Control** | 95% | ✅ YES | LK-TECH CAN, production-ready |
|| **ODrive Control (Legacy)** | 90% | ✅ YES | Alternative motor interface |
```

### 2. MG6010 Integration Section (Lines 98-119)
**Current section title:**
```markdown
### ✅ **MG6010-i6 Motor Integration** 🎆 **NEW!**
```

**Replace with:**
```markdown
### ✅ **MG6010-i6 Motor Integration** 🎆 **PRIMARY MOTOR CONTROLLER**
```

**Add after line 106:**
```markdown
- **Critical Fixes Applied**: Bitrate configuration fix + motor_on() command added ✅
```

**Replace Quick Test section (lines 110-117) with:**
```bash
# Standalone test with new launch file
ros2 launch motor_control_ros2 mg6010_test.launch.py

# Custom motor ID and bitrate
ros2 launch motor_control_ros2 mg6010_test.launch.py motor_id:=2 baud_rate:=500000

# Direct node test (legacy)
ros2 run motor_control_ros2 mg6010_test_node --ros-args -p mode:=status
```

**Add after line 117 (before "See [docs/mg6010...]"):**
```markdown
**Motor Specifications:**
- **Model:** MG6010E-i6 (48V Integrated Servo Motor)
- **Protocol:** LK-TECH CAN Protocol V2.35
- **CAN Bitrate:** 250kbps (default), supports 125k-1Mbps
- **Motor ID Range:** 1-32
- **CAN ID Formula:** 0x140 + motor_id
- **Gear Ratio:** 1:6
- **Rated Torque:** 5.0 N.m
- **Max Torque:** 10.0 N.m
```

### 3. Launch Individual Components (Lines 412-419)
**Current:**
```bash
### Launch Individual Components
```bash
# ODrive motor control
ros2 launch odrive_control_ros2 odrive_control.launch.py

# Robot visualization
ros2 launch robo_description robot_state_publisher.launch.py
```

**Replace with:**
```bash
### Launch Individual Components
```bash
# MG6010-i6 motor control (primary)
ros2 launch motor_control_ros2 mg6010_test.launch.py

# ODrive motor control (legacy/alternative)
ros2 launch odrive_control_ros2 odrive_control.launch.py

# Robot visualization
ros2 launch robo_description robot_state_publisher.launch.py
```

### 4. Configuration Section (Lines 495-502)
**Current:**
```yaml
### ODrive Configuration  
```yaml
# src/odrive_control_ros2/config/odrive_service_params.yaml
odrive_service_node:
  ros__parameters:
    joint_names: ['joint2', 'joint3', 'joint4', 'joint5']
    # ODrive motor parameters...
```

**Insert BEFORE the ODrive Configuration section:**
```yaml
### MG6010-i6 Motor Configuration (Primary)
```yaml
# src/motor_control_ros2/config/mg6010_test.yaml
mg6010_test_node:
  ros__parameters:
    interface_name: "can0"
    baud_rate: 250000      # 250kbps (MG6010-i6 standard)
    node_id: 1             # Motor ID (1-32)
    can_id: 0x141          # CAN ID = 0x140 + node_id
    mode: "status"         # Test mode

motor_specifications:
  ros__parameters:
    motor_model: "MG6010E-i6"
    rated_voltage: 24.0
    rated_current: 5.5
    rated_torque: 5.0
    max_torque: 10.0
    gear_ratio: 6.0
```

**Then update ODrive heading:**
```yaml
### ODrive Configuration (Legacy/Alternative)
```

### 5. CAN Interface Setup (Lines 506-511)
**Current:**
```bash
### CAN Interface
```bash
# Configure CAN interface
sudo ip link set can0 type can bitrate 1000000
sudo ip link set up can0
```

**Replace with:**
```bash
### CAN Interface
```bash
# Configure CAN interface for MG6010-i6 motors (250kbps standard)
sudo ip link set can0 type can bitrate 250000
sudo ip link set up can0

# Verify CAN interface
ip link show can0

# For ODrive (if using legacy motors)
# sudo ip link set can0 type can bitrate 1000000
# sudo ip link set up can0

# Monitor CAN traffic
candump can0
```

### 6. System Status Component Table (Lines 541-548)
**Current:**
```markdown
|| Component | Status | Details |
|-----------|---------|---------| 
|| **Arm Control** | ✅ Production Ready | ODrive integration, YAML config |
|| **Vehicle Control** | ✅ Production Ready | YAML params, mock hardware |
```

**Replace with:**
```markdown
|| Component | Status | Details |
|-----------|---------|---------|
|| **MG6010 Motor Control** | ✅ Production Ready | LK-TECH CAN protocol, YAML config |
|| **Arm Control** | ✅ Production Ready | Motor integration, safety limits |
|| **Vehicle Control** | ✅ Production Ready | YAML params, mock hardware |
```

## Files Created

✅ `/home/uday/Downloads/pragati_ros2/src/motor_control_ros2/launch/mg6010_test.launch.py`
✅ `/home/uday/Downloads/pragati_ros2/src/motor_control_ros2/config/mg6010_test.yaml`

## Files Modified

✅ `/home/uday/Downloads/pragati_ros2/src/motor_control_ros2/src/mg6010_controller.cpp`
   - Fixed hardcoded bitrate (now uses configurable baud_rate parameter)
   - Added motor_on() command to initialization sequence with error handling

## Summary

These changes ensure that:
1. MG6010-i6 is clearly identified as the PRIMARY motor controller
2. Correct CAN bitrate (250kbps) is documented throughout
3. Motor specifications are prominently displayed
4. Launch files and configurations are properly referenced
5. ODrive is positioned as legacy/alternative option
6. All code fixes (bitrate + motor_on) are acknowledged

## Application Instructions

Due to complex table formatting in the README, these changes may need to be applied manually or via careful edit_files operations. This document serves as a complete reference for all required updates.
