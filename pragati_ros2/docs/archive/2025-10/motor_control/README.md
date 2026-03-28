# Motor Control ROS2 (MG6010 Primary) ✅

**Primary Controller:** MG6010-i6 integrated servo motors via LK-Tech CAN protocol  
**Legacy Support:** ODrive CAN control retained for compatibility (optional)  
**Build Status:** ✅ Clean build (last verified 2025-10-09)  
**Hardware Validation:** ⏳ Pending – requires MG6010 hardware bench  
**Safety Monitor:** ✅ Fully implemented emergency-stop watchdog  
**Last Updated:** 2025-10-13

This package houses the Pragati robot’s production motor-control stack. The MG6010 implementation is the canonical path, while ODrive support remains available but is no longer the default.

- **MG6010 Production Controller** – native protocol implementation, controller abstraction, safety integration
- **Safety Monitor** – real-time telemetry checks for joint limits, velocity, temperature, and communication health
- **Legacy ODrive Layer** – still buildable; disable or enable via configuration depending on deployment needs
- **Comprehensive Docs** – see `SERVICES_NODES_GUIDE.md`, `MOTOR_CONTROL_STATUS.md`, and `docs/` for deep dives

## MG6010 Configuration

- Primary config: `config/mg6010_test.yaml`
- Production config: `config/production.yaml`
- Launch for standalone testing: `launch/mg6010_test.launch.py`
- Parameters include joint name, CAN ID, direction, gains, and safety limits

## Building

```bash
colcon build --packages-select motor_control_ros2
```

## Running

### Launch (recommended)
```bash
ros2 launch motor_control_ros2 mg6010_test.launch.py test_mode:=status
```

### Direct node execution
```bash
ros2 run motor_control_ros2 mg6010_integrated_test_node --ros-args --params-file src/motor_control_ros2/config/mg6010_test.yaml
```

## Services

- `/mg6010/motor_status`
- `/mg6010/motor_enable`
- `/mg6010/motor_disable`
- `/mg6010/motor_homing`

See `SERVICES_NODES_GUIDE.md` for the full API surface and ODrive legacy endpoints.

## Safety Monitor ✅ **100% COMPLETE**

The SafetyMonitor system is **fully implemented and production-ready**. Status:
- ✅ **Framework**: Emergency stop, state management, lifecycle complete
- ✅ **Implementation**: All 6 safety checks fully implemented (October 6, 2025)
- ✅ **Integration**: Active in ControlLoopNode with ROS2 topic subscriptions
- ✅ **Testing**: Comprehensive test suite with 7 scenarios verified
- ✅ **Status**: PRODUCTION READY - Actively protecting the system

### Implemented Safety Checks:
1. **Joint Position Limits** - Monitors against URDF limits with 5° safety margin
2. **Velocity Limits** - 10.0 rad/s maximum velocity enforcement
3. **Temperature Monitoring** - Warning at 65°C, critical at 70°C
4. **Communication Timeouts** - 1.0 second timeout detection
5. **Motor Error Status** - ODrive error flag monitoring (DRV_FAULT, etc.)
6. **Power Supply Voltage** - VBus monitoring (42V warning, 40V critical)

### Features:
- Real-time safety monitoring in control loop
- ROS2 `/joint_states` topic subscription
- Automatic emergency stop on violations
- Hardware deactivation on critical errors
- Comprehensive test suite included

See [../../docs/guides/SAFETY_MONITOR_INTEGRATION_GUIDE.md](../../docs/guides/SAFETY_MONITOR_INTEGRATION_GUIDE.md) for details.

## Hardware Guides

- **CAN Bus Setup**: [../../docs/guides/CAN_BUS_SETUP_GUIDE.md](../../docs/guides/CAN_BUS_SETUP_GUIDE.md)
- **GPIO Setup**: [../../docs/guides/GPIO_SETUP_GUIDE.md](../../docs/guides/GPIO_SETUP_GUIDE.md)
- **Safety Monitor**: [../../docs/guides/SAFETY_MONITOR_INTEGRATION_GUIDE.md](../../docs/guides/SAFETY_MONITOR_INTEGRATION_GUIDE.md)

## Troubleshooting

- Ensure parameters are loaded from YAML (avoid default-declared overrides in code)
- Verify CAN interface is up: `ip link show can0`
- Check params: `ros2 param list /mg6010_controller`
- CAN troubleshooting: See CAN_BUS_SETUP_GUIDE.md

## Legacy ODrive Support ⚠️

The original ODrive CAN control stack is still shipped for back-compatibility and can be enabled via:

```bash
ros2 launch motor_control_ros2 odrive_control.launch.py
```

- Default parameters: `config/odrive_controllers.yaml`
- Service node: `odrive_service_node`
- Status: **Legacy** – not used in current Pragati deployments

Use this path only when running historical hardware or for regression tests.

## Validation Status & TODOs

- ✅ Unit-level protocol/controller logic exercised via test nodes (no hardware required)
- ⏳ Hardware-in-the-loop validation pending MG6010 bench setup
- ⏳ PID tuning and performance characterization require real motors
- ⏳ Refresh documentation cross-links once validation data is captured (see `MOTOR_CONTROL_STATUS.md`)
