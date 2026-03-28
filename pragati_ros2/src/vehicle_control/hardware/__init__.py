"""
Hardware module for Vehicle Control System

Components:
- GPIOManager: GPIO pin control for LEDs, inputs
- VehicleMotorController: High-level vehicle motor control
- AdvancedSteeringController: Ackermann steering, pivot modes
- ROS2MotorInterface: Adapter for motor_control_ros2

Motor commands go through ROS2MotorInterface -> motor_control_ros2 package
"""

from .gpio_manager import GPIOManager
from .motor_controller import (
    VehicleMotorController,
    MotorControllerInterface,
    MotorStatus,
    ControlMode,
    MotorError,
    SafetyLimitError,
)
from .advanced_steering import (
    AdvancedSteeringController,
    SteeringAngles,
)
from .ros2_motor_interface import ROS2MotorInterface
from .mcp3008 import MCP3008, MCP3008Config, MCP3008Joystick

__all__ = [
    'GPIOManager',
    'VehicleMotorController',
    'MotorControllerInterface',
    'MotorStatus',
    'ControlMode',
    'MotorError',
    'SafetyLimitError',
    'AdvancedSteeringController',
    'SteeringAngles',
    'ROS2MotorInterface',
    'MCP3008',
    'MCP3008Config',
    'MCP3008Joystick',
]
