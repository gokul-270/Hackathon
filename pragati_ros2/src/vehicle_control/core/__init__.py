"""
Core module for Vehicle Control System
Contains main vehicle control logic, state management, and safety systems
"""

from .vehicle_controller import VehicleController
from .state_machine import VehicleStateMachine
from .safety_manager import SafetyManager

__all__ = [
    'VehicleController',
    'VehicleStateMachine',
    'SafetyManager'
]
