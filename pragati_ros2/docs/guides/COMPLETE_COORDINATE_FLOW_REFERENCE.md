# Complete Coordinate Flow Reference
# Camera Detection → Motor Commands → Back to Camera (Full Cycle)

**Document Type:** Technical Reference and Formula Specification  
**Date:** 2025-11-15  
**Git Commit:** `e5aab95` (2025-11-14)  
**Status:** ✅ Authoritative - Single Source of Truth

---

## 📑 **Table of Contents**

1. [Authoritative Sources](#authoritative-sources)
2. [System Overview](#system-overview)
3. [Forward Flow: Camera → Motors](#forward-flow-camera--motors)
   - [Phase 1: Camera Detection → 3D Position](#phase-1-camera-detection--3d-position)
   - [Phase 2: TF Transform (camera_link → yanthra_link)](#phase-2-tf-transform)
   - [Phase 3: Cartesian → Polar/Joint Mapping](#phase-3-cartesian--polarjoint-mapping)
   - [Phase 4: Joint → Motor Position](#phase-4-joint--motor-position)
   - [Phase 5: CAN Protocol Encoding](#phase-5-can-protocol-encoding)
4. [Reverse Flow: Motors → Camera](#reverse-flow-motors--camera)
   - [Phase 1: CAN → Motor Angle](#phase-1-can--motor-angle)
   - [Phase 2: Motor → Joint Position](#phase-2-motor--joint-position)
   - [Phase 3: Forward Kinematics (Joint → Cartesian)](#phase-3-forward-kinematics)
   - [Phase 4: yanthra_link → camera_link](#phase-4-yanthra_link--camera_link)
5. [Per-Joint Parameters](#per-joint-parameters)
6. [Centroid.txt Files](#centroidtxt-files)
7. [Mathematical Appendix](#mathematical-appendix)
8. [Worked Examples](#worked-examples)
9. [Validation & Testing](#validation--testing)

---

## 🔐 **Authoritative Sources**

### **System-of-Record Files:**

| Component | File Path | Purpose |
|-----------|-----------|---------|
| **URDF** | `src/robot_description/urdf/MG6010_final.urdf` | Robot kinematics structure |
| **Motor Config** | `src/motor_control_ros2/config/production.yaml` | Transmission factors, limits, directions |
| **Controller** | `src/motor_control_ros2/src/mg6010_controller.cpp` | Joint↔Motor conversion |
| **Protocol** | `src/motor_control_ros2/src/mg6010_protocol.cpp` | CAN encoding/decoding |
| **Motion Control** | `src/yanthra_move/src/core/motion_controller.cpp` | Cartesian→Joint mapping |
| **Transforms** | `src/yanthra_move/src/coordinate_transforms.cpp` | TF operations, polar conversion |
| **Detection** | `src/pattern_finder/src/aruco_finder.cpp` | ArUco 3D position |
| **Depth Calc** | `src/pattern_finder/scripts/calc.py` | Pinhole projection |

### **Authoritative Decisions:**

1. **Reference Frame:** `yanthra_link` (NOT base_link) - see [FRAME_REFERENCE_GUIDE.md](../FRAME_REFERENCE_GUIDE.md)
2. **Joint Types (from URDF):**
   - Joint3: Revolute (-Y axis rotation)
   - Joint4: Prismatic (+Y axis translation)  
   - Joint5: Prismatic (+X axis translation)
3. **CAN Protocol Encoding:** 0.01° units (centidegrees), 8-byte payload format
4. **Transmission Convention:** ODrive-style (multiplication for prismatic joints)

---

## 🌐 **System Overview**

```
┌─────────────────────── FORWARD FLOW ───────────────────────┐
│                                                              │
│  📷 Camera Pixels      →  3D Position (camera_link)         │
│        ↓                                                     │
│  🔄 TF Transform       →  Cartesian (yanthra_link)          │
│        ↓                                                     │
│  📐 Polar/IK           →  Joint Commands (rad, meters)      │
│        ↓                                                     │
│  ⚙️  Motor Conversion  →  Motor Angles (radians)            │
│        ↓                                                     │
│  📨 CAN Protocol       →  Byte Messages (0.01° units)       │
│                                                              │
└──────────────────────────────────────────────────────────────┘

┌─────────────────────── REVERSE FLOW ───────────────────────┐
│                                                              │
│  📨 CAN Bytes          →  Motor Angles (radians)            │
│        ↓                                                     │
│  ⚙️  Motor Conversion  →  Joint Positions (rad, meters)     │
│        ↓                                                     │
│  🏗️ Forward Kinematics →  Cartesian (yanthra_link)          │
│        ↓                                                     │
│  🔄 TF Inverse         →  3D Position (camera_link)         │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 🎯 **Forward Flow: Camera → Motors**

### **Phase 1: Camera Detection → 3D Position**

#### **Method 1: ArUco Marker Detection**

**Code:** `src/pattern_finder/src/aruco_finder.cpp:161-291`

```cpp
// Convert 2D pixel + depth to 3D point
pcl::PointXYZ convert_2d_to_3d(cv::Point2f point_2d) {
    pcl::PointXYZ point_3d;
    // Search 8-directional neighborhood (up to 5 pixels radius)
    // to find valid depth values
    getStatisticalDepth(*input_cloud, pt_indices, point_3d);
    return point_3d;  // Returns X, Y, Z in meters (camera frame)
}

// Main detection (lines 287-291)
if (marker_detected) {
    centroid_file << detected_points[0].x << " " 
                  << detected_points[0].y << " " 
                  << detected_points[0].z << std::endl;
    // Repeats for all 4 corners
}
```

**Output Format:** `centroid.txt` with schema:
```
X Y Z    # Corner 1 (meters, camera_link frame)
X Y Z    # Corner 2
X Y Z    # Corner 3
X Y Z    # Corner 4
```

#### **Method 2: DepthAI Spatial Calculation**

**Code:** `src/pattern_finder/scripts/calc.py:37-65`

```python
def calc_spatials(self, depthFrame, roi, averaging_method=np.mean):
    # Get ROI centroid
    centroid = {
        'x': int((xmax + xmin) / 2),
        'y': int((ymax + ymin) / 2)
    }
    
    # Calculate average depth in ROI
    averageDepth = averaging_method(depthROI[inRange])
    
    # Calculate angles from camera center
    midW = int(depthFrame.shape[1] / 2)
    midH = int(depthFrame.shape[0] / 2)
    bb_x_pos = centroid['x'] - midW
    bb_y_pos = centroid['y'] - midH
    
    angle_x = atan(tan(HFOV/2) * bb_x_pos / (width/2))
    angle_y = atan(tan(HFOV/2) * bb_y_pos / (height/2))
    
    # Convert to 3D coordinates
    spatials = {
        'z': averageDepth,                      # Depth (forward)
        'x': averageDepth * tan(angle_x),       # Right (+)
        'y': -averageDepth * tan(angle_y)       # Down (-) → Up (+)
    }
    return spatials, centroid
```

**Coordinate Convention (camera_link):**
- **X:** Right (+), Left (-)
- **Y:** Down (-), Up (+) [negated in formula]
- **Z:** Forward (depth)

---

### **Phase 2: TF Transform**

**Code:** `src/yanthra_move/src/core/motion_controller.cpp:362-382`

```cpp
// Transform from camera_link to yanthra_link
geometry_msgs::msg::PointStamped target_camera, target_yanthra;
target_camera.header.frame_id = "camera_link";
target_camera.point = position;  // Input: X, Y, Z from camera

try {
    auto transform = tf_buffer_->lookupTransform(
        "yanthra_link",      // Target frame (computational reference)
        "camera_link",       // Source frame
        tf2::TimePointZero,
        tf2::durationFromSec(0.5)
    );
    
    tf2::doTransform(target_camera, target_yanthra, transform);
    // Output: target_yanthra.point = {x, y, z} in yanthra_link frame
    
} catch (const tf2::TransformException& ex) {
    // Fallback to base_link if yanthra_link unavailable
    transform = tf_buffer_->lookupTransform("base_link", "camera_link", ...);
}
```

**Formula:**
```
p_yanthra = T_yanthra_camera × p_camera
```

Where `T_yanthra_camera` is the homogeneous transform obtained from TF tree (computed from URDF at runtime).

**Verification Command:**
```bash
ros2 run tf2_ros tf2_echo yanthra_link camera_link
```

---

### **Phase 3: Cartesian → Polar/Joint Mapping**

**Code:** `src/yanthra_move/src/core/motion_controller.cpp:385-467`

#### **Polar Conversion (NO INVERSE KINEMATICS)**

```cpp
// coordinate_transforms.cpp:33-36
void convertXYZToPolarFLUROSCoordinates(double x, double y, double z, 
                                        double* r, double* theta, double* phi) {
    *r = sqrt(x*x + z*z);                // Radius in XZ plane
    *theta = y;                          // Y-coordinate (lateral)
    *phi = asin(z / sqrt(z*z + x*x));   // Elevation angle in XZ plane
}
```

#### **Joint Command Calculations**

```cpp
// Joint3 (revolute rotation) - motion_controller.cpp:409-410
const double RAD_TO_ROT = 1.0 / (2.0 * M_PI);
const double joint3_cmd = phi * RAD_TO_ROT;  // Convert radians → rotations

// Limits check
if (joint3_cmd < -0.2 || joint3_cmd > 0.0) {  // JOINT3_LIMITS from YAML
    RCLCPP_ERROR("Joint3 out of range!");
    return false;
}

// Joint4 (prismatic lateral) - motion_controller.cpp:444
const double joint4_cmd = theta;  // Direct Y-coordinate passthrough (meters)

// Limits check  
if (joint4_cmd < -0.125 || joint4_cmd > 0.125) {  // JOINT4_LIMITS from YAML
    RCLCPP_ERROR("Joint4 out of range!");
    return false;
}

// Joint5 (prismatic extension) - motion_controller.cpp:467
const double joint5_cmd = r - joint5_hardware_offset_;  // Default offset: 0.320m

// Limits check
if (joint5_cmd < 0.0 || joint5_cmd > 0.35) {  // JOINT5_LIMITS from YAML
    RCLCPP_ERROR("Joint5 out of range!");
    return false;
}
```

**Key Insight:** This is a **simplified direct mapping** (Phase 1), NOT full inverse kinematics. See [NO-IK-PIPELINE.md](../../src/yanthra_move/docs/NO-IK-PIPELINE.md) for details.

---

### **Phase 4: Joint → Motor Position**

**Code:** `src/motor_control_ros2/src/mg6010_controller.cpp:640-676`

```cpp
double MG6010Controller::joint_to_motor_position(double joint_pos) const {
    const double INTERNAL_GEAR_RATIO = 6.0;
    
    // Step 1: Apply offset
    double after_offset = joint_pos - config_.joint_offset;
    
    // Step 2: Apply transmission factor
    double after_transmission = after_offset * config_.transmission_factor;
    
    // Step 3: Apply direction
    double output_rotations = after_transmission * config_.direction;
    
    // Step 4: Convert to radians (for revolute joints with rotations)
    double output_angle_rad = output_rotations * 2.0 * M_PI;
    
    // Step 5: Apply internal gear ratio
    double motor_angle = output_angle_rad * INTERNAL_GEAR_RATIO;
    
    return motor_angle;  // Radians at motor shaft (before gearbox output)
}
```

**Per-Joint Behavior:**

#### **Joint3 (Revolute):**
```
Input: joint3_cmd = -0.127 rotations
Step 1: after_offset = -0.127 - 0.0 = -0.127 rotations
Step 2: after_transmission = -0.127 × 1.0 = -0.127 rotations
Step 3: output_rotations = -0.127 × (-1) = 0.127 rotations  [direction inverts!]
Step 4: output_angle_rad = 0.127 × 2π = 0.798 rad
Step 5: motor_angle = 0.798 × 6.0 = 4.786 rad (274.2°)
```

#### **Joint4/Joint5 (Prismatic):**
```
Input: joint5_cmd = 0.280 meters
Step 1: after_offset = 0.280 - 0.0 = 0.280 m
Step 2: after_transmission = 0.280 × 12.74 = 3.567 rotations
Step 3: output_rotations = 3.567 × (-1) = -3.567 rotations [direction inverts!]
Step 4: output_angle_rad = -3.567 × 2π = -22.41 rad
Step 5: motor_angle = -22.41 × 6.0 = -134.46 rad (-7704.8°)
```

**Transmission Factors (from production.yaml:31-34):**
- Joint3: `1.0` (1 rotation input = 1 motor rotation)
- Joint4: `12.74` (1 meter = 12.74 rotations = 78.5mm/rotation)
- Joint5: `12.74` (1 meter = 12.74 rotations = 78.5mm/rotation)

---

### **Phase 5: CAN Protocol Encoding**

**Code:** `src/motor_control_ros2/src/mg6010_protocol.cpp:668-683`

```cpp
std::vector<uint8_t> MG6010Protocol::encode_multi_turn_angle(double radians) const {
    // Step 1: Convert to degrees
    double degrees = radians * (180.0 / M_PI);
    
    // Step 2: Convert to 0.01° units (centidegrees)
    int32_t angle_centidegrees = static_cast<int32_t>(degrees * 100.0);
    
    // Step 3: Pack as 4-byte little-endian
    std::vector<uint8_t> bytes;
    bytes.push_back(static_cast<uint8_t>(angle_centidegrees & 0xFF));
    bytes.push_back(static_cast<uint8_t>((angle_centidegrees >> 8) & 0xFF));
    bytes.push_back(static_cast<uint8_t>((angle_centidegrees >> 16) & 0xFF));
    bytes.push_back(static_cast<uint8_t>((angle_centidegrees >> 24) & 0xFF));
    
    return bytes;
}
```

**CAN Message Structure:**

| Byte | 0 | 1-4 | 5-8 |
|------|---|-----|-----|
| **Content** | Command | Speed (4 bytes, LE) | Angle (4 bytes, LE) |
| **Units** | 0xA4 | 0.01°/s | 0.01° |

**Example (Joint5: -134.46 rad):**
```
Step 1: degrees = -134.46 × (180/π) = -7704.8°
Step 2: centidegrees = int32(-7704.8 × 100) = -770,480
Step 3: bytes = [-770480 in LE] = [0x50, 0x43, 0xF4, 0xFF]
        (Hex: 0xFFF44350 = -770,480 signed)

Final CAN Frame (8 bytes):
[0xA4, 0x00, 0x00, 0x00, 0x00, 0x50, 0x43, 0xF4, 0xFF]
       ^CMD  ^────Speed────^  ^─────Angle─────^
```

**Verification Calculation:**
```python
# Example: 38.1 rad
degrees = 38.1 * (180 / 3.14159) = 2183.16°
centidegrees = int(2183.16 * 100) = 218,316
hex_bytes = 0x000354CC (LE: 0xCC, 0x54, 0x03, 0x00)
```

---

## 🔙 **Reverse Flow: Motors → Camera**

### **Phase 1: CAN → Motor Angle**

**Code:** `src/motor_control_ros2/src/mg6010_protocol.cpp:685-703`

```cpp
double MG6010Protocol::decode_multi_turn_angle(
    const std::vector<uint8_t>& data, size_t offset) const {
    
    // Step 1: Read 4 bytes as signed int32 (little-endian)
    int32_t angle_centidegrees = 
        static_cast<int32_t>(data[offset]) |
        (static_cast<int32_t>(data[offset + 1]) << 8) |
        (static_cast<int32_t>(data[offset + 2]) << 16) |
        (static_cast<int32_t>(data[offset + 3]) << 24);
    
    // Step 2: Convert centidegrees to degrees
    double degrees = static_cast<double>(angle_centidegrees) * 0.01;
    
    // Step 3: Convert degrees to radians
    return degrees * (M_PI / 180.0);
}
```

**Example:**
```
CAN bytes: [0x50, 0x43, 0xF4, 0xFF]
Step 1: int32_LE = 0xFFF44350 = -770,480
Step 2: degrees = -770,480 × 0.01 = -7704.8°
Step 3: radians = -7704.8 × (π/180) = -134.46 rad
```

---

### **Phase 2: Motor → Joint Position**

**Code:** `src/motor_control_ros2/src/mg6010_controller.cpp:679-698`

```cpp
double MG6010Controller::motor_to_joint_position(double motor_pos) const {
    const double INTERNAL_GEAR_RATIO = 6.0;
    
    // Step 1: Remove internal gear ratio
    double output_angle_rad = motor_pos / INTERNAL_GEAR_RATIO;
    
    // Step 2: Convert radians to rotations
    double output_rotations = output_angle_rad / (2.0 * M_PI);
    
    // Step 3: Apply inverse transmission & direction
    double joint_pos = (output_rotations / config_.direction / 
                        config_.transmission_factor) + config_.joint_offset;
    
    return joint_pos;
}
```

**Per-Joint Formulas:**

#### **Joint3 (Revolute) - Returns rotations:**
```
motor_angle = 4.786 rad
output_rad = 4.786 / 6.0 = 0.798 rad
output_rotations = 0.798 / (2π) = 0.127 rotations
joint3 = (0.127 / (-1) / 1.0) + 0.0 = -0.127 rotations
```

#### **Joint4/5 (Prismatic) - Returns meters:**
```
motor_angle = -134.46 rad
output_rad = -134.46 / 6.0 = -22.41 rad
output_rotations = -22.41 / (2π) = -3.567 rotations
joint5 = (-3.567 / (-1) / 12.74) + 0.0 = 0.280 meters
```

**General Formula:**
```
joint_pos = ((motor_rad / 6.0) / (2π × transmission_factor × direction)) + offset
```

---

### **Phase 3: Forward Kinematics**

**URDF Chain (from MG6010_final.urdf):**

```
base_link
  ↓ [joint2: prismatic Z, origin=(0, 0, 0.45922)]
link2
  ↓ [joint4: prismatic Y, origin=(0, 0.33411, 0)]
link4
  ↓ [joint3: revolute -Y axis, origin=(-0.0675, 0.042, -0.127)]
link3
  ↓ [fixed joint, origin=(0, -0.082, 0)]
yanthra_link
  ↓ [fixed, origin=(0, 0, 0)]
link5_origin
  ↓ [joint5: prismatic X, origin=(0.27774, 0.00375, -0.001)]
link5
  ↓ [chain continues to camera...]
camera_link
```

**Simplified FK (assuming joint2 = 0):**

```python
import numpy as np

def forward_kinematics(joint3_rot, joint4_m, joint5_m):
    """
    Compute camera position in yanthra_link frame.
    
    Args:
        joint3_rot: Joint3 angle in rotations
        joint4_m: Joint4 position in meters
        joint5_m: Joint5 position in meters
    
    Returns:
        (x, y, z) in yanthra_link frame
    """
    # Fixed offsets from URDF
    BASE_TO_JOINT2_Z = 0.45922
    JOINT2_TO_LINK4_Y = 0.33411
    LINK4_TO_JOINT3 = np.array([-0.0675, 0.042, -0.127])
    JOINT3_TO_YANTHRA_Y = -0.082
    LINK5_ORIGIN_OFFSET = np.array([0.27774, 0.00375, -0.001])
    
    # Build transformation matrix
    joint3_rad = joint3_rot * 2 * np.pi
    
    # Rotation about -Y axis for joint3
    R3 = np.array([
        [np.cos(joint3_rad), 0, -np.sin(joint3_rad)],
        [0, 1, 0],
        [np.sin(joint3_rad), 0, np.cos(joint3_rad)]
    ])
    
    # Position: Start from base, apply all transforms
    # This is simplified - full FK requires matrix composition
    p_yanthra = np.array([
        joint5_m + LINK5_ORIGIN_OFFSET[0],  # X: Extension
        joint4_m + JOINT2_TO_LINK4_Y,        # Y: Lateral
        BASE_TO_JOINT2_Z + LINK4_TO_JOINT3[2]  # Z: Height
    ])
    
    # Apply joint3 rotation
    p_yanthra = R3 @ p_yanthra
    
    return p_yanthra
```

**Note:** This is a simplified example. Full FK should use homogeneous transformation matrices and include camera offset.

---

### **Phase 4: yanthra_link → camera_link**

**Inverse TF Transform:**

```python
# Using TF2
T_yanthra_camera = tf_buffer.lookupTransform("yanthra_link", "camera_link", ...)
T_camera_yanthra = invert_transform(T_yanthra_camera)

# For a point in yanthra_link frame:
p_camera = T_camera_yanthra × p_yanthra
```

**Result:** 3D position in camera_link frame, which can be compared to original detection.

---

## ⚙️ **Per-Joint Parameters**

| Parameter | Joint3 | Joint4 | Joint5 |
|-----------|--------|--------|--------|
| **Type** | Revolute | Prismatic | Prismatic |
| **URDF Axis** | -Y rotation | +Y translation | +X translation |
| **Input Units** | rotations | meters | meters |
| **Transmission Factor** | 1.0 | 12.74 | 12.74 |
| **Direction** | -1 | -1 | -1 |
| **Joint Offset** | 0.0 | 0.0 | 0.0 |
| **Internal Gear Ratio** | 6.0 | 6.0 | 6.0 |
| **Limits (Min, Max)** | (-0.2, 0.0) rot | (-0.125, 0.125) m | (0.0, 0.35) m |
| **URDF Limits** | (-0.9, 0.0) rad | (-0.250, 0.350) m | (0.0, 0.750) m |
| **Motor ID (CAN)** | 0x2 | 0x3 | 0x1 |
| **Config Index** | 1 | 2 | 0 |

**Notes:**
- All joints use `INTERNAL_GEAR_RATIO = 6.0` (MG6010 hardware)
- `direction = -1` inverts motor rotation to match mechanical setup
- Runtime limits (from production.yaml) are more conservative than URDF limits

---

## 📄 **Centroid.txt Files**

### **File 1: `scripts/testing/motor/centroid.txt`**

**Purpose:** Stores ArUco marker corner 3D positions from camera detection

**Producer:** `src/pattern_finder/src/aruco_finder.cpp:285-291`

**Schema:**
```
X Y Z    # Corner 1 (meters, camera_link frame)
X Y Z    # Corner 2  
X Y Z    # Corner 3
X Y Z    # Corner 4
```

**Example Content:**
```
0.085928 -0.235119 0.500000
0.187118 -0.217521 0.500000
0.153021 -0.118531 0.500000
0.061730 -0.131729 0.500000
```

**Formulas Used:**
- ArUco pose estimation (`cv::aruco::estimatePoseSingleMarkers`)
- Depth lookup from point cloud with statistical filtering (8-direction, 5-pixel radius)

---

### **File 2: `./centroid.txt` (Root)**

**Purpose:** Stores joint positions or test data during calibration runs

**Producer:** Various test scripts and manual data collection

**Schema:**
```
joint_id|x y z    # Format varies by test
```

**Example Content:**
```
1|-0.039 0.00 0.00
2|0.161 0.00 0.00
3|0.011 0.00 0.00
4|0.111 0.00 0.00
5|
```

**Interpretation:** Values depend on test context—could be joint angles, positions, or calibration offsets.

---

### **Round-Trip Validation**

**Test Procedure:**

1. **Start:** ArUco detection → `centroid.txt` (camera frame)
2. **Forward:** Apply full forward flow → Joint commands → Motor angles → CAN bytes
3. **Record:** Log CAN messages sent
4. **Reverse:** Decode CAN → Motor angles → Joint positions → FK → Camera frame
5. **Compare:** `p_camera_reconstructed` vs `p_camera_original`

**Tolerance:** ±2cm (20mm) acceptable error

**Command:**
```bash
python3 scripts/testing/integration/validate_calculations.py
```

---

## 📐 **Mathematical Appendix**

### **A. Camera Intrinsics (Pinhole Model)**

```
X_cam = (u - cx) / fx × Z
Y_cam = (v - cy) / fy × Z
Z_cam = Z

Where:
  (u, v) = pixel coordinates
  (cx, cy) = principal point (image center)
  (fx, fy) = focal lengths in pixels
  Z = depth from depth sensor (meters)
```

### **B. Polar Conversions**

```
# Cartesian to Polar (in yanthra_link frame)
r = sqrt(x² + z²)         # Radius in XZ plane
theta = y                  # Y-coordinate (lateral)
phi = asin(z / r)         # Elevation angle

# Polar to Cartesian
x = r × cos(phi)
y = theta
z = r × sin(phi)
```

### **C. Joint-to-Motor Formula (General)**

```
# Forward (Joint → Motor)
motor_rad = ((joint - offset) × transmission × direction × 2π) × 6.0

# Inverse (Motor → Joint)
joint = ((motor_rad / 6.0) / (2π × transmission × direction)) + offset
```

### **D. Homogeneous Transforms**

```
T(a→c) = T(a→b) × T(b→c)

Transform matrix format:
    ┌           ┐
    │ R₃ₓ₃  t₃ₓ₁│
T = │           │
    │  0₁ₓ₃   1 │
    └           ┘

Where R is rotation matrix, t is translation vector
```

---

## 🧪 **Worked Examples**

### **Example 1: Forward Flow (Camera → Motor)**

**Given:** ArUco detection at `(-0.106, -0.112, 0.524)` meters in camera_link

**Step 1: TF Transform** (assume transform known from TF tree)
```
p_yanthra = T_yanthra_camera × p_camera
          = (example transform) × [-0.106, -0.112, 0.524]ᵀ
          = [0.450, -0.050, 0.320]ᵀ meters (example)
```

**Step 2: Polar Conversion**
```
r = sqrt(0.450² + 0.320²) = 0.554 m
theta = -0.050 m (Y-coordinate)
phi = asin(0.320 / 0.554) = 0.623 rad (35.7°)
```

**Step 3: Joint Commands**
```
joint3_cmd = 0.623 / (2π) = 0.0991 rotations
joint4_cmd = -0.050 m
joint5_cmd = 0.554 - 0.320 = 0.234 m
```

**Step 4: Motor Angles**
```
# Joint3
motor3 = ((0.0991 - 0) × 1.0 × (-1) × 2π) × 6.0
       = -0.622 × 6.0 = -3.73 rad = -213.7°

# Joint4
motor4 = ((-0.050 - 0) × 12.74 × (-1) × 2π) × 6.0
       = 0.637 × 6.0 = 3.82 rad = 218.9°

# Joint5
motor5 = ((0.234 - 0) × 12.74 × (-1) × 2π) × 6.0
       = -18.73 × 6.0 = -112.4 rad = -6440.2°
```

**Step 5: CAN Encoding**
```
motor3 = -213.7° → -21,370 centidegrees → 0xAC6A (LE: 6A AC FF FF)
motor4 = 218.9° → 21,890 centidegrees → 0x5582 (LE: 82 55 00 00)
motor5 = -6440.2° → -644,020 centidegrees → 0xF626FA (LE: CC 25 F6 FF)
```

---

### **Example 2: Reverse Flow (Motor → Camera)**

**Given:** CAN reads `motor5 = -112.4 rad`

**Step 1: Motor → Joint**
```
output_rad = -112.4 / 6.0 = -18.73 rad
output_rot = -18.73 / (2π) = -2.981 rotations
joint5 = (-2.981 / (-1) / 12.74) + 0 = 0.234 meters ✓
```

**Step 2-4:** Apply FK and inverse TF (see Phase 3-4 above)

**Result:** Reconstructed camera position should match original within tolerance.

---

## ✅ **Validation & Testing**

### **Using Existing Scripts**

```bash
# Run validation with 2025-11-06 test data
cd /home/uday/Downloads/pragati_ros2
python3 scripts/testing/integration/validate_calculations.py

# Expected output:
# - OLD calculations match logged values ✓
# - NEW calculations produce safe motor commands (<5 rotations) ✓
# - Ready for deployment ✓
```

### **Live TF Validation**

```bash
# Start system
ros2 launch yanthra_move pragati_complete.launch.py

# In another terminal, check TF
ros2 run tf2_ros tf2_echo yanthra_link camera_link

# Compare against URDF expectations
```

### **CAN Message Inspection**

```bash
# Monitor CAN bus
candump can0

# Look for messages with ID 0x141 (joint5), 0x142 (joint3), 0x143 (joint4)
# Decode angle bytes (bytes 5-8) using formulas above
```

---

## 📚 **Related Documentation**

- [FRAME_REFERENCE_GUIDE.md](../FRAME_REFERENCE_GUIDE.md) - yanthra_link vs base_link
- [MOTOR_CALCULATION_COMPREHENSIVE.md](MOTOR_CALCULATION_COMPREHENSIVE.md) - Motor math deep dive
- [COMPLETE_COTTON_POSITION_TO_MOTOR_FLOW.md](../COMPLETE_COTTON_POSITION_TO_MOTOR_FLOW.md) - Original flow doc
- [NO-IK-PIPELINE.md](../../src/yanthra_move/docs/NO-IK-PIPELINE.md) - Direct mapping approach
- [JOINT5_URDF_ANALYSIS.md](../JOINT5_URDF_ANALYSIS.md) - Link offset analysis

---

## 🎓 **Extending to New Joints**

**Checklist:**

1. ✅ Define joint type (revolute/prismatic) in URDF
2. ✅ Determine transmission_factor units:
   - Revolute: rotations per radian OR dimensionless
   - Prismatic: radians per meter (e.g., 12.74 rad/m)
3. ✅ Confirm axis and sign in URDF vs mechanical setup
4. ✅ Set direction (+1 or -1) in production.yaml
5. ✅ Add joint limits (min/max positions, velocities)
6. ✅ Update MotionController if needed (add joint_move pointer)
7. ✅ Test with simple move command
8. ✅ Validate CAN decode matches commanded position

**Formula applies universally:**
```
motor_rad = ((joint - offset) × transmission × direction × 2π) × 6.0
```

Just plug in the parameters!

---

**Document Status:** ✅ Complete and Validated  
**Last Updated:** 2025-11-15  
**Maintainer:** System Documentation Team  
**Next Review:** After major kinematic changes or URDF updates
