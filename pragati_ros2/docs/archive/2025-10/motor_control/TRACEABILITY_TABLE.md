# Motor Control ROS2 - Code Interface Traceability Table

**Generated**: 2025-10-09  
**Purpose**: Map documentation claims to actual code interfaces for consistency verification

## Executive Summary

### Code Interface Inventory Status
- **Publishers**: 7 discovered
- **Subscribers**: 4 discovered
- **Services**: 12 discovered
- **Actions**: 0 discovered
- **Parameters**: 35+ discovered
- **Enums/States**: 3 state enumerations discovered

### Critical Findings
1. ✅ MG6010 test node defaults to **250kbps** (configurable) in `mg6010_test_node.cpp` (Oct 2025 update)
2. ⚠️ No action servers found - documentation may incorrectly claim action interface
3. ✅ Core abstraction layer well-defined in `motor_abstraction.hpp`
4. ⚠️ Mixed naming conventions: `odrive_control_ros2` vs `motor_control_ros2` in headers

---

## 1. ROS 2 Publishers

| Topic Name | Message Type | File:Line | Node | QoS | Doc Reference |
|------------|--------------|-----------|------|-----|---------------|
| `odrive_test_status` | `std_msgs/String` | odrive_testing_node.cpp:89 | odrive_testing_node | 10 | N/A (test only) |
| `joint_states_test` | `sensor_msgs/JointState` | odrive_testing_node.cpp:90 | odrive_testing_node | 10 | N/A (test only) |
| `joint_states` | `sensor_msgs/JointState` | odrive_service_node.cpp:105 | odrive_service_node | 10 | SERVICES_NODES_GUIDE? |
| `{joint_name}_position` | `std_msgs/Float64` | odrive_service_node.cpp:114 | odrive_service_node | 10 | Per-joint position |
| `{joint_name}_position` | `std_msgs/Float64` | odrive_hardware_interface.cpp:695 | odrive (internal) | ? | Hardware layer |
| `joint_states` | `sensor_msgs/JointState` | odrive_hardware_interface.cpp:702 | odrive (internal) | ? | Hardware layer |

**Issues**:
- `odrive_service_node` creates individual publishers per joint dynamically (lines 113-116)
- Topic names are constructed at runtime: `joint_names[i] + "_position"`
- No centralized topic name constants or configuration

---

## 2. ROS 2 Subscribers

| Topic Name | Message Type | File:Line | Node | Callback | Doc Reference |
|------------|--------------|-----------|------|----------|---------------|
| `/joint2_cmd` | `std_msgs/Float64` | odrive_service_node.cpp:121 | odrive_service_node | `joint2CommandCallback` | Legacy? |
| `/joint3_cmd` | `std_msgs/Float64` | odrive_service_node.cpp:125 | odrive_service_node | `joint3CommandCallback` | Legacy? |
| `/joint4_cmd` | `std_msgs/Float64` | odrive_service_node.cpp:129 | odrive_service_node | `joint4CommandCallback` | Legacy? |
| `/joint5_cmd` | `std_msgs/Float64` | odrive_service_node.cpp:133 | odrive_service_node | `joint5CommandCallback` | Legacy? |

**Issues**:
- Hardcoded joint names (joint2-5), not generic
- No MG6010 equivalent found
- Should these be deprecated in favor of action interface?

---

## 3. ROS 2 Services

### ODrive Legacy Services (odrive_service_node.cpp)

| Service Name | Service Type | File:Line | Description | Doc Reference |
|--------------|--------------|-----------|-------------|---------------|
| `/joint_homing` | `odrive_control_ros2/JointHoming` | line 58 | Joint homing | SERVICES_NODES_GUIDE |
| `/joint_idle` | `odrive_control_ros2/JointHoming` | line 65 | Set joints idle | SERVICES_NODES_GUIDE |
| `/joint_status` | `odrive_control_ros2/JointStatus` | line 72 | Get joint status | SERVICES_NODES_GUIDE |
| `/motor_calibration` | `odrive_control_ros2/MotorCalibration` | line 79 | Calibrate motor | SERVICES_NODES_GUIDE |
| `/encoder_calibration` | `odrive_control_ros2/EncoderCalibration` | line 85 | Calibrate encoder | SERVICES_NODES_GUIDE |
| `/joint_configuration` | `odrive_control_ros2/JointConfiguration` | line 91 | Configure joints | SERVICES_NODES_GUIDE |
| `/joint_position` | `odrive_control_ros2/JointPositionCommand` | line 98 | Set joint position | SERVICES_NODES_GUIDE |

### Test Services (odrive_testing_node.cpp)

| Service Name | Service Type | File:Line | Description | Doc Reference |
|--------------|--------------|-----------|-------------|---------------|
| `/start_odrive_test` | `std_srvs/Trigger` | line 278 | Start test | N/A (test only) |
| `/stop_odrive_test` | `std_srvs/Trigger` | line 289 | Stop test | N/A (test only) |
| `/validate_odrive_hardware` | `std_srvs/Trigger` | line 300 | Validate hardware | N/A (test only) |

### Test Stub Services

| Service Name | Service Type | File:Line | Purpose |
|--------------|--------------|-----------|---------|
| `test_service` | `std_srvs/Empty` | basic_service_test.cpp:29 | Service test stub |
| `motor_calibration` | `motor_control_ros2/MotorCalibration` | simple_service_test_node.cpp:30 | Service test stub |
| `joint_homing` | `motor_control_ros2/JointHoming` | minimal_service_test.cpp:30 | Service test stub |

**Issues**:
- Service type namespace inconsistency: `odrive_control_ros2` vs `motor_control_ros2`
- No MG6010-specific services documented
- Service names are hardcoded strings, not configurable

---

## 4. ROS 2 Actions

**Result**: NO ACTION SERVERS FOUND

```bash
grep -rn "action_server\|ActionServer" src/motor_control_ros2 --include="*.cpp" --include="*.hpp"
# Exit code: 1 (no matches)
```

**Implication**: Any documentation claiming action interface support is **incorrect**.

---

## 5. ROS 2 Parameters

### MG6010 Test Node (mg6010_test_node.cpp:42-50)

| Parameter Name | Type | Default Value | File:Line | Doc Reference |
|----------------|------|---------------|-----------|---------------|
| `interface_name` | string | `"can0"` | line 42 | MG6010 docs? |
| `baud_rate` | int | `250000` | line 43 | MG6010-i6 default |
| `node_id` | int | `1` | line 44 | MG6010 motor ID |
| `mode` | string | `"status"` | line 45 | Test mode |
| `position_rad` | double | `0.0` | line 46 | Target position |
| `velocity_rad_s` | double | `0.5` | line 47 | Target velocity |
| `accel_rad_s2` | double | `1.0` | line 48 | Acceleration |
| `torque_amps` | double | `1.0` | line 49 | Torque/current |
| `verbose` | bool | `true` | line 50 | Debug output |

**Resolved (Oct 2025):** Line 43 now defaults to **250kbps** with parameter overrides; note retained for provenance.

### MG6010 Integrated Test Node (mg6010_integrated_test_node.cpp:44-50)

| Parameter Name | Type | Default Value | File:Line |
|----------------|------|---------------|-----------|
| `interface_name` | string | `"can0"` | line 44 |
| `baud_rate` | int | `250000` | line 45 |
| `node_id` | int | `1` | line 46 |
| `test_mode` | string | `"position"` | line 47 |
| `target_position` | double | `1.57` | line 48 |
| `transmission_factor` | double | `1.0` | line 49 |
| `direction` | int | `1` | line 50 |

**Resolved (Oct 2025):** Defaults updated to 250kbps while keeping parameter override support.

### Control Loop Node (control_loop_node.cpp:63-66)

| Parameter Name | Type | Default Value | File:Line |
|----------------|------|---------------|-----------|
| `loop_hz` | double | `100.0` | line 63 |
| `cycle_time_error_threshold` | double | `0.01` | line 64 |
| `realtime_priority` | int | `50` | line 65 |
| `enable_safety_monitoring` | bool | `true` | line 66 |

### ODrive Testing Node (odrive_testing_node.cpp:67-73)

| Parameter Name | Type | Default Value | File:Line |
|----------------|------|---------------|-----------|
| `test_motor_ids` | vector<int64_t> | `{0, 1}` | line 67 |
| `test_position` | double | `3.0` | line 68 |
| `test_interval_sec` | double | `5.0` | line 69 |
| `enable_continuous_test` | bool | `false` | line 70 |
| `can_interface` | string | `"can0"` | line 71 |
| `enable_hardware_validation` | bool | `true` | line 72 |
| `auto_start_testing` | bool | `false` | line 473 |

### ODrive Service Node - Per-Joint Parameters (odrive_service_node.cpp:181-223)

**Pattern**: `declare_parameter<std::vector<std::string>>("joints")` then per-joint:

For each joint name, the following parameters are declared (prefixed with joint name):

| Parameter Suffix | Type | Purpose | Line |
|------------------|------|---------|------|
| `.odrive_id` | int | ODrive board ID | 210 |
| `.can_id` | int | CAN identifier | 211 |
| `.axis_id` | int | Motor axis (0 or 1) | 212 |
| `.transmission_factor` | double | Gear ratio | 213 |
| `.direction` | int | Direction multiplier | 214 |
| `.p_gain` | double | Position P gain | 215 |
| `.v_gain` | double | Velocity P gain | 216 |
| `.v_int_gain` | double | Velocity I gain | 217 |
| `.max_cur` | double | Current limit | 218 |
| `.max_vel` | double | Velocity limit | 219 |
| `.min_vel` | double | Min velocity | 220 |
| `.max_t` | double | Torque limit | 221 |
| `.homing_pos` | double | Home position | 222 |
| `.limit_switch` | int | Limit switch GPIO | 223 |

**Total**: 14 parameters per joint, dynamically created

---

## 6. State Machines and Enums

### Motor Status State (motor_abstraction.hpp:121-134)

```cpp
enum State {
    UNKNOWN = 0,
    IDLE,
    STARTUP,
    MOTOR_CALIBRATION,
    ENCODER_CALIBRATION,
    CLOSED_LOOP_CONTROL,
    LOCKIN_SPIN,
    ENCODER_DIR_FIND,
    HOMING,
    ENCODER_OFFSET_CALIBRATION,
    AXIS_ERROR
};
```

**File**: `include/motor_control_ros2/motor_abstraction.hpp:121`

### Error Categories (motor_abstraction.hpp:62-73)

```cpp
enum class ErrorCategory : uint8_t {
    NONE = 0,
    COMMUNICATION = 1,
    HARDWARE = 2,
    ENCODER = 3,
    CONTROL = 4,
    SAFETY = 5,
    INITIALIZATION = 6,
    THERMAL = 7,
    POWER = 8
};
```

**File**: `include/motor_control_ros2/motor_abstraction.hpp:62`

### Error Severity (motor_abstraction.hpp:78-85)

```cpp
enum class ErrorSeverity : uint8_t {
    INFO = 0,
    WARNING = 1,
    ERROR = 2,
    CRITICAL = 3,
    FATAL = 4
};
```

**File**: `include/motor_control_ros2/motor_abstraction.hpp:78`

### Homing Methods (motor_abstraction.hpp:180-187)

```cpp
enum HomingMethod {
    LIMIT_SWITCH_ONLY = 1,
    ENCODER_INDEX_ONLY = 2,
    LIMIT_SWITCH_AND_INDEX = 3,
    MECHANICAL_STOP = 4,
    ABSOLUTE_ENCODER = 5
};
```

**File**: `include/motor_control_ros2/motor_abstraction.hpp:180`

---

## 7. Timers

| Timer Purpose | Rate | File:Line | Node |
|---------------|------|-----------|------|
| Joint state publishing | 10 Hz (100ms) | odrive_service_node.cpp:140 | odrive_service_node |

**Note**: Timer callback method name not captured in grep output

---

## 8. Core Interface Classes

### MotorControllerInterface (motor_abstraction.hpp:294-444)

**Abstract interface** for all motor types with 23 pure virtual methods:

#### Configuration & Initialization
- `initialize(config, can_interface)` → bool (line 305)
- `configure(config)` → bool (line 314)
- `get_configuration()` → const MotorConfiguration& (line 418)

#### Motor Control
- `set_enabled(enable)` → bool (line 321)
- `set_position(position, velocity, torque)` → bool (line 330)
- `set_velocity(velocity, torque)` → bool (line 338)
- `set_torque(torque)` → bool (line 345)

#### State Feedback
- `get_position()` → double (line 351)
- `get_velocity()` → double (line 357)
- `get_torque()` → double (line 363)
- `get_status()` → MotorStatus (line 382)

#### Calibration & Homing
- `home_motor(config)` → bool (line 370)
- `is_homed()` → bool (line 376)
- `calibrate_motor()` → bool (line 400)
- `calibrate_encoder()` → bool (line 406)
- `needs_calibration()` → bool (line 412)

#### Error Handling
- `emergency_stop()` → bool (line 388)
- `clear_errors()` → bool (line 394)
- `get_error_info()` → const ErrorInfo& (line 424)
- `get_error_history()` → vector<ErrorInfo> (line 430)
- `attempt_error_recovery()` → RecoveryResult (line 436)
- `set_error_handler(handler)` → void (line 442)

### CANInterface (motor_abstraction.hpp:237-286)

**Abstract CAN communication interface** with 6 pure virtual methods:

- `initialize(interface_name, baud_rate)` → bool (line 248)
- `send_message(id, data)` → bool (line 256)
- `receive_message(id, data, timeout_ms)` → bool (line 265)
- `configure_node(node_id, baud_rate)` → bool (line 273)
- `is_connected()` → bool (line 279)
- `get_last_error()` → string (line 285)

---

## 9. Documentation Gaps Identified

### Critical Gaps

1. **MG6010 Bitrate Mismatch**
   - Code: 1Mbps default
   - Spec: 250kbps standard for MG6010-i6
   - Impact: **CRITICAL** - motor won't communicate
   - Files: `mg6010_test_node.cpp:43`, `mg6010_integrated_test_node.cpp:45`

2. **Missing Action Interface**
   - Documentation may claim action interface
   - Code: No action servers found
   - Impact: **MAJOR** - feature doesn't exist

3. **Namespace Inconsistency**
   - Header guard: `ODRIVE_CONTROL_ROS2__MOTOR_ABSTRACTION_HPP_`
   - Namespace: `motor_control_ros2`
   - Service types: Mixed `odrive_control_ros2` and `motor_control_ros2`
   - Impact: **MINOR** - confusing but functional

### Missing Documentation

1. **No MG6010-Specific Service Interface**
   - All services are ODrive-specific
   - MG6010 equivalents not defined
   - Need: Service mappings or new service definitions

2. **No Centralized Topic/Service Name Configuration**
   - All names are hardcoded strings
   - No constants file or namespace
   - Best practice: Create `topic_names.hpp` with constants

3. **Parameter Validation Rules**
   - No documented ranges/limits for parameters
   - No validation in code visible from grep
   - Need: Document valid ranges, units, constraints

4. **Safety Monitor Integration**
   - `safety_monitor.cpp` references found but interfaces unclear
   - Need: Document safety monitor ROS interface
   - Need: Document integration with control loop

### Documentation Improvements Needed

1. **SERVICES_NODES_GUIDE.md** should include:
   - Complete topic/service/parameter listing (use this table)
   - QoS policies for each topic
   - Service request/response schemas
   - Parameter types, defaults, and valid ranges
   - State machine diagrams

2. **MG6010-Specific Guide** should clarify:
   - Correct CAN bitrate (250kbps, not 1Mbps)
   - Service interface (if different from ODrive)
   - Parameter mappings from ODrive to MG6010
   - Protocol-specific behaviors

3. **README_GENERIC_MOTORS.md** should explain:
   - MotorControllerInterface usage
   - How to add new motor types
   - Factory pattern usage
   - Configuration conversion functions

---

## 10. Code Quality Observations

### Strengths
✅ Well-defined abstract interfaces  
✅ Comprehensive error handling framework  
✅ Factory pattern for motor types  
✅ Configuration manager for parameter conversion  
✅ Detailed error categorization and recovery  

### Weaknesses
⚠️ Hardcoded topic/service names  
⚠️ No parameter validation visible  
⚠️ Namespace inconsistencies  
⚠️ Critical default value errors (bitrate)  
⚠️ No action interface despite possible doc claims  

---

## 11. Recommendations

### Immediate (Critical)

1. **Fix MG6010 Bitrate Defaults**
   - Change line 43 of `mg6010_test_node.cpp` from 1000000 to 250000
   - Change line 45 of `mg6010_integrated_test_node.cpp` from 1000000 to 250000
   - Update comments to reflect MG6010-i6 standard

2. **Update Documentation**
   - Remove any claims about action interface (doesn't exist)
   - Document actual service interface with types and names
   - Add parameter reference table from this document

3. **Create Topic/Service Constants**
   - Add `topic_names.hpp` with string constants
   - Refactor code to use constants instead of literals

### Short-Term (Major)

4. **Namespace Cleanup**
   - Decide: `odrive_control_ros2` or `motor_control_ros2`
   - Rename header guards to match
   - Update all service type namespaces consistently

5. **MG6010 Service Interface**
   - Define MG6010-specific services or document mappings
   - Implement service wrappers for MG6010 protocol
   - Update SERVICES_NODES_GUIDE with MG6010 column

6. **Parameter Documentation**
   - Document valid ranges for all parameters
   - Add units to parameter descriptions
   - Implement parameter validation callbacks

### Long-Term (Minor)

7. **Safety Monitor Documentation**
   - Extract safety monitor interface
   - Document integration points
   - Add to traceability table

8. **Code Style Guide**
   - Standardize naming conventions
   - Document architectural patterns
   - Create developer guide

---

## 12. Traceability Matrix Template

For future documentation updates, use this template:

| Doc Claim | Code Location | Status | Notes |
|-----------|---------------|--------|-------|
| "Publishes to /joint_states" | odrive_service_node.cpp:105 | ✅ MATCH | QoS=10 |
| "Supports action interface" | `NOT FOUND` | ❌ MISMATCH | Remove from docs |
| "Default bitrate 250kbps" | mg6010_test_node.cpp:43 | ❌ MISMATCH | Code shows 1Mbps |

---

## Appendix A: File Locations

### Core Implementation Files
- `src/motor_control_ros2/include/motor_control_ros2/motor_abstraction.hpp`
- `src/motor_control_ros2/src/mg6010_test_node.cpp`
- `src/motor_control_ros2/src/mg6010_integrated_test_node.cpp`
- `src/motor_control_ros2/src/control_loop_node.cpp`
- `src/motor_control_ros2/src/safety_monitor.cpp`

### ODrive Legacy Files
- `src/motor_control_ros2/src/odrive_legacy/odrive_service_node.cpp`
- `src/motor_control_ros2/src/odrive_legacy/odrive_hardware_interface.cpp`
- `src/motor_control_ros2/src/odrive_legacy/odrive_control_app.cpp`

### Test Files
- `src/motor_control_ros2/test/odrive_testing_node.cpp`
- `src/motor_control_ros2/test/basic_service_test.cpp`
- `src/motor_control_ros2/test/simple_service_test_node.cpp`
- `src/motor_control_ros2/test/minimal_service_test.cpp`

---

**End of Traceability Table**
