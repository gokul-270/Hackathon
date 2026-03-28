# 🚀 QUICK REFERENCE - Gazebo Simulation Commands

## Launch Commands

```bash
# Basic simulation
ros2 launch robot_description gazebo_sim.launch.py

# Simulation + RViz
ros2 launch robot_description display_gazebo.launch.py

# Custom spawn position
ros2 launch robot_description gazebo_sim.launch.py x:=2.0 y:=1.0 z:=1.0 yaw:=1.57

# Custom world
ros2 launch robot_description gazebo_sim.launch.py world:=/path/to/world.sdf
```

## Control Commands

```bash
# List active controllers
ros2 control list_controllers

# List hardware interfaces
ros2 control list_hardware_interfaces

# Send joint trajectory (Example)
ros2 action send_goal /joint_trajectory_controller/follow_joint_trajectory \
  control_msgs/action/FollowJointTrajectory \
  "{trajectory: {joint_names: ['joint 2', 'joint 3', 'joint 4', 'joint 5', 'joint 7'], \
   points: [{positions: [0.25, 0.5, 0.1, 0.0, 0.02], time_from_start: {sec: 2}}]}}"
```

## Monitoring Commands

```bash
# View joint states
ros2 topic echo /joint_states

# View camera feed
ros2 run rqt_image_view rqt_image_view /camera/image_raw

# View IMU data
ros2 topic echo /imu

# List all topics
ros2 topic list

# View TF tree
ros2 run rqt_tf_tree rqt_tf_tree

# View node graph
rqt_graph
```

## Debugging Commands

```bash
# Check controller status
ros2 control list_controllers

# View controller details
ros2 control view_controller_chains

# Check node information
ros2 node info /controller_manager
ros2 node info /robot_state_publisher

# Monitor rosout
ros2 topic echo /rosout

# Check Gazebo topics
gz topic -l
```

## Build & Setup Commands

```bash
# Build package
cd ~/pragati_ros2
colcon build --packages-select robot_description
source install/setup.bash

# Verify URDF
xacro src/robot_description/urdf/MG6010_gazebo.xacro

# Check package
ros2 pkg list | grep robot_description
```

## Recording & Playback

```bash
# Record simulation data
ros2 bag record -a

# Record specific topics
ros2 bag record /joint_states /camera/image_raw /imu

# Play back recording
ros2 bag play <bag_file>
```

## Joint Limits Quick Reference

| Joint | Type | Min | Max |
|-------|------|-----|-----|
| joint 2 | Prismatic (Z) | 0.1 m | 0.32 m |
| joint 3 | Revolute | -π rad | π rad |
| joint 4 | Prismatic (Y) | -0.25 m | 0.35 m |
| joint 5 | Revolute | -π rad | π rad |
| joint 7 | Prismatic (grip) | -0.05 m | 0.05 m |

## Key Topics

| Topic | Type | Description |
|-------|------|-------------|
| `/joint_states` | sensor_msgs/JointState | Current joint states |
| `/camera/image_raw` | sensor_msgs/Image | RGB camera feed |
| `/camera/camera_info` | sensor_msgs/CameraInfo | Camera parameters |
| `/imu` | sensor_msgs/Imu | IMU measurements |
| `/clock` | rosgraph_msgs/Clock | Simulation time |

## Troubleshooting

```bash
# Check if Gazebo is running
gz sim --version

# Check ROS-Gazebo bridge
ros2 node list | grep bridge

# View Gazebo logs
tail -f ~/.gz/sim/log/*/server_console.log

# Kill all Gazebo processes
pkill -9 gz

# Reset simulation
# Press Ctrl+R in Gazebo GUI or restart launch file
```

## File Locations

- URDF Files: `~/pragati_ros2/src/robot_description/urdf/`
- Controllers: `~/pragati_ros2/src/robot_description/config/controllers.yaml`
- Worlds: `~/pragati_ros2/src/robot_description/worlds/`
- Launch Files: `~/pragati_ros2/src/robot_description/launch/`

## Documentation

- Quick Start: `GAZEBO_QUICKSTART.md`
- Setup Summary: `GAZEBO_SETUP_SUMMARY.md`
- Complete Guide: `GAZEBO_SIMULATION_COMPLETE.md`
- Architecture: `ARCHITECTURE_DIAGRAM.txt`
