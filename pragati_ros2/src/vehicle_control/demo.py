"""
Vehicle Control System - Quick Demo

A simple demonstration of the vehicle control simulation system.
Run this script to see the vehicle in action!
"""

import sys
import os
from pathlib import Path

# Add simulation directory to path
current_dir = Path(__file__).parent
simulation_dir = current_dir / "simulation"
sys.path.insert(0, str(simulation_dir))
sys.path.insert(0, str(current_dir))

print("🚗 Vehicle Control System Demo v2.1.0")
print("=" * 50)

# Check for GUI availability
try:
    import tkinter as tk
    import matplotlib.pyplot as plt
    import numpy as np
    GUI_AVAILABLE = True
    print("✅ GUI components available")
except ImportError as e:
    GUI_AVAILABLE = False
    print(f"❌ GUI components missing: {e}")

# Try to import simulation modules
try:
    from run_simulation import run_gui_simulation, run_headless_simulation
    SIMULATION_AVAILABLE = True
    print("✅ Simulation modules loaded")
except ImportError as e:
    SIMULATION_AVAILABLE = False
    print(f"❌ Simulation modules failed: {e}")

print("=" * 50)

if GUI_AVAILABLE and SIMULATION_AVAILABLE:
    print("🎮 Starting GUI simulation...")
    print("Use the control panels to drive the vehicle!")
    print("=" * 50)
    
    try:
        # Run the GUI simulation
        sys.argv = ['demo.py', '--mode', 'gui']  # Set command line args
        from run_simulation import main
        main()
    except Exception as e:
        print(f"❌ GUI simulation failed: {e}")
        print("\n🤖 Trying headless simulation instead...")
        try:
            run_headless_simulation(duration=5.0)
        except Exception as e2:
            print(f"❌ Headless simulation also failed: {e2}")

elif SIMULATION_AVAILABLE:
    print("🤖 GUI not available, running headless demonstration...")
    try:
        run_headless_simulation(duration=5.0)
    except Exception as e:
        print(f"❌ Headless simulation failed: {e}")

else:
    print("❌ Simulation not available.")
    print("\n📦 To install simulation dependencies:")
    print("pip install matplotlib numpy scipy")
    print("\n📋 System Status:")
    print("- Core vehicle control: ✅ Available")
    print("- Simulation features: ❌ Missing dependencies")
    
    # Try a basic import test
    print("\n🔍 Testing basic imports...")
    try:
        # Test basic vehicle simulator without dependencies
        import vehicle_simulator
        print("✅ Vehicle simulator module found")
        
        # Create a minimal demonstration
        print("\n🚀 Running minimal physics demo...")
        simulator = vehicle_simulator.VehicleSimulator()
        
        print("Initial position:", simulator.get_state_dict()['position'])
        
        # Apply some commands
        simulator.set_motor_command('steering_front', 15.0)
        simulator.set_motor_command('drive_front', 25.0)
        
        # Run a few simulation steps
        for i in range(10):
            state = simulator.update(0.1)
            if i % 3 == 0:  # Print every 3rd step
                pos = state['position']
                print(f"Step {i+1}: Position ({pos['x']:.2f}, {pos['y']:.2f}), Heading {pos['heading']:.2f}rad")
        
        print("✅ Basic simulation successful!")
        
    except Exception as e:
        print(f"❌ Basic simulation failed: {e}")

print("\n👋 Demo completed!")
print("💡 For full GUI experience, install: pip install matplotlib numpy scipy tkinter")
input("Press Enter to exit...")
