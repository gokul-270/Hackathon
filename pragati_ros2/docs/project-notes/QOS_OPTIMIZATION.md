# Publisher/Subscriber QoS Optimization
**Goal**: Fix slow switch/move command response

---

## Problem

**Observed**: "Switch command, or move commands, the responses were very slow"

**Root Causes**:
1. Using default QoS (may not match publisher/subscriber)
2. Small queue depth (commands getting dropped)
3. No explicit reliability settings

---

## Solution: Explicit QoS Configuration

### Motor Command Publishers

```cpp
// In yanthra_move_system_hardware.cpp or yanthra_move_system_core.cpp
// Find where publishers are created

// OLD (implicit defaults):
joint3_cmd_pub_ = node_->create_publisher<std_msgs::msg::Float64>(
    "joint3_position_controller/command", 10);

// NEW (explicit QoS):
auto motor_cmd_qos = rclcpp::QoS(rclcpp::KeepLast(5))
    .reliability(rclcpp::ReliabilityPolicy::Reliable)  // Don't drop commands!
    .durability(rclcpp::DurabilityPolicy::Volatile);   // Don't need history

joint3_cmd_pub_ = node_->create_publisher<std_msgs::msg::Float64>(
    "joint3_position_controller/command", 
    motor_cmd_qos);
```

### Switch/Button Subscribers

```cpp
// For START_SWITCH, EMERGENCY_STOP - MUST NOT MISS!
auto switch_qos = rclcpp::QoS(rclcpp::KeepLast(1))
    .reliability(rclcpp::ReliabilityPolicy::Reliable)
    .durability(rclcpp::DurabilityPolicy::TransientLocal)  // Remember last state
    .liveliness(rclcpp::LivelinessPolicy::Automatic)
    .liveliness_lease_duration(std::chrono::seconds(1));  // Detect disconnects

start_switch_sub_ = node_->create_subscription<std_msgs::msg::Bool>(
    "/start_switch",
    switch_qos,
    callback);
```

### Joint State Subscribers (for Position Feedback)

```cpp
// For position feedback - sensor data, can tolerate drops
auto state_qos = rclcpp::QoS(rclcpp::KeepLast(10))
    .reliability(rclcpp::ReliabilityPolicy::BestEffort)  // OK for high-rate data
    .durability(rclcpp::DurabilityPolicy::Volatile);

joint_state_sub_ = node_->create_subscription<std_msgs::msg::Float64>(
    "joint3/state",
    state_qos,
    callback);
```

---

## Implementation

### Step 1: Find Publisher/Subscriber Creations

```bash
cd /home/uday/Downloads/pragati_ros2
grep -r "create_publisher" src/yanthra_move/src/ | grep -v ".backup"
grep -r "create_subscription" src/yanthra_move/src/ | grep -v ".backup"
```

### Step 2: Add Explicit QoS

For each publisher/subscriber:
1. Define appropriate QoS profile
2. Replace default `10` with QoS object
3. Add comment explaining choice

### Step 3: Test Responsiveness

```bash
# Before: Measure command latency
ros2 topic pub --once /joint3_position_controller/command std_msgs/Float64 "{data: 0.1}"
# Note time to see effect

# After: Should be faster and more reliable
```

---

## Quick Reference: QoS Settings

| Use Case | Reliability | Durability | Queue | Notes |
|----------|-------------|------------|-------|-------|
| **Motor commands** | RELIABLE | VOLATILE | 5 | Must not drop |
| **Switch inputs** | RELIABLE | TRANSIENT_LOCAL | 1 | Remember last |
| **Joint states** | BEST_EFFORT | VOLATILE | 10 | High rate OK |
| **ArUco results** | RELIABLE | VOLATILE | 3 | Infrequent |

---

**Priority**: HIGH - Affects user experience  
**Risk**: LOW - Easy to revert  
**Testing**: Can test immediately  
**Deploy**: With Phase 1 or separately
