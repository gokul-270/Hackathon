# Simulation Trigger Commands

## Launch Simulation

```bash
# Terminal 1: Launch complete simulation (Gazebo + Yanthra Move)
source ~/pragati_ros2/install/setup.bash
ros2 launch yanthra_move simulation_complete.launch.py
```

The simulation will automatically:
1. Start Gazebo Harmonic with GUI (0s)
2. Spawn robot from `robot_description/urdf/MG6010_FLU.urdf`
3. Bridge joint commands + clock via `ros_gz_bridge`
4. Launch `yanthra_move` with simulation config (5s)

### Architecture
- **URDF**: `robot_description/urdf/MG6010_FLU.urdf`
- **Joint control**: Gazebo native `JointPositionController` per joint (NO ros2_control)
- **Command topics**: `/joint2_cmd`, `/joint3_cmd`, `/joint4_cmd`, `/joint5_cmd` (std_msgs/Float64)
- **Joint states**: `/joint_states` (bridged from Gazebo)

## Manual Trigger Commands

### 1. Trigger Yanthra Move to Start

```bash
# Publish start signal to begin operation cycle
ros2 topic pub --once /start_switch/command std_msgs/msg/Bool "data: true"
```

### 2. Move Joints Directly (Float64 → Gazebo)

```bash
# Joint 2 - Height (prismatic Z, range: 0.1 to 0.32 m)
ros2 topic pub --once /joint2_cmd std_msgs/msg/Float64 "data: 0.2"

# Joint 3 - Rotation/elevation (revolute, range: -1.5708 to 0.0 rad)
ros2 topic pub --once /joint3_cmd std_msgs/msg/Float64 "data: -0.5"

# Joint 4 - Lateral (prismatic Y, range: -0.250 to 0.350 m)
ros2 topic pub --once /joint4_cmd std_msgs/msg/Float64 "data: 0.1"

# Joint 5 - Extension (prismatic X, range: 0 to 0.450 m)
ros2 topic pub --once /joint5_cmd std_msgs/msg/Float64 "data: 0.3"

# Home all joints (zero position)
ros2 topic pub --once /joint2_cmd std_msgs/msg/Float64 "data: 0.1"
ros2 topic pub --once /joint3_cmd std_msgs/msg/Float64 "data: 0.0"
ros2 topic pub --once /joint4_cmd std_msgs/msg/Float64 "data: 0.0"
ros2 topic pub --once /joint5_cmd std_msgs/msg/Float64 "data: 0.0"
```

### 3. Monitor Joint States

```bash
# Watch all joint positions in real-time
ros2 topic echo /joint_states
```

### 4. Test 4-Position Scanning

The system will automatically scan these 4 positions:
- **L1**: J4 = -0.075m (left)
- **L2**: J4 = -0.025m (left-center)
- **L3**: J4 = +0.025m (right-center)
- **L4**: J4 = +0.075m (right)

Watch the scanning:
```bash
# Monitor J4 commands
ros2 topic echo /joint4_cmd
```

### 5. View Cotton Detection Data

```bash
# Check if cotton positions are being published
ros2 topic echo /cotton_detection/results
```

## Verification

```bash
# List running nodes
ros2 node list
# Expected: /yanthra_move, /robot_state_publisher, /ros_gz_bridge

# List available topics
ros2 topic list
# Key topics:
#   /joint2_cmd          (Float64 → Gazebo joint 2)
#   /joint3_cmd          (Float64 → Gazebo joint 3)
#   /joint4_cmd          (Float64 → Gazebo joint 4)
#   /joint5_cmd          (Float64 → Gazebo joint 5)
#   /joint_states        (bridged from Gazebo)
#   /clock               (sim time)

# Check joint state update rate
ros2 topic hz /joint_states

# Verify simulation mode
ros2 param get /yanthra_move simulation_mode
```

## Clean Shutdown

```bash
# Press Ctrl+C in the launch terminal

# Force kill if needed:
killall -9 gz-sim
killall -9 yanthra_move
```

## Notes

- **No ros2_control** — uses Gazebo native `JointPositionController` plugins directly
- **No simulation_bridge** — `ros_gz_bridge` handles Float64 ↔ gz.msgs.Double conversion
- **Joint names have spaces** in URDF: `"joint 2"`, `"joint 3"`, `"joint 4"`, `"joint 5"`
- Centroid file: `~/pragati_ros2/centroid.txt` (4 test positions for L1–L4)
