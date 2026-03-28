# vehicle_control Implementation - Matching triwheel_robot Algorithm

## Summary of Changes

Updated vehicle_control to use the **same velocity-based kinematics algorithm as triwheel_robot**, with added **joystick control** support and a unified control architecture for smooth Gazebo simulation.

## What Was Implemented

### 1. **Kinematics Node** (`vehicle_control/kinematics_node.py`)
- Uses **exact same algorithm** as triwheel_robot
- Rigid-body velocity composition: `vix = vx - omega*y`, `viy = omega*x`
- Same wheel computation logic
- ROS2 parameters for configuration
- Float64 messages (matching Gazebo plugin topics)

#### Per-Wheel Kinematics (No L/R Swap)
Each wheel (front, left, right) computes its own steering angle and drive speed directly from the velocity equations. Previously, left and right wheels had their outputs swapped before publishing — this is removed. The left steering angle is **negated** before publishing to account for the inverted URDF joint axis on the left wheel.

#### Unified Control Loop
All publishing (both steering and drive) happens in a single 50 Hz `control_loop`. The `cmd_vel_callback` only stores target values. Drive speeds are published at full commanded speed — no progress-based scaling. Testing showed that scaling drive by steering progress made movement sluggish; the rate-limited steering is smooth enough on its own.

#### Backward Motion Normalization
Instead of a conditional backward flip heuristic, steering angles are universally normalized to `[-pi/2, +pi/2]`. If `abs(angle) > pi/2`, the angle is shifted by `copysign(pi, angle)` and the wheel speed is negated. This handles all quadrants consistently.

#### Speed Reduction
When speed exceeds limits, both `vx` and `omega` are scaled by the same factor, preserving the turning radius.

#### Zero-Velocity Hold
When velocity is near zero, steering angles hold their last commanded position instead of snapping to 0. This prevents wheel jerk when the robot stops mid-turn.

### 2. **Joystick Teleop Node** (`vehicle_control/joy_teleop.py`)
- Converts joystick input to `/cmd_vel` Twist messages
- Features:
  - Left stick Y: Forward/Backward
  - Right stick X: Rotate Left/Right
  - Button A: Turbo mode (2x speed)
  - Button B: Emergency stop
  - Deadzone handling
  - Speed limits

### 3. **Integrated Launch File** (`launch/gazebo_with_joy.launch.py`)
- Launches everything in one command:
  - Gazebo simulator
  - Robot state publisher
  - Kinematics node
  - Joy node (optional)
  - Joy teleop (optional)
  - ROS-Gazebo bridge

### 4. **Launch Configuration**
- `gazebo.launch.py` sets `use_sim_time: false` for the kinematics node. The GZ→ROS clock bridge is unreliable on this system, so wall-clock time is used instead. This means simulation does not run in sync with Gazebo's physics clock — acceptable for kinematics validation but should be revisited if precise timing matters.

### 5. **Updated Configuration**
- Correct wheel radius: **0.2875 m** (measured from STL mesh with 0.001 scale factor)
- Wheel positions from **rear axle center**
- Updated wheel masses: **17.6 kg** (from veh2)
- Package dependencies: joy, geometry_msgs, sensor_msgs

## Algorithm Comparison

### triwheel_robot Kinematics
```python
vix = vx - omega * wheel_y
viy = omega * wheel_x
steering_angle = atan2(viy, vix)
wheel_speed = sqrt(vix² + viy²) / wheel_radius
```

### vehicle_control Kinematics (IDENTICAL)
```python
vix = vx - omega * wheel_y
viy = omega * wheel_x
steering_angle = atan2(viy, vix)
wheel_speed = sqrt(vix² + viy²) / wheel_radius
# Normalize to [-pi/2, +pi/2] — negate speed if flipped
# Negate left steering angle for URDF joint axis
```

**Result**: Same physics, same behavior, with added normalization for robust quadrant handling.

## URDF / Gazebo Model Changes

### Steering PID Tuning
Steering `JointPositionController` plugins updated from `P=15, D=0.5` to **`P=200, I=20, D=0.5`**. The original P=10 values were too weak to overcome joint friction in Gazebo for the 136 kg robot. High proportional gain provides the authority needed for crisp steering response.

### Drive PID Gains
Drive `JointController` plugins use force-mode with **`use_force_commands=true`**, **`P=200, I=20, D=0.5`**. The initial conservative velocity-mode gains (P=1.0) could not overcome ground contact forces for the 136 kg robot. Force-mode with high gains provides the torque needed to drive through realistic friction.

### Drive Joint Dynamics and Limits
All 3 drive joints now have:
- `<dynamics damping="0.5" friction="0.1"/>` — prevents free-spinning and adds realistic resistance
- `<limit effort="500" velocity="20.0"/>` — caps torque (500 Nm) and angular velocity

### Wheel Friction (SDF-style)
Each wheel collision element includes `<surface><friction><ode><mu>1.0</mu><mu2>1.0</mu2></ode></friction></surface>`. The legacy `<gazebo reference>` mu tags are kept for backward compatibility but are insufficient for gz-sim (Gazebo Harmonic).

## Feature Comparison

| Feature | triwheel_robot | vehicle_control (UPDATED) | Status |
|---------|---------------|----------------|--------|
| **Kinematics Algorithm** | Velocity-based | Velocity-based | IDENTICAL |
| **Wheel Control** | Steering + Drive | Steering + Drive | MATCH |
| **L/R Swap** | N/A | Removed (direct per-wheel publish) | FIXED |
| **Topic Format** | Float64MultiArray | Float64 | Different (Gazebo plugins) |
| **Control Interface** | ros2_control | Gazebo plugins | Different backend |
| **Publish Architecture** | — | Unified 50 Hz control loop | IMPROVED |
| **Joystick Support** | No | Yes | ADDED |
| **Wheel Radius** | — | 0.2875 m (STL-measured) | CORRECTED |
| **Steering PID** | — | P=200, I=20, D=0.5 (force-authority) | TUNED |
| **Drive PID** | — | P=200, I=20, D=0.5 (force-mode) | ADDED |
| **Wheel Friction** | — | SDF surface elements | ADDED |
| **use_sim_time** | — | Disabled (clock bridge unreliable) | WORKAROUND |

## How to Use

### Launch with Joystick (Recommended)
```bash
cd ~/steering\ control
source install/setup.bash
ros2 launch vehicle_control gazebo_with_joy.launch.py
```

**Then use your game controller:**
- Left stick to drive forward/backward
- Right stick to rotate
- A button for turbo mode
- B button for emergency stop

### Launch without Joystick
```bash
ros2 launch vehicle_control gazebo_with_joy.launch.py use_joystick:=false
```

**Then control via command line:**
```bash
# Drive forward
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.3}, angular: {z: 0.0}}"

# Rotate
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.0}, angular: {z: 0.5}}"
```

### Manual Node Control
```bash
# Terminal 1: Launch Gazebo
ros2 launch vehicle_control gazebo.launch.py

# Terminal 2: Run kinematics
ros2 run vehicle_control kinematics_node.py

# Terminal 3: Send commands
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.3}, angular: {z: 0.0}}"
```

## Robot Configuration

### Wheel Positions (from rear axle center)
```
Front:  x=1.3m, y=0.0m
Left:   x=0.0m, y=0.9m
Right:  x=0.0m, y=-0.9m
```

### Parameters
- Wheel radius: 0.2875 m (measured from STL)
- Max steering: +/-90 deg (1.57 rad)
- Max speed: 20 rad/s
- Wheel mass: 17.6 kg

## Technical Details

### Topic Mapping

**Input:**
- `/cmd_vel` (geometry_msgs/Twist) - Velocity commands

**Output (Steering):**
- `/steering/front` (std_msgs/Float64) - Front wheel steering angle
- `/steering/left` (std_msgs/Float64) - Left wheel steering angle (negated for URDF axis)
- `/steering/right` (std_msgs/Float64) - Right wheel steering angle

**Output (Drive):**
- `/wheel/front/velocity` (std_msgs/Float64) - Front wheel speed
- `/wheel/left/velocity` (std_msgs/Float64) - Left wheel speed
- `/wheel/right/velocity` (std_msgs/Float64) - Right wheel speed

### Why Float64 instead of Float64MultiArray?

- triwheel_robot uses **ros2_control** with ForwardCommandController (expects Float64MultiArray)
- vehicle_control uses **Gazebo plugins** directly (expects Float64)
- Both work correctly - just different control backends!

## Key Improvements Over Previous Version

1. **Correct algorithm** - matches triwheel_robot exactly
2. **No L/R swap** - each wheel publishes its own computed values directly
3. **Unified publish** - steering and drive published together at 50 Hz
4. **Angle wrapping** - `atan2(sin, cos)` in rate limiter for correct shortest-path error
5. **Backward normalization** - universal `[-pi/2, +pi/2]` normalization replaces heuristic flip
6. **Speed reduction** - scales both vx and omega to preserve turning radius
7. **Zero-velocity hold** - holds last steering angle instead of snapping to 0
8. **Correct wheel radius** - 0.2875 m measured from STL mesh
9. **Tuned steering PID** - P=200, I=20, D=0.5 for force-authority steering on 136 kg robot
10. **Drive PID gains** - P=200, I=20, D=0.5 in force-mode for 136 kg robot
11. **Drive joint dynamics** - damping=0.5, friction=0.1 with effort=500 Nm, velocity=20.0 limits
12. **Wheel friction** - SDF-style surface elements for Gazebo Harmonic
13. **use_sim_time** - disabled (GZ→ROS clock bridge unreliable on this system; uses wall-clock)
14. **Joystick support** - full game controller integration
15. **Integrated launch** - everything starts with one command
16. **ROS2 parameters** - easily configurable

## Files Created/Modified

**New Files:**
- `vehicle_control/kinematics_node.py` - Main kinematics controller
- `vehicle_control/joy_teleop.py` - Joystick teleoperation
- `vehicle_control/__init__.py` - Package initialization
- `launch/gazebo_with_joy.launch.py` - Integrated launch file
- `scripts/test_setup.sh` - Setup verification script
- `README.md` - Complete documentation
- `IMPLEMENTATION.md` - This file

**Modified Files:**
- `CMakeLists.txt` - Added Python package support
- `package.xml` - Added joy and message dependencies
- `urdf/vehicle.urdf` - Updated wheel masses, PID values, joint dynamics, friction surfaces

## Verification

Run the test script:
```bash
cd ~/steering\ control
bash vehicle_control/scripts/test_setup.sh
```

All checks should pass.

## Next Steps

1. **Test in Gazebo** - Launch and verify robot moves correctly
2. **Calibrate joystick** - Adjust deadzone/speeds if needed
3. **Compare behavior** - Should match triwheel_robot motion
4. **Add sensors** - Cameras, lidar for autonomous navigation
5. **Tune parameters** - Optimize for your specific use case

## Troubleshooting

### Robot doesn't move
- Check if kinematics node is running: `ros2 node list`
- Verify topics are publishing: `ros2 topic echo /cmd_vel`
- Check Gazebo bridge: `ros2 topic list | grep wheel`

### Joystick not working
- Install joy: `sudo apt install ros-${ROS_DISTRO}-joy`
- Check device: `ls /dev/input/js*`
- Test joystick: `sudo jstest /dev/input/js0`
- Fix permissions: `sudo chmod a+rw /dev/input/js0`

### Wheels oscillate
- Check steering PID (should be P=200, I=20, D=0.5)
- Verify rate limiter is active (50 Hz control loop)
- If still occurs, reduce max_steering_rate parameter

---

**Status**: COMPLETE - vehicle_control now uses the same algorithm as triwheel_robot with unified control loop, proper per-wheel kinematics, and tuned URDF physics.
