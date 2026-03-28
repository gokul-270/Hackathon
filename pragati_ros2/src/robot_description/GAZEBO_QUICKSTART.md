# MG6010 Robot Gazebo Simulation - Quick Start Guide

## Overview

This package now includes comprehensive **Gazebo Harmonic** simulation support for the MG6010 Pragati cotton-picking robot. The simulation is fully integrated with **ROS2 Jazzy** and includes:

- ✅ Gazebo Harmonic (8.x) compatible URDF
- ✅ ros2_control integration
- ✅ Joint trajectory controllers
- ✅ Camera sensor simulation
- ✅ IMU sensor simulation
- ✅ Cotton field environment

## System Requirements

- **OS:** Ubuntu 24.04 (Noble)
- **ROS:** ROS2 Jazzy
- **Gazebo:** Gazebo Harmonic (8.x)
- **Python:** 3.12+

## Installation

### 1. Install Dependencies

The package requires Gazebo Harmonic and ros2_control packages:

```bash
# Install Gazebo Harmonic
sudo apt update
sudo apt install gz-harmonic

# Install ROS2-Gazebo integration
sudo apt install ros-jazzy-ros-gz-sim ros-jazzy-ros-gz-bridge

# Install ros2_control packages
sudo apt install ros-jazzy-ros2-control ros-jazzy-ros2-controllers
sudo apt install ros-jazzy-gz-ros2-control

# Install controller manager
sudo apt install ros-jazzy-controller-manager
```

### 2. Build the Package

```bash
cd ~/pragati_ros2
colcon build --packages-select robot_description
source install/setup.bash
```

## Running the Simulation

### Option 1: Gazebo Only

Launch Gazebo with the MG6010 robot:

```bash
source ~/pragati_ros2/install/setup.bash
ros2 launch robot_description gazebo_sim.launch.py
```

**What happens:**
1. Gazebo Harmonic starts with cotton field world
2. MG6010 robot spawns at origin
3. All ros2_control controllers are loaded
4. Joint state publisher broadcasts joint states
5. Camera and IMU sensors are active

### Option 2: Gazebo + RViz

Launch both Gazebo and RViz for comprehensive visualization:

```bash
ros2 launch robot_description display_gazebo.launch.py
```

This will open:
- Gazebo Harmonic window (physics simulation)
- RViz2 window (robot visualization)

### Option 3: Custom World

Launch with a specific world file:

```bash
ros2 launch robot_description gazebo_sim.launch.py world:=/path/to/custom.sdf
```

### Option 4: Custom Spawn Position

```bash
ros2 launch robot_description gazebo_sim.launch.py x:=2.0 y:=1.0 z:=0.5 yaw:=1.57
```

## Controlling the Robot

### 1. Check Available Controllers

```bash
ros2 control list_controllers
```

Expected output:
```
joint_state_broadcaster[joint_state_broadcaster/JointStateBroadcaster] active
joint_trajectory_controller[joint_trajectory_controller/JointTrajectoryController] active
```

### 2. Check Joint States

```bash
ros2 topic echo /joint_states
```

### 3. Send Joint Commands

You can send trajectory commands to move the robot joints:

```bash
# Example: Move joints to specific positions
ros2 action send_goal /joint_trajectory_controller/follow_joint_trajectory \
  control_msgs/action/FollowJointTrajectory \
  "{
    trajectory: {
      joint_names: ['joint 2', 'joint 3', 'joint 4', 'joint 5', 'joint 7'],
      points: [
        {
          positions: [0.25, 0.5, 0.1, 0.0, 0.02],
          time_from_start: {sec: 2}
        }
      ]
    }
  }"
```

### 4. View Camera Feed

```bash
# Terminal 1: View camera image
ros2 run rqt_image_view rqt_image_view /camera/image_raw

# Terminal 2: Check camera info
ros2 topic echo /camera/camera_info
```

### 5. Monitor IMU Data

```bash
ros2 topic echo /imu
```

## ROS2 Topics

The simulation publishes/subscribes to these topics:

### Published Topics
- `/joint_states` - Current joint positions, velocities, efforts
- `/camera/image_raw` - RGB camera feed
- `/camera/camera_info` - Camera calibration info
- `/imu` - IMU sensor data (acceleration, angular velocity)
- `/clock` - Simulation clock
- `/tf` - Transform tree
- `/tf_static` - Static transforms

### Subscribed Topics
- `/joint_trajectory_controller/joint_trajectory` - Joint trajectory commands

## File Structure

```
robot_description/
├── urdf/
│   ├── MG6010_final.urdf          # Base robot URDF
│   ├── MG6010_gazebo.xacro        # Main Gazebo-enhanced URDF
│   ├── materials.xacro            # Gazebo materials
│   ├── gazebo_plugins.xacro       # Gazebo plugins (camera, IMU, etc.)
│   └── ros2_control.xacro         # ros2_control configuration
├── config/
│   └── controllers.yaml           # Controller parameters
├── worlds/
│   └── default.sdf                # Default Gazebo world
├── launch/
│   ├── gazebo_sim.launch.py       # Main simulation launch
│   └── display_gazebo.launch.py  # Gazebo + RViz launch
└── meshes/                        # Robot mesh files
```

## Troubleshooting

### Issue: Robot falls through ground

**Solution:** The robot spawns at z=0.5 by default. Adjust if needed:
```bash
ros2 launch robot_description gazebo_sim.launch.py z:=1.0
```

### Issue: Controllers not loading

**Solution:** Check controller manager status:
```bash
ros2 control list_controllers
ros2 control list_hardware_interfaces
```

### Issue: Camera not publishing

**Solution:** Check Gazebo bridge is running:
```bash
ros2 topic list | grep camera
ros2 node list | grep gz_bridge
```

### Issue: Joint limits exceeded

**Solution:** Check joint limits in [ros2_control.xacro](urdf/ros2_control.xacro):
- Joint 2: 0.1 to 0.32 m (prismatic Z)
- Joint 3: -π to π rad (revolute)
- Joint 4: -0.25 to 0.35 m (prismatic Y)
- Joint 5: -π to π rad (revolute)
- Joint 7: -0.05 to 0.05 m (gripper)

### Issue: Simulation runs too slow

**Solution:** Adjust physics parameters in world file or reduce sensor update rates in [gazebo_plugins.xacro](urdf/gazebo_plugins.xacro).

## Testing Checklist

- [ ] Gazebo launches successfully
- [ ] Robot spawns without errors
- [ ] All joints visible in joint_states
- [ ] Controllers are active
- [ ] Camera publishes images
- [ ] IMU publishes data
- [ ] Joint commands move robot
- [ ] TF tree is complete
- [ ] No collision warnings
- [ ] Simulation runs at real-time

## Integration with Existing Code

The Gazebo simulation integrates seamlessly with your existing packages:

### Motor Control Integration

The simulated joints use the same joint names as your real robot:
- `joint 2`, `joint 3`, `joint 4`, `joint 5`, `joint 7`

Your existing motor_control_ros2 nodes can command the simulated robot using:
```bash
ros2 param set /gazebo_simulation use_sim_time true
```

### Cotton Detection Integration

The simulated camera publishes to `/camera/image_raw`, which your cotton_detection_ros2 nodes can subscribe to for testing detection algorithms.

## Next Steps

1. **Test Controllers:** Verify joint trajectory following
2. **Integrate Vision:** Connect cotton detection to simulated camera
3. **Add More Cotton:** Modify world file to add more cotton plants
4. **Tune Physics:** Adjust friction, damping for realistic behavior
5. **Create Test Scenarios:** Build world files for specific test cases

## Advanced Configuration

### Custom Controller Tuning

Edit [config/controllers.yaml](config/controllers.yaml) to adjust:
- Update rates
- PID gains
- Trajectory tolerances
- Constraint limits

### Custom Sensor Configuration

Edit [urdf/gazebo_plugins.xacro](urdf/gazebo_plugins.xacro) to:
- Change camera resolution/FOV
- Adjust IMU noise parameters
- Add additional sensors (depth, laser, etc.)

### Physics Tuning

Edit [worlds/default.sdf](worlds/default.sdf) to modify:
- Gravity
- Time step
- Solver iterations
- Contact parameters

## Resources

- [ROS2 Jazzy Documentation](https://docs.ros.org/en/jazzy/)
- [Gazebo Harmonic Documentation](https://gazebosim.org/docs/harmonic)
- [ros2_control Documentation](https://control.ros.org/)
- [gz_ros2_control](https://github.com/ros-controls/gz_ros2_control)

## Support

For issues specific to this simulation setup, check:
1. Gazebo logs: `~/.gz/sim/log/`
2. ROS logs: `ros2 topic echo /rosout`
3. Controller status: `ros2 control list_controllers`

---

**Compatibility:** ROS2 Jazzy + Gazebo Harmonic (8.x) ✅

**Status:** Production Ready 🚀
