"""
Vehicle Control System - Simulation Launcher

Main entry point for running the vehicle control simulation with GUI.
Provides easy access to different simulation modes and configurations.
"""

import sys
import os
import argparse
from pathlib import Path

# Add the parent directory to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import tkinter as tk
    GUI_AVAILABLE = True
except ImportError as e:
    print(f"GUI not available: {e}")
    GUI_AVAILABLE = False

import numpy as np
import time
from typing import Dict, Optional

# Import simulation modules with absolute imports
try:
    from vehicle_simulator import VehicleSimulator
    from physics_engine import VehiclePhysics, PhysicsParameters
    if GUI_AVAILABLE:
        from gui_interface import SimulationGUI
except ImportError:
    # Fallback to relative imports if absolute fails
    try:
        from .vehicle_simulator import VehicleSimulator
        from .physics_engine import VehiclePhysics, PhysicsParameters
        if GUI_AVAILABLE:
            from .gui_interface import SimulationGUI
    except ImportError as e:
        print(f"Could not import simulation modules: {e}")
        VehicleSimulator = None
        VehiclePhysics = None
        PhysicsParameters = None
        if GUI_AVAILABLE:
            SimulationGUI = None

# Import constants
try:
    from config.constants import MotorIDs
except ImportError:
    # Create a minimal MotorIDs class for standalone operation
    class MotorIDs:
        STEERING_FRONT = 1
        STEERING_REAR_LEFT = 3
        STEERING_REAR_RIGHT = 5
        DRIVE_FRONT = 0
        DRIVE_REAR_LEFT = 2
        DRIVE_REAR_RIGHT = 4


def run_headless_simulation(duration: float = 10.0, output_file: Optional[str] = None):
    """
    Run simulation without GUI (headless mode).
    
    Args:
        duration: Simulation duration in seconds
        output_file: Optional CSV file to save results
    """
    print("Starting headless simulation...")
    
    # Initialize simulator
    simulator = VehicleSimulator()
    
    # Simulation parameters
    dt = 0.02  # 50 Hz update rate
    steps = int(duration / dt)
    
    # Data collection
    data = {
        'time': [],
        'pos_x': [],
        'pos_y': [],
        'heading': [],
        'velocity': [],
        'angular_velocity': []
    }
    
    print(f"Running simulation for {duration} seconds ({steps} steps)")
    
    # Simple test trajectory: figure-8 pattern
    for step in range(steps):
        t = step * dt
        
        # Generate test commands (figure-8 pattern)
        steering_amplitude = 30.0  # degrees
        drive_speed = 20.0  # percent
        
        # Sinusoidal steering for figure-8
        steering_front = steering_amplitude * np.sin(0.2 * t)
        steering_rear = -steering_amplitude * 0.5 * np.sin(0.2 * t)
        
        # Set motor commands
        simulator.set_motor_command('steering_front', steering_front)
        simulator.set_motor_command('steering_rear_left', steering_rear)
        simulator.set_motor_command('steering_rear_right', steering_rear)
        simulator.set_motor_command('drive_front', drive_speed)
        simulator.set_motor_command('drive_rear_left', drive_speed * 0.8)
        simulator.set_motor_command('drive_rear_right', drive_speed * 0.8)
        
        # Update simulation
        state = simulator.update(dt)
        
        # Collect data
        data['time'].append(t)
        data['pos_x'].append(state['position']['x'])
        data['pos_y'].append(state['position']['y'])
        data['heading'].append(state['position']['heading'])
        data['velocity'].append(state['velocity']['linear'])
        data['angular_velocity'].append(state['velocity']['angular'])
        
        # Progress indicator
        if step % (steps // 10) == 0:
            progress = (step / steps) * 100
            print(f"Progress: {progress:.0f}% - Position: ({state['position']['x']:.2f}, {state['position']['y']:.2f})")
    
    print("Simulation completed!")
    
    # Save results if requested
    if output_file:
        save_simulation_data(data, output_file)
        print(f"Results saved to: {output_file}")
    
    # Print summary
    print_simulation_summary(data)


def save_simulation_data(data: Dict, filename: str):
    """Save simulation data to CSV file."""
    import csv
    
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        
        # Write header
        writer.writerow(['Time', 'Pos_X', 'Pos_Y', 'Heading', 'Velocity', 'Angular_Velocity'])
        
        # Write data
        for i in range(len(data['time'])):
            writer.writerow([
                data['time'][i],
                data['pos_x'][i],
                data['pos_y'][i],
                data['heading'][i],
                data['velocity'][i],
                data['angular_velocity'][i]
            ])


def print_simulation_summary(data: Dict):
    """Print simulation summary statistics."""
    print("\n" + "="*50)
    print("SIMULATION SUMMARY")
    print("="*50)
    
    print(f"Duration: {data['time'][-1]:.2f} seconds")
    print(f"Total distance: {calculate_total_distance(data):.2f} meters")
    print(f"Max velocity: {max(data['velocity']):.2f} m/s")
    print(f"Avg velocity: {np.mean(data['velocity']):.2f} m/s")
    print(f"Final position: ({data['pos_x'][-1]:.2f}, {data['pos_y'][-1]:.2f})")
    print(f"Max angular velocity: {max(data['angular_velocity']):.2f} rad/s")


def calculate_total_distance(data: Dict) -> float:
    """Calculate total distance traveled."""
    total_distance = 0.0
    
    for i in range(1, len(data['pos_x'])):
        dx = data['pos_x'][i] - data['pos_x'][i-1]
        dy = data['pos_y'][i] - data['pos_y'][i-1]
        total_distance += np.sqrt(dx**2 + dy**2)
    
    return total_distance


def run_gui_simulation():
    """Run simulation with graphical user interface."""
    if not GUI_AVAILABLE:
        print("Error: GUI components not available. Please install required packages:")
        print("  pip install tkinter matplotlib numpy")
        return
    
    print("Starting GUI simulation...")
    app = SimulationGUI()
    app.run()


def create_test_scenario():
    """Create and run a predefined test scenario."""
    print("Running test scenario: Autonomous Navigation")
    
    simulator = VehicleSimulator()
    physics = VehiclePhysics()
    
    # Test scenario: Navigate around obstacles
    waypoints = [
        (0, 0),
        (10, 0),
        (10, 10),
        (0, 10),
        (0, 0)
    ]
    
    print("Waypoints:", waypoints)
    
    # Simple waypoint following
    dt = 0.05
    total_time = 0.0
    max_time = 60.0  # Maximum simulation time
    
    for i, (target_x, target_y) in enumerate(waypoints[1:], 1):
        print(f"Navigating to waypoint {i}: ({target_x}, {target_y})")
        
        while total_time < max_time:
            state = simulator.get_state_dict()
            current_x = state['position']['x']
            current_y = state['position']['y']
            current_heading = state['position']['heading']
            
            # Calculate distance to target
            dx = target_x - current_x
            dy = target_y - current_y
            distance = np.sqrt(dx**2 + dy**2)
            
            # Check if reached waypoint
            if distance < 1.0:  # 1 meter tolerance
                print(f"Reached waypoint {i} after {total_time:.2f} seconds")
                break
            
            # Simple navigation logic
            target_heading = np.arctan2(dy, dx)
            heading_error = target_heading - current_heading
            
            # Normalize heading error
            while heading_error > np.pi:
                heading_error -= 2 * np.pi
            while heading_error < -np.pi:
                heading_error += 2 * np.pi
            
            # Control commands
            steering_angle = np.clip(heading_error * 20, -30, 30)  # Proportional control
            drive_speed = min(30, distance * 10)  # Speed proportional to distance
            
            # Set motor commands
            simulator.set_motor_command('steering_front', steering_angle)
            simulator.set_motor_command('drive_front', drive_speed)
            simulator.set_motor_command('drive_rear_left', drive_speed * 0.9)
            simulator.set_motor_command('drive_rear_right', drive_speed * 0.9)
            
            # Update simulation
            simulator.update(dt)
            total_time += dt
        
        if total_time >= max_time:
            print("Test scenario timed out")
            break
    
    print(f"Test scenario completed in {total_time:.2f} seconds")


def main():
    """Main entry point for the simulation."""
    parser = argparse.ArgumentParser(description='Vehicle Control System Simulator')
    parser.add_argument('--mode', choices=['gui', 'headless', 'test'], default='gui',
                       help='Simulation mode (default: gui)')
    parser.add_argument('--duration', type=float, default=10.0,
                       help='Simulation duration in seconds (for headless mode)')
    parser.add_argument('--output', type=str, help='Output CSV file (for headless mode)')
    
    args = parser.parse_args()
    
    print("Vehicle Control System Simulator v2.1.0")
    print("="*50)
    
    try:
        if args.mode == 'gui':
            run_gui_simulation()
        elif args.mode == 'headless':
            run_headless_simulation(args.duration, args.output)
        elif args.mode == 'test':
            create_test_scenario()
        else:
            print(f"Unknown mode: {args.mode}")
            return 1
            
    except KeyboardInterrupt:
        print("\nSimulation interrupted by user")
        return 0
    except Exception as e:
        print(f"Error during simulation: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
