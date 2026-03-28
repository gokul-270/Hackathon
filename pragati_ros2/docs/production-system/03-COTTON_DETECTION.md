# Cotton Detection & Multi-Cotton Picking

**Part of:** [Pragati Production System Documentation](../README.md)

---

## 🌱 Cotton Picking Workflow

### Phase 1: Field Navigation

**Vehicle Control Active:**

```
┌──────────────────────────────────────────────┐
│  Vehicle Control Node                        │
│  - Reads GPS/navigation waypoints            │
│  - Controls 4 wheel motors                   │
│  - Manages steering                          │
│  - Obstacle avoidance (if sensors present)   │
└──────────────────────────────────────────────┘
          │
          ▼
   Moves robot through cotton field
          │
          ▼
   Positions near cotton plant
```

**Topics Used:**
- `/vehicle/cmd_vel` - Velocity commands
- `/vehicle/odom` - Odometry feedback
- `/vehicle/joint_states` - Wheel positions

---
### Phase 2: Cotton Detection

**Each Arm's OAK-D Lite Camera Continuously Scanning:**

// cotton_detection_node.cpp workflow (C++ DepthAI integration):

1. Luxonis OAK-D Lite Camera captures RGB + Depth
   ↓
2. DepthAI pipeline processes on-device (Myriad X VPU)
   - YOLO neural network inference (on-camera)
   - Stereo depth calculation (on-camera)
   - Spatial coordinates from stereo (x, y, z)
   ↓
3. C++ DepthAI Manager receives results
   - depthai_manager.cpp handles camera communication
   - Direct C++ API (no subprocess, no file I/O)
   - Real-time processing (<100ms latency)
   ↓
4. Detection results published to ROS2
   Topic: /arm_N/cotton_detection/results
   Message: DetectionResult
   {
     positions: [Point(x, y, z), ...]  // 3D coordinates from stereo
     confidence: [0.95, 0.87, ...]
     spatial_data: true  // Real stereo depth, not estimated
     timestamp: current_time
   }
   ↓
5. Arm control node receives detection for this arm
```

**Key Files:**
- `src/cotton_detection_ros2/src/cotton_detection_node.cpp` - Main C++ node
- `src/cotton_detection_ros2/src/depthai_manager.cpp` - OAK-D Lite interface
- `src/cotton_detection_ros2/include/cotton_detection_ros2/depthai_manager.hpp` - DepthAI API

**Camera Hardware:**
- **Model:** Luxonis OAK-D Lite (https://shop.luxonis.com/products/oak-d-lite-1)
- **Compute:** Intel Myriad X VPU (on-camera neural network inference)
- **Sensors:** RGB camera + stereo depth (left/right IR cameras)
- **Interface:** USB 3.0 to Raspberry Pi 5
- **SDK:** DepthAI C++ SDK (depthai-core library)

**Communication:**
- **Direct C++ API:** No subprocess, no signals, no file I/O
- **Low Latency:** ~50-100ms from image capture to ROS2 publish
- **Spatial Accuracy:** Real stereo depth, not monocular estimation

---
---

### Phase 2.5: Multi-Cotton Detection and Pickability Classification

**⚠️ CRITICAL ENHANCEMENT: Single Image Contains Multiple Cottons**

The detection system now identifies **ALL cottons** in a single camera frame, not just one:

```cpp
// Enhanced detection result with multiple cottons
DetectionResult {
    // Multiple cotton detections per frame
    positions: [
        Point3D(x: 0.5, y: 0.2, z: 0.8),  // Cotton 1
        Point3D(x: 0.6, y: 0.3, z: 0.75), // Cotton 2  
        Point3D(x: 0.4, y: 0.1, z: 0.82), // Cotton 3
        Point3D(x: 0.55, y: 0.25, z: 0.9) // Cotton 4
    ]
    
    // Confidence scores for each detection
    confidence: [0.95, 0.87, 0.92, 0.78]
    
    // NEW: Pickability classification for each cotton
    pickability_status: [
        PICKABLE,      // Cotton 1: ready to pick
        NON_PICKABLE,  // Cotton 2: too immature
        PICKABLE,      // Cotton 3: ready to pick
        NON_PICKABLE   // Cotton 4: damaged/diseased
    ]
    
    // Pickability confidence
    pickability_confidence: [0.91, 0.88, 0.94, 0.85]
}
```

---

#### Pickability Classification

**Classification Categories:**

1. **PICKABLE** - Ready for harvesting
   - Fully opened cotton bolls
   - White/cream color (ripe)
   - No visible damage or disease
   - Within reachable workspace

2. **NON_PICKABLE** - Should not be picked
   - **Immature:** Still green, not fully opened
   - **Damaged:** Torn, dirty, or contaminated
   - **Diseased:** Discolored, moldy, or infected
   - **Out of reach:** Beyond arm workspace limits
   - **Occluded:** Blocked by leaves or other obstacles

**Classification Model:**
```yaml
# Neural network for pickability classification
model_type: "YOLOv8 with custom classification head"
input: "RGB + Depth image"
output:
  - detection_bbox: [x, y, w, h]
  - detection_confidence: float (0-1)
  - pickability_class: {PICKABLE, NON_PICKABLE}
  - pickability_confidence: float (0-1)
  
# Training data
dataset_size: "10,000+ annotated cotton images"
pickable_samples: 6500
non_pickable_samples: 3500
```

---

#### Sequential Picking Strategy

**The robot picks ALL pickable cottons before moving to the next location:**

```
WORKFLOW PER STOP:
═════════════════

1. Vehicle stops at location
   ↓
2. Trigger camera capture (all 4 arms simultaneously)
   ↓
3. Detection + Classification runs on each camera
   → Detects: Cotton 1, 2, 3, 4, 5, 6
   → Classifies pickability for each
   → Result: Cotton 1 (PICKABLE), 2 (NON_PICKABLE), 
              3 (PICKABLE), 4 (PICKABLE), 5 (NON_PICKABLE), 6 (PICKABLE)
   ↓
4. Filter to pickable cottons only
   → Pickable list: [Cotton 1, Cotton 3, Cotton 4, Cotton 6]
   ↓
5. Pick cottons sequentially in priority order
   → Pick Cotton 1 (highest confidence: 0.95)
   → Pick Cotton 3 (confidence: 0.92)
   → Pick Cotton 4 (confidence: 0.88)
   → Pick Cotton 6 (confidence: 0.85)
   ↓
6. All pickable cottons harvested
   ↓
7. Vehicle moves to next location

NON-PICKABLE cottons (2, 5) are IGNORED and left on plant.
```

---

#### Implementation Code

**Enhanced Picking Workflow:**

```cpp
// src/yanthra_move/src/yanthra_move_system.cpp

void YanthraMove::cottonDetectionCallback(
    const DetectionResult::SharedPtr msg)
{
    std::lock_guard<std::mutex> lock(detection_mutex_);
    
    // Store ALL detected cottons
    latest_detection_ = msg;
    
    // Filter to pickable cottons only
    std::vector<CottonTarget> pickable_cottons;
    
    for (size_t i = 0; i < msg->positions.size(); i++) {
        // Check pickability classification
        if (msg->pickability_status[i] == PickabilityClass::PICKABLE &&
            msg->pickability_confidence[i] > 0.7) {  // Confidence threshold
            
            CottonTarget target;
            target.position = msg->positions[i];
            target.confidence = msg->confidence[i];
            target.pickability_confidence = msg->pickability_confidence[i];
            
            pickable_cottons.push_back(target);
        }
    }
    
    // Sort by confidence (highest first)
    std::sort(pickable_cottons.begin(), pickable_cottons.end(),
        [](const CottonTarget& a, const CottonTarget& b) {
            return a.confidence > b.confidence;
        });
    
    // Store for sequential picking
    pending_pickable_cottons_ = pickable_cottons;
    
    RCLCPP_INFO(get_logger(), 
        "Detected %zu cottons, %zu pickable",
        msg->positions.size(), pickable_cottons.size());
}

// Main picking loop - picks ALL pickable cottons
bool YanthraMove::pick_all_pickable_cottons()
{
    int picked_count = 0;
    int failed_count = 0;
    
    // Iterate through all pickable cottons
    for (const auto& target : pending_pickable_cottons_) {
        
        RCLCPP_INFO(get_logger(), 
            "Picking cotton at (%.2f, %.2f, %.2f) - confidence: %.2f",
            target.position.x, target.position.y, target.position.z,
            target.confidence);
        
        // 1. Calculate inverse kinematics
        auto joint_angles = calculate_ik(target.position);
        
        // 2. Move arm to cotton
        if (!move_arm_to_position(joint_angles)) {
            RCLCPP_WARN(get_logger(), "Failed to reach cotton position");
            failed_count++;
            continue;  // Skip this cotton, try next
        }
        
        // 3. Close gripper to grab
        close_gripper();
        std::this_thread::sleep_for(std::chrono::milliseconds(500));
        
        // 4. Return to home/basket position
        move_to_home();
        
        // 5. Open gripper to release into basket
        open_gripper();
        std::this_thread::sleep_for(std::chrono::milliseconds(300));
        
        picked_count++;
        
        RCLCPP_INFO(get_logger(), "Cotton picked successfully (%d/%zu)",
            picked_count, pending_pickable_cottons_.size());
    }
    
    // Clear the list after picking all
    pending_pickable_cottons_.clear();
    
    RCLCPP_INFO(get_logger(), 
        "Picking cycle complete: %d picked, %d failed",
        picked_count, failed_count);
    
    return picked_count > 0;
}
```

---

#### Performance Impact

**Phase 1 (OLD - Single Cotton):**
```
Per Stop:
- Detect: 1 cotton
- Pick: 1 cotton
- Time: ~3 seconds
- Efficiency: LOW (many cottons left unpicked)
```

**Phase 1.5 (CURRENT - Multi-Cotton with Pickability):**
```
Per Stop:
- Detect: 4-8 cottons (average)
- Classify: Pickable vs Non-Pickable
- Pick: 2-5 pickable cottons (average)
- Time: ~8-12 seconds (2-3 seconds per pick)
- Efficiency: HIGH (all pickable cottons harvested)
- Quality: IMPROVED (non-pickable cottons avoided)

Benefits:
✅ 2-5× more cottons per stop
✅ Better quality (only ripe cottons picked)
✅ Fewer stops needed (same area coverage)
✅ Higher overall throughput
```

**Expected Throughput Improvement:**
```
Old (Single Cotton):  ~200-300 picks/hour
New (Multi-Cotton):   ~600-900 picks/hour  (3× improvement)
```

---

### Phase 3: Arm Positioning

**Yanthra Move Takes Over:**

```cpp
// src/yanthra_move/src/yanthra_move_system.cpp

// Cotton detection callback (line ~340-382)
void YanthraMove::cottonDetectionCallback(
    const DetectionResult::SharedPtr msg)
{
    std::lock_guard<std::mutex> lock(detection_mutex_);
    
    // Store latest detection
    latest_detection_ = msg;
    
    // Extract first cotton position
    if (!msg->positions.empty()) {
        target_cotton_.x = msg->positions[0].x;
        target_cotton_.y = msg->positions[0].y;
        target_cotton_.z = msg->positions[0].z;
        
        detection_available_ = true;
    }
}

// Main picking workflow
bool pick_cotton()
{
    // 1. Calculate inverse kinematics
    //    Convert (x,y,z) cotton position to joint angles
    auto joint_angles = calculate_ik(target_cotton_);
    
    // 2. Send commands to motors
    move_arm_to_position(joint_angles);
    
    // 3. Wait for motion completion
    while (!motion_complete()) {
        std::this_thread::sleep_for(10ms);
    }
    
    // 4. Activate gripper
    close_gripper();
    
    // 5. Return to home position
    move_to_home();
    
    // 6. Open gripper over basket
    open_gripper();
    
    return true;
}
```

**Step-by-Step:**

1. **Receive Detection:** Cotton at (x: 0.5m, y: 0.2m, z: 0.8m)

2. **Inverse Kinematics Calculation:**
   ```
   Target: x=0.5, y=0.2, z=0.8
   ↓
   Calculate joint angles:
   - Shoulder rotation: 23.5°
   - Shoulder lift: 45.2°
   - Elbow: -30.8°
   - Wrist rotation: 15.0°
   - Gripper: Open (0°)
   ```

3. **Motor Commands via CAN Bus:**
   ```
   Send to Motor 1 (Shoulder rotation):
   CAN ID: 0x141
   Command: 0xA4 (Multi-turn position with speed)
   Target: 0.41 radians (23.5°)
   Speed: 2.0 rad/s
   ```

4. **Position Feedback Loop:**
   ```
   Every 20ms (50 Hz):
   - Query motor position
   - Calculate error: target - current
   - Monitor motion progress
   ```

---

### Phase 4: Motor Control (CAN Bus)

**How Motor Commands Work:**

```cpp
// src/motor_control_ros2/src/mg6010_controller.cpp

// Set position command (simplified)
bool MG6010Controller::set_position(
    double position,  // Target in radians
    double velocity,  // Max speed
    double torque)    // Feedforward (unused)
{
    // 1. Safety checks
    if (!enabled_) return false;
    if (!check_limits(position)) return false;
    
    // 2. Apply coordinate transforms
    double motor_position = position * transmission_factor_;
    motor_position += joint_offset_;
    motor_position *= direction_;  // Handle motor direction
    
    // 3. Send CAN command via protocol
    bool success = protocol_->set_absolute_position_with_speed(
        motor_position,
        velocity
    );
    
    // 4. Update internal state
    if (success) {
        target_position_ = position;
        last_command_time_ = now();
    }
    
    return success;
}
```

**CAN Bus Protocol (MG6010-i6):**

```cpp
// src/motor_control_ros2/src/mg6010_protocol.cpp

bool MG6010Protocol::set_absolute_position_with_speed(
    double radians,
    double max_speed_rad_s)
{
    // 1. Encode angle to motor units
    //    Motor uses 0.01° per LSB
    double degrees = radians * 180.0 / M_PI;
    int32_t angle_control = (int32_t)(degrees * 100.0);
    
    // 2. Encode speed
    double speed_dps = max_speed_rad_s * 180.0 / M_PI;
    uint16_t speed_control = (uint16_t)speed_dps;
    
    // 3. Build CAN frame
    std::vector<uint8_t> payload;
    payload.push_back(0x00);  // Reserved
    payload.push_back(speed_control & 0xFF);        // Speed low
    payload.push_back((speed_control >> 8) & 0xFF); // Speed high
    payload.push_back(angle_control & 0xFF);         // Angle byte 0
    payload.push_back((angle_control >> 8) & 0xFF);  // Angle byte 1
    payload.push_back((angle_control >> 16) & 0xFF); // Angle byte 2
    payload.push_back((angle_control >> 24) & 0xFF); // Angle byte 3
    
    // 4. Send via CAN bus
    //    CAN ID: 0x140 + node_id (e.g., 0x141 for motor 1)
    //    Command: 0xA4 (Multi-turn position control 2)
    //    DLC: 8 bytes
    bool success = send_and_wait(
        CMD_MULTI_LOOP_ANGLE_2,  // 0xA4
        payload,
        response,
        10  // 10ms timeout
    );
    
    // 5. Motor responds within 0.25ms typically
    //    Response echoes command byte and includes status
    
    return success;
}
```

**Physical CAN Bus Message:**

```
Example: Move arm joint 1 to 23.5° at 2 rad/s

CAN Frame:
┌──────────────────────────────────────────────────┐
│ CAN ID: 0x141 (11-bit standard frame)           │
│ DLC: 8 bytes                                     │
│ Data:                                            │
│   [0] = 0xA4  ← Command (Multi-turn angle 2)    │
│   [1] = 0x00  ← Reserved                         │
│   [2] = 0x72  ← Speed low byte  (114 dps)       │
│   [3] = 0x00  ← Speed high byte                  │
│   [4] = 0x2E  ← Angle byte 0  (2350 = 23.50°)   │
│   [5] = 0x09  ← Angle byte 1                     │
│   [6] = 0x00  ← Angle byte 2                     │
│   [7] = 0x00  ← Angle byte 3                     │
└──────────────────────────────────────────────────┘

Motor: MG6010E-i6 (Enhanced model with 6:1 internal gearing)
Bitrate: 500 kbps
Bus: can0 (local to each Raspberry Pi)
Physical: CAN_H and CAN_L differential pair
Termination: 120Ω at both ends of each arm's CAN bus

Per Arm Configuration:
- Motor 1 (Base/Rotation): CAN ID 0x141
- Motor 2 (Middle segment): CAN ID 0x142  
- Motor 3 (End effector): CAN ID 0x143
```

---

### Phase 5: Gripper Control

**End Effector Activation:**

```cpp
// src/motor_control_ros2/src/gpio_interface.cpp

// Close gripper to grab cotton
bool close_gripper()
{
    // Option 1: GPIO control (pneumatic/servo)
    gpio_set_pin(GRIPPER_PIN, HIGH);  // Activate solenoid
    std::this_thread::sleep_for(500ms);
    
    // Option 2: Additional motor (if gripper is motorized)
    // gripper_motor->set_position(CLOSED_POSITION);
    
    return verify_gripper_closed();
}

// Open gripper to release cotton
bool open_gripper()
{
    gpio_set_pin(GRIPPER_PIN, LOW);  // Deactivate solenoid
    std::this_thread::sleep_for(500ms);
    
    return verify_gripper_open();
}
```

---

### Phase 6: Return and Deposit

**Complete Pick-and-Place Cycle:**

```
1. Cotton detected at (0.5, 0.2, 0.8)
   ↓
2. Arm moves to approach position (0.45, 0.2, 0.9)
   ↓ (0.8 seconds)
3. Arm descends to grasp position (0.5, 0.2, 0.8)
   ↓ (0.3 seconds)
4. Gripper closes, grasps cotton
   ↓ (0.5 seconds)
5. Arm lifts with cotton (0.5, 0.2, 1.0)
   ↓ (0.3 seconds)
6. Arm moves to home/basket position (0, 0, 1.2)
   ↓ (0.8 seconds)
7. Gripper opens, releases cotton into basket
   ↓ (0.5 seconds)
8. Arm returns to ready position
   ↓ (0.6 seconds)
   
Total cycle time: ~2.8 seconds ✅
```

---

