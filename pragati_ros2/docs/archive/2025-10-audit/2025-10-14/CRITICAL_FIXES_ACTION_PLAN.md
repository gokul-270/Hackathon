# CRITICAL FIXES - IMMEDIATE ACTION PLAN

**Date:** 2025-10-09  
**Priority:** 🔴 CRITICAL - Motor communication will fail without these fixes  
**Total Time:** ~45 minutes

---

## OVERVIEW

These are **code-level bugs** that prevent MG6010-i6 motor from working. All fixes are small, targeted, and low-risk.

---

## FIX #1: MG6010 Controller Bitrate (CRITICAL)

**File:** `src/motor_control_ros2/src/mg6010_controller.cpp`  
**Line:** 90  
**Current Code:**
```cpp
if (!protocol_->initialize(can_interface_, config_.can_id, 1000000)) {
    // HARDCODED to 1Mbps!
```

**Problem:** Bitrate hardcoded to 1Mbps, but MG6010-i6 uses 250kbps

**Fix:**
```cpp
// BEFORE (Line 90):
if (!protocol_->initialize(can_interface_, config_.can_id, 1000000)) {

// AFTER:
// Get bitrate from config, default to 250kbps for MG6010-i6
uint32_t baud_rate = 250000;  // MG6010-i6 standard
if (config_.motor_params.count("baud_rate") > 0) {
    baud_rate = static_cast<uint32_t>(config_.motor_params["baud_rate"]);
}
if (!protocol_->initialize(can_interface_, config_.can_id, baud_rate)) {
```

**Test:**
```bash
cd /home/uday/Downloads/pragati_ros2
colcon build --packages-select motor_control_ros2
```

---

## FIX #2: MG6010 Test Node Bitrate Default (CRITICAL)

**File:** `src/motor_control_ros2/src/mg6010_test_node.cpp`  
**Line:** 43  
**Current Code:**
```cpp
this->declare_parameter<int>("baud_rate", 1000000);  // Default 1Mbps per official spec
```

**Problem:** Comment says "official spec" but MG6010-i6 spec is 250kbps

**Fix:**
```cpp
// BEFORE (Line 43):
this->declare_parameter<int>("baud_rate", 1000000);  // Default 1Mbps per official spec

// AFTER:
this->declare_parameter<int>("baud_rate", 250000);  // MG6010-i6 standard: 250kbps
```

---

## FIX #3: MG6010 Integrated Test Node Bitrate (CRITICAL)

**File:** `src/motor_control_ros2/src/mg6010_integrated_test_node.cpp`  
**Line:** 45  
**Current Code:**
```cpp
this->declare_parameter<int>("baud_rate", 1000000);
```

**Fix:**
```cpp
// BEFORE (Line 45):
this->declare_parameter<int>("baud_rate", 1000000);

// AFTER:
this->declare_parameter<int>("baud_rate", 250000);  // MG6010-i6 standard
```

---

## FIX #4: Add motor_on() Call to Initialization (CRITICAL)

**File:** `src/motor_control_ros2/src/mg6010_controller.cpp`  
**Line:** After line 97 (after protocol initialization succeeds)  

**Problem:** motor_on() function exists but never called - motor won't activate

**Fix:**

Insert this block AFTER line 97 (after `protocol_->initialize()` succeeds):

```cpp
// ✨ NEW CODE - Add after protocol->initialize() and before initialized_ = true:

// Get bitrate from config (from Fix #1 above)
uint32_t baud_rate = 250000;
if (config_.motor_params.count("baud_rate") > 0) {
    baud_rate = static_cast<uint32_t>(config_.motor_params["baud_rate"]);
}

if (!protocol_->initialize(can_interface_, config_.can_id, baud_rate)) {
    record_error(
        ErrorFramework::ErrorCategory::INITIALIZATION,
        ErrorFramework::ErrorSeverity::ERROR,
        1,
        "Failed to initialize MG6010 protocol");
    return false;
}

// ✨ NEW: Send Motor ON command (REQUIRED by MG6010 protocol)
std::cout << "Sending Motor ON command to motor " 
          << static_cast<int>(config_.can_id) << std::endl;

if (!protocol_->motor_on()) {
    record_error(
        ErrorFramework::ErrorCategory::INITIALIZATION,
        ErrorFramework::ErrorSeverity::ERROR,
        10,
        "Failed to turn motor ON: " + protocol_->get_last_error());
    return false;
}

// Small delay for motor to process command
std::this_thread::sleep_for(std::chrono::milliseconds(50));

// ✨ NEW: Read initial status to verify motor is ON
auto status = protocol_->read_motor_status();
if (!status.success) {
    std::cerr << "Warning: Could not read motor status after ON command" << std::endl;
} else if (status.error_state != 0) {
    std::cerr << "Warning: Motor error state: 0x" << std::hex 
              << static_cast<int>(status.error_state) << std::dec << std::endl;
    // Try to clear errors
    protocol_->clear_errors();
}

initialized_ = true;
calibrated_ = true;
enabled_ = true;  // ← Mark as enabled after successful motor_on

std::cout << "MG6010Controller initialized and motor enabled for joint: " 
          << config_.joint_name << std::endl;

return true;
```

---

## FIX #5: Create MG6010 Test Launch File (HIGH PRIORITY)

**File:** `src/motor_control_ros2/launch/mg6010_test.launch.py` (NEW FILE)

**Create this new file:**

```python
#!/usr/bin/env python3
"""
MG6010-i6 Motor Test Launch File
Simple launch for testing single MG6010 motor
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        # Arguments
        DeclareLaunchArgument(
            'can_interface',
            default_value='can0',
            description='CAN interface name'
        ),
        DeclareLaunchArgument(
            'baud_rate',
            default_value='250000',
            description='CAN baud rate (250kbps for MG6010-i6)'
        ),
        DeclareLaunchArgument(
            'motor_id',
            default_value='1',
            description='Motor CAN ID (1-32)'
        ),
        DeclareLaunchArgument(
            'test_mode',
            default_value='status',
            description='Test mode: status, position, velocity, torque'
        ),
        
        # MG6010 Test Node
        Node(
            package='motor_control_ros2',
            executable='mg6010_test_node',
            name='mg6010_test',
            output='screen',
            parameters=[{
                'interface_name': LaunchConfiguration('can_interface'),
                'baud_rate': LaunchConfiguration('baud_rate'),
                'node_id': LaunchConfiguration('motor_id'),
                'mode': LaunchConfiguration('test_mode'),
            }]
        ),
    ])
```

**Usage:**
```bash
ros2 launch motor_control_ros2 mg6010_test.launch.py
ros2 launch motor_control_ros2 mg6010_test.launch.py motor_id:=2
ros2 launch motor_control_ros2 mg6010_test.launch.py test_mode:=position
```

---

## FIX #6: Create MG6010 Test Configuration File (HIGH PRIORITY)

**File:** `src/motor_control_ros2/config/mg6010_test.yaml` (NEW FILE)

**Create this new file:**

```yaml
# MG6010-i6 Motor Test Configuration
# Motor: MG6010E-i6 (48V Integrated Servo)
# Protocol: LK-TECH CAN V2.35

mg6010_test_node:
  ros__parameters:
    # CAN Interface
    interface_name: "can0"
    baud_rate: 250000  # 250kbps (supported: 1M, 500k, 250k, 125k, 100k)
    
    # Motor Configuration
    node_id: 1  # Motor ID (1-32)
    can_id: 0x141  # 0x140 + node_id
    
    # Motor Specifications (MG6010E-i6)
    motor_type: "mg6010"
    rated_voltage: 24.0  # V
    rated_current: 5.5   # A
    rated_torque: 5.0    # N.m
    max_torque: 10.0     # N.m
    max_speed: 251.0     # RPM @ 24V
    
    # Control Parameters
    position_kp: 50.0
    position_ki: 0.0
    velocity_kp: 20.0
    velocity_ki: 0.1
    torque_kp: 1.0
    torque_ki: 0.01
    
    # Limits
    max_acceleration: 1000  # dps/s
    position_limit_min: -3.14159  # rad
    position_limit_max: 3.14159   # rad
    velocity_limit: 5.0  # rad/s
    current_limit: 33.0  # A (MG series max)
    
    # Communication
    response_timeout_ms: 10  # Protocol spec: ~0.25ms, use 10ms for safety
    max_retries: 3
    
    # Safety
    enable_safety_monitoring: true
    temperature_warning: 65.0   # °C
    temperature_critical: 70.0  # °C
    voltage_warning: 22.0       # V
    voltage_critical: 20.0      # V
```

**Usage:**
```bash
ros2 launch motor_control_ros2 mg6010_test.launch.py \
  --params-file src/motor_control_ros2/config/mg6010_test.yaml
```

---

## EXECUTION CHECKLIST

### Step 1: Backup Current Code (2 minutes)
```bash
cd /home/uday/Downloads/pragati_ros2
git status
git diff src/motor_control_ros2/
# If changes exist, commit or stash them first
```

### Step 2: Apply Code Fixes (15 minutes)

**Fix #1 - Controller Bitrate:**
```bash
# Edit file: src/motor_control_ros2/src/mg6010_controller.cpp
# Line 90: Replace hardcoded 1000000 with config-based approach
```

**Fix #2 - Test Node Bitrate:**
```bash
# Edit file: src/motor_control_ros2/src/mg6010_test_node.cpp
# Line 43: Change 1000000 to 250000
```

**Fix #3 - Integrated Test Node Bitrate:**
```bash
# Edit file: src/motor_control_ros2/src/mg6010_integrated_test_node.cpp
# Line 45: Change 1000000 to 250000
```

**Fix #4 - motor_on() Call:**
```bash
# Edit file: src/motor_control_ros2/src/mg6010_controller.cpp
# After line 97: Insert motor_on() sequence
```

### Step 3: Create New Files (10 minutes)

**Fix #5 - Launch File:**
```bash
# Create: src/motor_control_ros2/launch/mg6010_test.launch.py
# Paste content from Fix #5 above
chmod +x src/motor_control_ros2/launch/mg6010_test.launch.py
```

**Fix #6 - Config File:**
```bash
# Create: src/motor_control_ros2/config/mg6010_test.yaml
# Paste content from Fix #6 above
```

### Step 4: Rebuild (5 minutes)
```bash
cd /home/uday/Downloads/pragati_ros2
colcon build --packages-select motor_control_ros2
source install/setup.bash
```

### Step 5: Test CAN Setup (5 minutes)
```bash
# Setup CAN interface at correct bitrate
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 250000
sudo ip link set can0 up

# Verify
ip link show can0
```

### Step 6: Test Motor Communication (5 minutes)
```bash
# Monitor CAN bus
candump can0 &

# Run test node
ros2 run motor_control_ros2 mg6010_test_node --ros-args \
  -p interface_name:=can0 \
  -p baud_rate:=250000 \
  -p node_id:=1 \
  -p mode:=status

# Or use launch file
ros2 launch motor_control_ros2 mg6010_test.launch.py
```

**Expected Output:**
```
Sending Motor ON command to motor 321
MG6010Controller initialized and motor enabled for joint: joint_x
```

### Step 7: Verify (3 minutes)
```bash
# Check for errors in logs
ros2 topic list
ros2 topic echo /joint_states

# Manual CAN test
cansend can0 141#8800000000000000  # Motor ON command
# Expect response within 10ms
```

---

## SUCCESS CRITERIA

✅ **Code compiles without errors**  
✅ **Motor ON command sent successfully**  
✅ **Motor responds to status queries**  
✅ **No timeout errors in logs**  
✅ **CAN communication at 250kbps verified**

---

## ROLLBACK (If Needed)

If issues occur:
```bash
cd /home/uday/Downloads/pragati_ros2
git diff src/motor_control_ros2/ > /tmp/motor_fixes.patch
git checkout src/motor_control_ros2/
# Then debug and reapply carefully
```

---

## VERIFICATION COMMANDS

After all fixes applied:

```bash
# 1. Verify bitrate in code
grep -n "1000000\|250000" src/motor_control_ros2/src/mg6010*.cpp

# 2. Verify motor_on call exists
grep -n "motor_on()" src/motor_control_ros2/src/mg6010_controller.cpp

# 3. Verify launch file exists
ls -la src/motor_control_ros2/launch/mg6010_test.launch.py

# 4. Verify config file exists
ls -la src/motor_control_ros2/config/mg6010_test.yaml

# 5. Build test
colcon build --packages-select motor_control_ros2 2>&1 | tee /tmp/build.log
```

---

## NEXT STEPS AFTER CRITICAL FIXES

Once these 6 critical fixes are applied and tested:

1. ✅ Motor communication working
2. → Update documentation (README.md, etc.) - 2.5 hours
3. → Delete deprecated files - 10 minutes
4. → Consolidate status documents - 2 hours

---

**QUESTIONS?** See full audit report: `doc_audit/COMPREHENSIVE_AUDIT_REPORT.md`
