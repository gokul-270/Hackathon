# 🎮 Gazebo Simulations — Pragati Robot

> Quick-start README for all Gazebo simulations in the Pragati cotton-picking robot project.
>
> 📖 For the **full guide** (installation, concepts, architecture, troubleshooting), see [docs/GAZEBO_SIMULATION_GUIDE.md](../docs/GAZEBO_SIMULATION_GUIDE.md).

---

## Prerequisites

| Requirement | Version |
|-------------|---------|
| Ubuntu | 24.04 LTS |
| ROS 2 | Jazzy |
| Gazebo | Harmonic (8.x) |

### Install All Dependencies (One Command)

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

### Verify

```bash
gz sim --version      # Should show 8.x
echo $ROS_DISTRO      # Should show jazzy
```

---

## Build

```bash
cd ~/pragati_ros2
colcon build --packages-select vehicle_control MG6010 robot_description --symlink-install
source install/setup.bash
```

---

## 🚗 Vehicle Simulation (Three-Wheeled Robot)

**Package:** `vehicle_control` · **World:** Cotton field

```bash
# Basic launch
ros2 launch vehicle_control gazebo.launch.py

# With joystick
ros2 launch vehicle_control gazebo_with_joy.launch.py

# With sensors + cotton plants
ros2 launch vehicle_control gazebo_sensors.launch.py

# Headless (no GUI)
ros2 launch vehicle_control gazebo.launch.py headless:=true

# Drive it
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.3}, angular: {z: 0.0}}"
```

**Web UI Control:** `./src/vehicle_control/simulation/gazebo/web_ui/launch_web_ui.sh` → open `http://localhost:8888`

---

## 🦾 Arm Simulation (MG6010)

**Package:** `MG6010` · **Joints:** 4 DOF

```bash
# Quick start
ros2 launch MG6010 mg6010_gazebo_simple.launch.py

# Full integration with yanthra_move
ros2 launch MG6010 mg6010_gazebo_yanthra.launch.py

# Test cotton picking sequence
ros2 run MG6010 ros_gazebo_control.py pick

# Manual joint control
ros2 topic pub /joint3_position_controller/command std_msgs/msg/Float64 "{data: -0.5}" --once
```

---

## 🤖 Full Robot Simulation (robot_description)

**Package:** `robot_description` · **Sensors:** Camera + IMU

```bash
# Launch simulation
ros2 launch robot_description gazebo_sim.launch.py

# With RViz
ros2 launch robot_description display_gazebo.launch.py

# Complete system (Gazebo + bridge + yanthra_move)
ros2 launch yanthra_move simulation_complete.launch.py

# View camera
ros2 run rqt_image_view rqt_image_view /camera/image_raw
```

---

## Quick Troubleshooting

| Issue | Fix |
|-------|-----|
| GUI crashes (snap/libpthread) | Use `headless:=true` or launch from system terminal |
| Robot invisible / white | Set `GZ_SIM_RESOURCE_PATH` (see full guide) |
| Robot not moving | Check `ros2 topic list \| grep steering` and `ros2 node list \| grep bridge` |
| "Package not found" | `colcon build` then `source install/setup.bash` |
| No joint states | Verify bridge: `ros2 topic hz /joint_states` |

---

## File Map

```
src/vehicle_control/simulation/gazebo/   ← Vehicle sim (worlds, launch, nodes, web UI)
src/MG6010/                              ← Arm sim (launch, URDF, scripts, controllers)
src/robot_description/                   ← Full robot sim (URDF, launch, worlds, config)
docs/GAZEBO_SIMULATION_GUIDE.md          ← Full documentation
```

---

## Useful Commands

```bash
gz topic -l                            # List Gazebo topics
ros2 topic list                        # List ROS 2 topics
ros2 topic echo /joint_states          # Monitor joints
ros2 control list_controllers          # Check controllers
ros2 bag record -a -o my_run           # Record everything
```

---

*See [docs/GAZEBO_SIMULATION_GUIDE.md](../docs/GAZEBO_SIMULATION_GUIDE.md) for the complete guide with installation details, bridge concFollow link (ctrl + click)

epts, architecture diagrams, and beginner tutorials.*
