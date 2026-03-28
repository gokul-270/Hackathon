# Archived Motor Control Code

## Archive Date: 2025-11-28

## Why These Files Were Archived

These files were developed for advanced features that are NOT currently used in production.
The production system uses only `mg6010_controller_node` with the MG6010 CAN protocol.

These features may be re-integrated in the future when:
1. Basic motor control is stable and proven
2. Advanced features are needed (auto-tuning, dual encoders, etc.)

## What Was Archived

### unused_sources_2025-11/
Source files that were **never compiled** (not in CMakeLists.txt):
- `advanced_initialization_system.cpp` - Advanced motor initialization sequences
- `comprehensive_error_handler.cpp` - Complex error recovery system
- `control_loop_node.cpp` - Alternative control loop implementation
- `enhanced_can_interface.cpp` - Extended CAN bus interface
- `error_handling.cpp` - Error handling utilities
- `simple_control_loop_node.cpp` - Simplified control loop
- `production_odrive_legacy.yaml` - ODrive configuration (no longer used)
- `test_error_handling.cpp` - Tests for error handling
- `test_generic_motor.cpp` - Generic motor tests

### unused_headers_2025-11/
Headers for the above unused source files:
- `advanced_initialization_system.hpp`
- `comprehensive_error_handler.hpp`
- `control_loop_node.hpp`
- `enhanced_can_interface.hpp`
- `enhanced_motor_abstraction.hpp`
- `enhanced_motor_examples.hpp`
- `hardware_in_loop_testing.hpp` - HIL testing framework
- `motor_control_validation_framework.hpp` - Test validation

**Note**: `mock_can_interface.hpp` remains in `test/` (used by test_can_communication).
The `MockEnhancedCANController` class was removed from it since it depended on
the archived `enhanced_can_interface.hpp`.

### advanced_features_2025/ (Previously Archived)
- PID auto-tuner
- Dual encoder system
- Cascaded PID controller

## To Restore

If you need to restore any file:
```bash
# Example: Restore enhanced_can_interface
cd src/motor_control_ros2
mv archive/unused_sources_2025-11/enhanced_can_interface.cpp src/
mv archive/unused_headers_2025-11/enhanced_can_interface.hpp include/motor_control_ros2/
# Then add to CMakeLists.txt
```

## Production Files (What's Actually Used)

The production system uses only these files:
```
src/
├── generic_hw_interface.cpp      # ros2_control hardware interface
├── generic_motor_controller.cpp  # Motor controller abstraction
├── gpio_control_functions.cpp    # GPIO for end effector
├── gpio_interface.cpp            # GPIO abstraction
├── mg6010_can_interface.cpp      # MG6010 CAN driver
├── mg6010_controller.cpp         # MG6010 controller logic
├── mg6010_controller_node.cpp    # PRODUCTION NODE
├── mg6010_protocol.cpp           # CAN protocol implementation
├── mg6010_test_node.cpp          # Test node (optional)
├── motor_abstraction.cpp         # Motor type abstraction
├── motor_parameter_mapping.cpp   # Parameter handling
└── safety_monitor.cpp            # Safety monitoring
```

### unused_services_2025-11/
Services that were defined but never used in production:
- `MotorCalibration.srv` - Full motor calibration sequence
- `EncoderCalibration.srv` - Encoder index search
- `JointConfiguration.srv` - Runtime parameter changes

**Production only uses**: `JointHoming.srv`, `JointStatus.srv`, `JointPositionCommand.srv`

### unused_tests_2025-11/
Test files that referenced the removed services:
- `minimal_service_test.cpp`
- `simple_service_test.cpp`
- `simple_service_test_node.cpp`

## Build Impact

**Before cleanup**: ~2min 27s cold build  
**After removing 3 services**: ~1min 36s cold build (**35% faster**)  
**Benefit**: Faster builds + cleaner codebase
