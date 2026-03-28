# Error Handling and Auto-Reconnect Guide

## Overview
This guide documents error handling patterns and auto-reconnect strategies for robust operation of the Pragati ROS2 system.

---

## Auto-Reconnect Patterns

### CAN Interface Auto-Reconnect

**Implementation Pattern:**
```cpp
class CANInterface {
private:
    int reconnect_attempts_ = 0;
    const int MAX_RECONNECT_ATTEMPTS = 5;
    std::chrono::milliseconds base_delay_{100};
    
public:
    bool send_with_retry(uint32_t id, const std::vector<uint8_t>& data) {
        for (int attempt = 0; attempt < MAX_RECONNECT_ATTEMPTS; attempt++) {
            if (send_message(id, data)) {
                reconnect_attempts_ = 0;  // Reset on success
                return true;
            }
            
            // Exponential backoff: 100ms, 200ms, 400ms, 800ms, 1600ms
            auto delay = base_delay_ * (1 << attempt);
            RCLCPP_WARN(logger_, "CAN send failed, retry %d/%d after %ldms",
                        attempt + 1, MAX_RECONNECT_ATTEMPTS, delay.count());
            std::this_thread::sleep_for(delay);
            
            // Attempt to reinitialize connection
            if (!is_connected()) {
                reinitialize();
            }
        }
        
        RCLCPP_ERROR(logger_, "CAN send failed after %d attempts", MAX_RECONNECT_ATTEMPTS);
        return false;
    }
    
    bool reinitialize() {
        RCLCPP_INFO(logger_, "Attempting CAN interface reinitialization");
        close_can_socket();
        std::this_thread::sleep_for(std::chrono::milliseconds(500));
        return initialize(interface_name_, baud_rate_);
    }
};
```

**Usage:**
```cpp
// In motor_control_ros2/src/mg6010_can_interface.cpp
if (!can_interface_->send_with_retry(arbitration_id, payload)) {
    // Enter safe mode
    safety_monitor_->trigger_emergency_shutdown("CAN communication lost");
    return false;
}
```

### Camera Auto-Reconnect

**Implementation Pattern:**
```cpp
class CameraManager {
private:
    rclcpp::TimerBase::SharedPtr reconnect_timer_;
    std::chrono::steady_clock::time_point last_frame_time_;
    const std::chrono::seconds FRAME_TIMEOUT{5};
    
public:
    void start_health_monitoring() {
        reconnect_timer_ = node_->create_wall_timer(
            std::chrono::seconds(1),
            [this]() { check_health(); }
        );
    }
    
    void check_health() {
        auto now = std::chrono::steady_clock::now();
        auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(
            now - last_frame_time_
        );
        
        if (elapsed > FRAME_TIMEOUT && is_connected_) {
            RCLCPP_WARN(logger_, "Camera timeout detected, attempting reconnect");
            reconnect();
        }
    }
    
    bool reconnect() {
        is_connected_ = false;
        disconnect();
        std::this_thread::sleep_for(std::chrono::seconds(2));
        
        if (initialize()) {
            RCLCPP_INFO(logger_, "Camera reconnected successfully");
            is_connected_ = true;
            return true;
        }
        
        RCLCPP_ERROR(logger_, "Camera reconnection failed");
        return false;
    }
    
    void on_frame_received() {
        last_frame_time_ = std::chrono::steady_clock::now();
    }
};
```

---

## Error Categories and Handling

### 1. Recoverable Errors

**Examples:**
- CAN message send failure (single)
- Camera frame drop
- TF lookup timeout
- Planning failure (single attempt)

**Strategy:**
```cpp
// Retry with backoff
bool retry_with_backoff(std::function<bool()> operation, int max_retries = 3) {
    for (int i = 0; i < max_retries; i++) {
        if (operation()) return true;
        std::this_thread::sleep_for(std::chrono::milliseconds(100 * (1 << i)));
    }
    return false;
}

// Usage
if (!retry_with_backoff([&]() { return send_can_message(msg); })) {
    RCLCPP_ERROR_THROTTLE(logger_, clock_, 1000, "Failed after retries");
    // Enter degraded mode
}
```

### 2. Critical Errors

**Examples:**
- Motor encoder failure
- Safety limit violation
- Emergency stop triggered
- Power supply critical

**Strategy:**
```cpp
void handle_critical_error(const std::string& error_msg) {
    // 1. Trigger emergency stop
    safety_monitor_->trigger_emergency_shutdown(error_msg);
    
    // 2. Stop all motor commands
    for (auto& motor : motors_) {
        motor->emergency_stop();
    }
    
    // 3. Publish diagnostic error
    diagnostic_msgs::msg::DiagnosticStatus diag;
    diag.level = diagnostic_msgs::msg::DiagnosticStatus::ERROR;
    diag.name = "system_safety";
    diag.message = error_msg;
    diagnostic_pub_->publish(diag);
    
    // 4. Log with context
    RCLCPP_ERROR(logger_, "CRITICAL ERROR: %s", error_msg.c_str());
    RCLCPP_ERROR(logger_, "System entering safe mode - manual intervention required");
    
    // 5. Set system state
    system_state_ = SystemState::FAULT;
}
```

### 3. Transient Errors

**Examples:**
- Network congestion
- Temporary CPU spike
- Brief sensor occlusion

**Strategy:**
```cpp
// Use throttled logging to avoid log spam
RCLCPP_WARN_THROTTLE(logger_, clock_, 5000,  // Log every 5 seconds max
    "Transient error: %s", error_msg.c_str());

// Continue operation with degraded performance
if (detection_failed) {
    // Use last known good detection
    return last_valid_detection_;
}
```

---

## Safe Mode Behaviors

### Motor Control Safe Mode
```cpp
void enter_motor_safe_mode() {
    // 1. Stop accepting new commands
    accepting_commands_ = false;
    
    // 2. Gradually decelerate to zero
    for (auto& motor : motors_) {
        motor->set_velocity(0.0);
        motor->set_torque(0.0);
    }
    
    // 3. Activate brakes if available
    if (brake_available_) {
        activate_brakes();
    }
    
    // 4. Publish status
    std_msgs::msg::String status_msg;
    status_msg.data = "SAFE_MODE_ACTIVE";
    status_pub_->publish(status_msg);
    
    // 5. Wait for manual reset
    RCLCPP_WARN(logger_, "Safe mode active - call /reset_system service to recover");
}
```

### Vision Safe Mode
```cpp
void enter_vision_safe_mode() {
    // Publish empty detection messages with DEGRADED status
    cotton_detection_ros2::msg::CottonDetections empty_msg;
    empty_msg.header.stamp = now();
    empty_msg.status = "DEGRADED_CAMERA_ERROR";
    empty_msg.detections.clear();
    detection_pub_->publish(empty_msg);
    
    // Attempt background reconnection
    std::thread([this]() {
        while (!reconnect_camera() && rclcpp::ok()) {
            std::this_thread::sleep_for(std::chrono::seconds(5));
        }
    }).detach();
}
```

---

## Graceful Degradation Checklist

### System Startup
- [ ] Detect missing hardware gracefully
- [ ] Allow simulation mode as fallback
- [ ] Log clear warnings for unavailable components
- [ ] Disable features that depend on missing hardware

### Runtime Operations
- [ ] Monitor communication timeouts
- [ ] Track frame drop rates
- [ ] Measure control loop jitter
- [ ] Validate sensor data ranges

### Shutdown Sequence
- [ ] Stop motors before closing CAN
- [ ] Flush logs before exit
- [ ] Save system state
- [ ] Close hardware interfaces cleanly

---

## Diagnostic Publishing

### Standard Pattern
```cpp
void publish_diagnostics() {
    diagnostic_msgs::msg::DiagnosticArray diag_array;
    diag_array.header.stamp = now();
    
    // Component status
    diagnostic_msgs::msg::DiagnosticStatus status;
    status.name = "motor_control";
    status.hardware_id = "mg6010_motors";
    
    // Determine level
    if (all_motors_ok) {
        status.level = diagnostic_msgs::msg::DiagnosticStatus::OK;
        status.message = "All systems operational";
    } else if (recoverable_error) {
        status.level = diagnostic_msgs::msg::DiagnosticStatus::WARN;
        status.message = "Degraded performance";
    } else {
        status.level = diagnostic_msgs::msg::DiagnosticStatus::ERROR;
        status.message = "Critical failure";
    }
    
    // Add key-value details
    diagnostic_msgs::msg::KeyValue kv;
    kv.key = "temperature_max";
    kv.value = std::to_string(max_temperature_);
    status.values.push_back(kv);
    
    kv.key = "can_errors";
    kv.value = std::to_string(can_error_count_);
    status.values.push_back(kv);
    
    diag_array.status.push_back(status);
    diagnostic_pub_->publish(diag_array);
}
```

---

## Monitoring Commands

### Check System Health
```bash
# Monitor diagnostics
ros2 topic echo /diagnostics

# Check specific node
ros2 node info /motor_control_node

# View error logs
ros2 run rqt_console rqt_console
```

### Force Reconnection
```bash
# CAN interface
ros2 service call /motor_control/reconnect_can std_srvs/srv/Trigger

# Camera
ros2 service call /cotton_detection/reconnect_camera std_srvs/srv/Trigger
```

### Recovery Services
```bash
# Clear errors and reset
ros2 service call /motor_control/clear_errors motor_control_ros2/srv/ClearErrors

# System reset
ros2 service call /system_reset std_srvs/srv/Trigger
```

---

## Error Code Reference

### Motor Control Error Codes
| Code | Description | Action |
|------|-------------|--------|
| 0x01 | Voltage error | Check power supply |
| 0x02 | Temperature error | Cool down motors |
| 0x04 | Encoder error | Recalibrate |
| 0x08 | Communication timeout | Check CAN connection |
| 0x10 | Position limit exceeded | Reset position |
| 0x20 | Velocity limit exceeded | Reduce speed |

### Detection Error Codes
| Code | Description | Action |
|------|-------------|--------|
| CAM_TIMEOUT | Camera not responding | Reconnect camera |
| MODEL_LOAD_FAIL | YOLO model not loaded | Check model path |
| INFERENCE_ERROR | Inference failed | Check GPU/memory |
| INVALID_IMAGE | Corrupted frame | Skip frame, retry |

---

## Testing Error Handling

### Inject Faults (Testing Only)
```bash
# Simulate CAN failure
ros2 service call /motor_control/inject_fault motor_control_ros2/srv/InjectFault "{fault_type: 'can_disconnect', duration: 5.0}"

# Simulate camera loss
ros2 service call /cotton_detection/inject_fault cotton_detection_ros2/srv/InjectFault "{fault_type: 'camera_timeout', duration: 10.0}"
```

### Verify Recovery
```bash
# Watch system state
watch -n 0.5 'ros2 topic echo /system_state --once'

# Monitor reconnection attempts
ros2 topic echo /diagnostics | grep -i "reconnect"
```

---

## Best Practices

1. **Always use throttled logging** for recurring errors
2. **Publish diagnostic messages** for monitoring systems
3. **Implement exponential backoff** for retries
4. **Enter safe mode** on critical errors
5. **Provide recovery services** for operator intervention
6. **Test fault injection** regularly
7. **Document error codes** with recovery procedures
8. **Monitor system health** continuously

**Last Updated:** 2025-10-21
