# vehicle_control Robot - Velocity-Based Kinematics Control

## Overview

The vehicle_control package implements velocity-based kinematics control for a three-wheeled robot, matching the algorithm from triwheel_robot. Each wheel has independent steering and drive control.

## Features

- ✅ **Velocity-based kinematics** (same algorithm as triwheel_robot)
- ✅ **Joystick control** with turbo mode
- ✅ **ROS2 cmd_vel** interface
- ✅ **Lightweight wheels** (17.6 kg from veh2 design)
- ✅ **Gazebo simulation** with ros_gz_bridge

## Quick Start

### 1. Build the Package

```bash
cd ~/steering\ control
colcon build --packages-select vehicle_control --symlink-install
source install/setup.bash
```

### 2. Launch Simulation

#### With Joystick Control (Recommended)
```bash
ros2 launch vehicle_control gazebo_with_joy.launch.py
```

#### Without Joystick
```bash
ros2 launch vehicle_control gazebo_with_joy.launch.py use_joystick:=false
```

Or use the basic launch file:
```bash
ros2 launch vehicle_control gazebo.launch.py
```

### 3. Run Kinematics Node (if not auto-started)

```bash
ros2 run vehicle_control kinematics_node.py
```

## Control Methods

### A. Joystick Control

**Requirements:**
- Install joy package: `sudo apt install ros-${ROS_DISTRO}-joy`
- Connect a game controller (Xbox, PS4, Logitech, etc.)

**Controls:**
- **Left Stick Y-axis**: Forward/Backward
- **Right Stick X-axis**: Rotate Left/Right
- **Button A (0)**: Toggle Turbo Mode (2x speed)
- **Button B (1)**: Emergency Stop

**Speed Settings:**
- Normal: 0.5 m/s linear, 1.0 rad/s angular
- Turbo: 1.0 m/s linear, 2.0 rad/s angular

### B. Command Line Control

Send velocity commands directly:

```bash
# Drive forward
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.3}, angular: {z: 0.0}}"

# Rotate in place
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.0}, angular: {z: 0.5}}"

# Drive forward while turning
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.3}, angular: {z: 0.3}}"

# Stop
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.0}, angular: {z: 0.0}}"
```

### C. Web UI Joystick Control

A browser-based joystick UI for real-time interactive control of the robot. Works from any browser on the same network, including mobile devices.

**Prerequisites:**
```bash
sudo apt install ros-jazzy-rosbridge-suite
```

**Setup & Launch:**

```bash
# Terminal 1: Launch Gazebo simulation
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch vehicle_control gazebo.launch.py

# Terminal 2: Launch Web UI (rosbridge + HTTP server)
./src/vehicle_control/simulation/gazebo/web_ui/launch_web_ui.sh
```

**Access the UI:**
- Open your browser: `http://localhost:8888`
- On WSL, use `localhost` (not the WSL IP) from Windows browser

**Features:**
- **Virtual Joystick** — drag to control linear.x (forward/back) and angular.z (turning)
- **E-Stop Button** — green = safe, red = stopped. Click to toggle. While active, publishes zero velocity and disables joystick
- **Speed Modes** — three presets:

  | Mode   | Max linear (m/s) | Max angular (rad/s) |
  |--------|------------------:|--------------------:|
  | Slow   | 0.2               | 0.3                 |
  | Medium | 0.5               | 0.8                 |
  | Fast   | 1.0               | 1.5                 |

- **Live Telemetry** — displays steering angles (deg), wheel velocities (rad/s), commanded velocity, and actual joint states from Gazebo
- **Connection Status** — shows Connected/Disconnected with auto-reconnect
- **Configurable Bridge URL** — defaults to `ws://localhost:9090`, editable in the UI

**Architecture:**
```
Browser (Windows/mobile)
  ├── nipplejs (virtual joystick)
  ├── roslibjs (WebSocket client)
  │
  └── WebSocket ──► rosbridge_server (port 9090)
                         │
                         ├── publishes /cmd_vel
                         └── subscribes /steering/*, /wheel/*, /joint_states
```

**Files:**
```
web_ui/
├── index.html          # Page layout
├── style.css           # Dark theme styling
├── app.js              # Joystick logic, ROS connection, telemetry
└── launch_web_ui.sh    # Starts rosbridge + HTTP server
```

**Ports:**
| Port | Service | Protocol |
|------|---------|----------|
| 8888 | Static file server (web UI) | HTTP |
| 9090 | rosbridge_server | WebSocket |

**Options:**
```bash
# Use different ports
HTTP_PORT=3000 ROSBRIDGE_PORT=9091 ./launch_web_ui.sh

# Skip rosbridge (if already running separately)
./launch_web_ui.sh --no-bridge
```

**Troubleshooting:**

| Problem | Solution |
|---------|----------|
| 404 Not Found | Port conflict — try a different port: `HTTP_PORT=3000 ./launch_web_ui.sh` |
| ERR_CONNECTION_TIMED_OUT | Use `http://localhost:8888` instead of WSL IP |
| UI loads but "Disconnected" | rosbridge not running — check `ss -tlnp \| grep 9090` |
| Joystick works but no telemetry | Gazebo/kinematics node not running |
| Port 8080 conflict | Gazebo's Embedthis server uses 8080 — that's why we default to 8888 |

### D. Keyboard Control (Legacy)

```bash
ros2 run vehicle_control wheel_controller.py
```

## Robot Configuration

### Wheel Positions (relative to rear axle center)
- **Front wheel**: x=1.3m, y=0.0m
- **Left rear wheel**: x=0.0m, y=0.9m
- **Right rear wheel**: x=0.0m, y=-0.9m

### Parameters
- **Wheel radius**: 0.2 m
- **Max steering angle**: ±90° (1.57 rad)
- **Max wheel speed**: 20 rad/s
- **Wheel mass**: 17.6 kg (from veh2 design)

## Kinematics Algorithm

The robot uses **velocity-based rigid-body kinematics** (same as triwheel_robot):

```python
# For each wheel at position (x, y):
vix = vx - omega * y  # Velocity x-component at wheel
viy = omega * x       # Velocity y-component at wheel

steering_angle = atan2(viy, vix)
wheel_speed = sqrt(vix² + viy²) / wheel_radius
```

This approach:
- ✅ Works correctly for asymmetric wheel configurations
- ✅ Avoids Ackermann steering assumptions
- ✅ Provides proper velocity composition at each wheel

## Troubleshooting

### Joystick not detected
```bash
# Check if joystick is connected
ls /dev/input/js*

# Test joystick
sudo jstest /dev/input/js0

# Grant permissions
sudo chmod a+rw /dev/input/js0
```

### Robot not moving
1. Check if kinematics node is running:
   ```bash
   ros2 node list | grep kinematics
   ```

2. Check topics:
   ```bash
   ros2 topic list
   ros2 topic echo /cmd_vel
   ros2 topic echo /steering/front
   ```

3. Verify Gazebo bridge:
   ```bash
   ros2 topic list | grep "/wheel\|/steering"
   ```

### Wheels oscillating
- The updated kinematics uses correct wheel positions from rear axle center
- Wheel radius is set to realistic 0.2m
- If still oscillating, check URDF joint configurations

## Differences from triwheel_robot

| Feature | triwheel_robot | vehicle_control |
|---------|---------------|------|
| Control System | ros2_control + ForwardCommandController | Direct Gazebo plugins |
| Topic Format | Float64MultiArray | Float64 |
| Wheel Mass | ~150 kg | ~17.6 kg |
| Joystick Support | ❌ No | ✅ Yes |
| Launch Integration | Separate nodes | Integrated launch file |

## Files Structure

```
vehicle_control/
├── vehicle_control/                      # Python package
│   ├── kinematics_node.py     # Main kinematics controller
│   ├── joy_teleop.py          # Joystick teleoperation
│   └── __init__.py
├── scripts/
│   └── wheel_controller.py    # Legacy keyboard control
├── launch/
│   ├── gazebo.launch.py       # Basic Gazebo launch
│   └── gazebo_with_joy.launch.py  # With joystick support
├── urdf/
│   └── vehicle.urdf           # Robot description
├── meshes/                    # STL mesh files
├── config/                    # Configuration files
├── CMakeLists.txt
└── package.xml
```

## Next Steps

1. **Tune Parameters**: Adjust speeds in launch file or via ROS parameters
2. **Add Sensors**: Integrate cameras, lidars to URDF
3. **Path Planning**: Use with nav2 for autonomous navigation
4. **Record Data**: Use `ros2 bag` to record test runs

## Support

For issues or questions:
- Check terminal output for error messages
- Verify all dependencies are installed
- Ensure workspace is sourced: `source install/setup.bash`
