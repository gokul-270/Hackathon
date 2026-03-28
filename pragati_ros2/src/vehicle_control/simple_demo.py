"""
Vehicle Control System - Simple Demo

A quick demonstration that shows what's available in the vehicle control system.
"""

import sys
import os
from pathlib import Path

print("🚗 Vehicle Control System Simulator v2.1.0")
print("=" * 60)

# Check Python version
print(f"🐍 Python version: {sys.version}")
print(f"📁 Running from: {Path(__file__).parent}")
print()

# Check available dependencies
dependencies = {
    'numpy': 'Scientific computing',
    'matplotlib': 'Plotting and visualization', 
    'tkinter': 'GUI framework',
    'scipy': 'Advanced scientific computing'
}

print("📦 Dependency Status:")
available_deps = []
for dep, desc in dependencies.items():
    try:
        __import__(dep)
        print(f"  ✅ {dep:<12} - {desc}")
        available_deps.append(dep)
    except ImportError:
        print(f"  ❌ {dep:<12} - {desc} (MISSING)")

print()

# Check simulation modules
print("🔧 Simulation Module Status:")
simulation_files = [
    'vehicle_simulator.py',
    'physics_engine.py', 
    'gui_interface.py',
    'visualization.py',
    'run_simulation.py'
]

simulation_dir = Path(__file__).parent / 'simulation'
available_modules = []

for file in simulation_files:
    file_path = simulation_dir / file
    if file_path.exists():
        print(f"  ✅ {file:<20} - Available")
        available_modules.append(file)
    else:
        print(f"  ❌ {file:<20} - Missing")

print()

# Test basic functionality
print("🧪 Testing Basic Functionality:")

if 'numpy' in available_deps:
    try:
        import numpy as np
        print("  ✅ NumPy operations working")
        
        # Simple vehicle position calculation
        x, y = 0.0, 0.0
        heading = np.pi / 4  # 45 degrees
        velocity = 5.0
        dt = 0.1
        
        # Update position
        x += velocity * np.cos(heading) * dt
        y += velocity * np.sin(heading) * dt
        
        print(f"  📍 Sample calculation: Vehicle moved to ({x:.2f}, {y:.2f})")
        
    except Exception as e:
        print(f"  ❌ NumPy test failed: {e}")
else:
    print("  ⚠️  NumPy not available - basic math operations only")

# Check if we can create a simple simulator
print()
print("🚀 Simulation Capabilities:")

# Add simulation directory to path for import testing
sys.path.insert(0, str(simulation_dir))

try:
    # Test if we can at least import the physics module
    import physics_engine
    print("  ✅ Physics engine importable")
    
    # Try to create a basic physics instance
    physics = physics_engine.VehiclePhysics()
    print("  ✅ Physics engine instantiation successful")
    
    # Test basic physics update
    forces = {'x': 100, 'y': 0}
    moments = {'z': 0}
    physics.update(forces, moments, 0.1)
    state = physics.get_state()
    
    print(f"  📊 Physics test: Position = ({state['position']['x']:.3f}, {state['position']['y']:.3f})")
    
except ImportError as e:
    print(f"  ❌ Cannot import physics engine: {e}")
except Exception as e:
    print(f"  ❌ Physics engine test failed: {e}")

try:
    import vehicle_simulator
    print("  ✅ Vehicle simulator importable")
    
    # Create simulator instance
    simulator = vehicle_simulator.VehicleSimulator()
    print("  ✅ Vehicle simulator instantiation successful")
    
    # Test motor commands
    simulator.set_motor_command('steering_front', 15.0)
    simulator.set_motor_command('drive_front', 30.0)
    print("  ✅ Motor commands set successfully")
    
    # Run simulation step
    state = simulator.update(0.1)
    pos = state['position']
    print(f"  🎯 Simulation step: Position = ({pos['x']:.3f}, {pos['y']:.3f}), Heading = {pos['heading']:.3f}rad")
    
except ImportError as e:
    print(f"  ❌ Cannot import vehicle simulator: {e}")
except Exception as e:
    print(f"  ❌ Vehicle simulator test failed: {e}")

# GUI availability
if 'tkinter' in available_deps and 'matplotlib' in available_deps:
    print("  ✅ GUI simulation possible")
    print("  💡 To run GUI: python simulation/run_simulation.py --mode gui")
else:
    print("  ⚠️  GUI simulation not available (missing tkinter or matplotlib)")

# Summary and recommendations
print()
print("📋 Summary:")
total_deps = len(dependencies)
available_count = len(available_deps)
total_modules = len(simulation_files)
available_modules_count = len(available_modules)

print(f"  Dependencies: {available_count}/{total_deps} available")
print(f"  Modules: {available_modules_count}/{total_modules} available")

if available_count == total_deps and available_modules_count == total_modules:
    print("  🎉 Full simulation system ready!")
    print("  🚀 Run: python simulation/run_simulation.py")
elif available_count >= 2:
    print("  ⚡ Partial simulation capability available")
    print("  🛠️  To enable full features: pip install matplotlib tkinter scipy")
else:
    print("  🔧 Limited capability - install dependencies for full experience")
    print("  📦 Install: pip install numpy matplotlib tkinter scipy")

print()
print("🎮 Available Demo Modes:")
print("  1. GUI Mode: python simulation/run_simulation.py --mode gui")
print("  2. Headless: python simulation/run_simulation.py --mode headless --duration 10")
print("  3. Test Mode: python simulation/run_simulation.py --mode test")

print()
print("=" * 60)
print("Vehicle Control System Demo Complete! 🎯")
