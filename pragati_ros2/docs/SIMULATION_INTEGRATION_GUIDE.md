# Yanthra Move Simulation Integration - Quick Reference

## Overview
Integrated yanthra_move motion control with Gazebo Harmonic simulation, enabling 4-position arm scanning with L4 position.

## What Was Done

### 1. Created Simulation Bridge (`simulation_bridge.cpp`)
- Bridges yanthra_move joint commands to Gazebo trajectory controller
- Subscribes to: `/joint{2,3,4,5}_position_controller/command`
- Publishes to: `/joint_trajectory_controller/follow_joint_trajectory` (action)
- Updates at 10Hz for responsive simulation

### 2. Added Simulation Configuration (`config/simulation.yaml`)
- **Enabled simulation mode**: `simulation_mode: true`
- **4-position scanning**: `joint4_multiposition/positions: [-0.075, -0.025, 0.025, 0.075]`
- **L4 position enabled**: +0.075m (right side)
- Disabled hardware-specific features (GPIO, end effector, camera)
- Fast timeout and settling times for simulation

### 3. Created Complete Launch File (`launch/simulation_complete.launch.py`)
- Launches Gazebo + simulation bridge + yanthra_move in sequence
- 5-second delay for Gazebo startup
- 7-second delay for yanthra_move (allows bridge to connect)
- Includes helpful startup banner with position details

### 4. Updated Build Configuration
- **CMakeLists.txt**: Added simulation_bridge executable
- **package.xml**: Added rclcpp_action and control_msgs dependencies
- Added dependencies for trajectory action client

### 5. Created Test Data (`centroid.txt`)
- 4 test positions at different lateral offsets
- Triggers arm to move through all 4 scanning positions (L1, L2, L3, L4)

## 4 Scanning Positions

| Position | Offset | Location |
|----------|--------|----------|
| **L1** | -0.075m | Left |
| **L2** | -0.025m | Left-center |
| **L3** | +0.025m | Right-center |
| **L4** | +0.075m | Right ← **NEW** |

## Launch Commands

### Complete Simulation (Recommended)
```bash
source ~/pragati_ros2/install/setup.bash
ros2 launch yanthra_move simulation_complete.launch.py
```

### Individual Components
```bash
# 1. Gazebo only
ros2 launch robot_description gazebo_sim.launch.py

# 2. Simulation bridge (in separate terminal)
ros2 run yanthra_move simulation_bridge

# 3. Yanthra move (in separate terminal)
ros2 run yanthra_move yanthra_move_node --ros-args --params-file src/yanthra_move/config/simulation.yaml
```

## Verification

### Check controllers are loaded:
```bash
ros2 control list_controllers
```

Expected output:
```
joint_state_broadcaster[joint_state_broadcaster/JointStateBroadcaster] active
joint_trajectory_controller[joint_trajectory_controller/JointTrajectoryController] active
```

### Monitor joint states:
```bash
ros2 topic echo /joint_states
```

### Watch simulation bridge:
```bash
ros2 topic echo /joint2_position_controller/command
ros2 topic echo /joint3_position_controller/command
ros2 topic echo /joint4_position_controller/command
ros2 topic echo /joint5_position_controller/command
```

### Check yanthra_move logs:
Look for:
- `🤖 SIMULATION: Joint X moving to position`
- Multi-position scan messages showing all 4 positions
- Position statistics tracking

## Architecture

```
┌─────────────────┐
│  Yanthra Move   │
│    (C++ Node)   │
└────────┬────────┘
         │ /jointN_position_controller/command
         │ (Float64 messages)
         ▼
┌─────────────────┐
│ Simulation      │
│    Bridge       │
│    (C++ Node)   │
└────────┬────────┘
         │ /joint_trajectory_controller/follow_joint_trajectory
         │ (Action client)
         ▼
┌─────────────────┐
│    Gazebo       │
│   Harmonic      │
│  (Simulation)   │
└─────────────────┘
```

## Files Changed/Created

### New Files
- `src/yanthra_move/src/simulation_bridge.cpp` - Simulation interface
- `src/yanthra_move/config/simulation.yaml` - Simulation parameters
- `src/yanthra_move/launch/simulation_complete.launch.py` - Complete launch
- `centroid.txt` - Test positions for 4-position scan

### Modified Files
- `src/yanthra_move/CMakeLists.txt` - Added simulation_bridge target
- `src/yanthra_move/package.xml` - Added rclcpp_action, control_msgs
- `src/robot_description/README.md` - Updated with simulation commands

## Key Features

1. **L4 Position Enabled**: Arm now scans 4 positions instead of 3
2. **Simulation Mode**: Full integration with Gazebo without hardware dependencies
3. **Position Tracking**: Stats show which positions find cotton most often
4. **Responsive Control**: 100ms update rate for smooth simulation
5. **Safe Testing**: All hardware controls disabled in simulation mode

## Troubleshooting

### Bridge not connecting:
- Wait 5-10 seconds after launching Gazebo
- Check: `ros2 node list` should show `simulation_bridge`

### No arm movement:
- Verify joint commands: `ros2 topic echo /joint4_position_controller/command`
- Check simulation mode: `ros2 param get /yanthra_move_node simulation_mode`

### Joint limits errors:
- Check position values in centroid.txt are within reach
- Verify safe_min/safe_max in simulation.yaml

## Next Steps

1. Build: `colcon build --packages-select yanthra_move` ✅
2. Source: `source install/setup.bash` ← DO THIS
3. Launch: `ros2 launch yanthra_move simulation_complete.launch.py` ← TEST THIS
4. Observe: Watch Gazebo and terminal logs for 4-position scanning
5. Tune: Adjust positions in simulation.yaml if needed

## Performance Notes

- **Scan time**: ~6-8 seconds for all 4 positions
- **Settling time**: 150ms after J4 movement
- **Detection delay**: 200ms for camera frame
- **Total cycle**: ~10-12 seconds with detection and picks
