"""
Advanced Steering Controller
Implements Ackermann steering geometry, three-wheel steering, and pivot modes
"""

import math
import logging
from typing import Tuple, Optional, Dict
from dataclasses import dataclass

try:
    from ..config.constants import (
        MOTOR_IDS, GEAR_RATIOS, PHYSICAL, PivotDirection
    )
except ImportError:
    # Fallback for standalone testing
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from config.constants import (
        MOTOR_IDS, GEAR_RATIOS, PHYSICAL, PivotDirection
    )

@dataclass
class SteeringAngles:
    """Container for calculated steering angles"""
    left: float
    right: float
    front: float = 0.0  # For three-wheel systems

class AdvancedSteeringController:
    """Advanced steering control with Ackermann geometry and three-wheel support"""
    
    def __init__(self, motor_interface):
        """Initialize steering controller with motor interface"""
        self.motor_interface = motor_interface
        self.logger = logging.getLogger(__name__)
        
        # Vehicle geometry parameters (from original code)
        self.wheel_base = PHYSICAL.WHEEL_BASE  # 1500 mm
        self.wheel_tread = PHYSICAL.WHEEL_TREAD  # 1800 mm
        self.wheel_center_distance = self.wheel_tread / 2  # 900 mm
        
        self.logger.info(f"Steering controller initialized with geometry:")
        self.logger.info(f"  Wheel base: {self.wheel_base}mm")
        self.logger.info(f"  Wheel tread: {self.wheel_tread}mm")
        self.logger.info(f"  Center distance: {self.wheel_center_distance}mm")
    
    def calculate_ackermann_angles(self, input_rotation: float) -> SteeringAngles:
        """
        Calculate Ackermann steering angles for proper turning geometry
        
        Args:
            input_rotation: Input steering rotation (-1.0 to 1.0)
            
        Returns:
            SteeringAngles with calculated left and right wheel angles
        """
        if abs(input_rotation) < 0.001:  # Essentially straight
            return SteeringAngles(left=0.0, right=0.0)
        
        try:
            # Convert input rotation to angle in degrees
            angle_of_rotation = (input_rotation * 360.0) / GEAR_RATIOS.STEERING_MOTOR
            
            # Calculate radius of curvature
            radius_of_curvature = abs(
                self.wheel_base / math.tan(math.radians(angle_of_rotation))
            )
            
            # Calculate outside and inside wheel angles using Ackermann geometry
            outside_wheel_angle = math.degrees(
                math.atan(
                    self.wheel_base / (radius_of_curvature + self.wheel_center_distance)
                )
            )
            inside_wheel_angle = math.degrees(
                math.atan(
                    self.wheel_base / abs(radius_of_curvature - self.wheel_center_distance)
                )
            )
            
            # Convert angles back to motor rotations
            outside_rotation = (outside_wheel_angle / 360.0) * GEAR_RATIOS.STEERING_MOTOR
            inside_rotation = (inside_wheel_angle / 360.0) * GEAR_RATIOS.STEERING_MOTOR
            
            # Determine which wheel is inside/outside based on turn direction
            if input_rotation > 0:  # Right turn
                left_rotation = outside_rotation   # Left wheel is outside
                right_rotation = inside_rotation   # Right wheel is inside
            else:  # Left turn
                left_rotation = -inside_rotation   # Left wheel is inside
                right_rotation = -outside_rotation # Right wheel is outside
            
            self.logger.debug(f"Ackermann calculation:")
            self.logger.debug(f"  Input rotation: {input_rotation}")
            self.logger.debug(f"  Angle of rotation: {angle_of_rotation}°")
            self.logger.debug(f"  Radius of curvature: {radius_of_curvature}mm")
            self.logger.debug(f"  Outside wheel angle: {outside_wheel_angle}°")
            self.logger.debug(f"  Inside wheel angle: {inside_wheel_angle}°")
            self.logger.debug(f"  Left rotation: {left_rotation}")
            self.logger.debug(f"  Right rotation: {right_rotation}")
            
            return SteeringAngles(left=left_rotation, right=right_rotation)
            
        except (ValueError, ZeroDivisionError) as e:
            self.logger.error(f"Ackermann calculation failed: {e}")
            return SteeringAngles(left=0.0, right=0.0)
    
    def calculate_three_wheel_ackermann_angles(self, input_rotation: float) -> SteeringAngles:
        """
        Calculate three-wheel Ackermann steering angles
        
        Args:
            input_rotation: Input steering rotation (-1.0 to 1.0)
            
        Returns:
            SteeringAngles with calculated left, right, and front wheel angles
        """
        if abs(input_rotation) < 0.001:  # Essentially straight
            return SteeringAngles(left=0.0, right=0.0, front=0.0)
        
        try:
            # First calculate standard Ackermann angles
            angles = self.calculate_ackermann_angles(input_rotation)
            
            # Convert back to degrees for rear wheel calculation
            left_angle_deg = (angles.left * 360.0) / GEAR_RATIOS.STEERING_MOTOR
            right_angle_deg = (angles.right * 360.0) / GEAR_RATIOS.STEERING_MOTOR
            
            # Calculate rear (front) wheel angle as average of left and right
            # Note: The "front" wheel is actually at the rear in this vehicle configuration
            rear_wheel_angle_deg = (abs(left_angle_deg) + abs(right_angle_deg)) / 2
            
            # Apply correct sign based on turn direction
            if input_rotation > 0:  # Right turn
                rear_wheel_rotation = -(rear_wheel_angle_deg / 360.0) * GEAR_RATIOS.STEERING_MOTOR
            else:  # Left turn
                rear_wheel_rotation = (rear_wheel_angle_deg / 360.0) * GEAR_RATIOS.STEERING_MOTOR
            
            self.logger.debug(f"Three-wheel Ackermann calculation:")
            self.logger.debug(f"  Left angle: {left_angle_deg}°")
            self.logger.debug(f"  Right angle: {right_angle_deg}°") 
            self.logger.debug(f"  Rear angle: {rear_wheel_angle_deg}°")
            self.logger.debug(f"  Rear rotation: {rear_wheel_rotation}")
            
            return SteeringAngles(
                left=angles.left,
                right=angles.right, 
                front=rear_wheel_rotation
            )
            
        except Exception as e:
            self.logger.error(f"Three-wheel Ackermann calculation failed: {e}")
            return SteeringAngles(left=0.0, right=0.0, front=0.0)
    
    def apply_ackermann_steering(self, input_rotation: float) -> bool:
        """Apply Ackermann steering to motors"""
        try:
            angles = self.calculate_ackermann_angles(input_rotation)
            
            success = True
            success &= self.motor_interface.move_to_position(
                MOTOR_IDS.STEERING_REAR_LEFT, angles.left
            )
            success &= self.motor_interface.move_to_position(
                MOTOR_IDS.STEERING_REAR_RIGHT, angles.right
            )
            
            if success:
                self.logger.debug(f"Applied Ackermann steering: {input_rotation}")
            else:
                self.logger.error("Failed to apply Ackermann steering")
                
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to apply Ackermann steering: {e}")
            return False
    
    def apply_three_wheel_ackermann_steering(self, input_rotation: float) -> bool:
        """Apply three-wheel Ackermann steering to all motors"""
        try:
            angles = self.calculate_three_wheel_ackermann_angles(input_rotation)
            
            success = True
            success &= self.motor_interface.move_to_position(
                MOTOR_IDS.STEERING_REAR_LEFT, angles.left
            )
            success &= self.motor_interface.move_to_position(
                MOTOR_IDS.STEERING_REAR_RIGHT, angles.right
            )
            success &= self.motor_interface.move_to_position(
                MOTOR_IDS.STEERING_FRONT, angles.front
            )
            
            if success:
                self.logger.debug(f"Applied three-wheel Ackermann steering: {input_rotation}")
            else:
                self.logger.error("Failed to apply three-wheel Ackermann steering")
                
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to apply three-wheel Ackermann steering: {e}")
            return False
    
    def set_pivot_mode(self, direction: PivotDirection) -> bool:
        """
        Set vehicle to pivot mode with precise angles
        
        Args:
            direction: Pivot direction (LEFT, RIGHT, or NONE)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Calculate absolute rotations for different angles
            rotation_45_deg = (45.0 / 360.0) * GEAR_RATIOS.STEERING_MOTOR
            rotation_90_deg = (90.0 / 360.0) * GEAR_RATIOS.STEERING_MOTOR  
            rotation_135_deg = (135.0 / 360.0) * GEAR_RATIOS.STEERING_MOTOR
            
            if direction == PivotDirection.LEFT:
                # Left pivot configuration (from original code)
                motor_positions = {
                    MOTOR_IDS.STEERING_REAR_LEFT: -rotation_135_deg,
                    MOTOR_IDS.STEERING_REAR_RIGHT: -rotation_45_deg,
                    MOTOR_IDS.STEERING_FRONT: rotation_90_deg
                }
                self.logger.info("Setting LEFT pivot mode")
                
            elif direction == PivotDirection.RIGHT:
                # Right pivot configuration (from original code)
                motor_positions = {
                    MOTOR_IDS.STEERING_REAR_LEFT: rotation_45_deg,
                    MOTOR_IDS.STEERING_REAR_RIGHT: rotation_135_deg,
                    MOTOR_IDS.STEERING_FRONT: -rotation_90_deg
                }
                self.logger.info("Setting RIGHT pivot mode")
                
            else:  # PivotDirection.NONE
                # Straight configuration
                motor_positions = {
                    MOTOR_IDS.STEERING_REAR_LEFT: 0.0,
                    MOTOR_IDS.STEERING_REAR_RIGHT: 0.0,
                    MOTOR_IDS.STEERING_FRONT: 0.0
                }
                self.logger.info("Setting STRAIGHT mode (pivot disabled)")
            
            # Apply positions to all steering motors
            success = True
            for motor_id, position in motor_positions.items():
                if not self.motor_interface.move_to_position(motor_id, position):
                    success = False
                    self.logger.error(f"Failed to set pivot angle for motor {motor_id}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to set pivot mode {direction}: {e}")
            return False
    
    def move_steering_to_90_degrees(self, direction: str) -> bool:
        """
        Move all steering motors to 90-degree position
        
        Args:
            direction: "left", "right", or "center"
            
        Returns:
            True if successful, False otherwise
        """
        try:
            rotation_90_deg = (90.0 / 360.0) * GEAR_RATIOS.STEERING_MOTOR
            
            if direction.lower() == "left":
                target_rotation = rotation_90_deg
                self.logger.info("Moving steering motors to 90° LEFT")
            elif direction.lower() == "right":
                target_rotation = -rotation_90_deg
                self.logger.info("Moving steering motors to 90° RIGHT") 
            elif direction.lower() == "center":
                target_rotation = 0.0
                self.logger.info("Moving steering motors to CENTER (0°)")
            else:
                self.logger.error(f"Invalid direction: {direction}")
                return False
            
            # Apply same angle to all steering motors
            motor_positions = {
                MOTOR_IDS.STEERING_REAR_LEFT: target_rotation,
                MOTOR_IDS.STEERING_REAR_RIGHT: target_rotation,
                MOTOR_IDS.STEERING_FRONT: target_rotation
            }
            
            success = True
            for motor_id, position in motor_positions.items():
                if not self.motor_interface.move_to_position(motor_id, position):
                    success = False
                    self.logger.error(f"Failed to move motor {motor_id} to {direction}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to move steering to 90 degrees {direction}: {e}")
            return False
    
    def automatic_straighten_steering(self, back_rotation: float) -> bool:
        """
        Automatically straighten steering after a turn
        
        Args:
            back_rotation: Amount to rotate back towards straight
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # This function would implement gradual return to straight position
            # For now, just move to center
            return self.move_steering_to_90_degrees("center")
            
        except Exception as e:
            self.logger.error(f"Failed to automatically straighten steering: {e}")
            return False
    
    def get_current_steering_angles(self) -> Optional[SteeringAngles]:
        """
        Get current steering angles from motors
        
        Returns:
            Current steering angles or None if failed
        """
        try:
            # This would read actual motor positions
            # For now, return None as we don't have position feedback
            self.logger.warning("Position feedback not implemented")
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to get current steering angles: {e}")
            return None
    
    def validate_steering_limits(self, angles: SteeringAngles) -> bool:
        """
        Validate that steering angles are within safe limits
        
        Args:
            angles: Steering angles to validate
            
        Returns:
            True if within limits, False otherwise
        """
        max_rotation = PHYSICAL.MAX_STEERING_ROTATION
        
        if abs(angles.left) > max_rotation:
            self.logger.error(f"Left steering angle {angles.left} exceeds limit {max_rotation}")
            return False
            
        if abs(angles.right) > max_rotation:
            self.logger.error(f"Right steering angle {angles.right} exceeds limit {max_rotation}")
            return False
            
        if abs(angles.front) > max_rotation:
            self.logger.error(f"Front steering angle {angles.front} exceeds limit {max_rotation}")
            return False
            
        return True
