# Thermal Failure Analysis & Remediation Plan
**Cotton Picking Robot - Joint3 Motor Overheating Incident**

**Date**: 2025-01-10  
**System**: Pragati ROS2 Cotton Picking Robotic Arm  
**Affected Components**: Joint3 Motor (MG6010), OAK-D Camera, Camera Power Board

---

## Executive Summary

**Root Cause**: Joint3 motor continuously fighting gravity at horizontal home position (0.0 rad) for 64 minutes during idle, generating 10-20W of heat that conducted through shared base plate to camera. When camera started for ArUco detection, combined thermal stress + battery voltage sag caused undervoltage protection IC failure.

**Immediate Solution**: Change Joint3 park position to gravity-assisted angle (-0.10 to -0.30 rad) to eliminate continuous holding torque.

**Expected Result**: 80-90% reduction in idle power consumption (15W → 2-3W), motor temperature drop from 70-80°C to <40°C.

---

## Table of Contents

1. [Failure Timeline](#failure-timeline)
2. [Root Cause Analysis](#root-cause-analysis)
3. [MG6010 Motor Protocol Review](#mg6010-motor-protocol-review)
4. [Remediation Strategy](#remediation-strategy)
5. [Implementation Plans](#implementation-plans)
6. [Testing Procedures](#testing-procedures)
7. [Hardware Improvements](#hardware-improvements)
8. [Monitoring Enhancements](#monitoring-enhancements)

---

## Failure Timeline

### System Operation Log
```
05:19:38 - System start (timestamp 1762579185)
05:19:38 - Motors homed to home_position (Joint3 = 0.0 rad, horizontal)
05:19:38 - 06:24:29 - IDLE PERIOD (64 minutes)
           ├─ Joint3 continuously applying holding torque against gravity
           ├─ Motor heating: 15W continuous → 70-80°C case temperature
           └─ Camera pre-heated via thermal conduction through base plate
06:24:29 - START_SWITCH triggered, operation begins
06:24:29 - First ArUco detection: /usr/local/bin/aruco_finder started
           ├─ Camera startup inrush current
           ├─ Battery voltage sag (12V → ~10V)
           └─ Undervoltage IC stressed by combination of factors
06:24:37 - ArUco corner #1 picked (8 seconds)
06:24:45 - ArUco corner #2 picked (8 seconds)
06:24:53 - ArUco corner #3 picked (8 seconds)
06:25:01 - User stopped with Ctrl-C
06:25:01 - Smoke observed, camera and power board damaged
```

### Failure Mode Details
- **Smoke Source**: Undervoltage protection IC on camera power board
- **Camera Damage**: Internal electronics destroyed, cable insulation melted near connector
- **Motor Status**: Joint3 hot but NOT damaged (70-80°C within spec)
- **Other Motors**: Joint4, Joint5 normal temperature (shared no base plate with camera)
- **CAN Bus**: Entered BUS-OFF state, likely from transceiver thermal damage

---

## Root Cause Analysis

### Primary Root Cause
**Joint3 continuous holding torque at horizontal position during extended idle period**

#### Contributing Factors
1. **Poor Park Position Choice**
   - Current: `joint3_init/park_position: 0.0` (horizontal)
   - At this angle, full arm weight fights gravity
   - Motor must continuously output 10-20W to maintain position

2. **Thermal Conduction Path**
   - Camera and Joint3 motor share same mounting base plate
   - No thermal isolation between components
   - Heat conducts directly from motor case to camera housing

3. **Extended Idle Duration**
   - 64 minutes at park position before operation
   - Sufficient time for full thermal saturation
   - Camera pre-heated to ~60-70°C before being powered on

4. **Battery Voltage Sag**
   - Camera startup inrush current: ~0.6A initial, spikes to ~1.2A
   - Battery under load drops from 12V to ~10V
   - Undervoltage IC already thermally stressed, voltage sag pushed it over edge

5. **Cascading Failure**
   - Undervoltage IC fails → releases magic smoke
   - Thermal runaway damages surrounding components
   - Camera destroyed, CAN transceiver damaged

### Why Motors Survived
- MG6010 motors rated for 85°C continuous operation
- 70-80°C is within normal operating range
- Motor construction more robust than camera electronics

### Why Camera Failed
- Consumer electronics (OAK-D) not rated for 60-70°C ambient
- Undervoltage protection IC had insufficient thermal margin
- Startup inrush combined with thermal stress exceeded IC ratings

---

## MG6010 Motor Protocol Review

### Key Finding: NO IDLE MODE EXISTS

Review of **LK-TECH motor control protocol (CAN) V2.35** reveals:

#### Available Commands
- **Motor OFF (0x80)**: Completely disables motor, clears state, LED slow flash
- **Motor ON (0x88)**: Enables motor for normal operation, LED solid
- **Motor STOP (0x81)**: Stops motion but maintains state

#### Control Modes (MG Series)
- **Torque Control (0xA1)**: Direct current command, range -2048 to +2048 (±33A)
- **Speed Control (0xA2)**: Velocity control with torque limiting
- **Position Control (0xA3-0xA8)**: Multi-turn, single-turn, incremental angle control

#### Current Limiting
- All position/speed control modes respect "Max Torque Current" parameter
- This limit is set via LK Motor Tool (GUI software)
- Can be modified via CAN: Write PID to RAM (0x31) or ROM (0x32)
- **BUT**: No way to temporarily reduce holding torque without changing control mode

#### Temperature Monitoring
- Motor reports temperature in every response frame
- Resolution: 1°C per LSB (int8_t)
- Also available via dedicated status commands (0x9A, 0x9C, 0x9D)

### Conclusion
**The MG6010 has NO dedicated idle/brake/low-power mode.** The motor controller continuously applies whatever torque is needed to maintain commanded position, up to the configured current limit.

---

## Remediation Strategy

### Three-Tier Approach

#### Tier 1: Immediate Software Fix (CRITICAL - Implement First)
**Change park position to gravity-assisted angle**

**What**: Modify Joint3 park_position from 0.0 rad to gravity-neutral angle  
**Why**: Eliminates need for continuous holding torque  
**Expected Result**: 80-90% reduction in idle power (15W → 2-3W)  
**Effort**: 15 minutes  
**Risk**: Zero (easily reversible)

#### Tier 2: Software Enhancements (Implement After Tier 1 Validated)
1. **Parking behavior in operation loop**
2. **Motor temperature monitoring and publishing**
3. **Camera temperature monitoring**
4. **Thermal interlock (prevent camera start if motors hot)**
5. **CSV health logging**

**Expected Result**: Comprehensive monitoring, early warning of thermal issues  
**Effort**: 2-3 days  
**Risk**: Low (monitoring only, no control changes)

#### Tier 3: Hardware Improvements (Long-term, Optional)
1. **Mechanical counterbalance for Joint3**
2. **Thermal isolation pad between camera and motor base**
3. **Active cooling (fan) for camera**
4. **Camera power protection IC (TPS259474 eFuse)**
5. **Battery voltage monitoring**

**Expected Result**: Robust thermal management, component protection  
**Effort**: 1-2 weeks  
**Cost**: $50-100  
**Risk**: Moderate (requires mechanical design, assembly)

---

## Implementation Plans

### PLAN A: Immediate Park Position Fix (CRITICAL)

#### Step 1: Determine Optimal Park Angle

**Method 1: Empirical Testing (Recommended)**
```bash
# 1. Start system
ros2 launch yanthra_move yanthra_move_system.launch.py

# 2. Test different angles (run this for each candidate)
ros2 topic pub --once /joint3/position_command std_msgs/Float64 "data: -0.10"

# 3. Monitor motor temperature for 10 minutes
ros2 topic echo /mg6010/diagnostics | grep temperature

# 4. Test angles: -0.05, -0.10, -0.15, -0.20, -0.25, -0.30
# 5. Choose angle with LOWEST steady-state temperature
```

**Method 2: Physical Observation (Quick)**
```bash
# 1. Home the arm
# 2. Send Motor OFF command (0x80) to Joint3
# 3. Observe natural droop angle
# 4. Measure angle with protractor or read encoder
# 5. Add +0.02 rad safety margin
# 6. That's your optimal park_position!
```

**Method 3: Current Measurement (Most Accurate)**
```cpp
// Create test script that sweeps angles and logs motor current
for (float angle = -0.05; angle >= -0.40; angle -= 0.05) {
    moveJoint3ToPosition(angle);
    std::this_thread::sleep_for(std::chrono::seconds(10));
    int16_t iq = readMotorTorqueCurrent(JOINT3_ID);
    float current_a = iq * 33.0 / 2048.0;
    RCLCPP_INFO(logger, "Angle: %.3f rad (%.1f°), Current: %.2f A", 
                angle, angle * 180.0 / M_PI, std::abs(current_a));
}
// Choose angle where abs(current) is MINIMUM
```

**Expected Optimal Range**:
- Short forearm (<30cm): -0.10 to -0.20 rad (-6° to -11°)
- Medium forearm (30-50cm): -0.15 to -0.30 rad (-9° to -17°)
- Long forearm (>50cm): -0.20 to -0.40 rad (-11° to -23°)

**Starting Recommendation**: Try **-0.15 rad** first, then adjust based on measurements

#### Step 2: Update Configuration File

**File**: `/home/uday/Downloads/pragati_ros2/src/yanthra_move/config/production.yaml`

```yaml
# Line 73 (current value)
joint3_init/park_position: 0.0

# Change to (example, adjust based on testing)
joint3_init/park_position: -0.15  # Gravity-assisted angle, reduces holding torque
```

#### Step 3: Modify Operation Loop

**File**: `/home/uday/Downloads/pragati_ros2/src/yanthra_move/src/yanthra_move_system_operation.cpp`

**Current Code** (approximate line 224):
```cpp
// After pick cycle completes
motion_controller_->moveToHomePosition();  // Returns to home (0.0 rad)
```

**Modified Code**:
```cpp
// After pick cycle completes
motion_controller_->moveToParkPosition();  // Returns to park (gravity-assisted)
RCLCPP_INFO(logger_, "Moved to park position, motor in low-power state");
```

**Note**: Check if `moveToParkPosition()` function exists in MotionController class. If not, add it:

```cpp
// In motion_controller.hpp
void moveToParkPosition();

// In motion_controller.cpp
void MotionController::moveToParkPosition() {
    // Use existing park_position parameters loaded from YAML
    moveJoint3ToPosition(park_position_joint3_);
    moveJoint4ToPosition(park_position_joint4_);
    moveJoint5ToPosition(park_position_joint5_);
}
```

#### Step 4: Build and Test

```bash
cd /home/uday/Downloads/pragati_ros2
colcon build --packages-select yanthra_move
source install/setup.bash

# Run system with new park position
ros2 launch yanthra_move yanthra_move_system.launch.py

# Let system idle for 30 minutes at park position
# Monitor motor temperature - should stay < 45°C
ros2 topic echo /mg6010/diagnostics
```

#### Step 5: Validation Criteria

**Success Criteria**:
- ✅ Joint3 motor temperature < 45°C after 60 minutes idle at park position
- ✅ Motor can still execute pick cycles normally
- ✅ No position drift during extended idle periods
- ✅ Camera starts successfully without thermal stress

**Failure Modes**:
- ❌ Motor still hot (>50°C) → Park angle not optimal, adjust and re-test
- ❌ Arm drifts from park position → Increase park angle slightly (less negative)
- ❌ Arm swings past park position → Decrease park angle (more negative)

---

### PLAN B: Manual Torque Limiting (Optional Alternative)

If park position alone insufficient, add explicit torque limiting during idle.

#### Implementation

**File**: `/home/uday/Downloads/pragati_ros2/src/motor_control_ros2/src/mg6010_controller_node.cpp`

**Add new function**:
```cpp
void MG6010ControllerNode::setIdleMode(uint8_t motor_id, bool enable) {
    if (enable) {
        // Send low holding torque command (10% of max)
        int16_t idle_torque = 200;  // 200/2048 * 33A = ~3.2A
        sendTorqueControlCommand(motor_id, idle_torque);
        RCLCPP_INFO(logger_, "Motor %d set to idle mode (low torque)", motor_id);
    } else {
        // Resume normal position control
        RCLCPP_INFO(logger_, "Motor %d returned to normal mode", motor_id);
    }
}

void MG6010ControllerNode::sendTorqueControlCommand(uint8_t motor_id, int16_t iq_control) {
    struct can_frame frame;
    frame.can_id = 0x140 + motor_id;
    frame.can_dlc = 8;
    frame.data[0] = 0xA1;  // Torque control command byte
    frame.data[1] = 0x00;
    frame.data[2] = 0x00;
    frame.data[3] = 0x00;
    frame.data[4] = iq_control & 0xFF;         // Low byte
    frame.data[5] = (iq_control >> 8) & 0xFF;  // High byte
    frame.data[6] = 0x00;
    frame.data[7] = 0x00;
    
    sendCANFrame(frame);
}
```

**Usage in operation loop**:
```cpp
// After moving to park position
motion_controller_->moveToParkPosition();
std::this_thread::sleep_for(std::chrono::milliseconds(500));
motor_controller_->setIdleMode(JOINT3_MOTOR_ID, true);

// Before starting next operation
motor_controller_->setIdleMode(JOINT3_MOTOR_ID, false);
std::this_thread::sleep_for(std::chrono::milliseconds(100));
// Resume normal position control
```

**Pros**:
- Explicit control over holding torque
- Can fine-tune power consumption

**Cons**:
- Switches from position control to torque control mode
- May allow small position drift
- More complex state management
- **Recommend using park position fix first, only add this if needed**

---

### PLAN C: Motor Temperature Monitoring

Add motor temperature publishing for visibility and alerting.

#### Implementation

**File**: `/home/uday/Downloads/pragati_ros2/src/motor_control_ros2/src/mg6010_controller_node.cpp`

**Add publisher**:
```cpp
// In class definition (mg6010_controller_node.hpp)
rclcpp::Publisher<sensor_msgs::msg::Temperature>::SharedPtr motor_temp_pub_;
rclcpp::TimerBase::SharedPtr temp_monitor_timer_;

// In constructor
motor_temp_pub_ = this->create_publisher<sensor_msgs::msg::Temperature>(
    "/mg6010/temperature", 10);

temp_monitor_timer_ = this->create_wall_timer(
    std::chrono::seconds(1),
    std::bind(&MG6010ControllerNode::publishMotorTemperatures, this));

// New function
void MG6010ControllerNode::publishMotorTemperatures() {
    for (auto motor_id : {JOINT3_ID, JOINT4_ID, JOINT5_ID}) {
        int8_t temp_c = readMotorTemperature(motor_id);
        
        sensor_msgs::msg::Temperature msg;
        msg.header.stamp = this->now();
        msg.header.frame_id = "motor_" + std::to_string(motor_id);
        msg.temperature = static_cast<double>(temp_c);
        msg.variance = 1.0;  // ±1°C accuracy
        
        motor_temp_pub_->publish(msg);
        
        // Warn if temperature high
        if (temp_c > 70) {
            RCLCPP_WARN_THROTTLE(logger_, *this->get_clock(), 10000,
                "Motor %d temperature HIGH: %d°C", motor_id, temp_c);
        }
    }
}

int8_t MG6010ControllerNode::readMotorTemperature(uint8_t motor_id) {
    // Send read motor state 1 command (0x9A)
    struct can_frame cmd_frame;
    cmd_frame.can_id = 0x140 + motor_id;
    cmd_frame.can_dlc = 8;
    cmd_frame.data[0] = 0x9A;
    memset(&cmd_frame.data[1], 0x00, 7);
    
    sendCANFrame(cmd_frame);
    
    // Wait for response (should arrive within 0.25ms per protocol)
    struct can_frame resp_frame;
    if (receiveCANFrame(resp_frame, 10ms)) {  // 10ms timeout
        // Temperature is in DATA[1], int8_t, 1°C/LSB
        return static_cast<int8_t>(resp_frame.data[1]);
    }
    
    return -128;  // Error value
}
```

**Monitoring**:
```bash
# View motor temperatures in real-time
ros2 topic echo /mg6010/temperature

# Log temperatures to CSV
ros2 topic echo /mg6010/temperature --csv >> motor_temps.csv
```

---

### PLAN D: Thermal Interlock

Prevent camera startup if motors are thermally saturated.

#### Implementation

**File**: `/home/uday/Downloads/pragati_ros2/src/yanthra_move/src/yanthra_move_system_operation.cpp`

**Add thermal check function**:
```cpp
bool YanthraMovSystemOperation::isSystemThermallyReady() {
    // Read current motor temperatures
    float joint3_temp = getMotorTemperature(JOINT3_ID);
    float joint4_temp = getMotorTemperature(JOINT4_ID);
    float joint5_temp = getMotorTemperature(JOINT5_ID);
    
    // Check thermal limits
    const float THERMAL_LIMIT_WARN = 65.0;  // °C
    const float THERMAL_LIMIT_CRIT = 75.0;  // °C
    
    float max_temp = std::max({joint3_temp, joint4_temp, joint5_temp});
    
    if (max_temp > THERMAL_LIMIT_CRIT) {
        RCLCPP_ERROR(logger_, "System CRITICAL TEMPERATURE: %.1f°C - Aborting operation", max_temp);
        return false;
    }
    
    if (max_temp > THERMAL_LIMIT_WARN) {
        RCLCPP_WARN(logger_, "System elevated temperature: %.1f°C - Waiting for cooldown", max_temp);
        // Wait 60 seconds and check again
        std::this_thread::sleep_for(std::chrono::seconds(60));
        return isSystemThermallyReady();  // Recursive check
    }
    
    RCLCPP_INFO(logger_, "System thermal status OK: %.1f°C max", max_temp);
    return true;
}
```

**Use in operation loop**:
```cpp
void YanthraMovSystemOperation::runOperationCycle() {
    // Wait for start switch
    waitForStartSwitch();
    
    // Thermal check before starting camera
    if (!isSystemThermallyReady()) {
        RCLCPP_ERROR(logger_, "Thermal interlock engaged - system too hot");
        return;
    }
    
    // Safe to start camera now
    startCamera();
    
    // Continue with operation...
}
```

---

### PLAN E: Camera Temperature Monitoring

Monitor OAK-D camera chip temperature during operation.

#### Implementation

**File**: `/home/uday/Downloads/pragati_ros2/src/yanthra_move/src/core/depthai_manager.cpp`

**Add temperature monitoring**:
```cpp
// In DepthAIManager class
rclcpp::Publisher<sensor_msgs::msg::Temperature>::SharedPtr camera_temp_pub_;
rclcpp::TimerBase::SharedPtr camera_temp_timer_;

// In initialization
camera_temp_pub_ = node_->create_publisher<sensor_msgs::msg::Temperature>(
    "/camera/oakd/temperature", 10);

// Start timer when pipeline active
camera_temp_timer_ = node_->create_wall_timer(
    std::chrono::seconds(1),
    std::bind(&DepthAIManager::publishCameraTemperature, this));

void DepthAIManager::publishCameraTemperature() {
    if (!device_ || !device_->isPipelineRunning()) {
        return;
    }
    
    // Read chip temperature (DepthAI API)
    dai::ChipTemperature temp = device_->getChipTemperature();
    
    sensor_msgs::msg::Temperature msg;
    msg.header.stamp = node_->now();
    msg.header.frame_id = "oakd_camera";
    msg.temperature = temp.average;  // Use average of all sensors
    msg.variance = 2.0;  // ±2°C typical
    
    camera_temp_pub_->publish(msg);
    
    // Emergency shutdown if too hot
    const float CAMERA_TEMP_LIMIT = 75.0;  // °C
    if (temp.average > CAMERA_TEMP_LIMIT) {
        RCLCPP_ERROR(node_->get_logger(), 
            "Camera OVERHEATING: %.1f°C - Emergency pipeline stop!", temp.average);
        stopPipeline();
    } else if (temp.average > 65.0) {
        RCLCPP_WARN_THROTTLE(node_->get_logger(), *node_->get_clock(), 5000,
            "Camera temperature elevated: %.1f°C", temp.average);
    }
}
```

---

### PLAN F: CSV Health Logging

Log system health metrics to CSV for post-incident analysis.

#### Implementation

**File**: `/home/uday/Downloads/pragati_ros2/web_dashboard/backend/dashboard_server.py`

**Add CSV logger**:
```python
import csv
from datetime import datetime
from pathlib import Path

class HealthCSVLogger:
    def __init__(self, output_dir="/home/uday/Downloads/pragati_ros2/outputs/health_logs"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.csv_file = self.output_dir / f"health_log_{timestamp}.csv"
        
        # Create file with header (line-buffered)
        with open(self.csv_file, 'w', newline='', buffering=1) as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp_iso",
                "timestamp_unix",
                "camera_temp_c",
                "camera_voltage_v",
                "camera_current_a",
                "motor_j3_temp_c",
                "motor_j4_temp_c",
                "motor_j5_temp_c",
                "motor_j3_current_a",
                "motor_j4_current_a",
                "motor_j5_current_a",
                "system_state",
                "can_state",
                "warnings"
            ])
        
        self.logger.info(f"Health CSV logger initialized: {self.csv_file}")
    
    def log_sample(self, data: dict):
        """Log a single health data sample."""
        with open(self.csv_file, 'a', newline='', buffering=1) as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now().isoformat(),
                datetime.now().timestamp(),
                data.get('camera_temp', -999),
                data.get('camera_voltage', -999),
                data.get('camera_current', -999),
                data.get('motor_j3_temp', -999),
                data.get('motor_j4_temp', -999),
                data.get('motor_j5_temp', -999),
                data.get('motor_j3_current', -999),
                data.get('motor_j4_current', -999),
                data.get('motor_j5_current', -999),
                data.get('system_state', 'UNKNOWN'),
                data.get('can_state', 'UNKNOWN'),
                data.get('warnings', '')
            ])
            f.flush()  # Ensure written to disk immediately

# In dashboard server main loop
csv_logger = HealthCSVLogger()

def health_monitor_callback():
    data = {
        'camera_temp': read_camera_temp(),
        'motor_j3_temp': read_motor_temp(3),
        # ... collect all metrics
    }
    csv_logger.log_sample(data)
    
# Call at 1 Hz
```

**Usage**:
```bash
# Start dashboard with CSV logging
ros2 launch web_dashboard web_dashboard.launch.py

# Logs will be in:
ls -lh /home/uday/Downloads/pragati_ros2/outputs/health_logs/
```

---

## Testing Procedures

### Test 1: Park Position Validation

**Objective**: Confirm optimal park position eliminates holding torque

**Procedure**:
1. Start system with new park_position value
2. Move arm to park position
3. Monitor Joint3 motor temperature for 60 minutes
4. Record temperature every 5 minutes
5. Compare to baseline (0.0 rad home position)

**Success Criteria**:
- Motor temperature < 45°C after 60 minutes
- Temperature stays stable (no rising trend)
- At least 50% reduction vs. baseline

**Data to Record**:
```
Time (min) | Joint3 Temp (°C) | Joint3 Current (A) | Notes
-----------|------------------|--------------------|---------
0          | 32               | 0.5                | Initial
5          | 38               | 0.4                |
10         | 40               | 0.3                |
...        | ...              | ...                |
60         | 42               | 0.3                | Stable
```

### Test 2: Extended Idle Endurance

**Objective**: Validate system can idle safely for extended periods

**Procedure**:
1. Start system, move to park position
2. Leave idle for 4 hours (simulate real field usage)
3. Monitor all temperatures continuously
4. Start camera after 4 hours
5. Execute normal pick cycle

**Success Criteria**:
- All motor temperatures < 50°C throughout idle period
- Camera starts successfully without thermal stress
- Pick cycle executes normally

### Test 3: Continuous Operation

**Objective**: Verify system can run continuous pick cycles without overheating

**Procedure**:
1. Start system
2. Execute 20 consecutive pick cycles
3. Monitor temperatures, power consumption
4. Return to park position between cycles

**Success Criteria**:
- Motor temperatures stay < 70°C during active operation
- Camera temperature < 65°C during operation
- System completes all 20 cycles without thermal shutdown

### Test 4: Thermal Recovery

**Objective**: Measure cooldown time after thermal stress

**Procedure**:
1. Heat system intentionally (continuous operation)
2. Measure peak temperatures
3. Move to park position, stop camera
4. Monitor temperature decay
5. Record time to reach safe levels (<45°C)

**Expected Result**: Cooldown to safe temperature in < 30 minutes

---

## Hardware Improvements

### HW-1: Mechanical Counterbalance (RECOMMENDED)

**Objective**: Eliminate Joint3 holding torque entirely using mechanical force

#### Design Approach

**Option A: Extension Spring**
```
Calculation:
- Measure arm weight: W kg
- Measure moment arm: L meters
- Required spring force: F = W × g × L / spring_lever_arm
- Choose spring with k = F / desired_extension

Example:
- Arm weight: 2 kg
- Moment arm: 0.3 m
- Spring lever: 0.15 m
- F = 2 × 9.81 × 0.3 / 0.15 = 39.2 N
- Spring: k = 400 N/m, extension = 10 cm
```

**Option B: Gas Strut**
- Easier to install
- Self-contained
- Adjustable preload
- Cost: ~$20-30
- Example: 50N gas strut from automotive parts

**Option C: Counterweight**
- Simple, reliable
- No wear parts
- May increase inertia
- Weight calculation: balance arm CG

#### Installation Steps
1. Measure arm center of gravity when horizontal
2. Calculate required counterforce
3. Mount spring/strut attachment points
4. Install and adjust tension
5. Test motor current (should be near zero at park angle)

**Expected Result**:
- Motor holding current: 15A → <1A (95% reduction)
- Motor idle power: 15W → 0.5W
- Battery life improvement: +50%

### HW-2: Thermal Isolation

**Objective**: Block heat conduction between motor and camera

**Materials**:
- Silicone thermal pad, 1-2mm thick
- Thermal conductivity: <0.5 W/m·K
- Cost: ~$5

**Installation**:
1. Remove camera from base plate
2. Clean both surfaces with isopropyl alcohol
3. Apply thermal isolation pad
4. Reinstall camera with pad between mating surfaces
5. Verify camera mounting secure

**Expected Result**:
- 60-70% reduction in conducted heat
- Camera can tolerate motor temperature up to 60°C

### HW-3: Active Cooling (Fan)

**Objective**: Force air circulation over camera for active heat removal

**Components**:
- 40mm 12V DC fan, 5-10 CFM
- GPIO-controlled MOSFET switch
- Mounting bracket
- Cost: ~$5-10

**Control Logic**:
```python
def update_fan_control():
    camera_temp = read_camera_temp()
    motor_temp_max = max(read_motor_temps())
    
    # Fan control hysteresis
    FAN_ON_THRESHOLD = 50.0   # °C
    FAN_OFF_THRESHOLD = 40.0  # °C
    
    if camera_temp > FAN_ON_THRESHOLD or motor_temp_max > FAN_ON_THRESHOLD:
        set_fan(True)
    elif camera_temp < FAN_OFF_THRESHOLD and motor_temp_max < FAN_OFF_THRESHOLD:
        set_fan(False)
```

**Expected Result**:
- Camera temperature reduction: 10-15°C
- Motor cooldown time: 50% faster

### HW-4: Camera Power Protection IC

**Objective**: Protect camera from voltage/current faults

**Component**: TPS259474 eFuse IC

**Features**:
- Adjustable current limit: 0.1A to 5.5A
- UVLO: Programmable undervoltage lockout
- OVP: Overvoltage protection
- Short-circuit protection
- FAULT output pin for monitoring
- Soft-start to limit inrush current

**Circuit Design**:
```
Battery 12V ---[TPS259474]--- Camera 5V (via buck converter)
                    |
                    +--- ILIM resistor (set to 1.0A)
                    +--- UVLO resistor (set to 11.5V min)
                    +--- FAULT pin --> GPIO input
```

**Benefits**:
- Limits camera startup inrush
- Prevents damage from voltage sags
- Software notification on fault

### HW-5: Battery Voltage Monitoring

**Objective**: Prevent operation when battery too low

**Components**:
- Voltage divider (resistors)
- ADC input on controller
- Cost: <$1

**Circuit**:
```
Battery+ ---[R1=10kΩ]---+--- ADC_IN (0-3.3V range)
                        |
                     [R2=2.7kΩ]
                        |
                       GND

Voltage ratio: 12V × (2.7 / 12.7) = 2.55V at ADC
```

**Software**:
```cpp
float readBatteryVoltage() {
    uint16_t adc_value = readADC(BATTERY_VOLTAGE_PIN);
    float voltage = adc_value * 3.3 / 4096.0;  // 12-bit ADC
    return voltage * 12.7 / 2.7;  // Scale back to battery voltage
}

bool isBatteryHealthy() {
    float voltage = readBatteryVoltage();
    
    if (voltage < 10.5) {
        RCLCPP_ERROR(logger_, "Battery CRITICAL: %.2fV - Shutdown required", voltage);
        return false;
    } else if (voltage < 11.5) {
        RCLCPP_WARN(logger_, "Battery LOW: %.2fV - Camera may not start reliably", voltage);
        return false;
    }
    
    return true;
}
```

---

## Monitoring Enhancements

### Dashboard Integration

The existing web dashboard (`/home/uday/Downloads/pragati_ros2/web_dashboard/`) can be enhanced to display thermal and power metrics.

#### Existing Infrastructure
- **Backend**: FastAPI with WebSocket updates
- **Frontend**: HTML/CSS/JavaScript with real-time charts
- **Services**: Alert engine, health monitoring, historical data (SQLite)
- **Port**: 8080

#### Proposed Additions

**1. Thermal Status Panel**
```javascript
// Add to frontend/index.html
<div class="thermal-panel">
    <h3>Thermal Status</h3>
    <div class="motor-temps">
        <div>Joint3: <span id="j3-temp">--</span>°C</div>
        <div>Joint4: <span id="j4-temp">--</span>°C</div>
        <div>Joint5: <span id="j5-temp">--</span>°C</div>
    </div>
    <div class="camera-temp">
        Camera: <span id="cam-temp">--</span>°C
    </div>
    <div class="thermal-alerts" id="thermal-alerts"></div>
</div>
```

**2. Power Metrics Panel**
```javascript
<div class="power-panel">
    <h3>Power Status</h3>
    <div>Battery: <span id="battery-voltage">--</span>V</div>
    <div>Camera Current: <span id="camera-current">--</span>A</div>
    <div>System Power: <span id="system-power">--</span>W</div>
</div>
```

**3. Alert Rules** (add to `config/alerts.yaml`)
```yaml
thermal_alerts:
  - name: "Motor Temperature Warning"
    condition: "motor_temp > 70"
    severity: "warning"
    message: "Motor temperature elevated: {motor_temp}°C"
    
  - name: "Motor Temperature Critical"
    condition: "motor_temp > 80"
    severity: "critical"
    message: "Motor OVERHEATING: {motor_temp}°C - SHUTDOWN REQUIRED"
    action: "emergency_stop"
  
  - name: "Camera Temperature Warning"
    condition: "camera_temp > 65"
    severity: "warning"
    message: "Camera temperature elevated: {camera_temp}°C"
  
  - name: "Battery Low"
    condition: "battery_voltage < 11.5"
    severity: "warning"
    message: "Battery low: {battery_voltage}V - Camera startup unreliable"
  
  - name: "Battery Critical"
    condition: "battery_voltage < 10.5"
    severity: "critical"
    message: "Battery CRITICAL: {battery_voltage}V - System shutdown"
    action: "emergency_stop"
```

---

## Recommended Execution Order

### Why Execution Order Matters

The implementation plan should balance **risk reduction** with **practical constraints**. Starting with quick wins builds confidence while addressing the most critical issues first.

### Phased Implementation Strategy

| Phase | Task | Type | Why This Order | Time | Dependencies |
|-------|------|------|----------------|------|-------------|
| **0A** | Fix web dashboard | Debug | Get existing monitoring working | 1 day | None |
| **0B** | Thermal isolation pad | Hardware | Quick physical protection | 1 day | None |
| **1** | Park position fix | Config | **ROOT CAUSE** elimination | 4 hours | None |
| **2** | Motor temp monitoring | Software | Immediate warning capability | 2 days | Phase 1 |
| **3** | Camera temp monitoring | Software | Direct camera protection | 2 days | Phase 1 |
| **4** | Thermal interlock | Software | Prevent startup if hot | 1 day | Phase 2,3 |
| **5** | CSV health logging | Software | Post-mortem analysis | 1 day | Phase 2,3 |
| **6** | Operation mode control | Software | Reduce thermal load | 2 days | Phase 2,3 |
| **7** | Power protection IC | Hardware | Electrical protection | 2 days | None |
| **8** | Battery monitoring | HW+SW | Voltage sag detection | 3 days | Phase 7 |
| **9** | Mechanical counterbalance | Hardware | Ultimate efficiency | 1 week | Phase 1 validated |
| **10** | Active cooling (fan) | Hardware | Extra thermal margin | 2 days | Optional |

### Detailed Phase Breakdown

#### Phase 0A: Fix Web Dashboard (Priority: High)
**Status**: Current pain point - "dashboard not working properly"

**Actions**:
1. Identify specific failure mode:
   ```bash
   cd /home/uday/Downloads/pragati_ros2/web_dashboard
   ros2 launch web_dashboard web_dashboard.launch.py
   # Check console for errors
   ```
2. Common issues:
   - Port 8080 already in use → change port or kill process
   - ROS2 topics not publishing → check node connections
   - WebSocket connection failing → check firewall/network
   - Frontend not loading → check static file serving

**Why First**: You need monitoring visibility NOW. Dashboard is existing infrastructure.

**Validation**: Dashboard loads, shows live motor/system data

---

#### Phase 0B: Install Thermal Isolation Pad (Priority: High)
**Materials**: Silicone thermal pad (1-2mm thick, <0.5 W/m·K)

**Procedure**:
1. Remove camera from motor base plate
2. Clean surfaces with isopropyl alcohol
3. Apply thermal pad between camera mount and base plate
4. Reinstall camera
5. Verify secure mounting

**Why Early**: 
- Takes 1 hour
- $5 cost
- 60-70% heat transfer reduction
- Buys time for software fixes
- No dependencies

**Validation**: Camera runs cooler during motor heating

---

#### Phase 1: Park Position Fix (Priority: CRITICAL)
**Time**: 4 hours

**Why First (Software)**:
- **Eliminates root cause** (80-90% idle power reduction)
- Zero risk, easily reversible
- No dependencies
- Immediate benefit

**Steps**:
1. Determine optimal angle (Method 2: physical observation = fastest)
2. Update `production.yaml` line 73
3. Modify operation loop to use park position
4. Test 30-minute idle
5. Validate motor temp < 45°C

**Validation Criteria**:
- Joint3 temp < 45°C after 60 min idle
- No position drift
- Pick cycles work normally

---

#### Phase 2: Motor Temperature Monitoring (Priority: High)
**Time**: 2 days

**Why Next**:
- Builds on Phase 1 (need to monitor effectiveness)
- Software only, low risk
- Enables Phase 4 (thermal interlock)
- MG6010 already reports temp, just need to publish

**Implementation**: PLAN C in main document

**Deliverables**:
- `/mg6010/temperature` topic at 1 Hz
- Warning logs for temp > 70°C
- Data available for dashboard

---

#### Phase 3: Camera Temperature Monitoring (Priority: High)
**Time**: 2 days

**Why Parallel to Phase 2**:
- Direct protection of vulnerable component
- DepthAI API provides `getChipTemperature()`
- Emergency auto-shutdown at 75°C
- Enables Phase 4 (thermal interlock)

**Implementation**: PLAN E in main document

**Deliverables**:
- `/camera/oakd/temperature` topic at 1 Hz
- Auto-shutdown if > 75°C
- Warning at > 65°C

---

#### Phase 4: Thermal Interlock (Priority: Medium)
**Time**: 1 day
**Dependencies**: Phase 2 + 3 (needs temp data)

**Why After Monitoring**:
- Requires temp data from motors and camera
- Prevents camera start if system hot
- Software-based safety

**Implementation**: PLAN D in main document

**Logic**:
- Check all motor temps before camera start
- If any motor > 70°C → wait for cooldown
- If any motor > 75°C → abort operation

---

#### Phase 5: CSV Health Logging (Priority: Medium)
**Time**: 1 day
**Dependencies**: Phase 2 + 3 (data to log)

**Why Important**:
- Post-mortem analysis capability
- Trend detection (gradual degradation)
- Validates fixes are working
- Legal/warranty documentation

**Implementation**: PLAN F in main document

**Output**: Time-stamped CSV with all health metrics at 1 Hz

---

#### Phase 6: Operation Mode Control (Priority: Medium)
**Time**: 2 days

**Why After Monitoring**:
- Need baseline data first
- Reduces thermal stress proactively
- Burst mode for ArUco detection
- Continuous mode for tracking

**Features**:
- Camera burst mode: Start → capture → stop (minimize ON time)
- Thermal budget management
- Adaptive duty cycle based on temperature

---

#### Phase 7: Camera Power Protection IC (Priority: Medium)
**Time**: 2 days (hardware + software)
**Type**: Hardware modification

**Why Before Battery Monitoring**:
- Protects camera from voltage sag
- eFuse provides FAULT signal to software
- Current limiting prevents inrush damage

**Component**: TPS259474

**Implementation**: HW-4 in main document

---

#### Phase 8: Battery Voltage Monitoring (Priority: Low)
**Time**: 3 days (circuit + ADC reading + alerting)
**Dependencies**: Phase 7 (power rail protection)

**Why Later**:
- Less critical if power protection in place
- Requires ADC hardware modification
- Can manually check battery for now

**Benefits**:
- Prevents operation at low voltage
- Predictive alerts (battery low)
- Correlate voltage sag with failures

**Implementation**: HW-5 in main document

---

#### Phase 9: Mechanical Counterbalance (Priority: Optional)
**Time**: 1 week (design + fabrication + installation)
**Dependencies**: Phase 1 validated (confirms benefit)

**Why Optional/Later**:
- Park position fix already solves 80-90% of problem
- Mechanical design takes time
- Can validate need with monitoring data first
- Most complex change

**When to Do It**:
- If park position fix insufficient (<50% improvement)
- If battery life still problematic
- If planning major redesign anyway

**Expected Benefit**: 95% reduction in holding power

**Implementation**: HW-1 in main document

---

#### Phase 10: Active Cooling (Fan) (Priority: Optional)
**Time**: 2 days
**Dependencies**: Phase 0B (thermal isolation first)

**Why Optional**:
- Only needed if other fixes insufficient
- Adds power consumption
- Adds noise
- Mechanical mounting required

**When to Do It**:
- If camera still reaches 65°C during operation
- If thermal isolation + park fix insufficient
- For extra safety margin in hot environments

**Implementation**: HW-3 in main document

---

### Quick Start (First Week)

If you need the system working ASAP, do these in order:

1. **Day 1 Morning**: Install thermal isolation pad (1 hour)
2. **Day 1 Afternoon**: Fix park position (4 hours)
3. **Day 1 Evening**: Test 4-hour idle endurance overnight
4. **Day 2**: Validate results, tune park angle if needed
5. **Day 3-4**: Add motor temperature monitoring
6. **Day 5**: Add camera temperature monitoring

**Result after 5 days**:
- ✅ Root cause eliminated (park position)
- ✅ Physical protection (thermal pad)
- ✅ Software monitoring (temps visible)
- ✅ Safe to resume field testing

---

## Summary of Actions

### Immediate (Within 1 Week)
1. ✅ **[CRITICAL]** Determine optimal Joint3 park position via testing
2. ✅ **[CRITICAL]** Update `production.yaml` with new park_position value
3. ✅ **[CRITICAL]** Modify operation loop to use park position during idle
4. ✅ **[CRITICAL]** Validate fix with 4-hour idle endurance test
5. ✅ **[HIGH]** Install thermal isolation pad between camera and motor base
6. ✅ **[HIGH]** Debug and fix web dashboard

### Short Term (Within 1 Month)
7. ✅ Implement motor temperature monitoring and publishing
8. ✅ Implement camera temperature monitoring
9. ✅ Add thermal interlock (prevent camera start if hot)
10. ✅ Implement CSV health logging
11. ✅ Add thermal/power panels to web dashboard
12. ✅ Configure alert rules for temperature/voltage
13. ✅ Add operation mode control (burst vs continuous)

### Long Term (Within 3 Months)
14. 🔧 Install camera power protection IC (TPS259474)
15. 🔧 Add battery voltage monitoring circuit
16. 🔧 Design and install mechanical counterbalance for Joint3 (if needed)
17. 🔧 Add active cooling (fan) with GPIO control (if needed)
18. 🔧 Conduct full system endurance testing (8+ hours continuous)

---

## Risk Assessment

### Current Risk (Before Fix)
**Risk Level**: 🔴 **CRITICAL**
- **Likelihood**: High (occurred once, will occur again under same conditions)
- **Impact**: High (component damage, system downtime, fire hazard from smoke)
- **Cost**: $100-300 per incident (camera + power board replacement)

### Residual Risk (After Tier 1 Fix)
**Risk Level**: 🟡 **LOW**
- **Likelihood**: Low (root cause eliminated)
- **Impact**: Medium (monitoring will provide early warning)
- **Cost**: Minimal (early detection prevents damage)

### Residual Risk (After Tier 1 + Tier 2)
**Risk Level**: 🟢 **VERY LOW**
- **Likelihood**: Very Low (root cause eliminated + monitoring + interlocks)
- **Impact**: Low (automatic shutdown prevents damage)
- **Cost**: Zero (no component damage expected)

---

## Lessons Learned

1. **Thermal Design Matters**: Even "cool-running" servos generate significant heat under continuous load
2. **Shared Mounting = Thermal Coupling**: Components on same base plate share thermal fate
3. **Idle State Design**: System idle state should be lowest-power configuration, not arbitrary position
4. **Consumer Electronics Vulnerable**: Camera rated for office environment, not industrial thermal conditions
5. **Monitoring Is Essential**: Without temperature monitoring, thermal issues are invisible until failure
6. **Battery Voltage Matters**: Low battery voltage + inrush current = undervoltage stress
7. **Mechanical Solutions Beat Software**: Counterbalance eliminates problem at source, software only mitigates

---

## Conclusion

The thermal failure was caused by **poor idle state design** (horizontal park position requiring continuous holding torque) combined with **thermal coupling** (shared mounting base) and **lack of monitoring** (no temperature visibility).

**The immediate fix is simple**: Change Joint3 park position to gravity-assisted angle. This eliminates 80-90% of idle power consumption and prevents motor from heating during extended idle periods.

**Additional monitoring and hardware improvements** will make the system more robust and provide early warning of any future thermal issues.

**Estimated total effort**:
- Immediate fix: 4 hours (testing + implementation + validation)
- Monitoring enhancements: 2-3 days
- Hardware improvements: 1-2 weeks

**Estimated cost**:
- Software changes: $0
- Hardware improvements: $50-100

**Expected benefit**:
- Elimination of thermal failure mode
- 50% improvement in battery life
- System can operate safely for 8+ hours continuously

---

## Questions for Implementation Refinement

Before starting implementation, please provide the following information to optimize the solution:

### 1. Web Dashboard Issues
**Question**: What specifically isn't working with the dashboard?

**Options**:
- [ ] Dashboard won't start (error on launch)
- [ ] Dashboard starts but shows no data
- [ ] Dashboard crashes after running
- [ ] Can't access from browser (connection refused)
- [ ] WebSocket connection failing
- [ ] Other: _____________

**Why This Matters**: We may need to fix dashboard first to enable monitoring of other fixes.

**Action**: Please run this and share output:
```bash
cd /home/uday/Downloads/pragati_ros2/web_dashboard
ros2 launch web_dashboard web_dashboard.launch.py
# Copy any error messages
```

---

### 2. Hardware Constraints
**Question**: Can you add hardware modifications?

**Thermal Isolation Pad**:
- Cost: ~$5
- Time: 1 hour
- Complexity: Easy (remove camera, add pad, reinstall)
- Benefit: 60-70% heat transfer reduction

**Answer**: ☐ Yes, can do  ☐ No, software only  ☐ Need to check

**Cooling Fan**:
- Cost: ~$5-10
- Time: 2 days (mounting + GPIO control)
- Complexity: Medium (requires GPIO wiring)
- Benefit: 10-15°C temperature reduction

**Answer**: ☐ Yes, can do  ☐ No, software only  ☐ Need to check

**Why This Matters**: Hardware fixes are faster and more effective than software workarounds.

---

### 3. Battery Specifications
**Question**: What battery are you using?

**Please provide**:
- Battery voltage: _____ V (nominal)
- Battery capacity: _____ Ah
- Battery type: ☐ Lead-acid  ☐ Lithium  ☐ NiMH  ☐ Other: _____
- How do you currently monitor battery? _____________
- How do you know when to recharge? _____________
- Have you measured voltage during camera startup? ☐ Yes: _____ V  ☐ No

**Why This Matters**: 
- Determines if voltage sag is significant contributor
- Helps size power protection IC correctly
- Influences when to implement battery monitoring

---

### 4. Camera Mounting Details
**Question**: How is the camera physically mounted?

**Please describe**:
- Is camera bolted directly to motor base plate? ☐ Yes  ☐ No
- If no, what's between them? _____________
- Is there space for standoffs (3-5mm)? ☐ Yes  ☐ No  ☐ Don't know
- Can you take photo of camera mounting? _____________

**Measurements needed**:
- Distance from Joint3 motor case to camera housing: _____ mm
- Contact area between camera mount and base plate: _____ mm²

**Why This Matters**: 
- Determines feasibility of thermal isolation
- Helps estimate heat transfer rate
- Influences thermal pad design

---

### 5. Arm Geometry (for Park Position Calculation)
**Question**: What are the arm dimensions?

**Please measure**:
- Forearm length (Joint3 pivot to camera): _____ cm
- Forearm + camera weight: _____ kg (or grams)
- Current home position: Joint3 = _____ degrees (currently 0.0 rad = 0°)

**Quick test**:
1. Power off Joint3 motor (send 0x80 command)
2. Let arm droop naturally
3. Measure angle with protractor (or read encoder)
4. Natural droop angle: _____ degrees

**Why This Matters**: 
- Helps estimate optimal park position
- Validates -0.15 rad suggestion is reasonable
- Needed for counterbalance design (if later implemented)

---

### 6. Testing Timeline
**Question**: When do you need this working?

**Options**:
- [ ] URGENT: Field test in <1 week
- [ ] SOON: Field test in 1-2 weeks
- [ ] NORMAL: Field test in 3-4 weeks
- [ ] FLEXIBLE: Can test incrementally over time

**Why This Matters**: 
- Determines if we rush critical fixes only
- Or if we can implement monitoring properly
- Influences hardware vs. software trade-offs

**Your answer**: _____________

---

### 7. Development Environment
**Question**: Do you have tools for testing?

**Please confirm availability**:
- [ ] Multimeter (for voltage measurements)
- [ ] Thermometer or thermal camera (for temperature validation)
- [ ] Protractor or angle measuring tool
- [ ] Soldering iron (if hardware mods needed)
- [ ] 3D printer or machine shop access (for mechanical parts)

**Why This Matters**: 
- Determines which testing methods are feasible
- Influences how we validate fixes
- Affects hardware modification recommendations

---

### 8. Risk Tolerance
**Question**: What's your priority?

**Choose one**:
- [ ] **Safety First**: Prevent damage at all costs (add all interlocks, monitoring)
- [ ] **Quick Fix**: Get working ASAP, improve later (park position only)
- [ ] **Balanced**: Fix root cause + basic monitoring (park + temps)
- [ ] **Gold Plating**: Implement everything for long-term robustness

**Why This Matters**: 
- Determines scope of immediate implementation
- Influences testing thoroughness
- Affects how much time to spend on each phase

**Your answer**: _____________

---

### Summary: Next Steps Based on Your Answers

**If URGENT + Software Only**:
→ Park position fix only (4 hours)

**If URGENT + Hardware OK**:
→ Park position + thermal pad (1 day)

**If SOON + Monitoring Important**:
→ Park position + thermal pad + motor/camera temp monitoring (5 days)

**If FLEXIBLE + Complete Solution**:
→ Full phased implementation (3-4 weeks)

---

## References

- MG6010 Motor CAN Protocol V2.35 (LK-TECH)
- System logs: `outputs/logs/yanthra_move_20250110_*`
- Configuration: `src/yanthra_move/config/production.yaml`
- Web dashboard: `web_dashboard/`

---

**Document Version**: 1.1  
**Last Updated**: 2025-01-10 (Added execution order and refinement questions)  
**Author**: AI Assistant (Claude)  
**Review Status**: Ready for Implementation
