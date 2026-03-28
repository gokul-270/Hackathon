# robot_description

**Package:** `robot_description` (formerly `robo_description` - typo fixed)  
**Type:** ROS2 URDF/Description Package  
**Maintainer:** Pragati Team

## Overview

This package contains the URDF (Unified Robot Description Format) models and visualization configurations for the Pragati cotton-picking robot system.

## Contents

### URDF Models
- Robot kinematic structure
- Joint definitions (3-DOF arms)
- Link geometries and inertial properties
- Collision meshes
- Visual meshes

### Launch Files
- `robot_state_publisher.launch.py` - Publishes robot state to TF
- `view_robot.launch.py` - Visualize robot in RViz (if available)
- `gazebo_sim.launch.py` - Launch Gazebo Harmonic simulation with robot
- `display_gazebo.launch.py` - Launch Gazebo + RViz together
- `gazebo_simple.launch.py` - Simplified Gazebo launch
- `gazebo_sim_headless.launch.py` - Headless simulation (no GUI)

## Usage

### Arm Simulation in Gazebo with Yanthra Move (4-Position Scanning)

**Complete simulation with motion control:**
```bash
source ~/pragati_ros2/install/setup.bash
ros2 launch yanthra_move simulation_complete.launch.py
```

This launches:
- Gazebo Harmonic with robot model
- Simulation bridge (converts joint commands to trajectory controller)
- Yanthra Move node with 4-position scanning (L1, L2, L3, L4)

The arm will automatically scan 4 positions:
- **L1**: -0.075m (left)
- **L2**: -0.025m (left-center)
- **L3**: +0.025m (right-center)
- **L4**: +0.075m (right) ← NEW POSITION

**Basic Gazebo simulation only:**
```bash
ros2 launch robot_description gazebo_sim.launch.py
```

Launch with RViz for visualization:
```bash
ros2 launch robot_description display_gazebo.launch.py
```

Control the arm joints manually:
```bash
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

### Publish Robot State
```bash
ros2 launch robot_description robot_state_publisher.launch.py
```

## Architecture

**Multi-Arm System:**
- 4 independent 3-DOF arms (expandable to 6)
- Each arm: base rotation + 2 segment joints
- Motors: MG6010E-i6 integrated servos
- Cameras: OAK-D Lite per arm

## TF Tree

```
base_link
├── arm_1_base
│   ├── arm_1_joint_1
│   ├── arm_1_joint_2
│   └── arm_1_joint_3
├── arm_2_base
...
└── camera_links (4×)
```

## Configuration

URDF parameters can be adjusted in:
- `urdf/pragati_robot.urdf.xacro`
- Configuration files in package

## Related Packages

- [`motor_control_ros2`](../motor_control_ros2/) - Motor control implementation
- [`yanthra_move`](../yanthra_move/) - Arm coordination and picking logic
- [`cotton_detection_ros2`](../cotton_detection_ros2/) - Vision and detection

## Note

This package was renamed from `robo_description` to `robot_description` on 2025-10-21 to fix naming typo.

## Documentation

For system-level documentation, see:
- [`docs/architecture/SYSTEM_ARCHITECTURE.md`](../../docs/architecture/SYSTEM_ARCHITECTURE.md)
- [`docs/production-system/01-SYSTEM_OVERVIEW.md`](../../docs/production-system/01-SYSTEM_OVERVIEW.md)

## License

See repository root LICENSE file.
