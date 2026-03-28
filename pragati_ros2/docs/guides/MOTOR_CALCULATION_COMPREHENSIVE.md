# Motor Movement Calculation - Comprehensive Guide

**Purpose:** Complete reference for understanding how motor movements are calculated in the Pragati system  
**Audience:** Developers, hardware engineers, troubleshooters  
**Last Updated:** 2025-10-28

> **Note:** This guide consolidates and supersedes MOTOR_CALCULATION_FLOW.md and FINAL_MOTOR_FLOW_CORRECTED.md

---

## 🎯 Quick Answer: How Motor Movement Works

```
User Command (meters/degrees) 
    → Transmission Factor Application 
    → Gear Ratio Multiplication (6:1 internal) 
    → CAN Protocol Encoding (degrees) 
    → Motor Movement
```

---

## 📊 Complete Calculation Flow

### Example: Move Joint4 to 0.5 meters (Prismatic Joint)

#### Configuration (from mg6010_three_motors.yaml):
```yaml
joint4:
  transmission_factor: 12.7  # radians per meter (NOT gear ratio!)
  direction: 1
  joint_offset: 0.0
  internal_gear_ratio: 6.0  # MG6010 internal gearing
```

---

### Step-by-Step Calculation

#### Step 1: User Command
```cpp
// User/system wants to move joint4 to 0.5 meters
double desired_position = 0.5;  // meters (for prismatic joint)
```

#### Step 2: Publish to ROS Topic
```cpp
// joint_move.cpp:117-119
std_msgs::msg::Float64 cmd_msg;
cmd_msg.data = 0.5;  // Still in meters
publisher->publish(cmd_msg);  // Topic: /joint4_position_controller/command
```

#### Step 3: Controller Receives Command
```cpp
// mg6010_controller_node.cpp:304-321
void position_command_callback(size_t motor_idx, msg) {
    double position = msg->data;  // position = 0.5 meters
    controllers_[motor_idx]->set_position(position, 0.0, 0.0);
}
```

#### Step 4: Apply Transmission Factor
```cpp
// mg6010_controller.cpp:635-645
double MG6010Controller::joint_to_motor_position(double joint_pos) const {
    const double INTERNAL_GEAR_RATIO = 6.0;
    
    // Step 1: Apply transmission_factor (converts meters → radians)
    double output_angle = (joint_pos - offset) * transmission_factor * direction;
    // output_angle = (0.5 - 0.0) * 12.7 * 1 = 6.35 radians
    
    // Step 2: Apply 6:1 internal gear ratio
    double motor_angle = output_angle * INTERNAL_GEAR_RATIO;
    // motor_angle = 6.35 * 6.0 = 38.1 radians
    
    return motor_angle;
}
```

**⚠️ KEY INSIGHT:**
- Input: 0.5 meters (linear)
- After transmission: 6.35 radians (output shaft rotation)
- After gear ratio: 38.1 radians (motor shaft rotation)
- **Transmission factor 12.7 = radians per meter** (NOT the gear ratio!)

#### Step 5: Protocol Encoding
```cpp
// mg6010_protocol.cpp:666-679
std::vector<uint8_t> encode_multi_turn_angle(double radians) {
    // radians = 38.1
    
    // Convert to degrees (DIRECT, no 0.01° encoding)
    double degrees = radians * (180.0 / π);
    // degrees = 38.1 * 57.2958 = 2183.16°
    
    // Convert to int32 (direct degrees)
    int32_t angle_degrees = static_cast<int32_t>(degrees);
    // angle_degrees = 2183
    
    // Pack as 4 bytes little-endian
    bytes = [0x87, 0x08, 0x00, 0x00];  // 2183 in hex
}
```

#### Step 6: CAN Message Sent
```
CAN ID: 0x2 (joint4)
Command: 0xA4 (CMD_MULTI_LOOP_ANGLE_1)
Data: [0x00, 0x00, 0x00, 0x87, 0x08, 0x00, 0x00]
                     ^^^^^^^^^^^^^^^^^^^^
                     2183 degrees
```

#### Step 7: Motor Moves
```
Motor receives: 2183° (absolute position)
Motor rotates: 2183 ÷ 360 = 6.06 full rotations
Output shaft: 6.06 ÷ 6 = 1.01 rotations
Linear travel: 1.01 rotations = ~0.5 meters ✅
```

---

## 🔢 Calculation Summary Table

| Stage | Value | Unit | Calculation |
|-------|-------|------|-------------|
| **User Command** | 0.5 | meters | Input |
| **After Transmission** | 6.35 | radians | 0.5 × 12.7 |
| **Convert to Degrees** | 363.86 | degrees | 6.35 × 57.2958 |
| **After Gear Ratio** | 38.1 | radians | 6.35 × 6.0 |
| **Motor Degrees** | 2183 | degrees | 38.1 × 57.2958 |
| **Output Rotations** | 1.01 | rotations | 363.86 ÷ 360 |
| **Motor Rotations** | 6.06 | rotations | 2183 ÷ 360 |
| **Final Position** | ~0.5 | meters | ✅ Correct |

---

## 🔧 The Fix That Was Applied

### Problem 1: Double Gear Compensation (OLD)
```yaml
# OLD Configuration (WRONG)
transmission_factors: [6.0, 480.1, 480.1]  # Way too high!
homing_positions: [4200.0, 18000.0, 12000.0]  # Pre-multiplied!

# Result:
# homing_position = 18000° × 480.1 = 8,640,000° 
# = 24,000 rotations! 💥 VIGOROUS MOVEMENT
```

### Problem 2: Wrong Transmission Factors
```yaml
# OLD: 480.1 rad/meter
# To move 0.1 meter: 0.1 * 480.1 = 48.01 rad = 2751° = 7.64 rotations!
# Just 10cm caused 7.6 rotations! 💥
```

### Solution (NEW - CORRECT)
```yaml
# NEW Configuration
transmission_factors: [6.0, 12.7, 12.7]  # Correct!
homing_positions: [180.0, 360.0, 360.0]  # Output angles!

# Result:
# homing_position = 360° × 6.0 (gear) × 12.7 (transmission) = 4572°
# = 12.7 rotations ✅ SMOOTH, CONTROLLED
```

---

## 📐 Understanding Transmission Factors

### For Prismatic (Linear) Joints (Joint4, Joint5)

```
transmission_factor = radians_of_rotation / meters_of_linear_travel

12.7 rad/meter means:
- To move 1 meter linearly, output shaft rotates 12.7 radians
- 12.7 radians = 727.5° = ~2.02 full rotations per meter
```

**Example Calculations:**

| Linear Movement | Output Rotation (rad) | Output Rotation (°) | Output Rotations |
|-----------------|----------------------|---------------------|------------------|
| 0.1 m (10 cm)   | 0.1 × 12.7 = 1.27    | 72.75°              | 0.2              |
| 0.5 m (50 cm)   | 0.5 × 12.7 = 6.35    | 363.86°             | 1.01             |
| 1.0 m (100 cm)  | 1.0 × 12.7 = 12.7    | 727.5°              | 2.02             |

### For Rotational Joint (Joint3)

```
transmission_factor = 6.0 (gear ratio for rotation)

6.0 means:
- 1 rotation of output = 6 rotations of motor
- This is the internal gear ratio
```

**Example:**

| Output Angle | Motor Rotations | Motor Angle |
|--------------|-----------------|-------------|
| 180° (π rad) | 6 × 0.5 = 3     | 1080°       |
| 360° (2π rad)| 6 × 1.0 = 6     | 2160°       |

---

## 🎯 Key Concepts

### 1. Transmission Factor ≠ Gear Ratio
- **Transmission Factor:** Conversion coefficient (units: rad/meter for linear, dimensionless for rotary)
- **Gear Ratio:** Physical gearing (6:1 internal to MG6010 motors)
- **Apply BOTH:** transmission_factor first, then gear_ratio

### 2. Protocol Encoding (CORRECTED)
- **OLD (WRONG):** Multiplied by 100 (0.01° units)
- **NEW (CORRECT):** Direct degrees (1° units)
- No need for extra scaling

### 3. One Conversion Point
- Apply transmission_factor ONCE (in controller)
- Apply gear_ratio ONCE (in controller)
- YAML should have OUTPUT values, not pre-multiplied

### 4. Units Flow
```
User: meters/radians 
  → Controller: radians (output shaft)
  → Controller: radians (motor shaft, after gear)
  → Protocol: degrees (integer)
  → Motor: absolute position in degrees
```

---

## 🔍 Verification and Debugging

### Expected Log Messages
After the fix, you should see:

```bash
✅ CORRECT:
[mg6010_controller]: transmission_factor=12.700 (not 480.1)
[mg6010_controller]: Moving to homing position: 360.0° (not 18000°)
[mg6010_controller]: Motor angle: 38.10 rad (2183°)
[mg6010_protocol]: Sending position: 2183 (degrees)
```

```bash
❌ OLD (WRONG):
[mg6010_protocol]: Sending position: 218316 (0.01° units)
[mg6010_controller]: Moving to homing position: 18000°
```

### Check Configuration
```bash
# Verify your config file
cat src/motor_control_ros2/config/mg6010_three_motors.yaml

# Should show:
transmission_factors: [6.0, 12.7, 12.7]
homing_positions: [180.0, 360.0, 360.0]
```

### Test Movement
```bash
# Rebuild
colcon build --packages-select motor_control_ros2 --symlink-install
source install/setup.bash

# Launch and observe
ros2 launch yanthra_move pragati_complete.launch.py

# Expected: Smooth, controlled homing movements
# NOT: Vigorous, erratic movements
```

---

## 📊 Motor Movement Comparison (Before vs After)

| Joint | OLD Movement | NEW Movement | Improvement |
|-------|--------------|--------------|-------------|
| **joint3** | 70 rotations | 3 rotations | **23× less!** |
| **joint4** | 172,800° | 4572° | **38× less!** |
| **joint5** | 115,200° | 4572° | **25× less!** |

---

## 🛠️ Troubleshooting

### Motors Move Too Much
**Symptom:** Vigorous, erratic movements during homing

**Causes:**
1. Transmission factor too high (e.g., 480.1 instead of 12.7)
2. Homing positions pre-multiplied (e.g., 18000° instead of 360°)
3. Double gear compensation applied

**Solution:** Update config to correct values and rebuild

### Motors Don't Move Enough
**Symptom:** Motors barely move or don't reach target

**Causes:**
1. Transmission factor too low
2. Missing gear ratio multiplication
3. Direction parameter incorrect

**Solution:** Verify transmission factors match mechanical design

### Motors Move in Wrong Direction
**Symptom:** Motors move opposite to expected

**Solution:** Toggle `direction` parameter between 1 and -1

---

## 📚 Related Documentation

- **Motor Test Guide:** `MOTOR_CONTROLLER_TEST_GUIDE.md`
- **Motor Debug Guide:** `MOTOR_DEBUG.md`
- **Motor Initialization:** `MOTOR_INITIALIZATION_EXPLAINED.md`
- **Quick Reference:** `MOTOR_TEST_QUICK_REF.md`
- **Transmission Fix:** `TRANSMISSION_FACTOR_FIX.md`

---

## ✅ Success Criteria

After applying corrections:
- ✅ Smooth homing movements
- ✅ Correct position reached (±1% tolerance)
- ✅ No vigorous/erratic motion
- ✅ Log messages show reasonable angles (180°-4572°, not 8,640,000°)
- ✅ Motors respond predictably to commands

---

**Document Status:** ✅ Consolidated and Complete  
**Replaces:** MOTOR_CALCULATION_FLOW.md, FINAL_MOTOR_FLOW_CORRECTED.md  
**Created:** 2025-10-28  
**Last Updated:** 2025-10-28
