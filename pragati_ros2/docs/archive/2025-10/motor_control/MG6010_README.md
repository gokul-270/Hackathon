# MG6010-i6 Motor Integration Guide

## Overview

This document describes the integration of LK-TECH MG6010-i6 motor support into the pragati_ros2 project. The integration provides a standalone protocol implementation based on the official LK-TECH CAN Protocol V2.35 specification and tested colleague code.

## Key Features

- **Official Protocol Compliance**: Implements LK-TECH CAN Protocol V2.35
- **Tested Code Integration**: Incorporates proven patterns from colleague's tested implementation
- **Standalone Design**: MG6010Protocol class operates independently without affecting existing ODrive/CANopen code
- **Comprehensive Testing**: Includes standalone test node with 9 different test modes
- **Protocol Validation**: Tools for comparing CAN messages between implementations

## Files Added

### Core Implementation
- `src/odrive_control_ros2/include/odrive_control_ros2/mg6010_protocol.hpp` - Protocol API header
- `src/odrive_control_ros2/src/mg6010_protocol.cpp` - Protocol implementation
- `src/odrive_control_ros2/src/mg6010_test_node.cpp` - Standalone ROS2 test node

### Documentation
- `docs/comparison/MG6010_I6_PROTOCOL_COMPARISON.md` - Detailed protocol comparison
- `docs/MG6010_INTEGRATION_README.md` - This file

### Testing Scripts
- `scripts/test_mg6010_communication.sh` - Automated CAN testing with candump logging
- `scripts/compare_can_messages.py` - CAN message comparison tool

### Build System
- Updated `src/odrive_control_ros2/CMakeLists.txt` - Added MG6010 library and test node targets

## Building

```bash
cd /home/uday/Downloads/pragati_ros2
colcon build --packages-select odrive_control_ros2
source install/setup.bash
```

## CAN Interface Setup

### Configure CAN Interface (1Mbps - Official Default)
```bash
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 1000000
sudo ip link set can0 up
```

### Alternative: 250kbps (Tested Configuration)
```bash
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 250000
sudo ip link set can0 up
```

### Verify CAN Interface
```bash
ip link show can0
```

## Running the Test Node

### Basic Usage
```bash
ros2 run odrive_control_ros2 mg6010_test_node --ros-args \
  -p interface_name:=can0 \
  -p baud_rate:=1000000 \
  -p node_id:=1 \
  -p mode:=status
```

### Available Test Modes

1. **status** - Read motor status (temperature, voltage, errors)
   ```bash
   ros2 run odrive_control_ros2 mg6010_test_node --ros-args -p mode:=status -p node_id:=1
   ```

2. **angle** - Read multi-turn and single-turn angles
   ```bash
   ros2 run odrive_control_ros2 mg6010_test_node --ros-args -p mode:=angle -p node_id:=1
   ```

3. **pid** - Read PID parameters
   ```bash
   ros2 run odrive_control_ros2 mg6010_test_node --ros-args -p mode:=pid -p node_id:=1
   ```

4. **encoder** - Read encoder data
   ```bash
   ros2 run odrive_control_ros2 mg6010_test_node --ros-args -p mode:=encoder -p node_id:=1
   ```

5. **on_off** - Test motor on/off commands
   ```bash
   ros2 run odrive_control_ros2 mg6010_test_node --ros-args -p mode:=on_off -p node_id:=1
   ```

6. **position** - Test position control
   ```bash
   ros2 run odrive_control_ros2 mg6010_test_node --ros-args \
     -p mode:=position \
     -p node_id:=1 \
     -p position_rad:=1.57
   ```

7. **velocity** - Test velocity control
   ```bash
   ros2 run odrive_control_ros2 mg6010_test_node --ros-args \
     -p mode:=velocity \
     -p node_id:=1 \
     -p velocity_rad_s:=0.5
   ```

8. **torque** - Test torque control
   ```bash
   ros2 run odrive_control_ros2 mg6010_test_node --ros-args \
     -p mode:=torque \
     -p node_id:=1 \
     -p torque_amps:=1.0
   ```

9. **accel** - Test acceleration configuration
   ```bash
   ros2 run odrive_control_ros2 mg6010_test_node --ros-args \
     -p mode:=accel \
     -p node_id:=1 \
     -p accel_rad_s2:=2.0
   ```

## Automated Testing

### Run Full Test Suite
```bash
cd /home/uday/Downloads/pragati_ros2
./scripts/test_mg6010_communication.sh can0 1000000 1
```

This will:
- Configure the CAN interface
- Start candump logging
- Run all test modes sequentially
- Save logs to `/tmp/mg6010_test_<timestamp>/`
- Display summary of CAN messages

### Compare with Tested Implementation
```bash
python3 scripts/compare_can_messages.py \
  /tmp/mg6010_test_*/candump.log \
  /path/to/colleague/candump.log
```

## Protocol Details

### Baud Rates
- **Official Default**: 1Mbps
- **Tested**: 250kbps
- **Supported**: 1Mbps, 500kbps, 250kbps, 125kbps, 100kbps

### Arbitration ID
- Base: `0x140`
- Motor ID range: 1-32
- Formula: `0x140 + motor_id`
- Example: Motor ID 1 = `0x141`

### Key Commands

| Command | Code | Description |
|---------|------|-------------|
| MOTOR_OFF | 0x80 | Turn motor off |
| MOTOR_ON | 0x88 | Turn motor on |
| MOTOR_STOP | 0x81 | Emergency stop |
| SPEED_CTRL | 0xA2 | Speed control (0.01 dps/LSB) |
| TORQUE_CTRL | 0xA1 | Torque control (-33A ~ 33A) |
| MULTI_LOOP_ANGLE_1 | 0xA3 | Position control (multi-turn) |
| READ_STATUS_1 | 0x9A | Read temp, voltage, errors |
| READ_STATUS_2 | 0x9C | Read temp, current, speed, encoder |
| READ_MULTI_TURN_ANGLE | 0x92 | Read multi-turn position |
| READ_SINGLE_TURN_ANGLE | 0x94 | Read single-turn position |

### Response Timing
- Official spec: ~0.25ms typical
- Implementation: 10ms timeout with 3 retries
- Tested code used: 50ms timeout

## Architecture

### MG6010Protocol Class

The `MG6010Protocol` class provides a clean interface to MG6010 motors:

```cpp
// Initialize
auto can_interface = std::make_shared<GenericCANInterface>();
can_interface->initialize("can0", 1000000);

auto protocol = std::make_shared<MG6010Protocol>();
protocol->initialize(can_interface, 1, 1000000);

// Use
protocol->motor_on();
protocol->set_absolute_position(1.57);  // radians
double angle = 0.0;
protocol->read_multi_turn_angle(angle);
protocol->motor_off();
```

### Integration Points

- **Standalone**: Current implementation operates independently
- **Future Integration**: Can be integrated into `GenericMotorController` by detecting `motor_type == "mg6010"`
- **No Breaking Changes**: Existing ODrive and CANopen code remains unchanged

## Troubleshooting

### CAN Interface Issues

**Problem**: `Failed to bring up CAN interface`
```bash
# Check interface exists
ip link show can0

# Check for existing processes
sudo lsof | grep can0

# Restart interface
sudo ip link set can0 down
sudo ip link set can0 up type can bitrate 1000000
```

**Problem**: `No response from motor`
- Verify motor is powered
- Check CAN bus termination (120Ω resistors)
- Verify baud rate matches motor configuration
- Check motor node ID (1-32)
- Use `candump can0` to see if ANY messages appear

### Build Issues

**Problem**: `mg6010_protocol.hpp not found`
```bash
# Clean and rebuild
cd /home/uday/Downloads/pragati_ros2
rm -rf build install log
colcon build --packages-select odrive_control_ros2
```

**Problem**: `undefined reference to MG6010Protocol`
- Ensure CMakeLists.txt includes `${PROJECT_NAME}_mg6010` library
- Check C++17 standard is enabled

## Next Steps

1. **Validate with Real Hardware**: Test with actual MG6010 motor
2. **Compare with Tested Code**: Use `compare_can_messages.py` to verify protocol correctness
3. **Optional Integration**: Integrate into `GenericMotorController` once validated
4. **CAN Filters**: Add optional CAN filtering for better performance
5. **Documentation**: Update based on real-world testing results

## References

- **Official Protocol**: LK-TECH CAN Protocol V2.35 (CANprotocal.pdf)
- **Tested Implementation**: `/home/uday/Downloads/mgmotor-test/mg_can_compat.cpp`
- **Comparison Document**: `docs/comparison/MG6010_I6_PROTOCOL_COMPARISON.md`

## Support

For issues or questions:
1. Check the comparison document for protocol details
2. Review test logs in `/tmp/mg6010_test_*/`
3. Use `candump can0` to monitor raw CAN traffic
4. Compare with colleague's tested implementation

---

**Last Updated**: 2025-10-07  
**Feature Branch**: `feature/mg6010-integration`  
**Status**: Implementation complete, awaiting hardware validation
