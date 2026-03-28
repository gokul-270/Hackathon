# odrive_control_ros2

ROS2 control package for ODrive Pro motor controllers using CANSimple protocol (firmware 0.6.x).

## Overview

This package provides a standalone ROS2 node for controlling ODrive Pro motors via CAN bus on Linux. It uses the SocketCAN interface with hardware-level RX filtering to prevent cross-talk with other CAN devices (e.g., MG6010 motors).

**Key Features:**
- Full ODrive CANSimple 0.6.x protocol implementation
- SocketCAN with per-node RX filtering
- Standard ROS2 service interface (`/joint_homing`, `/joint_idle`, `/joint_status`)
- Joint states publishing and position command subscription
- Compatible with existing `yanthra_move` control system

## Quick Start

### 1. Setup ODrive Hardware

Configure each ODrive via USB before using with ROS2:
- Set unique CAN node IDs (0-63)
- Calibrate motors
- Configure PID gains and trajectory limits
- Save configuration to non-volatile memory

See [docs/ODRIVE_SETUP.md](docs/ODRIVE_SETUP.md) for detailed instructions.

### 2. Configure CAN Interface

```bash
sudo ip link set can0 type can bitrate 500000
sudo ip link set can0 up
```

### 3. Update Configuration

Edit `config/production.yaml` to match your robot setup:
- Joint names and node IDs
- Mechanical parameters (directions, transmission factors)
- Homing positions
- Position tolerances

### 4. Launch the Node

```bash
source install/setup.bash
ros2 launch odrive_control_ros2 odrive_control.launch.py
```

## Usage

### Services

**Home a joint:**
```bash
ros2 service call /joint_homing motor_control_ros2/srv/JointHoming "{joint_id: 3, homing_required: true}"
```

**Set joint to idle:**
```bash
ros2 service call /joint_idle motor_control_ros2/srv/JointHoming "{joint_id: 3, homing_required: false}"
```

**Query joint status:**
```bash
ros2 service call /joint_status motor_control_ros2/srv/JointStatus "{joint_id: -1}"
```

### Topics

**Subscribe to joint states:**
```bash
ros2 topic echo /joint_states
```

**Publish position commands:**
```bash
ros2 topic pub /joint3_position_controller/command std_msgs/msg/Float64 "{data: -0.127}"
```

## Documentation

- [USAGE.md](docs/USAGE.md) - Detailed usage guide with examples
- [ODRIVE_SETUP.md](docs/ODRIVE_SETUP.md) - ODrive hardware configuration guide

## Package Contents

- **odrive_cansimple_protocol.hpp** - CANSimple 0.6.x protocol definitions
- **socketcan_interface** - SocketCAN wrapper with RX filtering
- **odrive_service_node** - Main ROS2 node

## Dependencies

- ROS2 (tested on Humble)
- motor_control_ros2 (service definitions)
- SocketCAN (Linux kernel)

## License

Copyright 2025 Pragati Robotics

## Support

For issues and questions, please refer to the troubleshooting section in [USAGE.md](docs/USAGE.md).
