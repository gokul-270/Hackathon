# Complete Cotton Position to Motor Coordinate Flow

> ⚠️ **SUPERSEDED:** This document has been superseded by [COMPLETE_COORDINATE_FLOW_REFERENCE.md](guides/COMPLETE_COORDINATE_FLOW_REFERENCE.md) which includes:
> - Full bidirectional flow (forward AND reverse)
> - Updated formulas with code references
> - Per-joint parameter tables
> - Centroid.txt documentation
> - Worked examples with actual numbers
> - Frame clarification (yanthra_link vs base_link)
>
> **This document is kept for historical reference only.**

**Document Type:** Technical Reference and Bug Analysis  
**Date:** 2025-11-05  
**Status:** ⚠️ HISTORICAL - See new doc above  
**Scope:** End-to-end flow from camera pixels to motor CAN frames

---

## 🎯 Purpose

This document provides a **complete, accurate reference** for how cotton positions flow from camera detection through coordinate transformations to final motor commands. It also documents the **critical bug** where Joint4 (theta/horizontal rotation) is missing from the ROS2 implementation.

**Important:** This document does NOT modify any code. It serves as:
1. A reference for understanding the complete system flow
2. Documentation of the Joint4 bug discovered in ROS2
3. A comparison between working ROS1 code and incomplete ROS2 code
4. A specification for future fixes

---

## 🧠 Critical Bug: Joint4 Missing in ROS2

### **Summary**
The ROS2 implementation is **missing Joint4** (theta - horizontal rotation), which means the robot can only pick cotton positions that happen to lie along whatever horizontal angle the arm is currently at. This severely limits the workspace and causes positioning errors.

### **Robot Kinematic Structure (from URDF)**

```
Base (yanthra_link)
  └─ Joint2 (prismatic, Z-axis) - Vertical height
      └─ Joint3 (revolute, Z-axis) - PHI (vertical/base rotation around Z)
          └─ Joint4 (revolute, Y-axis) - THETA (horizontal/elbow rotation) ❌ MISSING IN ROS2!
              └─ Joint5 (prismatic, X-axis) - R (radial extension)
                  └─ End Effector
```

### **Correct Polar Coordinate Mapping**

```cpp
// From Cartesian (X, Y, Z) to Polar (r, theta, phi)
r     = sqrt(x² + y² + z²)        // Radial distance → Joint5
theta = atan2(y, x)                // Azimuth (horizontal) → Joint4 ❌ MISSING!
phi   = atan2(z, sqrt(x² + y²))   // Elevation (vertical) → Joint3
```

### **Evidence of Bug**

**ROS2 (BROKEN) - motion_controller.cpp:453-456:**
```cpp
motion_controller_ = std::make_unique<core::MotionController>(
    node_, 
    joint_move_3_.get(),  // joint3 for phi angle control ✅
    joint_move_5_.get()   // joint5 for radial extension ✅
    // ❌ joint4 is completely missing!
);
```

**ROS1 (WORKING) - yanthra_move.cpp:2212-2215:**
```cpp
joint_move_4.move_joint(thetaLink4, WAIT);              // ✅ Joint4 = theta
joint_move_3.move_joint(joint3_pose + phiLink3, WAIT);  // ✅ Joint3 = phi
// ... later ...
joint_move_5.move_joint(rLink5_origin, WAIT);           // ✅ Joint5 = r
```

---

## 📋 Complete End-to-End Flow

### **Overview Diagram**

```
Camera Pixels → Detection (HSV/YOLO/DepthAI) → 3D Position (camera frame)
   ↓
TF Transform (camera_link → yanthra_link/base)
   ↓
Cartesian (X, Y, Z) in base frame
   ↓
Inverse Kinematics → Polar (r, theta, phi)
   ↓
Joint Commands (joint2, joint3, joint4, joint5)
   ↓
Motor Controller → Joint to Motor Position Conversion
   ↓
Protocol Encoding → CAN Messages
   ↓
Motors Execute Movement
```

---

## 🧪 Phase 1: Cotton Detection

**Location:** `src/cotton_detection_ros2/src/cotton_detection_node_detection.cpp`

### **Detection Modes**

1. **DEPTHAI_DIRECT**: Neural network with spatial coordinates (X, Y, Z directly from camera)
2. **HSV_ONLY**: Color-based detection (pixel → 3D conversion needed)
3. **YOLO_ONLY**: Deep learning detection (pixel → 3D conversion needed)
4. **HYBRID_***: Combination voting/merging strategies

### **Pixel to 3D Conversion (HSV/YOLO modes)**

```cpp
// Lines 256-277
for (const auto& center : final_centers) {
    if (positions.size() >= static_cast<size_t>(max_cotton_detections_)) {
        break;
    }
    
    // Convert pixel coordinates to world coordinates
    geometry_msgs::msg::Point pos;
    pos.x = (center.x - processed_image.cols/2.0) * pixel_to_meter_scale_x_;
    pos.y = (center.y - processed_image.rows/2.0) * pixel_to_meter_scale_y_;
    pos.z = assumed_depth_m_;  // Assume fixed distance for now
    
    // Validate position is within configurable workspace bounds
    if (std::abs(pos.x) > workspace_max_x_ || std::abs(pos.y) > workspace_max_y_ || 
        pos.z < workspace_min_z_ || pos.z > workspace_max_z_) {
        RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 1000,
            "⚠️ Filtered out-of-bounds detection: (%.2f, %.2f, %.2f)m", 
            pos.x, pos.y, pos.z);
        continue;  // Skip invalid positions
    }
    
    positions.push_back(pos);
}
```

**Parameters:**
- `pixel_to_meter_scale_x_`: Calibrated X scale (meters/pixel)
- `pixel_to_meter_scale_y_`: Calibrated Y scale (meters/pixel)
- `assumed_depth_m_`: Fixed Z distance assumption (e.g., 0.5m)
- `workspace_max_x/y_`, `workspace_min/max_z_`: Safety limits

**Output:** `std::vector<geometry_msgs::msg::Point>` in **camera frame**

---

## 🔁 Phase 2: TF Transformations

**Location:** `src/yanthra_move/src/coordinate_transforms.cpp`

### **Transform Chain**

```
camera_link → yanthra_origin (or base_link) → link3 → link4 → link5 → link5_origin
```

### **Frame Definitions (from URDF)**

```xml
<!-- Joint2 - Prismatic (height control) -->
<joint name="joint2_joint" type="prismatic">
    <parent link="yanthra_link"/>
    <child link="joint2"/>
    <axis xyz="0 0 1"/>  <!-- Z-axis (vertical) -->
</joint>

<!-- Joint3 - Revolute (phi - vertical rotation) -->
<joint name="joint3_joint" type="revolute">
    <parent link="joint2"/>
    <child link="joint3"/>
    <axis xyz="0 0 1"/>  <!-- Z-axis (base rotation) -->
</joint>

<!-- Joint4 - Revolute (theta - horizontal rotation) -->
<joint name="joint4_joint" type="revolute">
    <parent link="link3"/>
    <child link="joint4"/>
    <axis xyz="0 1 0"/>  <!-- Y-axis (elbow/pitch) -->
</joint>

<!-- Joint5 - Prismatic (r - radial extension) -->
<joint name="joint5_joint" type="prismatic">
    <parent link="link4"/>
    <child link="joint5"/>
    <axis xyz="1 0 0"/>  <!-- X-axis (forward) -->
</joint>
```

### **Transform Code**

```cpp
// Lines 45-77 in coordinate_transforms.cpp
void getCottonCoordinates_cameraToYanthraOrigin(
    tf2_ros::Buffer& tf_buffer, 
    std::vector<geometry_msgs::msg::Point>& input_positions, 
    std::vector<geometry_msgs::msg::Point>& output_positions) 
{
    output_positions.clear();
    try {
        // Try yanthra_origin first, fallback to base_link if not available
        geometry_msgs::msg::TransformStamped transform;
        try {
            transform = tf_buffer.lookupTransform("yanthra_origin", "camera_link", tf2::TimePointZero);
        } catch (tf2::TransformException &ex1) {
            // Fallback to base_link if yanthra_origin doesn't exist
            transform = tf_buffer.lookupTransform("base_link", "camera_link", tf2::TimePointZero);
        }

        for (const auto& point : input_positions) {
            geometry_msgs::msg::PointStamped point_in, point_out;
            point_in.header.frame_id = "camera_link";
            point_in.point = point;
            tf2::doTransform(point_in, point_out, transform);
            output_positions.push_back(point_out.point);
        }
    } catch (tf2::TransformException &ex) {
        RCLCPP_WARN(rclcpp::get_logger("yanthra_move"), "Could not transform: %s", ex.what());
    }
}
```

**Output:** `std::vector<geometry_msgs::msg::Point>` in **base/yanthra_origin frame**

---

## 📐 Phase 3: Cartesian to Polar Conversion (Inverse Kinematics)

**Location:** `src/yanthra_move/src/core/motion_controller.cpp:271-323`

### **Current ROS2 Implementation (INCOMPLETE - Missing theta)**

```cpp
// Lines 271-323 in executeApproachTrajectory()
bool MotionController::executeApproachTrajectory(const geometry_msgs::msg::Point& position) {
    RCLCPP_INFO(node_->get_logger(), 
                "🎯 Executing approach trajectory to cotton at [%.3f, %.3f, %.3f] meters",
                position.x, position.y, position.z);

    // Step 1: Convert Cartesian coordinates (X,Y,Z) to polar (r, theta, phi)
    double r = 0.0, theta = 0.0, phi = 0.0;
    yanthra_move::coordinate_transforms::convertXYZToPolarFLUROSCoordinates(
        position.x, position.y, position.z, &r, &theta, &phi);
    
    RCLCPP_INFO(node_->get_logger(), 
                "   📐 Polar coordinates: r=%.3f m, theta=%.3f rad, phi=%.3f rad",
                r, theta, phi);
    
    // Step 2: Check reachability
    if (!yanthra_move::coordinate_transforms::checkReachability(r, theta, phi)) {
        RCLCPP_ERROR(node_->get_logger(), "❌ Position is out of reach! Skipping this cotton.");
        return false;
    }
    
    // Step 3: Command the motors
    // ❌ BUG: theta is computed but never used! Joint4 is missing!
    
    RCLCPP_INFO(node_->get_logger(), 
                "🚀 Commanding motors: joint3 (phi) = %.3f rad, joint5 (r) = %.3f m",
                phi, r);
    
    // Command joint3 for phi angle (base rotation)
    if (joint_move_3_) {
        joint_move_3_->move_joint(phi, false);  // Non-blocking
    }
    
    // ❌ MISSING: joint_move_4_->move_joint(theta, false);
    
    // Command joint5 for radial extension
    const double LINK5_MIN_LENGTH = joint5_init_.min_length;
    double joint5_target = r - LINK5_MIN_LENGTH;
    
    if (joint_move_5_) {
        joint_move_5_->move_joint(joint5_target, false);  // Non-blocking
    }
    
    // Wait for movement
    yanthra_move::utilities::ros2SafeSleep(
        std::chrono::milliseconds(static_cast<int>(min_sleep_time_for_motor_motion_ * 1000)));
    
    RCLCPP_INFO(node_->get_logger(), "✅ Approach trajectory completed");
    return true;
}
```

### **Polar Conversion Formulas**

```cpp
// Lines 33-37 in coordinate_transforms.cpp
void convertXYZToPolarFLUROSCoordinates(double x, double y, double z, 
                                        double* r, double* theta, double* phi) {
    *r = sqrt(x*x + y*y + z*z);           // Radial distance
    *theta = atan2(y, x);                  // Horizontal angle (azimuth)
    *phi = atan2(z, sqrt(x*x + y*y));     // Vertical angle (elevation)
}
```

### **ROS1 Working Implementation (CORRECT)**

```cpp
// From /home/uday/Downloads/pragati/src/yanthra_move/src/yanthra_move.cpp:2171-2175
ConvertXYZToPolarFLUROSCoordinates((it->point.x), (it->point.y), it->point.z, 
                                    &rYanthra, &thetaYanthra, &phiYanthra);
ConvertXYZToPolarFLUROSCoordinates((it_local3->point.x), (it_local3->point.y), it_local3->point.z, 
                                    &rLink3, &thetaLink3, &phiLink3);
ConvertXYZToPolarFLUROSCoordinates((it_local4->point.x), (it_local4->point.y), it_local4->point.z, 
                                    &rLink4, &thetaLink4, &phiLink4);
ConvertXYZToPolarFLUROSCoordinates((it_local5->point.x), (it_local5->point.y), it_local5->point.z, 
                                    &rLink5, &thetaLink5, &phiLink5);
ConvertXYZToPolarFLUROSCoordinates((it_local5_origin->point.x), (it_local5_origin->point.y), 
                                    it_local5_origin->point.z, 
                                    &rLink5_origin, &thetaLink5_origin, &phiLink5_origin);

// Lines 2212-2215, 2277 - Commands all three joints
joint_move_4.move_joint(thetaLink4, WAIT);              // ✅ Joint4 = theta
joint_move_3.move_joint(joint3_pose + phiLink3, WAIT);  // ✅ Joint3 = phi
// ... later ...
joint_move_5.move_joint(rLink5_origin, WAIT);           // ✅ Joint5 = r
```

---

## 🎮 Phase 4: Joint Commanding

### **Joint Responsibilities**

| Joint | Type | Axis | Controls | Units | ROS2 Status |
|-------|------|------|----------|-------|-------------|
| Joint2 | Prismatic | Z | Vertical height | meters | ⚠️ Not used in picking |
| Joint3 | Revolute | Z | Phi (base rotation) | radians | ✅ Working |
| Joint4 | Revolute | Y | Theta (horizontal/elbow) | radians | ❌ **MISSING** |
| Joint5 | Prismatic | X | R (radial extension) | meters | ✅ Working |

### **ROS2 System Integration (INCOMPLETE)**

```cpp
// From yanthra_move_system_core.cpp:453-456
motion_controller_ = std::make_unique<core::MotionController>(
    node_, 
    joint_move_3_.get(),  // ✅ joint3 for phi angle control
    joint_move_5_.get()   // ✅ joint5 for radial extension
    // ❌ joint4 pointer is missing from constructor!
);
```

### **Joint Move Command Flow**

```cpp
// From joint_move.cpp:82-128
void joint_move::move_joint(double value, bool wait) {
    if(error_code != NO_ERROR) {
        RCLCPP_ERROR(node_->get_logger(), "Can't move joint %s, error: %u", 
                     joint_name_.c_str(), error_code);
        return;
    }

    // Check for simulation mode
    if (yanthra_move::simulation_mode) {
        RCLCPP_INFO(node_->get_logger(), "🤖 SIMULATION: Joint %s moving to position: %.6f rad",
            joint_name_.c_str(), value);
        current_position_ = value;
        return;
    }

    // Select the correct publisher based on joint name
    rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr publisher;
    
    if (joint_name_ == "joint2" && joint2_cmd_pub_) {
        publisher = joint2_cmd_pub_;
    } else if (joint_name_ == "joint3" && joint3_cmd_pub_) {
        publisher = joint3_cmd_pub_;
    } else if (joint_name_ == "joint4" && joint4_cmd_pub_) {
        publisher = joint4_cmd_pub_;
    } else if (joint_name_ == "joint5" && joint5_cmd_pub_) {
        publisher = joint5_cmd_pub_;
    } else {
        RCLCPP_ERROR(node_->get_logger(), "No publisher found for joint: %s", joint_name_.c_str());
        return;
    }

    std_msgs::msg::Float64 cmd_msg;
    cmd_msg.data = value;
    publisher->publish(cmd_msg);  // Topic: /jointN_position_controller/command

    RCLCPP_INFO(node_->get_logger(), "🚀 Joint %s commanded to position: %.6f rad", 
        joint_name_.c_str(), value);
}
```

**Note:** The infrastructure supports joint4 (publisher exists at line 108-109), but MotionController never calls it because joint4 pointer was never passed to the constructor!

---

## ⚙️ Phase 5: Motor Controller Transformations

**Location:** `src/motor_control_ros2/src/mg6010_controller.cpp:640-676`

### **Joint to Motor Position Conversion**

```cpp
double MG6010Controller::joint_to_motor_position(double joint_pos) const {
    // MG6010 motor multi-turn angle is INTERNAL ROTOR angle (before 6:1 gearbox)
    // 2160° internal = 360° output shaft (1 full rotation)
    const double INTERNAL_GEAR_RATIO = 6.0;
    
    std::cout << "\n========== JOINT TO MOTOR CONVERSION (" << config_.joint_name 
              << ") ==========" << std::endl;
    std::cout << "[1] Input joint_pos: " << joint_pos << std::endl;
    std::cout << "[2] joint_offset: " << config_.joint_offset << std::endl;
    std::cout << "[3] transmission_factor: " << config_.transmission_factor << std::endl;
    std::cout << "[4] direction: " << config_.direction << std::endl;
    
    // Step 1: Apply offset
    double after_offset = joint_pos - config_.joint_offset;
    std::cout << "[5] After offset (joint_pos - offset): " << after_offset << std::endl;
    
    // Step 2: Apply transmission factor (MULTIPLY for this convention)
    double after_transmission = after_offset * config_.transmission_factor;
    std::cout << "[6] After transmission (× transmission): " << after_transmission << std::endl;
    
    // Step 3: Apply direction
    double output_rotations = after_transmission * config_.direction;
    std::cout << "[7] Output rotations (× direction): " << output_rotations << std::endl;
    
    // Step 4: Convert output rotations to radians
    double output_angle_rad = output_rotations * 2.0 * M_PI;
    std::cout << "[8] Output angle in radians (× 2π): " << output_angle_rad << " rad" << std::endl;
    
    // Step 5: Apply internal gear ratio to get motor rotor angle
    double motor_angle = output_angle_rad * INTERNAL_GEAR_RATIO;
    std::cout << "[9] Motor rotor angle (× 6.0 gear ratio): " << motor_angle << " rad" << std::endl;
    std::cout << "[10] Motor rotor angle in degrees: " << (motor_angle * 180.0 / M_PI) << "°" 
              << std::endl;
    std::cout << "[11] Motor rotor rotations: " << (motor_angle / (2.0 * M_PI)) 
              << " rotations" << std::endl;
    
    return motor_angle;
}
```

### **Transmission Factors (from mg6010_three_motors.yaml)**

```yaml
joint3:  # Base rotation (revolute)
  transmission_factor: 6.0  # output_rotations per joint_input (radians)
  
joint4:  # Horizontal rotation (revolute)
  transmission_factor: 12.7  # output_rotations per joint_input (radians)
  
joint5:  # Radial extension (prismatic)
  transmission_factor: 12.7  # radians_per_meter (linear)
```

### **Example Calculation: Joint4 (if it were working)**

```
Input: joint4_pos = 0.588 rad (33.7°)
Step 1: after_offset = 0.588 - 0.0 = 0.588 rad
Step 2: after_transmission = 0.588 × 12.7 = 7.468 rotations
Step 3: output_rotations = 7.468 × 1 = 7.468 rotations
Step 4: output_angle_rad = 7.468 × 2π = 46.92 rad
Step 5: motor_angle = 46.92 × 6.0 = 281.5 rad = 16,126° = 44.8 motor rotations
```

---

## 📨 Phase 6: CAN Protocol Encoding

**Location:** `src/motor_control_ros2/src/mg6010_protocol.cpp`

### **Angle Encoding**

```cpp
// Simplified from mg6010_protocol.cpp:666-680
std::vector<uint8_t> encode_multi_turn_angle(double radians) {
    // radians = motor_angle from previous phase
    
    // Convert to degrees
    double degrees = radians * (180.0 / M_PI);
    
    // Convert to 0.01 degree units (protocol format)
    int32_t angle_0_01deg = static_cast<int32_t>(degrees * 100.0);
    
    // Pack as 4 bytes little-endian
    std::vector<uint8_t> bytes(4);
    bytes[0] = angle_0_01deg & 0xFF;
    bytes[1] = (angle_0_01deg >> 8) & 0xFF;
    bytes[2] = (angle_0_01deg >> 16) & 0xFF;
    bytes[3] = (angle_0_01deg >> 24) & 0xFF;
    
    return bytes;
}
```

### **CAN Message Structure**

```
CAN ID: Motor address (e.g., 0x1 for joint3, 0x2 for joint4)
Command: 0xA4 (CMD_MULTI_LOOP_ANGLE_1)
Data: [speed_byte0, speed_byte1, speed_byte2, speed_byte3,
       angle_byte0, angle_byte1, angle_byte2, angle_byte3]
```

### **Example: Joint4 Command (if it were working)**

```
Target position: 0.588 rad = 33.7°
Motor position: 281.5 rad = 16,126° = 1,612,600 (in 0.01° units)

CAN Message:
  ID: 0x2 (joint4 motor)
  Command: 0xA4
  Data: [0x00, 0x00, 0x00, 0x00,    // Speed (default)
         0x58, 0x9F, 0x18, 0x00]    // 1,612,600 in hex (little-endian)
```

---

## 🛠️ Fix Requirements (Future Work - Not Implemented Here)

### **Root Causes**

1. **Constructor Issue:** `MotionController` only accepts `joint3` and `joint5` pointers (line 453-456 in yanthra_move_system_core.cpp)
2. **Missing Computation:** `theta` is computed but never used (line 278 in motion_controller.cpp)
3. **No Joint4 Wiring:** System never creates `joint_move_4_` instance for MotionController
4. **Missing Command:** `executeApproachTrajectory()` never calls `joint_move_4_->move_joint(theta, false)`

### **Minimal Fix Checklist** (Documentation only - no changes in this pass)

#### 1. Update MotionController Constructor

```cpp
// In motion_controller.hpp:43-45
explicit MotionController(std::shared_ptr<rclcpp::Node> node, 
                          joint_move* joint3,
                          joint_move* joint4,  // ← ADD THIS
                          joint_move* joint5);

// In motion_controller.cpp:31-42
MotionController::MotionController(std::shared_ptr<rclcpp::Node> node,
                                   joint_move* joint3,
                                   joint_move* joint4,  // ← ADD THIS
                                   joint_move* joint5)
    : node_(node), 
      joint_move_3_(joint3), 
      joint_move_4_(joint4),  // ← ADD THIS
      joint_move_5_(joint5) {
    
    if (!joint_move_3_ || !joint_move_4_ || !joint_move_5_) {  // ← UPDATE CHECK
        RCLCPP_ERROR(node_->get_logger(), 
                     "❌ MotionController initialized with NULL joint pointers!");
        throw std::runtime_error("Joint move pointers cannot be null");
    }
    
    RCLCPP_INFO(node_->get_logger(), 
                "✅ Motion Controller initialized with joint3, joint4, and joint5 controllers");
}
```

#### 2. Add Joint4 Member Variable

```cpp
// In motion_controller.hpp:99-101
joint_move* joint_move_3_;  // Controls phi angle (base rotation)
joint_move* joint_move_4_;  // Controls theta angle (horizontal rotation) ← ADD THIS
joint_move* joint_move_5_;  // Controls r (extension)
```

#### 3. Wire Joint4 in System Core

```cpp
// In yanthra_move_system_core.cpp:453-458
motion_controller_ = std::make_unique<core::MotionController>(
    node_, 
    joint_move_3_.get(),  // joint3 for phi angle control
    joint_move_4_.get(),  // joint4 for theta angle control ← ADD THIS
    joint_move_5_.get()   // joint5 for radial extension
);
```

#### 4. Command Joint4 in executeApproachTrajectory

```cpp
// In motion_controller.cpp, after line 302, ADD:
// Command joint4 for theta angle (horizontal rotation)
if (joint_move_4_) {
    joint_move_4_->move_joint(theta, false);  // Non-blocking
}
```

#### 5. Update Comments and Logs

```cpp
// Update line 297-298 in motion_controller.cpp:
RCLCPP_INFO(node_->get_logger(), 
            "🚀 Commanding motors: joint3 (phi)=%.3f rad, joint4 (theta)=%.3f rad, joint5 (r)=%.3f m",
            phi, theta, r);
```

### **Testing Plan** (Future Implementation)

1. **Unit Tests:**
   - Test `convertXYZToPolarFLUROSCoordinates()` with known positions
   - Verify theta output matches expected horizontal angle
   
2. **Integration Tests:**
   - Place test marker at known (X, Y, Z) position
   - Verify joint4 commands to correct theta angle
   - Check end effector arrives at target position
   
3. **HIL (Hardware-in-Loop) Tests:**
   - Run with real motors in simulation mode
   - Verify no collisions or limit violations
   - Measure positioning accuracy

4. **Field Tests:**
   - Pick cotton at various horizontal angles
   - Verify workspace coverage increased
   - Measure pick success rate improvement

---

## 📊 ROS1 vs ROS2 Comparison

| Aspect | ROS1 (Working) | ROS2 (Broken) | Status |
|--------|----------------|---------------|--------|
| **Joint2** | Used for height adjustment | Not used in picking loop | ⚠️ Partial |
| **Joint3 (phi)** | `joint_move_3.move_joint(joint3_pose + phiLink3)` | `joint_move_3_->move_joint(phi)` | ✅ Working |
| **Joint4 (theta)** | `joint_move_4.move_joint(thetaLink4)` | **MISSING** | ❌ **Bug** |
| **Joint5 (r)** | `joint_move_5.move_joint(rLink5_origin)` | `joint_move_5_->move_joint(r - offset)` | ✅ Working |
| **Coordinate Frames** | Computes for Link3, Link4, Link5, Link5_origin | Only yanthra_origin | ⚠️ Less precise |
| **Constructor** | N/A (monolithic) | Missing joint4 parameter | ❌ Root cause |
| **Picking Success** | High (full 3-DOF workspace) | Low (limited to 2-DOF slice) | ❌ Impact |

---

## ➗ Mathematical Formulas Reference

### **Cartesian to Polar (FLU Convention)**

Given target position **P** = [x, y, z]ᵀ in base frame:

```
r     = √(x² + y² + z²)
theta = atan2(y, x)           ← Used for Joint4 (horizontal rotation)
phi   = atan2(z, √(x² + y²))  ← Used for Joint3 (vertical rotation)
```

### **Inverse (Polar to Cartesian)**

```
x = r · cos(phi) · cos(theta)
y = r · cos(phi) · sin(theta)
z = r · sin(phi)
```

### **Reachability Check**

```cpp
bool checkReachability(double r, double theta, double phi) {
    return (r > R_MIN && r < R_MAX) &&
           (theta > THETA_MIN && theta < THETA_MAX) &&
           (phi > PHI_MIN && phi < PHI_MAX);
}
```

**Current implementation (simplified):**
```cpp
return (r > 0.1 && r < 2.0);  // Only checks r, ignores theta/phi limits
```

---

## ✅ Validation Checklist (Future)

### **Pre-Fix Validation (Current State)**
- [ ] Confirm theta is computed but not used
- [ ] Verify joint4 publisher exists but never called
- [ ] Measure current workspace coverage (2D slice only)
- [ ] Document positioning errors

### **Post-Fix Validation**
- [ ] All 4 joints receive commands (joint2, 3, 4, 5)
- [ ] Theta correctly mapped to joint4
- [ ] End effector reaches target (X, Y, Z) within ±2cm
- [ ] Full 3D workspace is accessible
- [ ] No new joint limit violations
- [ ] Pick success rate improves by >50%

---

## 📎 References

### **Key Files**

| File | Lines | Description |
|------|-------|-------------|
| `cotton_detection_node_detection.cpp` | 256-277 | Pixel to 3D conversion |
| `coordinate_transforms.cpp` | 33-37, 45-77 | Polar conversion & TF transforms |
| `motion_controller.cpp` | 271-323 | Missing joint4 command (BUG) |
| `yanthra_move_system_core.cpp` | 453-456 | Constructor missing joint4 (ROOT CAUSE) |
| `joint_move.cpp` | 82-128 | Joint commanding (infrastructure OK) |
| `mg6010_controller.cpp` | 640-676 | Joint to motor conversion |
| **ROS1 Reference** | | |
| `pragati/yanthra_move.cpp` | 2171-2175 | Polar conversion (correct) |
| `pragati/yanthra_move.cpp` | 2212-2215, 2277 | Joint4 commanding (working) |

### **Configuration Files**

| File | Purpose |
|------|---------|
| `pragati_robot_description.urdf` | Joint definitions and axes |
| `mg6010_three_motors.yaml` | Transmission factors |
| `production.yaml` | Motion parameters |

### **URDF Joint Summary**

```yaml
joint2: {type: prismatic, axis: [0,0,1], limits: [0.01, 1.0]}    # Z-axis (height)
joint3: {type: revolute,  axis: [0,0,1], limits: [-π, π]}       # Z-axis (phi)
joint4: {type: revolute,  axis: [0,1,0], limits: [-π, π]}       # Y-axis (theta) ← MISSING
joint5: {type: prismatic, axis: [1,0,0], limits: [0.162, 0.601]} # X-axis (r)
```

---

## 🔚 Conclusion

This document provides a **complete, accurate reference** for the cotton position to motor coordinate flow. The critical finding is that **Joint4 (theta) is completely missing** from the ROS2 implementation, severely limiting the robot's workspace and causing positioning errors.

The bug is well-understood with clear root causes and a minimal fix path documented above. **No code changes were made in this document** - it serves purely as technical reference and specification for future implementation.

### **Next Steps** (Not Performed Here)

1. Review this document with the team
2. Create GitHub issue referencing this doc
3. Implement the 5-step fix checklist above
4. Run validation tests
5. Deploy to hardware for field testing

---

**Document Version:** 1.0  
**Author:** AI Assistant (based on codebase analysis)  
**Review Status:** Pending team review  
**Implementation Status:** Not started (documentation only)
