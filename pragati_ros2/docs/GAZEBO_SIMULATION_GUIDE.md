# 🏗️ Gazebo Simulation Guide — Pragati ROS2 Project

> **Comprehensive guide for installing, configuring, and running Gazebo simulations in the Pragati cotton-picking robot project.**

---

## Table of Contents

1. [System Requirements](#1-system-requirements)
2. [Gazebo Installation](#2-gazebo-installation)
3. [ROS–Gazebo Bridge Installation](#3-rogazebo-bridge-installation)
4. [Verify Installation](#4-verify-installation)
5. [Project Simulation Overview](#5-project-simulation-overview)
6. [Simulation 1 — Vehicle (Three-Wheeled Robot)](#6-simulation-1--vehicle-three-wheeled-robot)
7. [Simulation 2 — Arm (MG6010 Robotic Arm)](#7-simulation-2--arm-mg6010-robotic-arm)
8. [Simulation 3 — Full Robot (robot_description)](#8-simulation-3--full-robot-robot_description)
9. [Beginner's Guide to Gazebo](#9-beginners-guide-to-gazebo)
10. [ROS–Gazebo Bridge Concepts](#10-rogazebo-bridge-concepts)
11. [Common Launch Arguments](#11-common-launch-arguments)
12. [Troubleshooting](#12-troubleshooting)
13. [Tips & Best Practices](#13-tips--best-practices)
14. [Useful Commands Cheat Sheet](#14-useful-commands-cheat-sheet)
15. [Architecture Diagrams](#15-architecture-diagrams)
16. [References](#16-references)

---

## 1. System Requirements

| Requirement        | Version / Spec                     |
|--------------------|------------------------------------|
| **OS**             | Ubuntu 24.04 LTS (Noble Numbat)    |
| **ROS 2**          | Jazzy Jalisco                      |
| **Gazebo**         | Harmonic (gz-sim 8.x)              |
| **Python**         | 3.12+                              |
| **GPU**            | OpenGL 3.3+ capable (recommended)  |
| **RAM**            | 8 GB minimum, 16 GB recommended    |
| **Disk**           | ~3 GB for Gazebo + ROS packages    |

> **Important:** ROS 2 Jazzy is paired with **Gazebo Harmonic**. Do NOT install Gazebo Fortress, Garden, or Classic — they are incompatible with Jazzy.

---

## 2. Gazebo Installation

### 2.1 Install Gazebo Harmonic via ROS 2 Packages (Recommended)

This is the simplest method — installs Gazebo Harmonic through the ROS 2 package manager:

```bash
# Update package list
sudo apt update

# Install Gazebo Harmonic (full desktop install)
sudo apt install ros-jazzy-ros-gz

# This meta-package installs:
#   - gz-sim8           (Gazebo Harmonic simulator)
#   - ros-gz-bridge     (ROS ↔ Gazebo message bridge)
#   - ros-gz-sim        (ROS launch integration)
#   - ros-gz-image      (Image transport bridge)
#   - ros-gz-interfaces (Shared message types)
```

### 2.2 Install Additional Simulation Packages

```bash
# ros2_control for joint/motor control in Gazebo
sudo apt install ros-jazzy-gz-ros2-control

# ros2_controllers (position, velocity, effort controllers)
sudo apt install ros-jazzy-ros2-controllers

# Controller manager
sudo apt install ros-jazzy-controller-manager

# Joint state broadcaster
sudo apt install ros-jazzy-joint-state-broadcaster

# Joint trajectory controller (used by arm simulation)
sudo apt install ros-jazzy-joint-trajectory-controller

# Robot state publisher & URDF tools
sudo apt install ros-jazzy-robot-state-publisher \
                 ros-jazzy-joint-state-publisher-gui \
                 ros-jazzy-xacro

# RViz for 3D visualization alongside Gazebo
sudo apt install ros-jazzy-rviz2

# Joystick support (for vehicle teleoperation)
sudo apt install ros-jazzy-joy

# Web-based rosbridge (for web UI joystick)
sudo apt install ros-jazzy-rosbridge-suite
```

### 2.3 One-Liner — Install Everything at Once

```bash
sudo apt update && sudo apt install -y \
  ros-jazzy-ros-gz \
  ros-jazzy-gz-ros2-control \
  ros-jazzy-ros2-controllers \
  ros-jazzy-controller-manager \
  ros-jazzy-joint-state-broadcaster \
  ros-jazzy-joint-trajectory-controller \
  ros-jazzy-robot-state-publisher \
  ros-jazzy-joint-state-publisher-gui \
  ros-jazzy-xacro \
  ros-jazzy-rviz2 \
  ros-jazzy-joy \
  ros-jazzy-rosbridge-suite \
  ros-jazzy-tf2-ros \
  ros-jazzy-rqt-image-view
```

---

## 3. ROS–Gazebo Bridge Installation

The bridge is already included in `ros-jazzy-ros-gz`, but here's what each bridge component does:

| Package               | Purpose                                                |
|-----------------------|--------------------------------------------------------|
| `ros_gz_bridge`       | Bidirectional topic/service bridge between ROS 2 and Gazebo Transport |
| `ros_gz_sim`          | Launch helpers to start `gz sim` from ROS 2 launch files |
| `ros_gz_image`        | Bridges Gazebo camera images to ROS 2 `sensor_msgs/Image` |
| `gz_ros2_control`     | Runs `ros2_control` hardware interfaces inside Gazebo  |

### Verify Bridge Installation

```bash
# Check ros_gz_bridge is installed
ros2 pkg list | grep ros_gz

# Expected output:
#   ros_gz_bridge
#   ros_gz_image
#   ros_gz_interfaces
#   ros_gz_sim
#   ros_gz_sim_demos

# Check gz_ros2_control
ros2 pkg list | grep gz_ros2_control
# Expected: gz_ros2_control
```

---

## 4. Verify Installation

Run these commands to confirm everything is installed correctly:

```bash
# 1. Check Gazebo version (should be 8.x Harmonic)
gz sim --version
# Expected: Gazebo Sim, version 8.10.0 (or similar 8.x)

# 2. Check ROS 2 distro
echo $ROS_DISTRO
# Expected: jazzy

# 3. Quick smoke test — launch empty world
gz sim -r empty.sdf
# Gazebo GUI should open with an empty ground plane
# Close with Ctrl+C

# 4. Test ROS-Gazebo integration
ros2 launch ros_gz_sim gz_sim.launch.py gz_args:="-r empty.sdf"
# Should launch Gazebo through ROS 2

# 5. Verify bridge executable exists
which parameter_bridge 2>/dev/null || ros2 pkg executables ros_gz_bridge
# Expected: ros_gz_bridge parameter_bridge
```

---

## 5. Project Simulation Overview

The Pragati project has **three simulation setups** that serve different purposes:

```
pragati_ros2/
├── src/
│   ├── vehicle_control/          ← 🚗 VEHICLE SIMULATION
│   │   └── simulation/
│   │       └── gazebo/
│   │           ├── launch/       (gazebo.launch.py, gazebo_with_joy.launch.py, gazebo_sensors.launch.py)
│   │           ├── worlds/       (cotton_field.sdf, cotton_field_with_plants.sdf)
│   │           ├── urdf/         (vehicle.urdf)
│   │           ├── models/       (cotton_plant_small/medium/tall)
│   │           ├── meshes/       (STL mesh files)
│   │           ├── nodes/        (kinematics, teleop, steering nodes)
│   │           ├── web_ui/       (browser-based joystick)
│   │           └── config/       (gazebo_gui.config)
│   │
│   ├── MG6010/                   ← 🦾 ARM SIMULATION
│   │   ├── launch/               (mg6010_gazebo_simple.launch.py, mg6010_gazebo_yanthra.launch.py, ...)
│   │   ├── urdf/                 (MG6010_gazebo.urdf, MG6010_gazebo_working.urdf)
│   │   ├── config/               (mg6010_controllers.yaml)
│   │   ├── meshes/               (STL mesh files for arm links)
│   │   └── scripts/              (gazebo_control.py, ros_gazebo_control.py, ...)
│   │
│   └── robot_description/        ← 🤖 FULL ROBOT (arm + sensors)
│       ├── launch/               (gazebo_sim.launch.py, display_gazebo.launch.py)
│       ├── urdf/                 (MG6010_gazebo.xacro, gazebo_plugins.xacro, ...)
│       ├── worlds/               (default.sdf)
│       └── config/               (controllers.yaml)
```

### Quick Summary

| Simulation | Package | What It Simulates | Primary Use |
|------------|---------|-------------------|-------------|
| **Vehicle** | `vehicle_control` | Three-wheeled robot driving in cotton field | Test vehicle kinematics, steering, navigation |
| **Arm** | `MG6010` | 4-DOF robotic arm with joint controllers | Test arm movements, cotton picking sequences |
| **Full Robot** | `robot_description` | Combined arm + sensors (camera, IMU) | Full system integration testing |

---

## 6. Simulation 1 — Vehicle (Three-Wheeled Robot)

### What It Does

Simulates the Pragati three-wheeled robot driving through a virtual cotton field. Features:
- Three independent steerable/drivable wheels
- Velocity-based kinematics (same algorithm as real hardware)
- Joystick, keyboard, web UI, and `cmd_vel` control
- Cotton field worlds with plant models
- Overhead camera for video recording

### 6.1 Build the Package

```bash
cd ~/pragati_ros2
colcon build --packages-select vehicle_control --symlink-install
source install/setup.bash
```

### 6.2 Launch Options

#### A. Basic Launch (Recommended Starting Point)

```bash
ros2 launch vehicle_control gazebo.launch.py
```

#### B. With Joystick Control

```bash
# Connect a game controller first, then:
ros2 launch vehicle_control gazebo_with_joy.launch.py
```

- **Left Stick Y-axis** → Forward/Backward
- **Right Stick X-axis** → Rotate Left/Right
- **Button A (0)** → Toggle Turbo Mode (2× speed)
- **Button B (1)** → Emergency Stop

#### C. With Sensors & Cotton Plants

```bash
ros2 launch vehicle_control gazebo_sensors.launch.py
```

This loads `cotton_field_with_plants.sdf` — a world with cotton plant models, IMU, GPS, camera, and odometry bridges.

#### D. Headless Mode (No GUI — for CI/SSH)

```bash
ros2 launch vehicle_control gazebo.launch.py headless:=true
```

#### E. With Ackermann Steering

```bash
ros2 launch vehicle_control gazebo.launch.py ackermann:=true
```

### 6.3 Drive the Robot

```bash
# Drive forward
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.3}, angular: {z: 0.0}}"

# Rotate in place
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.0}, angular: {z: 0.5}}"

# Arc turn
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.3}, angular: {z: 0.3}}"

# Stop
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.0}, angular: {z: 0.0}}"
```

### 6.4 Web UI Joystick (Browser Control)

Control the robot from any browser (including mobile):

```bash
# Terminal 1: Launch simulation
ros2 launch vehicle_control gazebo.launch.py

# Terminal 2: Start web UI
./src/vehicle_control/simulation/gazebo/web_ui/launch_web_ui.sh

# Open browser → http://localhost:8888
```

### 6.5 Key Topics

| Topic | Type | Direction | Purpose |
|-------|------|-----------|---------|
| `/cmd_vel` | Twist | → Gazebo | Velocity commands |
| `/joint_states` | JointState | ← Gazebo | Current wheel/steering states |
| `/wheel/front/velocity` | Float64 | → Gazebo | Front wheel drive speed |
| `/wheel/left/velocity` | Float64 | → Gazebo | Left wheel drive speed |
| `/wheel/right/velocity` | Float64 | → Gazebo | Right wheel drive speed |
| `/steering/front` | Float64 | → Gazebo | Front wheel steering angle |
| `/steering/left` | Float64 | → Gazebo | Left wheel steering angle |
| `/steering/right` | Float64 | → Gazebo | Right wheel steering angle |
| `/clock` | Clock | ← Gazebo | Simulation time |

### 6.6 Robot Configuration

| Parameter | Value |
|-----------|-------|
| Wheel radius | 0.2875 m |
| Max steering angle | ±90° (1.57 rad) |
| Max wheel speed | 20 rad/s |
| Wheel mass | 17.6 kg |
| Front wheel position | x=1.3 m, y=0.0 m |
| Left rear wheel | x=0.0 m, y=0.9 m |
| Right rear wheel | x=0.0 m, y=-0.9 m |

---

## 7. Simulation 2 — Arm (MG6010 Robotic Arm)

### What It Does

Simulates the MG6010 4-DOF robotic arm for testing cotton picking operations. Features:
- Position control on all 4 joints
- Integration with `yanthra_move` arm controller
- Automated cotton picking sequences
- `ros2_control` with `gz_ros2_control`

### 7.1 Build the Package

```bash
cd ~/pragati_ros2
colcon build --packages-select MG6010 --symlink-install
source install/setup.bash
```

### 7.2 Launch Options

#### A. Simple Visualization (Quick Start)

```bash
ros2 launch MG6010 mg6010_gazebo_simple.launch.py
```

#### B. Full Integration with Yanthra Move (Recommended)

```bash
# Terminal 1: Start Gazebo with controllers
ros2 launch MG6010 mg6010_gazebo_yanthra.launch.py

# Terminal 2: Start yanthra_move in simulation mode
ros2 launch yanthra_move pragati_complete.launch.py simulation:=true
```

#### C. Headless Mode

```bash
ros2 launch MG6010 mg6010_gazebo_headless.launch.py
```

#### D. With RViz

```bash
ros2 launch MG6010 mg6010_gazebo_rviz.launch.py
```

### 7.3 Control the Arm

#### Automated Picking Sequence

```bash
# Run the full cotton picking sequence
ros2 run MG6010 ros_gazebo_control.py pick

# Move individual joint
ros2 run MG6010 ros_gazebo_control.py move joint3 -0.5

# Return to home position
ros2 run MG6010 ros_gazebo_control.py home
```

#### Manual Joint Commands

```bash
# Move base rotation (joint2)
ros2 topic pub /joint2_position_controller/command std_msgs/msg/Float64 "{data: 0.20}" --once

# Lower arm (joint3)
ros2 topic pub /joint3_position_controller/command std_msgs/msg/Float64 "{data: -0.5}" --once

# Adjust vertical (joint4)
ros2 topic pub /joint4_position_controller/command std_msgs/msg/Float64 "{data: -0.1}" --once

# Extend arm (joint5)
ros2 topic pub /joint5_position_controller/command std_msgs/msg/Float64 "{data: 0.3}" --once
```

#### Test Movement Script

```bash
python3 src/MG6010/scripts/test_mg6010_movement.py
```

### 7.4 Joint Limits

| Joint | Type | Min | Max | Description |
|-------|------|-----|-----|-------------|
| joint2 | Revolute | 0.1 rad | 0.32 rad | Base rotation |
| joint3 | Revolute | -0.9 rad | 0.0 rad | Shoulder angle |
| joint4 | Prismatic | -0.35 m | 0.25 m | Vertical movement |
| joint5 | Prismatic | 0.0 m | 0.75 m | Arm extension |

### 7.5 Key Topics

| Topic | Type | Purpose |
|-------|------|---------|
| `/joint2_position_controller/command` | Float64 | Base rotation command |
| `/joint3_position_controller/command` | Float64 | Arm angle command |
| `/joint4_position_controller/command` | Float64 | Vertical position command |
| `/joint5_position_controller/command` | Float64 | Extension command |
| `/joint_states` | JointState | Current joint positions/velocities |

### 7.6 Cotton Picking Sequence

The automated picking cycle:
1. Rotate base to position (`joint2: 0.20`)
2. Lower arm (`joint3: -0.5`)
3. Adjust vertical position (`joint4: -0.1`)
4. Extend arm to cotton (`joint5: 0.3`)
5. Retract to pick (`joint5: 0.1`)
6. Return to home position

---

## 8. Simulation 3 — Full Robot (robot_description)

### What It Does

Provides the complete robot model with sensors for full system integration testing:
- 5 controllable joints (including gripper)
- RGB Camera (1280×720 @ 30 Hz)
- IMU Sensor (100 Hz)
- Cotton field environment
- Compatible with `yanthra_move` + `cotton_detection`

### 8.1 Launch

```bash
cd ~/pragati_ros2
source install/setup.bash

# Basic simulation
ros2 launch robot_description gazebo_sim.launch.py

# With RViz
ros2 launch robot_description display_gazebo.launch.py
```

### 8.2 Complete Simulation (with Yanthra Move)

```bash
# All-in-one launch (Gazebo + bridge + yanthra_move)
ros2 launch yanthra_move simulation_complete.launch.py
```

### 8.3 Control via Joint Trajectory

```bash
ros2 action send_goal /joint_trajectory_controller/follow_joint_trajectory \
  control_msgs/action/FollowJointTrajectory \
  "{
    trajectory: {
      joint_names: ['joint 2', 'joint 3', 'joint 4', 'joint 5', 'joint 7'],
      points: [{
        positions: [0.25, 0.5, 0.1, 0.0, 0.02],
        time_from_start: {sec: 2}
      }]
    }
  }"
```

### 8.4 View Camera Feed

```bash
ros2 run rqt_image_view rqt_image_view /camera/image_raw
```

### 8.5 Published Topics

| Topic | Type | Rate | Description |
|-------|------|------|-------------|
| `/joint_states` | JointState | 100 Hz | Joint positions/velocities |
| `/camera/image_raw` | Image | 30 Hz | RGB camera feed |
| `/camera/camera_info` | CameraInfo | 30 Hz | Camera intrinsics |
| `/imu` | Imu | 100 Hz | IMU measurements |
| `/clock` | Clock | 1 kHz | Simulation time |
| `/tf`, `/tf_static` | TFMessage | Varies | Transform tree |

---

## 9. Beginner's Guide to Gazebo

### 9.1 What Is Gazebo?

Gazebo is a **3D robot simulation tool**. It provides:
- **Physics engine** — gravity, friction, collisions, joint dynamics
- **Sensor simulation** — cameras, IMUs, GPS, lidar
- **3D rendering** — see your robot in a virtual world
- **ROS 2 integration** — control the simulated robot the exact same way as the real one

### 9.2 Key Concepts

| Concept | Description |
|---------|-------------|
| **World (`.sdf`)** | Defines the environment — ground, sky, lights, objects |
| **Model** | A robot or object — defined via URDF or SDF with links and joints |
| **Link** | A rigid body (e.g., a wheel, arm segment, chassis) |
| **Joint** | Connection between two links (revolute, prismatic, fixed) |
| **Plugin** | Adds behavior — physics, sensors, controllers |
| **Topic** | Gazebo's internal pub/sub messaging (separate from ROS topics) |
| **Bridge** | Converts between Gazebo topics ↔ ROS 2 topics |

### 9.3 How Gazebo + ROS 2 Work Together

```
┌──────────────────────────────────┐     ┌───────────────────────────┐
│         ROS 2 World              │     │      Gazebo World         │
│                                  │     │                           │
│  Your Nodes ──► /cmd_vel         │     │  Physics Engine           │
│  (python/C++)                    │     │  Sensor Simulation        │
│                                  │     │  3D Rendering             │
│  /joint_states ◄── Your Nodes   │     │                           │
└──────────┬───────────────────────┘     └─────────┬─────────────────┘
           │                                       │
           │        ┌───────────────────┐          │
           └───────►│   ros_gz_bridge   │◄─────────┘
                    │  (parameter_bridge)│
                    └───────────────────┘
                    Converts messages between
                    ROS 2 ↔ Gazebo Transport
```

### 9.4 Gazebo GUI Basics

When you launch Gazebo with a GUI:

1. **Navigate the 3D view:**
   - **Left-click + drag** → Rotate camera
   - **Right-click + drag** → Pan camera
   - **Scroll wheel** → Zoom in/out
   - **Middle-click + drag** → Pan

2. **Key panels:**
   - **Entity Tree** (left) → Shows all models in the world
   - **Component Inspector** (right) → Properties of selected entity
   - **Playback controls** (bottom) → Play, pause, step simulation

3. **Useful shortcuts:**
   - `Esc` → Select mode
   - `T` → Translate mode
   - `R` → Rotate mode

### 9.5 File Formats

| Format | Used For | Example |
|--------|----------|---------|
| `.sdf` | Gazebo world/model files | `cotton_field.sdf` |
| `.urdf` | ROS robot description | `vehicle.urdf` |
| `.xacro` | Parametric URDF (macros) | `MG6010_gazebo.xacro` |
| `.stl` | 3D mesh geometry | `front-wheel.stl` |
| `.yaml` | Controller configuration | `mg6010_controllers.yaml` |

### 9.6 Your First Steps

1. **Just launch and look:**
   ```bash
   gz sim -r empty.sdf
   ```

2. **Explore Gazebo topics:**
   ```bash
   gz topic -l          # List all Gazebo topics
   gz topic -e -t /clock # Echo a topic
   ```

3. **Spawn a simple shape:**
   ```bash
   gz service -s /world/empty/create \
     --reqtype gz.msgs.EntityFactory \
     --reptype gz.msgs.Boolean \
     --timeout 1000 \
     --req 'sdf: "<sdf version=\"1.9\"><model name=\"box\"><static>true</static><link name=\"link\"><visual name=\"v\"><geometry><box><size>1 1 1</size></box></geometry></visual></link></model></sdf>"'
   ```

4. **Launch our simulation:**
   ```bash
   cd ~/pragati_ros2
   source install/setup.bash
   ros2 launch vehicle_control gazebo.launch.py
   ```

---

## 10. ROS–Gazebo Bridge Concepts

### 10.1 How the Bridge Works

The `ros_gz_bridge` converts messages between ROS 2 and Gazebo Transport. The syntax:

```
/topic_name@ros_msg_type[direction]gz_msg_type
```

**Direction symbols:**
| Symbol | Direction |
|--------|-----------|
| `@` | Bidirectional (both ways) |
| `[` | Gazebo → ROS 2 (subscribe from Gazebo, publish to ROS) |
| `]` | ROS 2 → Gazebo (subscribe from ROS, publish to Gazebo) |

### 10.2 Examples from Our Project

```python
# Clock: Gazebo → ROS 2 only
'/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock'

# Wheel velocity: ROS 2 → Gazebo only
'/wheel/front/velocity@std_msgs/msg/Float64]gz.msgs.Double'

# Joint states: Gazebo → ROS 2
'/joint_states@sensor_msgs/msg/JointState[gz.msgs.Model'

# Joint command: Bidirectional
'/joint2_cmd@std_msgs/msg/Float64@gz.msgs.Double'
```

### 10.3 Common Message Mappings

| ROS 2 Message | Gazebo Message | Use Case |
|---------------|----------------|----------|
| `rosgraph_msgs/msg/Clock` | `gz.msgs.Clock` | Simulation time |
| `std_msgs/msg/Float64` | `gz.msgs.Double` | Joint commands, velocities |
| `sensor_msgs/msg/JointState` | `gz.msgs.Model` | Joint feedback |
| `sensor_msgs/msg/Image` | `gz.msgs.Image` | Camera images |
| `sensor_msgs/msg/Imu` | `gz.msgs.IMU` | IMU data |
| `geometry_msgs/msg/Twist` | `gz.msgs.Twist` | Velocity commands |

---

## 11. Common Launch Arguments

### Vehicle Simulation

```bash
ros2 launch vehicle_control gazebo.launch.py \
  headless:=false \      # true = no GUI (server only)
  ackermann:=false \     # true = Ackermann steering mode
  world:=empty \         # empty or cotton_field
  use_sim_time:=true     # Use Gazebo clock
```

### Arm Simulation

```bash
ros2 launch MG6010 mg6010_gazebo_yanthra.launch.py \
  use_sim_time:=true     # Use Gazebo clock
```

### Full Robot

```bash
ros2 launch robot_description gazebo_sim.launch.py \
  use_sim_time:=true \
  x:=0.0 y:=0.0 z:=0.5 \   # Spawn position
  roll:=0.0 pitch:=0.0 yaw:=0.0  # Spawn orientation
```

---

## 12. Troubleshooting

### Problem: Gazebo GUI Crashes (libpthread/snap error)

**Cause:** VS Code snap injects environment variables that conflict with Gazebo's GUI.

**Solutions:**
```bash
# Option 1: Use headless mode
ros2 launch vehicle_control gazebo.launch.py headless:=true

# Option 2: Launch from a non-snap terminal (e.g., GNOME Terminal)
# Close VS Code terminal, open system terminal, then launch

# Option 3: The vehicle launch file already handles this automatically
# by unsetting snap-injected variables (GTK_PATH, LD_PRELOAD, etc.)
```

### Problem: Robot Doesn't Appear in Gazebo

```bash
# Check if spawn succeeded
gz model -l

# Verify URDF is published
ros2 topic echo /robot_description --once

# Check Gazebo resource path
echo $GZ_SIM_RESOURCE_PATH
```

### Problem: Robot Not Moving

```bash
# Vehicle: Check if commands reach Gazebo
ros2 topic echo /cmd_vel
ros2 topic echo /steering/front
ros2 topic list | grep "/wheel\|/steering"

# Arm: Check controllers
ros2 control list_controllers
ros2 control list_hardware_interfaces

# Check bridge is running
ros2 node list | grep bridge
```

### Problem: No Joint States

```bash
# Check joint_states topic
ros2 topic echo /joint_states

# Verify bridge is translating
ros2 topic hz /joint_states

# Check Gazebo-side joint states
gz topic -e -t /world/empty/model/mg6010/joint_state
```

### Problem: "Package not found" Error

```bash
# Rebuild the workspace
cd ~/pragati_ros2
colcon build --packages-select vehicle_control MG6010 robot_description --symlink-install
source install/setup.bash
```

### Problem: Meshes Not Loading (White/Invisible Robot)

```bash
# Set resource path manually
export GZ_SIM_RESOURCE_PATH=$GZ_SIM_RESOURCE_PATH:~/pragati_ros2/install/share

# For vehicle_control:
export GZ_SIM_RESOURCE_PATH=$GZ_SIM_RESOURCE_PATH:$(ros2 pkg prefix vehicle_control)/share

# For MG6010:
export GZ_SIM_RESOURCE_PATH=$GZ_SIM_RESOURCE_PATH:$(ros2 pkg prefix MG6010)/share
```

### Problem: Slow Simulation / Low FPS

```bash
# Run headless (no rendering overhead)
ros2 launch vehicle_control gazebo.launch.py headless:=true

# Reduce physics update rate (edit world SDF)
# Change <max_step_size>0.001</max_step_size> to 0.002

# Check system load
htop
nvidia-smi   # If using NVIDIA GPU
```

---

## 13. Tips & Best Practices

### Development Workflow

1. **Always source before launching:**
   ```bash
   source /opt/ros/jazzy/setup.bash
   source ~/pragati_ros2/install/setup.bash
   ```

2. **Use symlink-install for faster iteration:**
   ```bash
   colcon build --packages-select <pkg> --symlink-install
   ```

3. **Record simulation runs for replay:**
   ```bash
   ros2 bag record -a -o my_sim_run
   ros2 bag play my_sim_run
   ```

4. **Use RViz alongside Gazebo** for TF tree debugging:
   ```bash
   rviz2 &
   # Add displays: TF, RobotModel, Image
   ```

5. **Check logs when things go wrong:**
   ```bash
   # Gazebo logs
   tail -f ~/.gz/sim/log/*/server_console.log

   # ROS logs
   ros2 topic echo /rosout
   ```

### Performance Tips

- Use **headless mode** when you don't need the GUI
- Run the **server and GUI as separate processes** (our vehicle launch already does this)
- Use **simple collision geometries** (boxes, cylinders) instead of full meshes
- Set `use_sim_time: false` if clock synchronization is not critical

---

## 14. Useful Commands Cheat Sheet

### Gazebo Commands

```bash
gz sim --version                       # Check version
gz sim -r empty.sdf                    # Launch empty world
gz sim -s -r empty.sdf                 # Server only (no GUI)
gz sim -g                              # Launch GUI client only
gz topic -l                            # List all Gazebo topics
gz topic -e -t /topic_name             # Echo a Gazebo topic
gz topic -i -t /topic_name             # Info about a topic
gz model -l                            # List spawned models
gz service -l                          # List Gazebo services
```

### ROS 2 + Simulation Commands

```bash
ros2 topic list                        # List all ROS 2 topics
ros2 topic echo /joint_states          # Monitor joint states
ros2 topic hz /topic_name              # Check publish rate
ros2 node list                         # List running nodes
ros2 control list_controllers          # List active controllers
ros2 control list_hardware_interfaces  # List HW interfaces
ros2 param list                        # List all parameters
ros2 run rqt_image_view rqt_image_view # View camera feed
```

### Build & Launch

```bash
# Build all simulation packages
colcon build --packages-select vehicle_control MG6010 robot_description --symlink-install

# Source workspace
source install/setup.bash

# Vehicle simulation
ros2 launch vehicle_control gazebo.launch.py
ros2 launch vehicle_control gazebo_with_joy.launch.py
ros2 launch vehicle_control gazebo_sensors.launch.py

# Arm simulation
ros2 launch MG6010 mg6010_gazebo_simple.launch.py
ros2 launch MG6010 mg6010_gazebo_yanthra.launch.py

# Full robot simulation
ros2 launch robot_description gazebo_sim.launch.py
ros2 launch yanthra_move simulation_complete.launch.py
```

---

## 15. Architecture Diagrams

### Vehicle Simulation Architecture

```
┌─────────────────────────────┐
│      User Input             │
│  (Joystick / Keyboard /     │
│   Web UI / cmd_vel)         │
└─────────────┬───────────────┘
              │ /cmd_vel (Twist)
              ▼
┌─────────────────────────────┐
│   Kinematics Node           │
│  (velocity → per-wheel      │
│   steering + drive)         │
└──────┬──────────────┬───────┘
       │              │
       ▼              ▼
  /steering/*    /wheel/*/velocity
  (Float64)      (Float64)
       │              │
       ▼              ▼
┌─────────────────────────────┐
│      ros_gz_bridge          │
│   (ROS 2 → Gazebo Transport)│
└─────────────┬───────────────┘
              ▼
┌─────────────────────────────┐
│    Gazebo Harmonic          │
│  (Physics, 3D, Sensors)     │
│                             │
│  ┌─────────────────────┐    │
│  │ Vehicle URDF Model  │    │
│  │ 3 wheels + chassis  │    │
│  └─────────────────────┘    │
└─────────────────────────────┘
```

### Arm Simulation Architecture

```
┌─────────────────────────────┐
│    Yanthra Move / Manual    │
│  (Arm control system)       │
└─────────────┬───────────────┘
              │ /jointN_position_controller/command (Float64)
              ▼
┌─────────────────────────────┐
│   ros2_control Controllers  │
│  (Position controllers ×4)  │
│  via gz_ros2_control plugin │
└─────────────┬───────────────┘
              ▼
┌─────────────────────────────┐
│    Gazebo Harmonic          │
│                             │
│  ┌─────────────────────┐    │
│  │ MG6010 URDF Model   │    │
│  │ 4 joints + gripper  │    │
│  └─────────────────────┘    │
└─────────────────────────────┘
```

---

## 16. References

| Resource | URL |
|----------|-----|
| Gazebo Harmonic Docs | https://gazebosim.org/docs/harmonic |
| ROS 2 Jazzy + Gazebo | https://gazebosim.org/docs/harmonic/ros2_integration |
| ros_gz_bridge | https://github.com/gazebosim/ros_gz |
| gz_ros2_control | https://github.com/ros-controls/gz_ros2_control |
| SDF Format Spec | http://sdformat.org/spec |
| URDF Tutorials | https://docs.ros.org/en/jazzy/Tutorials/Intermediate/URDF/ |
| ros2_control Docs | https://control.ros.org/jazzy/ |

---

*Last updated: February 2026*
*Compatible with: ROS 2 Jazzy + Gazebo Harmonic 8.10.0*
