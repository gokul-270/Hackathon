"""
Vehicle Control System Simulation Package

Provides visual simulation and testing capabilities for the vehicle control system.
Includes GUI interface, vehicle physics simulation, and real-time visualization.
"""

# Import simulation modules with error handling
try:
    from .vehicle_simulator import VehicleSimulator
except ImportError:
    VehicleSimulator = None

try:
    from .gui_interface import SimulationGUI
except ImportError:
    SimulationGUI = None

try:
    from .physics_engine import VehiclePhysics
except ImportError:
    VehiclePhysics = None

try:
    from .visualization import VehicleVisualizer
except ImportError:
    VehicleVisualizer = None

__all__ = []

# Only export available modules
if VehicleSimulator:
    __all__.append("VehicleSimulator")
if SimulationGUI:
    __all__.append("SimulationGUI")
if VehiclePhysics:
    __all__.append("VehiclePhysics")
if VehicleVisualizer:
    __all__.append("VehicleVisualizer")
