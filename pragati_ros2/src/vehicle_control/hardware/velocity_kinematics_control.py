#!/usr/bin/env python3
"""
Velocity-Based Kinematics Controller for Three-Wheeled Robot

This module implements rigid-body velocity kinematics for a robot with 3 fully-actuated wheels.
Each wheel has both steering (position) and drive (velocity) control.

Kinematics equations (for each wheel i at position (xi, yi) from base_link):
    vix = vx - omega * yi     (x-component of wheel velocity)
    viy = omega * xi          (y-component of wheel velocity)
    
    steer_angle_i = atan2(viy, vix)     (steering angle)
    wheel_speed_i = sqrt(vix^2 + viy^2) / wheel_radius   (wheel angular velocity)

This is NOT Ackermann steering - it's proper velocity-based kinematics that works
correctly for asymmetric wheel configurations.

Based on: steering control/triwheel_robot/triwheel_robot/kinematics_node.py
Adapted for: pragati_ros2 vehicle control
"""

import math
import logging
from typing import Dict, Tuple
from dataclasses import dataclass

try:
    from ..config.constants import PHYSICAL
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from config.constants import PHYSICAL


@dataclass
class WheelCommand:
    """Container for a single wheel's steering and drive commands"""
    steering_angle: float  # radians
    wheel_speed: float     # rad/s
    

@dataclass
class VehicleWheelCommands:
    """Container for all three wheels' commands"""
    front: WheelCommand
    rear_left: WheelCommand
    rear_right: WheelCommand


class VelocityKinematicsController:
    """
    Velocity-based kinematics controller for three-wheeled robot.
    
    Uses rigid-body velocity kinematics to compute per-wheel steering angles
    and drive speeds from body-frame velocity commands.
    """
    
    def __init__(self, motor_interface=None):
        """
        Initialize velocity kinematics controller
        
        Args:
            motor_interface: Optional motor interface for direct motor control
        """
        self.motor_interface = motor_interface
        self.logger = logging.getLogger(__name__)
        
        # Vehicle geometry parameters from constants
        self.wheel_radius = PHYSICAL.WHEEL_DIAMETER / 2 / 1000.0  # Convert mm to meters
        wheelbase_m = PHYSICAL.WHEEL_BASE / 1000.0  # Convert mm to meters
        tread_m = PHYSICAL.WHEEL_TREAD / 1000.0     # Convert mm to meters
        
        # Wheel positions relative to base_link (x, y in meters)
        # Front wheel is at front center, rear wheels at back corners
        self.wheel_positions = {
            'front': {'x': wheelbase_m / 2, 'y': 0.0},
            'rear_left': {'x': -wheelbase_m / 2, 'y': tread_m / 2},
            'rear_right': {'x': -wheelbase_m / 2, 'y': -tread_m / 2}
        }
        
        # Safety limits
        self.max_steering_angle = math.radians(90.0)  # ±90 degrees max
        self.max_wheel_speed = 10.0  # rad/s (adjustable based on motor specs)
        
        self.logger.info("Velocity Kinematics Controller initialized")
        self.logger.info(f"  Wheel radius: {self.wheel_radius:.4f} m")
        self.logger.info(f"  Wheelbase: {wheelbase_m:.4f} m")
        self.logger.info(f"  Tread: {tread_m:.4f} m")
        self.logger.info("  Wheel positions:")
        for name, pos in self.wheel_positions.items():
            self.logger.info(f"    {name}: x={pos['x']:.3f}m, y={pos['y']:.3f}m")
    
    def compute_wheel_kinematics(self, vx: float, omega: float, wheel_x: float, wheel_y: float) -> Tuple[float, float]:
        """
        Compute steering angle and wheel speed for a single wheel.
        
        This uses velocity-based rigid-body kinematics:
            vix = vx - omega * yi     (linear velocity x-component at wheel)
            viy = omega * xi          (linear velocity y-component at wheel)
            
        Args:
            vx: Linear velocity in x direction (m/s)
            omega: Angular velocity about z axis (rad/s)
            wheel_x: Wheel x position relative to base_link (m)
            wheel_y: Wheel y position relative to base_link (m)
            
        Returns:
            (steering_angle_rad, wheel_speed_rad_s) tuple
        """
        # Compute velocity components at wheel location
        # This is the key velocity-based kinematics equation
        vix = vx - omega * wheel_y  # Cross product: omega x r gives -omega*y for x component
        viy = omega * wheel_x       # Cross product: omega x r gives omega*x for y component
        
        # Compute steering angle (direction of velocity vector)
        if abs(vix) < 1e-6 and abs(viy) < 1e-6:
            # Near zero velocity - keep current steering angle (return 0)
            steering_angle = 0.0
            wheel_speed = 0.0
        else:
            steering_angle = math.atan2(viy, vix)
            
            # Compute wheel speed (magnitude of velocity / wheel_radius)
            linear_speed = math.sqrt(vix**2 + viy**2)
            wheel_speed = linear_speed / self.wheel_radius
        
        # Apply limits
        steering_angle = max(-self.max_steering_angle, 
                           min(self.max_steering_angle, steering_angle))
        wheel_speed = max(-self.max_wheel_speed, 
                         min(self.max_wheel_speed, wheel_speed))
        
        return steering_angle, wheel_speed
    
    def calculate_wheel_commands(self, linear_vel: float, angular_vel: float) -> VehicleWheelCommands:
        """
        Calculate wheel commands for all three wheels from body velocity.
        
        Args:
            linear_vel: Linear velocity in x direction (m/s)
            angular_vel: Angular velocity about z axis (rad/s)
            
        Returns:
            VehicleWheelCommands with steering angles and wheel speeds for all wheels
        """
        # Compute kinematics for each wheel
        results = {}
        for wheel_name, wheel_pos in self.wheel_positions.items():
            steer_angle, wheel_speed = self.compute_wheel_kinematics(
                linear_vel, angular_vel, wheel_pos['x'], wheel_pos['y']
            )
            results[wheel_name] = WheelCommand(
                steering_angle=steer_angle,
                wheel_speed=wheel_speed
            )
        
        self.logger.debug(
            f'Velocity kinematics: vx={linear_vel:.3f}m/s, ω={angular_vel:.3f}rad/s → '
            f'F[{math.degrees(results["front"].steering_angle):.1f}°, {results["front"].wheel_speed:.2f}rad/s] '
            f'RL[{math.degrees(results["rear_left"].steering_angle):.1f}°, {results["rear_left"].wheel_speed:.2f}rad/s] '
            f'RR[{math.degrees(results["rear_right"].steering_angle):.1f}°, {results["rear_right"].wheel_speed:.2f}rad/s]'
        )
        
        return VehicleWheelCommands(
            front=results['front'],
            rear_left=results['rear_left'],
            rear_right=results['rear_right']
        )
    
    def apply_velocity_command(self, linear_vel: float, angular_vel: float) -> bool:
        """
        Apply velocity command to motors using motor interface.
        
        Args:
            linear_vel: Linear velocity in x direction (m/s)
            angular_vel: Angular velocity about z axis (rad/s)
            
        Returns:
            True if commands applied successfully, False otherwise
        """
        if not self.motor_interface:
            self.logger.error("No motor interface configured")
            return False
        
        try:
            # Calculate wheel commands
            commands = self.calculate_wheel_commands(linear_vel, angular_vel)
            
            # Apply to motors (implementation depends on motor interface)
            # This would need to be implemented based on your motor interface API
            self.logger.warning("Motor interface apply_velocity_command not fully implemented")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to apply velocity command: {e}")
            return False
