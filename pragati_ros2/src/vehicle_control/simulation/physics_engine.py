"""
Vehicle Control System - Physics Engine

Provides realistic vehicle physics simulation including:
- Rigid body dynamics
- Tire forces and slip
- Suspension effects
- Environmental factors
"""

import numpy as np
from typing import Dict, Tuple
from dataclasses import dataclass


@dataclass
class PhysicsParameters:
    """Vehicle physics parameters."""
    # Vehicle dimensions
    mass: float = 1000.0              # kg
    inertia: float = 2000.0           # kg⋅m²
    wheelbase: float = 2.5            # m
    track_width: float = 1.8          # m
    
    # Tire parameters
    tire_radius: float = 0.35         # m
    tire_friction: float = 0.8        # coefficient
    
    # Aerodynamics
    drag_coefficient: float = 0.3     # Cd
    frontal_area: float = 2.2         # m²
    air_density: float = 1.225        # kg/m³
    
    # Environmental
    gravity: float = 9.81             # m/s²
    ground_friction: float = 0.02     # rolling resistance


class VehiclePhysics:
    """
    Advanced vehicle physics simulation engine.
    
    Implements realistic vehicle dynamics including:
    - 6-DOF rigid body motion
    - Tire force models
    - Aerodynamic effects
    - Environmental interactions
    """
    
    def __init__(self, params: PhysicsParameters = None):
        self.params = params or PhysicsParameters()
        
        # State variables
        self.position = np.array([0.0, 0.0, 0.0])  # x, y, heading
        self.velocity = np.array([0.0, 0.0, 0.0])  # vx, vy, angular_vel
        self.acceleration = np.array([0.0, 0.0, 0.0])  # ax, ay, angular_acc
        
        # Force and moment accumulators
        self.total_forces = np.array([0.0, 0.0])
        self.total_moments = 0.0
        
        # Tire states
        self.tire_forces = {
            'front': np.array([0.0, 0.0]),
            'rear_left': np.array([0.0, 0.0]),
            'rear_right': np.array([0.0, 0.0])
        }
        
        # Simulation time
        self.time = 0.0
    
    def update_parameters(self, **kwargs):
        """Update physics parameters."""
        for key, value in kwargs.items():
            if hasattr(self.params, key):
                setattr(self.params, key, value)
    
    def update(self, forces: Dict, moments: Dict, dt: float):
        """
        Update physics simulation by one time step.
        
        Args:
            forces: Dictionary of external forces {'x': fx, 'y': fy}
            moments: Dictionary of external moments {'z': mz}
            dt: Time step in seconds
        """
        self.time += dt
        
        # Clear accumulators
        self.total_forces = np.array([0.0, 0.0])
        self.total_moments = 0.0
        
        # Add external forces and moments
        self.total_forces[0] += forces.get('x', 0.0)
        self.total_forces[1] += forces.get('y', 0.0)
        self.total_moments += moments.get('z', 0.0)
        
        # Add environmental forces
        self._add_aerodynamic_forces()
        self._add_rolling_resistance()
        
        # Calculate accelerations
        self._calculate_accelerations()
        
        # Integrate motion
        self._integrate_motion(dt)
        
        # Apply constraints and limits
        self._apply_constraints()
    
    def _add_aerodynamic_forces(self):
        """Add aerodynamic drag forces."""
        # Get velocity in world frame
        velocity_magnitude = np.sqrt(self.velocity[0]**2 + self.velocity[1]**2)
        
        if velocity_magnitude > 0.1:  # Avoid division by zero
            # Drag force magnitude
            drag_force = 0.5 * self.params.air_density * self.params.drag_coefficient * \
                        self.params.frontal_area * velocity_magnitude**2
            
            # Drag force direction (opposite to velocity)
            drag_direction = -self.velocity[:2] / velocity_magnitude
            
            # Add drag forces
            self.total_forces += drag_force * drag_direction
    
    def _add_rolling_resistance(self):
        """Add rolling resistance forces."""
        # Normal force on each wheel (simplified)
        normal_force = self.params.mass * self.params.gravity / 3  # 3 contact points
        
        # Rolling resistance force per wheel
        rolling_resistance = self.params.ground_friction * normal_force
        
        # Apply resistance opposite to motion
        velocity_magnitude = np.sqrt(self.velocity[0]**2 + self.velocity[1]**2)
        if velocity_magnitude > 0.01:
            resistance_direction = -self.velocity[:2] / velocity_magnitude
            self.total_forces += 3 * rolling_resistance * resistance_direction
    
    def _calculate_accelerations(self):
        """Calculate accelerations from total forces and moments."""
        # Linear accelerations (in world frame)
        self.acceleration[0] = self.total_forces[0] / self.params.mass
        self.acceleration[1] = self.total_forces[1] / self.params.mass
        
        # Angular acceleration
        self.acceleration[2] = self.total_moments / self.params.inertia
    
    def _integrate_motion(self, dt: float):
        """Integrate motion equations using Euler method."""
        # Update velocities
        self.velocity += self.acceleration * dt
        
        # Update position (convert local velocities to world frame)
        heading = self.position[2]
        world_velocity = np.array([
            self.velocity[0] * np.cos(heading) - self.velocity[1] * np.sin(heading),
            self.velocity[0] * np.sin(heading) + self.velocity[1] * np.cos(heading)
        ])
        
        self.position[0] += world_velocity[0] * dt
        self.position[1] += world_velocity[1] * dt
        self.position[2] += self.velocity[2] * dt
        
        # Normalize heading angle
        self.position[2] = self._normalize_angle(self.position[2])
    
    def _apply_constraints(self):
        """Apply physical constraints and limits."""
        # Limit maximum speeds
        max_linear_speed = 50.0  # m/s
        max_angular_speed = 5.0  # rad/s
        
        velocity_magnitude = np.sqrt(self.velocity[0]**2 + self.velocity[1]**2)
        if velocity_magnitude > max_linear_speed:
            scale = max_linear_speed / velocity_magnitude
            self.velocity[0] *= scale
            self.velocity[1] *= scale
        
        if abs(self.velocity[2]) > max_angular_speed:
            self.velocity[2] = np.sign(self.velocity[2]) * max_angular_speed
    
    def _normalize_angle(self, angle: float) -> float:
        """Normalize angle to [-π, π] range."""
        while angle > np.pi:
            angle -= 2 * np.pi
        while angle < -np.pi:
            angle += 2 * np.pi
        return angle
    
    def get_state(self) -> Dict:
        """
        Get current physics state.
        
        Returns:
            Dictionary containing position, velocity, and acceleration data
        """
        return {
            'position': {
                'x': self.position[0],
                'y': self.position[1],
                'heading': self.position[2]
            },
            'velocity': {
                'x': self.velocity[0],
                'y': self.velocity[1],
                'linear': np.sqrt(self.velocity[0]**2 + self.velocity[1]**2),
                'angular': self.velocity[2]
            },
            'acceleration': {
                'x': self.acceleration[0],
                'y': self.acceleration[1],
                'linear': np.sqrt(self.acceleration[0]**2 + self.acceleration[1]**2),
                'angular': self.acceleration[2]
            },
            'forces': {
                'total_x': self.total_forces[0],
                'total_y': self.total_forces[1],
                'total_moment': self.total_moments
            },
            'time': self.time
        }
    
    def set_position(self, x: float, y: float, heading: float):
        """Set vehicle position and heading."""
        self.position = np.array([x, y, heading])
    
    def set_velocity(self, vx: float, vy: float, angular: float):
        """Set vehicle velocity."""
        self.velocity = np.array([vx, vy, angular])
    
    def reset(self):
        """Reset physics simulation to initial state."""
        self.position = np.array([0.0, 0.0, 0.0])
        self.velocity = np.array([0.0, 0.0, 0.0])
        self.acceleration = np.array([0.0, 0.0, 0.0])
        self.total_forces = np.array([0.0, 0.0])
        self.total_moments = 0.0
        self.time = 0.0
        
        for tire in self.tire_forces:
            self.tire_forces[tire] = np.array([0.0, 0.0])
    
    def calculate_tire_forces(self, steering_angles: Dict, drive_commands: Dict) -> Dict:
        """
        Calculate tire forces based on steering angles and drive commands.
        
        Args:
            steering_angles: Dictionary of steering angles in radians
            drive_commands: Dictionary of drive commands (0-1)
            
        Returns:
            Dictionary of tire forces
        """
        tire_forces = {}
        
        # Maximum tire force
        max_force = 3000.0  # N
        
        for tire_name in ['front', 'rear_left', 'rear_right']:
            if tire_name in steering_angles and tire_name in drive_commands:
                # Get steering angle and drive command
                angle = steering_angles[tire_name]
                drive = drive_commands[tire_name]
                
                # Calculate force magnitude
                force_magnitude = drive * max_force
                
                # Calculate force components
                fx = force_magnitude * np.cos(angle)
                fy = force_magnitude * np.sin(angle)
                
                tire_forces[tire_name] = np.array([fx, fy])
            else:
                tire_forces[tire_name] = np.array([0.0, 0.0])
        
        return tire_forces
    
    def get_tire_slip(self) -> Dict:
        """Calculate tire slip ratios."""
        # Simplified tire slip calculation
        tire_slip = {}
        
        velocity_magnitude = np.sqrt(self.velocity[0]**2 + self.velocity[1]**2)
        
        for tire_name in ['front', 'rear_left', 'rear_right']:
            if velocity_magnitude > 0.1:
                # Simplified slip calculation
                slip_ratio = abs(self.velocity[0]) / (velocity_magnitude + 0.01)
                tire_slip[tire_name] = min(slip_ratio, 1.0)
            else:
                tire_slip[tire_name] = 0.0
        
        return tire_slip
    
    def apply_disturbance(self, force_x: float, force_y: float, moment_z: float):
        """Apply external disturbance forces and moments."""
        self.total_forces[0] += force_x
        self.total_forces[1] += force_y
        self.total_moments += moment_z
    
    def get_energy_consumption(self) -> float:
        """
        Calculate instantaneous energy consumption.
        
        Returns:
            Power consumption in Watts
        """
        # Simplified energy calculation
        velocity_magnitude = np.sqrt(self.velocity[0]**2 + self.velocity[1]**2)
        force_magnitude = np.sqrt(self.total_forces[0]**2 + self.total_forces[1]**2)
        
        # Power = Force ⋅ Velocity
        power = force_magnitude * velocity_magnitude
        
        # Add rotational power
        rotational_power = abs(self.total_moments * self.velocity[2])
        
        return power + rotational_power
    
    def get_stability_metrics(self) -> Dict:
        """
        Calculate vehicle stability metrics.
        
        Returns:
            Dictionary with stability indicators
        """
        velocity_magnitude = np.sqrt(self.velocity[0]**2 + self.velocity[1]**2)
        
        # Understeer/oversteer indicator
        if velocity_magnitude > 1.0:
            lateral_acceleration = self.acceleration[1]
            angular_velocity = self.velocity[2]
            
            # Simplified stability metric
            stability_factor = abs(lateral_acceleration) / (velocity_magnitude**2 + 0.01)
            understeer_gradient = angular_velocity / (velocity_magnitude + 0.01)
        else:
            stability_factor = 0.0
            understeer_gradient = 0.0
        
        return {
            'stability_factor': stability_factor,
            'understeer_gradient': understeer_gradient,
            'velocity_magnitude': velocity_magnitude,
            'lateral_acceleration': self.acceleration[1],
            'angular_velocity': self.velocity[2]
        }
