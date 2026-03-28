# Archived Motor Abstraction Layer
**Date Archived:** 2025-12-04
**Date Restored:** 2025-12-04 (partial)

## Status: PARTIALLY RESTORED

The following files have been restored to `hardware/` and adapted:
- ✅ `motor_controller.py` - Abstract motor controller interface
- ✅ `advanced_steering.py` - Ackermann steering, pivot modes
- ✅ NEW: `ros2_motor_interface.py` - Adapter for motor_control_ros2

These remain archived (not needed):
- `robust_motor_controller.py` - Retry logic (handled by ROS2)
- `enhanced_motor_interface.py` - Direct CAN wrapper (use motor_control_ros2)

## Current Architecture
```
vehicle_control (Python)
    ├── VehicleMotorController (high-level)
    │       ↓
    ├── AdvancedSteeringController (Ackermann, pivot)
    │       ↓
    └── ROS2MotorInterface (adapter)
            ↓ topics/services
        motor_control_ros2 (C++) ← Controls MG6010/MG6012 motors via CAN
```

## Key Functions Now Available
- `VehicleMotorController.set_vehicle_velocity()` - Velocity control
- `VehicleMotorController.set_pivot_mode()` - Pivot mode
- `AdvancedSteeringController.calculate_ackermann_angles()` - Ackermann geometry
- `AdvancedSteeringController.calculate_three_wheel_ackermann_angles()` - 3-wheel steering
