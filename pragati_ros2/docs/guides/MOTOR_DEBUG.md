# Motor 2 & 3 Not Responding - Debug Guide

## Issue
Only Motor 1 (joint3) is responding to position commands.  
Motors 2 and 3 (joint4, joint5) are not moving.

## Possible Causes

### 1. Motors Not Enabled During Initialization
**Check:** Are motors 2 and 3 actually being enabled?

**On Raspberry Pi, check the launch log:**
```bash
grep "Motor.*initialized\|Motor ON\|Error flags" /tmp/final_3motors.log
```

**Expected output for all 3 motors:**
```
Motor 1 initialized: joint3 (CAN ID: 0x1)
Sending Motor ON command to motor (CAN ID: 0x1)
  Error flags: 0x0

Motor 2 initialized: joint4 (CAN ID: 0x2)
Sending Motor ON command to motor (CAN ID: 0x2)
  Error flags: 0x0

Motor 3 initialized: joint5 (CAN ID: 0x3)
Sending Motor ON command to motor (CAN ID: 0x3)
  Error flags: 0x0
```

### 2. CAN Communication Issue
**Check:** Are CAN messages being sent to motors 2 and 3?

**Monitor CAN bus:**
```bash
candump can0
```

Then send position commands and verify you see messages for all 3 CAN IDs:
- ID 0x141 (motor 1)
- ID 0x142 (motor 2)  
- ID 0x143 (motor 3)

### 3. Position Command Not Reaching Motors 2 & 3
**Check:** Do the callbacks receive commands for all motors?

**Look for these log messages:**
```bash
grep "Received position command" /tmp/final_3motors.log
```

**Expected:**
```
🎯 Received position command for joint3: 6.280 rad
🎯 Received position command for joint4: 6.280 rad
🎯 Received position command for joint5: 6.280 rad
```

### 4. Lambda Capture Issue (LIKELY CAUSE)
The lambda in `create_position_command_subscribers()` might have a capture issue:

```cpp
[this, i](const std_msgs::msg::Float64::SharedPtr msg) {
    this->position_command_callback(i, msg);
}
```

**The Problem:** In C++, capturing loop variables by value in lambdas can be tricky.  
All lambdas might end up with `i = 2` (the final value after loop completes).

**Solution:** Create a copy of `i` inside the loop:

```cpp
void create_position_command_subscribers()
{
  for (size_t i = 0; i < controllers_.size(); ++i) {
    std::string topic_name = "/" + joint_names_[i] + "_position_controller/command";
    
    // Create a copy to ensure proper capture
    size_t motor_index = i;  // ← ADD THIS LINE
    
    auto sub = this->create_subscription<std_msgs::msg::Float64>(
      topic_name, 10,
      [this, motor_index](const std_msgs::msg::Float64::SharedPtr msg) {  // ← USE motor_index
        this->position_command_callback(motor_index, msg);
      });
    
    position_cmd_subs_.push_back(sub);
    RCLCPP_INFO(this->get_logger(), "📥 Subscribed to: %s (motor_idx=%zu)", 
                topic_name.c_str(), motor_index);  // ← LOG THE INDEX
  }
}
```

### 5. Hardware Issue
**Check:** Are motors 2 and 3 properly connected and powered?

**Verify physical connections:**
- CAN H/L wiring for all 3 motors
- Power supply to all motors
- CAN termination resistors

**Test individual motors:**
```bash
# Send raw CAN frame to motor 2
cansend can0 142#0100000000000000

# Send raw CAN frame to motor 3  
cansend can0 143#0100000000000000
```

---

## Quick Fix

**File to modify:** `src/motor_control_ros2/src/mg6010_controller_node.cpp`

**Line 207-221:** Replace the `create_position_command_subscribers()` function:

```cpp
void create_position_command_subscribers()
{
  // Create position command subscriber for each motor
  for (size_t i = 0; i < controllers_.size(); ++i) {
    std::string topic_name = "/" + joint_names_[i] + "_position_controller/command";
    
    // CRITICAL FIX: Create local copy for proper lambda capture
    size_t motor_index = i;
    
    auto sub = this->create_subscription<std_msgs::msg::Float64>(
      topic_name, 10,
      [this, motor_index](const std_msgs::msg::Float64::SharedPtr msg) {
        RCLCPP_INFO(this->get_logger(), "📨 Callback triggered for motor_index=%zu", motor_index);
        this->position_command_callback(motor_index, msg);
      });
    
    position_cmd_subs_.push_back(sub);
    RCLCPP_INFO(this->get_logger(), "📥 Subscribed to: %s (motor_idx=%zu)", 
                topic_name.c_str(), motor_index);
  }
}
```

---

## Testing Steps

1. **Check initialization log:**
```bash
ssh ubuntu@10.133.251.157
source /home/ubuntu/pragati_ros2/install/setup.bash
ros2 node list
grep "Motor.*initialized" ~/.ros/log/*/launch.log | tail -20
```

2. **Test each motor individually:**
```bash
# Motor 1
ros2 topic pub -1 /joint3_position_controller/command std_msgs/msg/Float64 '{data: 0.5}'

# Motor 2
ros2 topic pub -1 /joint4_position_controller/command std_msgs/msg/Float64 '{data: 0.5}'

# Motor 3
ros2 topic pub -1 /joint5_position_controller/command std_msgs/msg/Float64 '{data: 0.5}'
```

3. **Check if commands are received:**
```bash
ros2 topic echo /joint3_position_controller/command &
ros2 topic echo /joint4_position_controller/command &
ros2 topic echo /joint5_position_controller/command &
```

4. **Monitor CAN traffic:**
```bash
candump can0 | grep -E "141|142|143"
```

---

## Expected Behavior

When you send a position command to joint4 or joint5, you should see:
1. Log message: `🎯 Received position command for joint4: X.XXX rad`
2. CAN message on bus with ID 0x142 or 0x143
3. Physical motor movement

---

## Most Likely Fix

The lambda capture issue is the most probable cause. Apply the fix above and rebuild:

```bash
cd /home/ubuntu/pragati_ros2
source /opt/ros/jazzy/setup.bash
colcon build --packages-select motor_control_ros2 --cmake-args -DBUILD_TEST_NODES=ON
source install/setup.bash
# Restart the launch file
```

Then test again!
