# Vehicle joystick → motor command pipeline (MCP3008) — 2025-12-19
This note documents how the analog joystick (via MCP3008) is converted into motor commands in the current ROS 2 vehicle stack.

## 1) End-to-end data path
1. MCP3008 ADC read (SPI)
   - `vehicle_control.hardware.mcp3008.MCP3008Joystick.read_raw()` reads channels `x_channel`, `y_channel`.
   - Backend is selectable via `joystick.spi_backend`:
     - `spidev` (recommended on systems where `can0` is an SPI controller via kernel `mcp251x`)
     - `pigpio`
2. Joystick filtering + deadband
   - `vehicle_control.utils.input_processing.JoystickProcessor.read_filtered()`:
     - optional center calibration (offsets)
     - moving-average smoothing
     - clamp to 0..1023
     - deadband around MID=512 (see `JOYSTICK.RESOLUTION`)
3. Vehicle control poll loop
   - `vehicle_control.integration.vehicle_control_node.ROS2VehicleControlNode._poll_joystick()` runs on a timer.
   - It:
     - normalizes ADC counts to `x_norm,y_norm ∈ [-1, +1]`
     - publishes `/joy` (`sensor_msgs/msg/Joy`) for visibility
     - optionally maps joystick to motor commands (gated by `joystick.apply_to_motors`)
4. Command publishing to motor_control_ros2
   - Steering command: publishes `std_msgs/msg/Float64` to `/<steering_joint>_position_controller/command`
   - Drive command: publishes `std_msgs/msg/Float64` to `/<drive_joint>_velocity_controller/command`
5. motor_control_ros2 consumes command topics
   - `mg6010_controller_node` subscribes to those topics and immediately sends CAN commands.

## 2) Key configs
Vehicle config: `src/vehicle_control/config/production.yaml`
- `enable_joystick: true|false`
- `joystick.apply_to_motors: false|true`
- `joystick.poll_frequency` (Hz)
- `joystick.max_linear_mps`
- `joystick.turn_scale`
- `steering_angular_scale` (deg at `angular_cmd=1.0`)
- `physical_params.wheel_diameter`

Motor config (vehicle): `src/motor_control_ros2/config/vehicle_motors.yaml`
- `control_frequency` (mg6010 controller loop)
- `directions[]`, `transmission_factors[]`

## 3) Rates (what runs how often)
- Joystick poll + publishing (`vehicle_control_node`):
  - `joystick.poll_frequency` (default 20 Hz) → every 50 ms:
    - reads MCP3008
    - publishes `/joy`
    - if `apply_to_motors=true`, publishes steering/drive commands
- Motor controller state publishing (`mg6010_controller_node`):
  - `control_frequency` (vehicle default 50 Hz) → publishes `joint_states` and does “smart polling” of motors
- Motion feedback polling (`mg6010_controller_node`):
  - `motion_feedback.poll_hz` (default 5 Hz) → low-rate feedback checks

## 4) Conversion math (joystick → steering/drive)
In `vehicle_control_node._poll_joystick()`:
- Normalize ADC counts:
  - `x_norm = (x - 512) / 512`
  - `y_norm = (y - 512) / 512`
- Map to a Twist-like command:
  - `linear_cmd (m/s) = y_norm * max_linear_mps`
  - `angular_cmd      = x_norm * turn_scale`

Then in `vehicle_control_node._cmd_vel_callback()`:
- Steering angle target (degrees):
  - `steering_angle_deg = angular_cmd * steering_angular_scale`
  - clamp to `physical_params.steering_limits`
- Convert to radians:
  - `steering_angle_rad = steering_angle_deg * π/180`
- Send steering:
  - `_send_steering_command(steering_angle_rad)`
- Send drive velocity:
  - `_send_drive_velocity(linear_cmd)`

### Steering position publish (front_only)
In `_send_steering_command()` (default `steering_mode=front_only`):
- Convert steering angle (radians) to an output-rotation setpoint using the steering gear ratio (50:1):
  - `motor_rotation = (steering_angle_deg / 360) * 50`
- Publish (note the sign flip in current ROS1-compatible behavior):
  - `/steering_front_position_controller/command = -motor_rotation`

### Drive velocity publish
In `_send_drive_velocity()`:
- Convert linear m/s to wheel angular velocity:
  - `wheel_circumference = π * wheel_diameter`
  - `wheel_rps = v_mps / wheel_circumference`
  - `wheel_rad_s = wheel_rps * 2π`
- Publish:
  - `/drive_front_velocity_controller/command = wheel_rad_s`
  - `/drive_left_back_velocity_controller/command = wheel_rad_s`
  - `/drive_right_back_velocity_controller/command = wheel_rad_s`

## 5) Worked example (matches field logs)
Given:
- `raw(x=980, y=512)`
- `max_linear_mps=0.5`, `turn_scale=1.0`, `steering_angular_scale=30°`

Normalize:
- `x_norm = (980-512)/512 = 0.914`
- `y_norm = 0.0`

Map:
- `linear_cmd = 0.0 * 0.5 = 0.00 m/s`
- `angular_cmd = 0.914 * 1.0 = 0.914`

Steering:
- `steering_angle_deg = 0.914 * 30 = 27.42°`
- `motor_rotation = (27.42/360)*50 = 3.81`
- Publish:
  - `/steering_front_position_controller/command = -3.81`

Drive:
- `linear_cmd = 0.0` → publish 0.0 rad/s to all drive velocity command topics.

## 6) Command semantics: “new commands before old completes”
This system behaves like a *streaming setpoint controller* (teleop style):
- Steering uses an absolute position setpoint.
- Drive uses a velocity setpoint.

So if a new command arrives at T0+50ms while the motor is still moving toward the prior setpoint:
- There is no “complete first command then start next” behavior.
- The new message simply updates the target.

This is the normal/desired behavior for joystick teleoperation: it keeps latency low and lets you stop immediately.

### Is there a queue?
Not intentionally for joystick teleop.
- Messages are delivered through ROS2 middleware queues (QoS depth), but the control model is “latest setpoint wins”.
- `mg6010_controller_node` applies each command immediately in the subscription callback (`set_position` / `set_velocity`).

### Queue vs discard (recommendation)
For joystick teleop:
- **Discard/overwrite (latest-wins) is safer and feels better.**
  - A command queue can create delayed motion (vehicle continues moving after you return stick to center), which is unsafe.
  - Queues add latency and make control feel “laggy”.

For discrete autonomous maneuvers:
- A queue/trajectory/action interface can make sense, but should support **preemption/cancel** and have explicit completion semantics.

## 7) Safety gate
If `joystick.apply_to_motors=false`:
- the node publishes `/joy` and logs mapped values
- but it does **not** publish any motor commands

This is intended for safe bring-up / validation.
