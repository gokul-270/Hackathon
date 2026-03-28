"""
Vehicle Control System - Vehicle Simulator

Provides a comprehensive vehicle simulation engine that models
the behavior of a 1 front + 2 rear motor vehicle system.
"""

import numpy as np
import time
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

# Import with fallback
try:
    from config.constants import MotorIDs, SystemConstants
except ImportError:
    # Create minimal constants for standalone operation
    class MotorIDs:
        STEERING_FRONT = 1
        STEERING_REAR_LEFT = 3
        STEERING_REAR_RIGHT = 5
        DRIVE_FRONT = 0
        DRIVE_REAR_LEFT = 2
        DRIVE_REAR_RIGHT = 4
    
    class SystemConstants:
        MAX_STEERING_ANGLE = 45.0

try:
    from physics_engine import VehiclePhysics
except ImportError:
    try:
        from .physics_engine import VehiclePhysics
    except ImportError:
        VehiclePhysics = None


@dataclass
class VehicleState:
    """Vehicle state representation."""
    # Position and orientation
    x: float = 0.0
    y: float = 0.0
    heading: float = 0.0  # radians
    
    # Velocities
    velocity_x: float = 0.0
    velocity_y: float = 0.0
    angular_velocity: float = 0.0
    
    # Motor states
    steering_front: float = 0.0
    steering_rear_left: float = 0.0
    steering_rear_right: float = 0.0
    drive_front: float = 0.0
    drive_rear_left: float = 0.0
    drive_rear_right: float = 0.0
    
    # System states
    timestamp: float = 0.0
    system_active: bool = True
    emergency_stop: bool = False


class VehicleSimulator:
    """
    Main vehicle simulator class.
    
    Simulates the behavior of a vehicle with:
    - 1 front motor (steering + drive)
    - 2 rear motors (steering + drive each)
    - Realistic physics and dynamics
    - Motor command processing
    """
    
    def __init__(self):
        self.state = VehicleState()
        self.physics = VehiclePhysics()
        
        # Motor commands (degrees for steering, percentage for drive)
        self.motor_commands = {
            'steering_front': 0.0,
            'steering_rear_left': 0.0,
            'steering_rear_right': 0.0,
            'drive_front': 0.0,
            'drive_rear_left': 0.0,
            'drive_rear_right': 0.0
        }
        
        # Simulation parameters
        self.max_steering_angle = 45.0  # degrees
        self.max_steering_rate = 90.0   # degrees/second
        self.max_drive_speed = 50.0     # m/s
        self.max_acceleration = 5.0     # m/s²
        
        # Internal state tracking
        self.previous_time = time.time()
        self.simulation_time = 0.0
        
        # Motor smoothing (to simulate real motor response)
        self.motor_actual = self.motor_commands.copy()
        self.motor_response_time = 0.1  # seconds
        
    def set_motor_command(self, motor_name: str, value: float):
        """
        Set a motor command value.
        
        Args:
            motor_name: Name of the motor ('steering_front', 'drive_rear_left', etc.)
            value: Command value (degrees for steering, percentage for drive)
        """
        if motor_name in self.motor_commands:
            # Clamp values to valid ranges
            if 'steering' in motor_name:
                value = np.clip(value, -self.max_steering_angle, self.max_steering_angle)
            else:  # drive motor
                value = np.clip(value, -100.0, 100.0)
            
            self.motor_commands[motor_name] = value
    
    def get_motor_command(self, motor_name: str) -> float:
        """Get current motor command value."""
        return self.motor_commands.get(motor_name, 0.0)
    
    def update(self, dt: float) -> Dict:
        """
        Update the vehicle simulation by one time step.
        
        Args:
            dt: Time step in seconds
            
        Returns:
            Dictionary containing current vehicle state
        """
        self.simulation_time += dt
        
        # Update motor responses (simulate motor dynamics)
        self._update_motor_responses(dt)
        
        # Calculate vehicle dynamics
        self._update_physics(dt)
        
        # Update vehicle state
        self._update_state(dt)
        
        return self.get_state_dict()
    
    def _update_motor_responses(self, dt: float):
        """Update actual motor positions based on commands (with realistic response time)."""
        response_factor = dt / self.motor_response_time
        
        for motor_name in self.motor_commands:
            command = self.motor_commands[motor_name]
            actual = self.motor_actual[motor_name]
            
            # First-order response
            self.motor_actual[motor_name] = actual + (command - actual) * response_factor
    
    def _update_physics(self, dt: float):
        """Update vehicle physics based on current motor states."""
        # Get actual steering angles (in radians)
        steering_front = np.radians(self.motor_actual['steering_front'])
        steering_rear_left = np.radians(self.motor_actual['steering_rear_left'])
        steering_rear_right = np.radians(self.motor_actual['steering_rear_right'])
        
        # Get drive commands (as percentage, convert to force)
        drive_front = self.motor_actual['drive_front'] / 100.0
        drive_rear_left = self.motor_actual['drive_rear_left'] / 100.0
        drive_rear_right = self.motor_actual['drive_rear_right'] / 100.0
        
        # Calculate forces and moments
        forces, moments = self._calculate_forces_and_moments(
            steering_front, steering_rear_left, steering_rear_right,
            drive_front, drive_rear_left, drive_rear_right
        )
        
        # Update physics engine
        self.physics.update(forces, moments, dt)
        
        # Get updated state from physics
        physics_state = self.physics.get_state()
        
        # Update vehicle state
        self.state.x = physics_state['position']['x']
        self.state.y = physics_state['position']['y']
        self.state.heading = physics_state['position']['heading']
        self.state.velocity_x = physics_state['velocity']['x']
        self.state.velocity_y = physics_state['velocity']['y']
        self.state.angular_velocity = physics_state['velocity']['angular']
    
    def _calculate_forces_and_moments(self, steering_front: float, steering_rear_left: float, 
                                    steering_rear_right: float, drive_front: float, 
                                    drive_rear_left: float, drive_rear_right: float) -> Tuple[Dict, Dict]:
        """
        Calculate forces and moments from motor commands.
        
        Returns:
            Tuple of (forces, moments) dictionaries
        """
        # Vehicle dimensions (meters)
        wheelbase = 2.5
        track_width = 1.8
        front_offset = wheelbase / 2
        rear_offset = -wheelbase / 2
        
        # Maximum force per motor (Newtons)
        max_force = 2000.0
        
        # Initialize forces and moments
        total_force_x = 0.0
        total_force_y = 0.0
        total_moment = 0.0
        
        # Front motor
        if abs(drive_front) > 0.001:
            # Force magnitude
            force_magnitude = drive_front * max_force
            
            # Force direction (in vehicle frame)
            force_x = force_magnitude * np.cos(steering_front)
            force_y = force_magnitude * np.sin(steering_front)
            
            # Add to totals
            total_force_x += force_x
            total_force_y += force_y
            
            # Moment from force at front axle
            total_moment += front_offset * force_y
        
        # Rear left motor
        if abs(drive_rear_left) > 0.001:
            force_magnitude = drive_rear_left * max_force
            
            force_x = force_magnitude * np.cos(steering_rear_left)
            force_y = force_magnitude * np.sin(steering_rear_left)
            
            total_force_x += force_x
            total_force_y += force_y
            
            # Moment from force at rear left position
            moment_arm_x = rear_offset
            moment_arm_y = -track_width / 2
            total_moment += moment_arm_x * force_y - moment_arm_y * force_x
        
        # Rear right motor
        if abs(drive_rear_right) > 0.001:
            force_magnitude = drive_rear_right * max_force
            
            force_x = force_magnitude * np.cos(steering_rear_right)
            force_y = force_magnitude * np.sin(steering_rear_right)
            
            total_force_x += force_x
            total_force_y += force_y
            
            # Moment from force at rear right position
            moment_arm_x = rear_offset
            moment_arm_y = track_width / 2
            total_moment += moment_arm_x * force_y - moment_arm_y * force_x
        
        # Add drag forces
        drag_coefficient = 0.5
        velocity_magnitude = np.sqrt(self.state.velocity_x**2 + self.state.velocity_y**2)
        if velocity_magnitude > 0.1:
            drag_force = -drag_coefficient * velocity_magnitude**2
            velocity_direction_x = self.state.velocity_x / velocity_magnitude
            velocity_direction_y = self.state.velocity_y / velocity_magnitude
            
            total_force_x += drag_force * velocity_direction_x
            total_force_y += drag_force * velocity_direction_y
        
        # Add angular drag
        angular_drag = -0.1 * self.state.angular_velocity
        total_moment += angular_drag
        
        forces = {
            'x': total_force_x,
            'y': total_force_y
        }
        
        moments = {
            'z': total_moment
        }
        
        return forces, moments
    
    def _update_state(self, dt: float):
        """Update internal state variables."""
        self.state.timestamp = self.simulation_time
        
        # Update motor states
        self.state.steering_front = self.motor_actual['steering_front']
        self.state.steering_rear_left = self.motor_actual['steering_rear_left']
        self.state.steering_rear_right = self.motor_actual['steering_rear_right']
        self.state.drive_front = self.motor_actual['drive_front']
        self.state.drive_rear_left = self.motor_actual['drive_rear_left']
        self.state.drive_rear_right = self.motor_actual['drive_rear_right']
    
    def get_state_dict(self) -> Dict:
        """
        Get current vehicle state as a dictionary.
        
        Returns:
            Dictionary containing all state information
        """
        return {
            'position': {
                'x': self.state.x,
                'y': self.state.y,
                'heading': self.state.heading
            },
            'velocity': {
                'x': self.state.velocity_x,
                'y': self.state.velocity_y,
                'linear': np.sqrt(self.state.velocity_x**2 + self.state.velocity_y**2),
                'angular': self.state.angular_velocity
            },
            'motors': {
                'steering_front': self.state.steering_front,
                'steering_rear_left': self.state.steering_rear_left,
                'steering_rear_right': self.state.steering_rear_right,
                'drive_front': self.state.drive_front,
                'drive_rear_left': self.state.drive_rear_left,
                'drive_rear_right': self.state.drive_rear_right
            },
            'system': {
                'timestamp': self.state.timestamp,
                'active': self.state.system_active,
                'emergency_stop': self.state.emergency_stop
            }
        }
    
    def reset(self):
        """Reset the vehicle simulation to initial state."""
        self.state = VehicleState()
        self.physics.reset()
        
        # Reset motor commands
        for motor in self.motor_commands:
            self.motor_commands[motor] = 0.0
            self.motor_actual[motor] = 0.0
        
        self.simulation_time = 0.0
        self.previous_time = time.time()
    
    def set_position(self, x: float, y: float, heading: float = 0.0):
        """Set vehicle position and heading."""
        self.state.x = x
        self.state.y = y
        self.state.heading = heading
        self.physics.set_position(x, y, heading)
    
    def set_velocity(self, vx: float, vy: float, angular: float = 0.0):
        """Set vehicle velocity."""
        self.state.velocity_x = vx
        self.state.velocity_y = vy
        self.state.angular_velocity = angular
        self.physics.set_velocity(vx, vy, angular)
    
    def emergency_stop(self):
        """Trigger emergency stop."""
        self.state.emergency_stop = True
        for motor in self.motor_commands:
            self.motor_commands[motor] = 0.0
    
    def clear_emergency_stop(self):
        """Clear emergency stop."""
        self.state.emergency_stop = False
    
    def get_motor_feedback(self) -> Dict:
        """
        Get motor feedback information.
        
        Returns:
            Dictionary with motor positions, velocities, and status
        """
        return {
            'positions': {
                'steering_front': self.motor_actual['steering_front'],
                'steering_rear_left': self.motor_actual['steering_rear_left'],
                'steering_rear_right': self.motor_actual['steering_rear_right'],
                'drive_front': self.motor_actual['drive_front'],
                'drive_rear_left': self.motor_actual['drive_rear_left'],
                'drive_rear_right': self.motor_actual['drive_rear_right']
            },
            'commands': self.motor_commands.copy(),
            'errors': {motor: cmd - actual for motor, (cmd, actual) in 
                      zip(self.motor_commands.keys(), 
                          zip(self.motor_commands.values(), self.motor_actual.values()))}
        }
