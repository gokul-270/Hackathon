# ODrive ROS2 Services and Nodes Documentation

## Overview
This document provides a complete guide to ODrive ROS2 services, nodes, and configuration for the Pragati robotic arm system. It includes ROS1-to-ROS2 migration mapping, service definitions, parameter loading, and usage examples.

---

## ✅ Parameter Loading Status

### YAML Configuration Loading: **WORKING ✅**
- **Source File**: `src/motor_control_ros2/config/odrive_service_params.yaml`
- **Loading Method**: ROS2 parameter system via `--params-file` argument
- **Status**: All parameters loaded correctly from YAML (no hardcoded fallbacks)

### Verified Parameters Loaded:
```
Joint joint2: ODrive=1, CAN=0x003, Axis=1, TF=125.236640, Dir=1, PGain=35.000
Joint joint3: ODrive=0, CAN=0x001, Axis=1, TF=0.870047, Dir=-1, PGain=35.000
Joint joint4: ODrive=1, CAN=0x002, Axis=0, TF=14.285710, Dir=-1, PGain=35.000
Joint joint5: ODrive=0, CAN=0x000, Axis=0, TF=25.477000, Dir=-1, PGain=35.000
```

---

## Services: ROS1 vs ROS2 Comparison

### ROS1 Baseline Services
| Service | Request | Response | Purpose |
|---------|---------|----------|---------|
| `odrive_control/joint_homing` | `int64 joint_id` | `string reason` | Home a specific joint |
| `yanthra_move/arm_status` | `none` | `string status` | Get overall arm status |

### ROS2 Services Overview

The project defines a larger service surface (including admin/maintenance services), but the current runtime exposes a focused subset for normal operation. Below are the definitions and the current runtime status observed on this build.

#### 1. `/joint_homing` ⭐ **ESSENTIAL** (ROS1 Parity)
Status: AVAILABLE (observed at runtime)
- **Type**: `motor_control_ros2/srv/JointHoming`
- **Request**: 
  ```
  bool homing_required
  int32 joint_id
  ```
- **Response**: 
  ```
  bool success
  string reason
  ```
- **Purpose**: Home a specific joint to its reference position
- **ROS1 Mapping**: Direct equivalent to ROS1 `joint_homing` service
- **Usage**: 
  ```bash
  ros2 service call /joint_homing motor_control_ros2/srv/JointHoming "{homing_required: true, joint_id: 3}"
  ```

#### 2. `/joint_status` ⭐ **ESSENTIAL** (Enhanced for ROS2)
Status: AVAILABLE (observed at runtime)
- **Type**: `motor_control_ros2/srv/JointStatus`
- **Request**: 
  ```
  int64 joint_id  # Use -1 for all joints
  ```
- **Response**: 
  ```
  bool success
  string reason
  int64[] joint_ids
  float64[] positions
  float64[] velocities
  float64[] efforts
  float64[] temperatures
  int32[] error_counts
  string[] status_messages
  ```
- **Purpose**: Query detailed status of one or all joints
- **ROS1 Mapping**: New service (ROS1 had no direct equivalent)
- **Usage**: 
  ```bash
  # Single joint
  ros2 service call /joint_status motor_control_ros2/srv/JointStatus "{joint_id: 3}"
  # All joints
  ros2 service call /joint_status motor_control_ros2/srv/JointStatus "{joint_id: -1}"
  ```

#### 3. `/joint_idle` 🔧 **OPTIONAL** (New in ROS2)
Status: AVAILABLE (observed at runtime)
- **Type**: `motor_control_ros2/srv/JointHoming` (reuses JointHoming type)
- **Request**: 
  ```
  bool homing_required  # ignored
  int32 joint_id
  ```
- **Response**: 
  ```
  bool success
  string reason
  ```
- **Purpose**: Set joint to IDLE state
- **ROS1 Mapping**: Not present in ROS1
- **Usage**: 
  ```bash
  ros2 service call /joint_idle motor_control_ros2/srv/JointHoming "{homing_required: false, joint_id: 3}"
  ```

#### 4. `/motor_calibration` 🔧 **ADMIN ONLY**
Status: NOT EXPOSED IN CURRENT BUILD (planned/optional)
- **Type**: `motor_control_ros2/srv/MotorCalibration`
- **Request**: 
  ```
  int64 joint_id
  bool full_calibration
  float64 timeout
  ```
- **Response**: 
  ```
  bool success
  string reason
  float64 calibration_time
  ```
- **Purpose**: Perform motor calibration (maintenance operation)
- **ROS1 Mapping**: Not present in ROS1
- **Usage**: 
  ```bash
  ros2 service call /motor_calibration motor_control_ros2/srv/MotorCalibration "{joint_id: 3, full_calibration: true, timeout: 30.0}"
  ```

#### 5. `/encoder_calibration` 🔧 **ADMIN ONLY**
Status: NOT EXPOSED IN CURRENT BUILD (planned/optional)
- **Type**: `motor_control_ros2/srv/EncoderCalibration`
- **Request**: 
  ```
  int64 joint_id
  bool index_search
  float64 timeout
  ```
- **Response**: 
  ```
  bool success
  string reason
  float64 encoder_offset
  float64 calibration_time
  ```
- **Purpose**: Perform encoder calibration (maintenance operation)
- **ROS1 Mapping**: Not present in ROS1
- **Usage**: 
  ```bash
  ros2 service call /encoder_calibration motor_control_ros2/srv/EncoderCalibration "{joint_id: 3, index_search: true, timeout: 20.0}"
  ```

#### 6. `/joint_configuration` 🔧 **ADMIN ONLY**
Status: NOT EXPOSED IN CURRENT BUILD (planned/optional)
- **Type**: `motor_control_ros2/srv/JointConfiguration`
- **Request**: 
  ```
  int64 joint_id
  string parameter_name
  float64 parameter_value
  bool save_to_file
  ```
- **Response**: 
  ```
  bool success
  string reason
  float64 previous_value
  ```
- **Purpose**: Update joint parameters at runtime
- **ROS1 Mapping**: Not present in ROS1
- **Usage**: 
  ```bash
  ros2 service call /joint_configuration motor_control_ros2/srv/JointConfiguration "{joint_id: 3, parameter_name: 'velocity_limit', parameter_value: 2.0, save_to_file: true}"
  ```

---

## Service Recommendations

### For ROS1 Parity (Minimal Set)
Exposed by default in this build:
- ✅ `/joint_homing` - Essential for joint homing
- ✅ `/joint_status` - Enhanced monitoring (safe addition)
- ✅ `/joint_idle` - Operational convenience

### For Full ROS2 Features
Admin/maintenance services (motor/encoder calibration, joint configuration) can be enabled in a future update via a launch parameter (e.g., `enable_admin_services`). In this build they are documented but not exposed. PRs welcome to wire the flag in `odrive_service_node` and launch files.

---

## Nodes in motor_control_ros2

### 1. `odrive_service_node` ⭐ **MAIN NODE**
- **Executable**: `ros2 run motor_control_ros2 odrive_service_node`
- **Purpose**: Exposes ODrive services and publishes joint states
- **Parameters**: Loads from `odrive_service_params.yaml`
- **Services Created**: All 6 services listed above
- **Publishers**: `/joint_states` (simulation mode)
- **Configuration**: 
  ```yaml
  odrive_service_node:
    ros__parameters:
      joints: ["joint2", "joint3", "joint4", "joint5"]
      joint2: {odrive_id: 1, can_id: 3, axis_id: 1, transmission_factor: 125.23664, direction: 1}
      joint3: {odrive_id: 0, can_id: 1, axis_id: 1, transmission_factor: 0.870047022, direction: -1}
      joint4: {odrive_id: 1, can_id: 2, axis_id: 0, transmission_factor: 14.28571, direction: -1}
      joint5: {odrive_id: 0, can_id: 0, axis_id: 0, transmission_factor: 25.477, direction: -1}
  ```

### 2. `odrive_hardware_interface` 🔧 **LOW-LEVEL**
- **Purpose**: Actual CAN bus communication with ODrive controllers
- **Source**: `odrive_hardware_interface.cpp`
- **Usage**: Used internally by service node and hardware interface
- **Configuration**: Uses same YAML parameters as service node

### 3. `odrive_testing_node` 🧪 **DEVELOPMENT**
- **Executable**: `ros2 run motor_control_ros2 odrive_testing_node`
- **Purpose**: Development and testing utilities
- **Usage**: For validating CAN bus, axis states, initialization sequences
- **Recommendation**: Development use only, not for production

### 4. `odrive_hw_test` 🧪 **DEVELOPMENT**
- **Executable**: `ros2 run motor_control_ros2 odrive_hw_test`
- **Purpose**: Hardware interface testing
- **Usage**: Low-level ODrive communication testing
- **Recommendation**: Development use only

---

## Parameter Structure

### Core Joint Parameters (Per Joint)
Each joint (joint2, joint3, joint4, joint5) has these parameters:

| Parameter | Type | Description | ROS1 Source |
|-----------|------|-------------|-------------|
| `odrive_id` | int | ODrive controller ID (0 or 1) | ✅ Mapped |
| `can_id` | int | CAN bus ID | ✅ Mapped |
| `axis_id` | int | Axis ID on ODrive (0 or 1) | ✅ Mapped |
| `transmission_factor` | double | Motor rotations per joint unit | ✅ Mapped |
| `direction` | int | Motor direction (-1 or 1) | ✅ Mapped |
| `p_gain` | double | Position gain | ✅ Mapped |
| `v_gain` | double | Velocity gain | ✅ Mapped |
| `v_int_gain` | double | Velocity integral gain | ✅ Mapped |
| `max_cur` | double | Maximum current limit | ✅ Mapped |
| `max_vel` | double | Maximum velocity limit | ✅ Mapped |
| `min_vel` | double | Minimum velocity limit | ✅ Mapped |
| `max_t` | double | Maximum temperature limit | ✅ Mapped |
| `homing_pos` | double | Homing position value | ✅ Mapped |
| `limit_switch` | int | GPIO pin for limit switch | ✅ Mapped |

### Loading Method
```bash
ros2 run motor_control_ros2 odrive_service_node --ros-args --params-file src/motor_control_ros2/config/odrive_service_params.yaml
```

---

## Quick Start Commands

### 1. Launch ODrive Service Node
```bash
cd /home/uday/Downloads/pragati_ros2
source install/setup.bash
ros2 run motor_control_ros2 odrive_service_node --ros-args --params-file src/motor_control_ros2/config/odrive_service_params.yaml
```

### 2. List Available Services
```bash
ros2 service list | grep joint
```

### 3. Test Joint Homing
```bash
ros2 service call /joint_homing motor_control_ros2/srv/JointHoming "{homing_required: true, joint_id: 3}"
```

### 4. Check Joint Status
```bash
ros2 service call /joint_status motor_control_ros2/srv/JointStatus "{joint_id: -1}"
```

### 5. Build ODrive Package
```bash
colcon build --packages-select motor_control_ros2
```

---

## Migration Status

### ✅ Completed
- [x] YAML parameter loading (no hardcoded values)
- [x] Service definitions matching ROS1 functionality
- [x] Enhanced monitoring with joint_status service
- [x] Clean compilation with no critical errors
- [x] Parameter validation and display

### 🔄 In Progress  
- [ ] ARM client node ROS2 conversion
- [ ] Launch time optimization
- [ ] Admin services enable/disable parameter

### ⏳ Planned
- [ ] Service response validation
- [ ] Hardware-in-the-loop testing
- [ ] Performance benchmarking vs ROS1

---

## Troubleshooting

### Common Issues
1. **Service not found**: Ensure node is running and parameters loaded
2. **Parameter loading failed**: Check YAML file path and syntax
3. **CAN communication errors**: Verify hardware connections and permissions

### Debug Commands
```bash
# Check if services are available
ros2 service list

# Check parameter values
ros2 param list /odrive_service_node

# Test service call with verbose output
ros2 service call /joint_status motor_control_ros2/srv/JointStatus "{joint_id: 3}" --verbose
```

---

**Document Version**: 1.0  
**Last Updated**: September 2025
**Status**: YAML Parameter Loading ✅ WORKING
