# MG6010 Nodes - Quick Reference Card

## Two Nodes, Two Purposes

```
┌─────────────────────────────────────────────────────────────┐
│                  MG6010 Test & Control Nodes                │
└─────────────────────────────────────────────────────────────┘

   TESTING                         PRODUCTION
   ───────                         ──────────

   mg6010_test_node                mg6010_controller_node
   
   • Protocol test                 • Production controller
   • Low-level CAN                 • Full ROS integration
   • No topics/services            • Topics & services
   • Quick hardware check          • Multi-motor control
   • Runs once, exits              • Continuous operation
```

---

## Launch Commands

### Testing
```bash
# Test CAN communication
ros2 launch motor_control_ros2 mg6010_test.launch.py test_mode:=status

# Test position control
ros2 launch motor_control_ros2 mg6010_test.launch.py test_mode:=position

# Other modes: velocity, torque, on_off, angle, pid, accel, encoder
```

### Production
```bash
# Launch production controller
ros2 launch motor_control_ros2 mg6010_controller.launch.py

# Full system launch
ros2 launch yanthra_move pragati_complete.launch.py
```

---

## Key Differences

| Feature | test_node | controller_node |
|---------|-----------|-----------------|
| **Purpose** | Hardware test | Production |
| **ROS Topics** | ❌ None | ✅ /joint_states |
| **ROS Services** | ❌ None | ✅ /enable_motors, /disable_motors |
| **Multi-motor** | ❌ Single | ✅ Multiple (3+) |
| **Homing** | ❌ No | ✅ Yes |
| **Duration** | Exits after test | Runs continuously |

---

## When to Use Which?

### Use `mg6010_test_node` for:
- ✅ Testing CAN communication
- ✅ Verifying motor responds
- ✅ Quick hardware checks
- ✅ Debugging protocol issues

### Use `mg6010_controller_node` for:
- ✅ Running the robot
- ✅ Production operations
- ✅ Multi-motor control
- ✅ ROS system integration

---

## Common Commands

### Check if controller is running
```bash
ros2 node list | grep mg6010
```

### Monitor joint states
```bash
ros2 topic echo /joint_states
```

### Enable/disable motors
```bash
ros2 service call /enable_motors std_srvs/srv/Trigger
ros2 service call /disable_motors std_srvs/srv/Trigger
```

### Send position command
```bash
ros2 topic pub /joint3_position_controller/command std_msgs/msg/Float64 "data: 1.57"
```

---

## Troubleshooting

### Motor not responding?
1. Start with `mg6010_test_node` to test CAN
2. Check CAN interface: `ip link show can0`
3. Verify bitrate: should be 500000

### Controller not starting?
```bash
# Rebuild
cd ~/Downloads/pragati_ros2
colcon build --packages-select motor_control_ros2 --symlink-install
```

### Old node name error?
The old `mg6010_integrated_test_node` has been renamed.  
Use `mg6010_controller_node` instead.

---

## File Locations

```
motor_control_ros2/
├── src/
│   ├── mg6010_test_node.cpp           # Protocol test
│   └── mg6010_controller_node.cpp     # Production controller
├── launch/
│   ├── mg6010_test.launch.py          # Protocol test launch
│   └── mg6010_controller.launch.py    # Production launch
└── config/
    ├── mg6010_test.yaml               # Test config
    └── production.yaml       # Production config
```

---

## Help & Documentation

- 📖 **README.md** - Package overview
- 📖 **README_NODES.md** - Detailed node comparison  
- 📖 **NODES_DIAGRAM.md** - Visual architecture
- 📖 **RENAME_SUMMARY.md** - What changed in the rename

---

## Remember

**Always use full node names when asking for help:**
- ✅ "`mg6010_test_node`"
- ✅ "`mg6010_controller_node`"
- ❌ "the motor node" or "the controller"

**These are different nodes with different purposes!**
