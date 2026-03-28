# MG6010 Motor Test Nodes - Clear Guide

## Overview
There are **TWO DIFFERENT** test nodes for MG6010 motors. They serve different purposes and test different parts of the stack.

---

## Node 1: `mg6010_test_node` (Protocol Test)

### Purpose
**Low-level protocol testing** - Tests raw MG6010Protocol implementation without ROS integration.

### What it tests
- Direct CAN communication
- MG6010Protocol class methods
- Basic motor commands (on/off, position, velocity, torque)
- Status reading
- NO ROS topics/services

### Launch
```bash
ros2 launch motor_control_ros2 mg6010_test.launch.py test_mode:=status
```

### Test modes
- `status` - Read motor status
- `on_off` - Motor enable/disable
- `position` - Position control
- `velocity` - Velocity control
- `torque` - Torque control
- `angle` - Angle reading
- `pid` - PID parameters
- `accel` - Acceleration settings
- `encoder` - Encoder reading

### When to use
- Testing CAN communication
- Debugging protocol issues
- Verifying motor responds to basic commands
- Quick hardware checks

---

## Node 2: `mg6010_controller_node` (Production Controller)

### Purpose
**Production motor controller** - The main controller node that manages MG6010 motors in production.

### What it tests
- MG6010Controller class
- MotorControllerInterface abstraction
- MG6010Protocol (underlying)
- ROS topics and services
- Multi-motor coordination
- Homing sequences

### Launch
```bash
ros2 launch motor_control_ros2 mg6010_controller.launch.py
```

### Features
- **Publishes**: `/joint_states` (sensor_msgs/JointState)
- **Subscribes**: 
  - `/joint3_position_controller/command`
  - `/joint4_position_controller/command`
  - `/joint5_position_controller/command`
- **Services**:
  - `/enable_motors` (std_srvs/Trigger)
  - `/disable_motors` (std_srvs/Trigger)
- **Multi-motor support**: Controls 3+ motors simultaneously
- **Homing**: Automatic homing sequence on startup

### When to use
- Testing full motor controller integration
- Running actual robot operations
- Testing with ROS ecosystem (MoveIt, controllers, etc.)
- Production motor control

---

## Quick Decision Tree

```
Need to test...
│
├─ Basic CAN communication?
│  └─ Use mg6010_test_node
│
├─ Motor responds to commands?
│  └─ Use mg6010_test_node
│
├─ Full ROS integration?
│  └─ Use mg6010_controller_node
│
├─ Multiple motors together?
│  └─ Use mg6010_controller_node
│
└─ Production robot control?
   └─ Use mg6010_controller_node
```

---

## Common Confusion Points

### ❌ WRONG: "The motor control node"
- Too vague - which node?

### ✅ RIGHT: Specify which one
- "The `mg6010_test_node` (protocol test)"
- "The `mg6010_controller_node` (production controller)"

### ❌ WRONG: "The integrated test node" or "The controller"
- Too vague - which controller?

### ✅ RIGHT: Use full name
- "`mg6010_controller_node`"

---

## File Locations

### mg6010_test_node
- **Source**: `src/motor_control_ros2/src/mg6010_test_node.cpp`
- **Launch**: `src/motor_control_ros2/launch/mg6010_test.launch.py`
- **Config**: `src/motor_control_ros2/config/mg6010_test.yaml`

### mg6010_controller_node
- **Source**: `src/motor_control_ros2/src/mg6010_controller_node.cpp`
- **Launch**: `src/motor_control_ros2/launch/mg6010_controller.launch.py`
- **Config**: `src/motor_control_ros2/config/production.yaml`

---

## Summary Table

| Feature | mg6010_test_node | mg6010_controller_node |
|---------|------------------|----------------------------|
| **Purpose** | Protocol testing | Full integration |
| **ROS Topics** | ❌ No | ✅ Yes |
| **ROS Services** | ❌ No | ✅ Yes |
| **Multi-motor** | ❌ No | ✅ Yes |
| **Homing** | ❌ No | ✅ Yes |
| **Test duration** | Runs once, exits | Continuous (spins) |
| **Use case** | Hardware debug | Production control |

---

## Pro Tips

1. **Always start with `mg6010_test_node`** when debugging hardware issues
2. **Use `mg6010_controller_node`** for actual robot operations
3. **Check the launch file** if unsure which node is being used
4. **Look for ROS topics** - if they exist, it's the controller node
5. **When asking for help, specify the exact node name** to avoid confusion
