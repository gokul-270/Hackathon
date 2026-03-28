# Real-Time Control & ROS2 Communication

**Part of:** [Pragati Production System Documentation](../README.md)

---

## 🔄 Real-Time Control Loop

**Main Control Loop (50 Hz / 20ms):**

```cpp
// Simplified main loop
while (system_running_)
{
    auto start = std::chrono::steady_clock::now();
    
    // 1. Read all motor positions (via CAN)
    read_motor_states();  // ~1ms for 5 motors
    
    // 2. Check for new cotton detections
    if (detection_available_) {
        target_position_ = latest_detection_;
        detection_available_ = false;
    }
    
    // 3. Calculate motion commands
    if (in_motion_) {
        update_trajectory();
        calculate_motor_commands();
    }
    
    // 4. Send motor commands (via CAN)
    send_motor_commands();  // ~1ms for 5 motors
    
    // 5. Update robot state publisher
    publish_joint_states();
    
    // 6. Safety checks
    check_safety_limits();
    
    // 7. Sleep to maintain 50 Hz
    auto elapsed = std::chrono::steady_clock::now() - start;
    auto sleep_time = 20ms - elapsed;
    if (sleep_time > 0ms) {
        std::this_thread::sleep_for(sleep_time);
    }
}
```

**Actual Timing:**
- Motor state read: ~1ms (5 motors @ 0.2ms each)
- IK calculation: ~0.1ms
- Motor command send: ~1ms
- ROS2 overhead: ~0.5ms
- Safety checks: ~0.1ms
- **Total:** ~2.7ms per cycle
- **Margin:** 17.3ms (85% headroom) ✅

---

## 📡 ROS2 Communication

### Topics (Data Streams)

**Published Topics:**
```
/joint_states              (sensor_msgs/JointState)
- All 5 motor positions, velocities, efforts
- Published at 50 Hz
- Used by robot state publisher for URDF visualization

/cotton_detection/results  (DetectionResult)
- Cotton positions in 3D space
- Published when cotton detected (asynchronous)
- Contains list of Point(x, y, z) and confidences

/vehicle/odom              (nav_msgs/Odometry)
- Robot position in field
- Published at 10 Hz
- Used for navigation

/camera/image_raw          (sensor_msgs/Image)
- Raw camera feed from OAK-D Lite
- Published at 30 Hz
- For monitoring and debugging
```

**Subscribed Topics:**
```
/cotton_detection/results  (by yanthra_move)
- Listens for cotton detections
- Triggers picking behavior

/vehicle/cmd_vel          (by vehicle_control)
- Receives velocity commands
- For navigation
```

---

### Services (Request/Response)

**Available Services:**
```
/yanthra_move/move_arm
- Request: target joint angles or cartesian position
- Response: success/failure, execution time
- Use: Manual arm control for testing

/yanthra_move/home_arm
- Request: none
- Response: success when home position reached
- Use: Return arm to safe home position

/yanthra_move/emergency_stop
- Request: none
- Response: immediate acknowledgment
- Use: Emergency stop all motion

/yanthra_move/get_motor_status
- Request: motor_id (or all)
- Response: position, velocity, temperature, errors
- Use: Health monitoring

/cotton_detection/trigger
- Request: none
- Response: number of cotton detected
- Use: Manual detection trigger
```

**Service Call Example:**
```bash
# Move arm to specific position
ros2 service call /yanthra_move/move_arm \
  yanthra_move_interfaces/srv/MoveArm \
  "{target_position: {x: 0.5, y: 0.2, z: 0.8}}"

# Response:
# success: True
# message: "Arm moved successfully"
# execution_time: 1.23
```

---

