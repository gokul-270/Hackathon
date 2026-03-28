# Complete Motor Movement Calculation Flow

> **⚠️ SUPERSEDED:** This document has been consolidated into [docs/guides/MOTOR_CALCULATION_COMPREHENSIVE.md](docs/guides/MOTOR_CALCULATION_COMPREHENSIVE.md)  
> **Date:** 2025-10-28  
> **Action:** Use the comprehensive guide for all motor calculation references  
> **Index:** See [MOTOR_DOCS_INDEX.md](MOTOR_DOCS_INDEX.md) for complete motor documentation

## 🎯 Your Question: How is motor movement calculated?

You're seeing vigorous/unexpected movements. Let me trace through EXACTLY what happens with real numbers.

---

## 📊 Example: Move Joint4 to 0.5 meters (prismatic joint)

### Given Configuration (from mg6010_three_motors.yaml):
```yaml
joint4:
  transmission_factor: 12.7  # radians (NOT gear ratio!)
  direction: 1
  joint_offset: 0.0
```

---

## 🔢 Step-by-Step Calculation

### Step 1: Command from yanthra_move
```cpp
// User/system wants to move joint4 to 0.5 meters linear position
double desired_position = 0.5;  // meters (for prismatic joint)
```

### Step 2: Convert to "joint space" (still in meters for prismatic)
```cpp
// In yanthra_move or motion controller
joint_move::move_joint(0.5, wait=false);
```

### Step 3: Publish to ROS topic
```cpp
// joint_move.cpp:117-119
std_msgs::msg::Float64 cmd_msg;
cmd_msg.data = 0.5;  // Still in meters!
publisher->publish(cmd_msg);  // Topic: /joint4_position_controller/command
```

### Step 4: MG6010 Controller receives command
```cpp
// mg6010_integrated_test_node.cpp:304-321
void position_command_callback(size_t motor_idx, msg) {
    double position = msg->data;  // position = 0.5 meters
    
    // Send to motor controller
    controllers_[motor_idx]->set_position(position, 0.0, 0.0);
}
```

### Step 5: Controller converts joint → motor space
```cpp
// mg6010_controller.cpp:248-273
bool MG6010Controller::set_position(double position, ...) {
    // position = 0.5 meters (joint space)
    
    // Convert to motor space
    double motor_position = joint_to_motor_position(position);
    
    // Send to protocol
    protocol_->set_absolute_position(motor_position);
}
```

### Step 6: **CRITICAL** - Joint to Motor Conversion
```cpp
// mg6010_controller.cpp:635-638
double MG6010Controller::joint_to_motor_position(double joint_pos) const {
    // Formula: motor_pos = (joint_pos - offset) * transmission_factor * direction
    
    // For joint4:
    // joint_pos = 0.5 meters
    // offset = 0.0
    // transmission_factor = 12.7  ← YOUR VALUE!
    // direction = 1
    
    motor_pos = (0.5 - 0.0) * 12.7 * 1;
    motor_pos = 6.35 radians;  ← MOTOR ANGLE IN RADIANS
}
```

**⚠️ KEY INSIGHT:** 
- Input: 0.5 meters (linear)
- Output: 6.35 radians (rotational)
- **Transmission factor 12.7 = radians per meter**
- This means: 1 meter of linear travel = 12.7 radians of motor rotation

### Step 7: Protocol encodes motor angle
```cpp
// mg6010_protocol.cpp:666-680
std::vector<uint8_t> encode_multi_turn_angle(double radians) {
    // radians = 6.35
    
    // Convert to degrees
    double degrees = 6.35 * (180.0 / π);
    degrees = 363.86°;  // More than 1 full rotation!
    
    // Convert to 0.01 degree units (protocol format)
    int32_t angle_0_01deg = static_cast<int32_t>(363.86 * 100.0);
    angle_0_01deg = 36386;  // ← Value sent to motor
    
    // Pack as 4 bytes little-endian
    bytes = [0x32, 0x8E, 0x00, 0x00];  // 36386 in hex
}
```

### Step 8: CAN message sent to motor
```
CAN ID: 0x2 (joint4)
Command: 0xA4 (CMD_MULTI_LOOP_ANGLE_1)
Data: [0x00, 0x00, 0x00, 0x32, 0x8E, 0x00, 0x00]
                     ^^^^^^^^^^^^^^^^^^^^^^^^
                     36386 = 363.86° in 0.01° units
```

### Step 9: Motor moves
```
Motor receives: 363.86° (absolute position)
Motor rotates: ~1.01 full rotations
```

---

## 🔍 Why Vigorous Movements During Homing?

### OLD Configuration (WRONG):
```yaml
transmission_factors: [6.0, 480.1, 480.1]  ← TOO HIGH!
homing_positions: [4200.0, 18000.0, 12000.0]  ← ALREADY MULTIPLIED!
```

### Homing Calculation (OLD):
```
Step 1: homing_position = 18000.0° from YAML
Step 2: Convert to radians = 18000 * π/180 = 314.16 rad
Step 3: Apply transmission_factor = 314.16 * 480.1 = 150,826 rad
Step 4: Convert to degrees = 150,826 * 180/π = 8,640,000°
Step 5: Send to motor = 864,000,000 (in 0.01° units)
Step 6: Motor tries to rotate 8,640,000° = 24,000 rotations! 💥
```

### NEW Configuration (FIXED):
```yaml
transmission_factors: [6.0, 12.7, 12.7]  ← CORRECT!
homing_positions: [180.0, 360.0, 360.0]  ← OUTPUT ANGLES!
```

### Homing Calculation (NEW):
```
Step 1: homing_position = 360.0° from YAML
Step 2: Convert to radians = 360 * π/180 = 6.283 rad
Step 3: Apply transmission_factor = 6.283 * 12.7 = 79.79 rad
Step 4: Convert to degrees = 79.79 * 180/π = 4572°
Step 5: Send to motor = 457,200 (in 0.01° units)
Step 6: Motor rotates 4572° = 12.7 rotations ✅
```

---

## 📐 What Does Transmission Factor 12.7 Mean?

For **prismatic (linear) joints**:

```
transmission_factor = radians_of_rotation / meters_of_linear_travel

12.7 rad/meter means:
- To move 1 meter linearly, motor rotates 12.7 radians
- 12.7 radians = 727.5° = ~2.02 full rotations per meter
```

### Example Calculations:

| Linear Movement | Motor Rotation (rad) | Motor Rotation (degrees) | Full Rotations |
|-----------------|---------------------|--------------------------|----------------|
| 0.1 m (10 cm)   | 0.1 × 12.7 = 1.27   | 72.75°                   | 0.2            |
| 0.5 m (50 cm)   | 0.5 × 12.7 = 6.35   | 363.86°                  | 1.01           |
| 1.0 m (100 cm)  | 1.0 × 12.7 = 12.7   | 727.5°                   | 2.02           |

---

## 🎯 Why Your OLD Config Was Wrong

### Problem 1: Wrong Transmission Factor (480.1)
```
Old: transmission_factor = 480.1 rad/meter

To move 0.1 meter:
motor_angle = 0.1 * 480.1 = 48.01 rad = 2751° = 7.64 rotations!

Just 10cm movement caused motor to spin 7.6 times! 💥
```

### Problem 2: Double Compensation
```
YAML already had: homing_position = 18000° (pre-multiplied by 6)
Controller multiplied AGAIN: 18000° * 480.1 = 8,640,000°

Result: 24,000 rotations instead of 50! 💥💥
```

---

## ✅ Correct Flow Summary

### For Prismatic Joints (Joint4, Joint5):

```
User Command:   0.5 meters (linear position)
       ↓
Joint Space:    0.5 (same, meters)
       ↓
× transmission_factor (12.7)
       ↓
Motor Space:    6.35 radians
       ↓
Convert to degrees × 100 (protocol)
       ↓
CAN Message:    36386 (in 0.01° units)
       ↓
Motor Moves:    363.86° = 1.01 rotations ✅
```

### For Rotational Joint (Joint3):

```
User Command:   180° (rotational position)
       ↓
Convert to rad: 3.14 radians
       ↓
Joint Space:    3.14 rad
       ↓
× transmission_factor (6.0)
       ↓
Motor Space:    18.85 radians
       ↓
Convert to degrees × 100
       ↓
CAN Message:    107956 (in 0.01° units)
       ↓
Motor Moves:    1079.56° = 3 rotations ✅
```

---

## 🛠️ The Fix Applied

1. **Removed double compensation:**
   - OLD: YAML had 4200° (already ×6), then controller ×6 again = ×36 total
   - NEW: YAML has 180° (output), then controller ×6 once = ×6 total ✅

2. **Correct transmission factors:**
   - OLD: 480.1 rad/meter (way too high)
   - NEW: 12.7 rad/meter (correct for your mechanism) ✅

3. **Reasonable homing positions:**
   - OLD: 18000° = 50 rotations
   - NEW: 360° = 1 rotation (after ×12.7 = 12.7 rotations) ✅

---

## 🔬 How to Verify

After applying the fix, check the logs:

```bash
# You should see:
[mg6010_controller]: transmission_factor=12.700 (not 480.1)
[mg6010_controller]: Moving to arm homing position: 360.0° (not 18000°)
[mg6010_controller]: Final position: 79.79 rad (4572°)
```

**Expected motor movement:**
- Smooth, controlled rotation
- ~12.7 rotations for joint4/5 homing
- ~3 rotations for joint3 homing
- NO vigorous/erratic motion

---

## 📚 Key Takeaways

1. **Transmission factor is NOT gear ratio** - it's a conversion coefficient
   - For rotational: relates joint angle to motor angle
   - For linear: rad/meter (or rad/mm depending on your convention)

2. **Units matter!**
   - Protocol expects: 0.01 degrees (int32)
   - Controller works in: radians (double)
   - User commands in: meters for prismatic, radians/degrees for rotational

3. **One conversion point!**
   - Apply transmission_factor ONCE (in controller)
   - YAML should have OUTPUT values, not pre-multiplied values

4. **Transmission factor 12.7 for your prismatic joints means:**
   - 12.7 radians of motor rotation = 1 meter of linear travel
   - This is determined by your mechanical design (pulley diameter, belt pitch, etc.)
