# Safety Systems & Error Handling

**Part of:** [Pragati Production System Documentation](../README.md)

---

## 🛡️ Safety Systems

### Multi-Layer Safety Architecture

**Layer 1: Hardware Safety**
```
- Emergency stop button (GPIO pin 4)
  → Cuts power to motors via relay
  
- Motor thermal protection (built-in)
  → Motors shut down at 80°C
  
- Current limiting (in motor controller)
  → Max 33A for MG series, configured to 15A safe limit
```

**Layer 2: Software Safety**
```cpp
// Safety monitor runs at 100 Hz
void safety_monitor_loop()
{
    // 1. Position limits
    if (position < joint_min || position > joint_max) {
        trigger_emergency_stop("Position limit exceeded");
    }
    
    // 2. Velocity limits
    if (abs(velocity) > velocity_max) {
        trigger_emergency_stop("Velocity limit exceeded");
    }
    
    // 3. Temperature monitoring
    if (temperature > TEMP_CRITICAL) {
        trigger_emergency_stop("Over temperature");
    }
    
    // 4. Communication timeout
    if (time_since_last_command() > 1.0s) {
        trigger_soft_stop("Communication timeout");
    }
    
    // 5. CAN bus errors
    if (can_error_count > 10) {
        trigger_emergency_stop("CAN bus failure");
    }
}
```

**Layer 3: ROS2 Safety**
```
- Watchdog timers on all nodes
- Automatic recovery on node crash
- Graceful shutdown on SIGINT/SIGTERM
- State validation before motion
```

---

## 🐛 Error Handling and Recovery

### Common Errors and Automatic Recovery

**Motor Communication Error:**
```cpp
if (motor_communication_timeout()) {
    // 1. Retry command (up to 3 times)
    for (int i = 0; i < 3; i++) {
        if (retry_command()) break;
        std::this_thread::sleep_for(10ms);
    }
    
    // 2. If still failing, stop motion
    if (!communication_ok()) {
        stop_all_motion();
        record_error("Motor communication failure");
        // Operator intervention required
    }
}
```

**Cotton Detection Timeout:**
```cpp
if (no_detection_for(30s)) {
    // Not an error - just no cotton in view
    // Continue navigation to next location
    publish_status("Searching for cotton...");
}
```

**Motor Over-Temperature:**
```cpp
if (motor_temperature > WARNING_TEMP) {
    // Reduce speed to 50%
    velocity_limit *= 0.5;
    log_warning("Motor temperature high, reducing speed");
}

if (motor_temperature > CRITICAL_TEMP) {
    // Emergency stop
    emergency_stop();
    wait_for_cooldown(60s);
    // Attempt to resume
}
```

**CAN Bus Error:**
```cpp
if (can_bus_off()) {
    // Attempt automatic recovery
    can_interface_->reset();
    std::this_thread::sleep_for(100ms);
    
    if (!can_interface_->reinitialize()) {
        // Require operator intervention
        system_fault("CAN bus hardware failure");
    }
}
```

---

