"""
Vehicle Control System - Main Package

A comprehensive Python-based vehicle control system with 1 front + 2 rear motor configuration
for autonomous and semi-autonomous vehicle control applications.

This package provides:
- Advanced motor control and feedback systems
- Real-time state management
- CAN bus and GPIO interfaces
- IMU and sensor integration
- Comprehensive logging and diagnostics

Note: This __init__.py uses lazy loading to avoid import cascade issues.
Import submodules directly, e.g.: from vehicle_control.hardware.gpio_manager import GPIOManager
"""

import os
from pathlib import Path

# Read version from VERSION file
try:
    _version_file = Path(__file__).parent / "VERSION"
    with open(_version_file, "r", encoding="utf-8") as f:
        __version__ = f.read().strip()
except FileNotFoundError:
    __version__ = "2.1.0"  # Fallback version

# Package metadata
__author__ = "Vehicle Control Development Team"
__email__ = "dev@vehicle-control.example"
__description__ = "Comprehensive Python-based vehicle control system"

__all__ = [
    "__version__",
    "__author__",
    "__email__",
    "__description__",
]
