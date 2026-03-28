# ODrive CANSimple ROS2 Control Package

## Overview
This package provides ROS2 control for ODrive Pro motor controllers (firmware 0.6.x) using the CANSimple protocol over SocketCAN on Linux.

## Features
- **CANSimple 0.6.x Protocol**: Full implementation of ODrive Pro CANSimple protocol
- **SocketCAN RX Filtering**: Hardware-level filtering to isolate ODrive traffic from other CAN devices
- **Service-based Control**: Standard ROS2 services for homing, idle, and status queries
- **Position Command Interface**: Compatible with `yanthra_move` control system
- **Joint States Publishing**: Real-time position/velocity feedback
- **Multi-joint Support**: Simultaneous control of multiple ODrive nodes

## Package Structure
```
odrive_control_ros2/
├── config/
│   └── production.yaml          # Robot configuration
├── docs/
│   └── USAGE.md                 # This file
├── include/odrive_control_ros2/
│   ├── odrive_cansimple_protocol.hpp  # Protocol definitions
│   └── socketcan_interface.hpp        # SocketCAN wrapper
├── launch/
│   └── odrive_control.launch.py      # Launch file
└── src/
    ├── odrive_service_node.cpp       # Main ROS2 node
    └── socketcan_interface.cpp       # SocketCAN implementation
```

## Installation

### 1. Build the Package
```bash
cd ~/rasfiles/pragati_ros2
colcon build --packages-select odrive_control_ros2
source install/setup.bash
```

### 2. Configure CAN Interface
Ensure `can0` is configured and up:
```bash
sudo ip link set can0 up type can bitrate 500000
ip link show can0
```

## Configuration

Edit `config/production.yaml` to match your robot setup:

### Key Parameters

**Joint Configuration:**
- `joint_names`: ROS joint names (e.g., ["joint3", "joint4", "joint5"])
- `node_ids`: Corresponding ODrive CAN node IDs (0-63)

**Mechanical Configuration:**
- `directions`: Motor direction multiplier (1.0 or -1.0)
- `transmission_factors`: Conversion from joint units to motor turns
  - Revolute joints (rotations): typically 1.0
  - Prismatic joints (meters): e.g., 12.74 means 1m = 12.74 turns
- `homing_positions`: Default homing target in joint units

**Position Control:**
- `position_tolerance`: Position error threshold for homing (joint units)
- `homing_timeout`: Maximum homing duration (seconds)
- `settle_time`: Duration to remain within tolerance (seconds)

**Important Notes:**
- **PID Gains & Trajectory Limits:** Configure these via USB using `odrivetool` and save them to ODrive's non-volatile memory. The ROS2 node will NOT override these settings via CAN.
- To configure ODrive parameters via USB:
  ```bash
  odrivetool
  odrv0.axis0.controller.config.pos_gain = 20.0
  odrv0.axis0.controller.config.vel_gain = 0.16
  odrv0.axis0.controller.config.vel_integrator_gain = 0.32
  odrv0.axis0.trap_traj.config.vel_limit = 2.0      # turns/s
  odrv0.axis0.trap_traj.config.accel_limit = 5.0    # turns/s²
  odrv0.axis0.trap_traj.config.decel_limit = 5.0    # turns/s²
  odrv0.save_configuration()
  ```

## Usage

### Launch the Node
```bash
ros2 launch odrive_control_ros2 odrive_control.launch.py
```

### ROS2 Services

#### 1. Home Joint (`/joint_homing`)
```bash
ros2 service call /joint_homing motor_control_ros2/srv/JointHoming "{joint_id: 3, homing_required: true}"
```

**What it does:**
1. Sets controller mode to POSITION_CONTROL + TRAP_TRAJ
2. Enters CLOSED_LOOP_CONTROL state
3. Commands homing position
4. Waits for position to settle within tolerance

**Note:** Trajectory limits and PID gains must be pre-configured via `odrivetool` and saved to ODrive NVM.

**Response:**
- `success: true/false`
- `reason: "Success/error message"`

#### 2. Set Joint to Idle (`/joint_idle`)
```bash
ros2 service call /joint_idle motor_control_ros2/srv/JointHoming "{joint_id: 3, homing_required: false}"
```

**What it does:**
- Sends Set_Axis_State → IDLE
- Motor enters coast mode (no torque)

#### 3. Query Joint Status (`/joint_status`)
```bash
# Query specific joint
ros2 service call /joint_status motor_control_ros2/srv/JointStatus "{joint_id: 3}"

# Query all joints
ros2 service call /joint_status motor_control_ros2/srv/JointStatus "{joint_id: -1}"
```

**Response includes:**
- Current positions and velocities
- Error counts
- Axis state information

### ROS2 Topics

#### Subscribe to Joint States
```bash
ros2 topic echo /joint_states
```

Output:
```yaml
header:
  stamp: {sec: ..., nanosec: ...}
name: ['joint3', 'joint4', 'joint5']
position: [0.0, 0.0, 0.0]
velocity: [0.0, 0.0, 0.0]
effort: [0.0, 0.0, 0.0]
```

#### Publish Position Commands
```bash
# Command joint3 to -0.127 rotations
ros2 topic pub /joint3_position_controller/command std_msgs/msg/Float64 "{data: -0.127}"

# Command joint5 to 0.280 meters
ros2 topic pub /joint5_position_controller/command std_msgs/msg/Float64 "{data: 0.280}"
```

## Integration with yanthra_move

This package is designed to be a drop-in replacement for the legacy `motor_control_ros2` node when using ODrive Pro motors.

### Services Compatibility
- `/joint_homing` - Fully compatible
- `/joint_idle` - Fully compatible  
- `/joint_status` - Fully compatible

### Topic Compatibility
- Publishes to: `/joint_states`
- Subscribes to: `/joint{N}_position_controller/command`

### Coordinate System
The package handles coordinate transformation automatically:
```
ODrive turns = joint_value × transmission_factor × direction
```

Example:
- `joint3`: -0.127 rotations × 1.0 × -1 = 0.127 turns (motor inverted)
- `joint5`: 0.280 meters × 12.74 × -1 = -3.567 turns

## Troubleshooting

### No Heartbeat Received
**Symptom:** Service calls fail with "No heartbeat received"

**Solutions:**
1. Check CAN interface is up: `ip link show can0`
2. Verify ODrive node IDs match configuration
3. Check CAN bus wiring and termination
4. Monitor CAN traffic: `candump can0`
5. Verify ODrive is powered and configured

### Homing Timeout
**Symptom:** Homing fails with "Homing timeout"

**Solutions:**
1. Increase `homing_timeout` in config
2. Check trajectory limits aren't too conservative
3. Verify motor has sufficient power
4. Check for mechanical obstructions
5. Review ODrive errors: `odrivetool` or check active_errors

### Position Doesn't Settle
**Symptom:** Homing completes but position oscillates

**Solutions:**
1. Increase `position_tolerance` in config
2. Tune ODrive PID gains
3. Increase `settle_time` duration
4. Check for mechanical backlash/compliance

### CAN Bus Errors
**Symptom:** "Failed to initialize CAN interface"

**Solutions:**
1. Check user has CAN permissions: `sudo usermod -a -G dialout $USER`
2. Verify interface name in config matches system (`can0`, `can1`, etc.)
3. Check for conflicting CAN applications
4. Review kernel logs: `dmesg | grep can`

## Protocol Reference

### CAN Message Format
- **Arbitration ID:** `(node_id << 5) | cmd_id`
- **Node ID:** 0-63 (bits 5-10)
- **Command ID:** 0-31 (bits 0-4)
- **Encoding:** Little-endian
- **Max payload:** 8 bytes

### Key Commands Used
- `0x01` - Heartbeat (RX)
- `0x03` - Get_Error (RX)
- `0x07` - Set_Axis_State (TX)
- `0x09` - Get_Encoder_Estimates (RX)
- `0x0B` - Set_Controller_Mode (TX)
- `0x0C` - Set_Input_Pos (TX)
- `0x11` - Set_Traj_Vel_Limit (TX)
- `0x12` - Set_Traj_Accel_Limits (TX)

### RX Filtering
The node applies per-node CAN filters:
- **Filter:** `can_id = (node_id << 5)`, `can_mask = 0x7E0`
- **Effect:** Only messages from configured ODrive node IDs pass to this node
- **Benefit:** Prevents MG6010 motor traffic from interfering with ODrive communication

## Development

### Adding New Commands
1. Define command ID in `odrive_cansimple_protocol.hpp` (CMD namespace)
2. Add encoder/decoder functions if needed
3. Use in `odrive_service_node.cpp` via `can_interface_->send_frame()`

### Debugging CAN Traffic
```bash
# Monitor all CAN traffic
candump can0

# Filter for specific node_id (e.g., node 0)
candump can0,000:7E0  # Mask to node_id bits

# Send manual CAN frame (Heartbeat request to node 0)
cansend can0 001#
```

### Logging
Adjust ROS2 log level for more detail:
```bash
ros2 run odrive_control_ros2 odrive_service_node --ros-args --log-level debug
```

## Safety Notes

1. **Emergency Stop:** Use ODrive's hardware E-Stop or call `/joint_idle` service
2. **Position Limits:** Enforce joint limits in higher-level control (`yanthra_move`)
3. **Current Limits:** Configure conservatively in `production.yaml`
4. **Homing:** Always home motors before operation to establish position reference
5. **CAN Filtering:** Critical for multi-device CAN buses to prevent cross-talk

## References

- ODrive Documentation: https://docs.odriverobotics.com/
- CANSimple Protocol: ODrive firmware 0.6.x source code
- SocketCAN Guide: https://www.kernel.org/doc/Documentation/networking/can.txt
