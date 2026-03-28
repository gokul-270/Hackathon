"""
Motor Controller Abstraction
Provides high-level interface for motor operations
"""
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from enum import Enum, auto
import threading

try:
    from config.constants import (
        MotorIDs, GearRatios, MotorLimits, PHYSICAL, 
        VehicleState, PivotDirection
    )
    from .advanced_steering import AdvancedSteeringController, SteeringAngles
except ImportError:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from config.constants import (
        MotorIDs, GearRatios, MotorLimits, PHYSICAL, 
        VehicleState, PivotDirection
    )
    from hardware.advanced_steering import AdvancedSteeringController, SteeringAngles


class MotorControllerError(Exception):
    """Motor controller error"""
    pass


class MotorError(Exception):
    """Motor operation error"""
    pass

class SafetyLimitError(MotorError):
    """Safety limit violation error"""
    pass


class ControlMode(Enum):
    """Motor control modes"""
    IDLE = auto()
    POSITION = auto()
    VELOCITY = auto() 
    TORQUE = auto()


@dataclass
class MotorStatus:
    """Motor status information"""
    motor_id: int
    position: float
    velocity: float
    torque: float
    error_code: int
    control_mode: ControlMode
    is_enabled: bool
    temperature: Optional[float] = None
    voltage: Optional[float] = None


@dataclass
class MotorCommand:
    """Motor command structure"""
    motor_id: int
    target_value: float
    control_mode: ControlMode
    timestamp: float
    metadata: Optional[dict] = None


class MotorControllerInterface(ABC):
    """Abstract interface for motor controllers"""
    
    @abstractmethod
    def initialize(self) -> bool:
        """Initialize motor controller"""
        pass
    
    @abstractmethod
    def set_control_mode(self, motor_id: int, mode: ControlMode) -> bool:
        """Set motor control mode"""
        pass
    
    @abstractmethod
    def move_to_position(self, motor_id: int, position: float) -> bool:
        """Move motor to absolute position"""
        pass
    
    @abstractmethod
    def set_velocity(self, motor_id: int, velocity: float) -> bool:
        """Set motor velocity"""
        pass
    
    @abstractmethod
    def set_torque(self, motor_id: int, torque: float) -> bool:
        """Set motor torque"""
        pass
    
    @abstractmethod
    def get_status(self, motor_id: int) -> MotorStatus:
        """Get motor status"""
        pass
    
    @abstractmethod
    def enable_motor(self, motor_id: int) -> bool:
        """Enable motor (closed-loop control)"""
        pass
    
    @abstractmethod
    def disable_motor(self, motor_id: int) -> bool:
        """Disable motor (idle state)"""
        pass
    
    @abstractmethod
    def clear_errors(self, motor_id: int) -> bool:
        """Clear motor errors"""
        pass


class VehicleMotorController:
    """
    High-level vehicle motor controller
    Manages steering and drive motors with safety checks
    """
    
    def __init__(self, motor_interface: MotorControllerInterface):
        self._motor_interface = motor_interface
        self._logger = logging.getLogger(__name__)
        
        # Motor groupings
        self._motor_ids = MotorIDs()
        self._gear_ratios = GearRatios()
        self._limits = MotorLimits()
        
        # Advanced steering controller
        self._steering_controller = AdvancedSteeringController(motor_interface)
        
        # Current motor states
        self._motor_states: Dict[int, MotorStatus] = {}
        self._state_lock = threading.Lock()
        
        # Safety parameters
        self._emergency_stop = threading.Event()
        self._max_position_error = 1.0  # rotations
        self._max_velocity_error = 5.0  # rps
        
        # Initialize
        self._initialized = False
    
    def initialize(self) -> bool:
        """Initialize all motors with safety checks"""
        try:
            self._logger.info("Initializing vehicle motor controller...")
            
            # Initialize interface
            if not self._motor_interface.initialize():
                raise MotorError("Failed to initialize motor interface")
            
            # Check all motors are responsive
            for motor_id in self._motor_ids.all_motors:
                try:
                    status = self._motor_interface.get_status(motor_id)
                    with self._state_lock:
                        self._motor_states[motor_id] = status
                    
                    if status.error_code != 0:
                        self._logger.warning(
                            f"Motor {motor_id} has error code: {status.error_code}"
                        )
                        self._motor_interface.clear_errors(motor_id)
                
                except Exception as e:
                    self._logger.error(f"Failed to initialize motor {motor_id}: {e}")
                    return False
            
            # Set motor limits
            self._configure_motor_limits()
            
            self._initialized = True
            self._logger.info("Vehicle motor controller initialized successfully")
            return True
            
        except Exception as e:
            self._logger.error(f"Motor controller initialization failed: {e}")
            return False
    
    def _configure_motor_limits(self):
        """Configure motor limits for all motors"""
        # Drive motors
        for motor_id in self._motor_ids.drive_motors:
            self._set_motor_limits(
                motor_id,
                current_limit=self._limits.CURRENT_LIMIT_A,
                velocity_limit=self._limits.VELOCITY_LIMIT_RPS
            )
        
        # Steering motors
        for motor_id in self._motor_ids.steering_motors:
            self._set_motor_limits(
                motor_id,
                current_limit=self._limits.CURRENT_LIMIT_A,
                velocity_limit=self._limits.STEERING_VELOCITY_LIMIT
            )
    
    def _set_motor_limits(self, motor_id: int, current_limit: float, 
                         velocity_limit: float):
        """Set limits for individual motor"""
        # This would call the appropriate CAN commands
        # Implementation depends on motor interface
        pass
    
    def emergency_stop(self):
        """Emergency stop all motors"""
        self._logger.critical("EMERGENCY STOP ACTIVATED")
        self._emergency_stop.set()
        
        # Disable all motors immediately
        for motor_id in self._motor_ids.all_motors:
            try:
                self._motor_interface.disable_motor(motor_id)
            except Exception as e:
                self._logger.error(f"Failed to stop motor {motor_id}: {e}")
    
    def clear_emergency_stop(self):
        """Clear emergency stop condition"""
        self._emergency_stop.clear()
        self._logger.info("Emergency stop cleared")
    
    def _check_safety(self) -> bool:
        """Perform safety checks before motor operations"""
        if not self._initialized:
            raise MotorError("Motor controller not initialized")
        
        if self._emergency_stop.is_set():
            raise MotorError("Emergency stop is active")
        
        return True
    
    # Drive Motor Operations
    def move_vehicle_distance(self, distance_mm: float, 
                            steering_angle_deg: float = 0.0) -> bool:
        """
        Move vehicle by specified distance with steering
        
        Args:
            distance_mm: Distance in millimeters
            steering_angle_deg: Steering angle in degrees
        """
        self._check_safety()
        
        try:
            # Convert distance to motor rotations
            rotations = distance_mm / (PHYSICAL.WHEEL_CIRCUMFERENCE / self._gear_ratios.DRIVE_MOTOR)
            
            # Set steering first
            if abs(steering_angle_deg) > 0.1:  # Only steer if significant angle
                self.set_steering_angle(steering_angle_deg)
            
            # Move all drive motors
            success = True
            for motor_id in self._motor_ids.drive_motors:
                # Get current position
                current_pos = self._get_motor_position(motor_id)
                target_pos = current_pos + rotations
                
                if not self._motor_interface.move_to_position(motor_id, target_pos):
                    success = False
                    self._logger.error(f"Failed to move drive motor {motor_id}")
            
            return success
            
        except Exception as e:
            self._logger.error(f"Failed to move vehicle: {e}")
            return False
    
    def set_vehicle_velocity(self, velocity_mps: float) -> bool:
        """Set vehicle velocity in meters per second"""
        self._check_safety()
        
        try:
            # Convert to motor RPS
            wheel_rps = velocity_mps / (PHYSICAL.WHEEL_CIRCUMFERENCE / 1000.0)  # mm to m
            motor_rps = wheel_rps * self._gear_ratios.DRIVE_MOTOR
            
            # Apply to all drive motors
            success = True
            for motor_id in self._motor_ids.drive_motors:
                if not self._motor_interface.set_velocity(motor_id, motor_rps):
                    success = False
                    self._logger.error(f"Failed to set velocity for motor {motor_id}")
            
            return success
            
        except Exception as e:
            self._logger.error(f"Failed to set vehicle velocity: {e}")
            return False
    
    def set_drive_velocity(self, velocity: float) -> bool:
        """Set drive motor velocity (normalized -1.0 to 1.0)"""
        self._check_safety()
        
        try:
            # Convert normalized velocity to actual motor velocity
            # Assuming velocity is normalized to motor limits
            actual_velocity = velocity * self._limits.VELOCITY_LIMIT_RPS
            
            success = True
            for motor_id in self._motor_ids.drive_motors:
                if not self._motor_interface.set_velocity(motor_id, actual_velocity):
                    success = False
                    self._logger.error(f"Failed to set drive velocity for motor {motor_id}")
            
            return success
            
        except Exception as e:
            self._logger.error(f"Failed to set drive velocity: {e}")
            return False
    
    def move_drive_motors_to_position(self, position: float) -> bool:
        """Move all drive motors to a specific position"""
        self._check_safety()
        
        try:
            success = True
            for motor_id in self._motor_ids.drive_motors:
                if not self._motor_interface.move_to_position(motor_id, position):
                    success = False
                    self._logger.error(f"Failed to move drive motor {motor_id} to position {position}")
            
            return success
            
        except Exception as e:
            self._logger.error(f"Failed to move drive motors to position: {e}")
            return False
    
    # Steering Operations
    def set_steering_angle(self, angle_deg: float) -> bool:
        """Set front steering angle in degrees"""
        self._check_safety()
        
        # Clamp angle to limits
        max_angle = PHYSICAL.MAX_STEERING_ANGLE_DEG
        angle_deg = max(-max_angle, min(max_angle, angle_deg))
        
        try:
            # Convert to motor rotations
            rotations = (angle_deg / 360.0) * self._gear_ratios.STEERING_MOTOR
            
            # Apply to front steering motor (negative for correct direction)
            return self._motor_interface.move_to_position(
                self._motor_ids.STEERING_FRONT, -rotations
            )
            
        except Exception as e:
            self._logger.error(f"Failed to set steering angle: {e}")
            return False
    
    def set_pivot_mode(self, direction: PivotDirection) -> bool:
        """Set vehicle to pivot mode"""
        self._check_safety()
        
        try:
            if direction == PivotDirection.LEFT:
                # Left pivot configuration
                angles = {
                    self._motor_ids.STEERING_LEFT: -135.0,
                    self._motor_ids.STEERING_RIGHT: -45.0,
                    self._motor_ids.STEERING_FRONT: 90.0
                }
            elif direction == PivotDirection.RIGHT:
                # Right pivot configuration  
                angles = {
                    self._motor_ids.STEERING_LEFT: 45.0,
                    self._motor_ids.STEERING_RIGHT: 135.0,
                    self._motor_ids.STEERING_FRONT: -90.0
                }
            else:  # PivotDirection.NONE
                # Straight configuration
                angles = {
                    self._motor_ids.STEERING_LEFT: 0.0,
                    self._motor_ids.STEERING_RIGHT: 0.0,
                    self._motor_ids.STEERING_FRONT: 0.0
                }
            
            # Apply angles to all steering motors
            success = True
            for motor_id, angle in angles.items():
                rotations = (angle / 360.0) * self._gear_ratios.STEERING_MOTOR
                if not self._motor_interface.move_to_position(motor_id, rotations):
                    success = False
                    self._logger.error(f"Failed to set pivot angle for motor {motor_id}")
            
            return success
            
        except Exception as e:
            self._logger.error(f"Failed to set pivot mode: {e}")
            return False
    
    def straighten_steering(self) -> bool:
        """Straighten all steering wheels"""
        return self.set_pivot_mode(PivotDirection.NONE)
    
    # Motor State Management
    def enable_drive_motors(self) -> bool:
        """Enable all drive motors"""
        success = True
        for motor_id in self._motor_ids.drive_motors:
            if not self._motor_interface.enable_motor(motor_id):
                success = False
        return success
    
    def disable_drive_motors(self) -> bool:
        """Disable all drive motors"""
        success = True
        for motor_id in self._motor_ids.drive_motors:
            if not self._motor_interface.disable_motor(motor_id):
                success = False
        return success
    
    def enable_steering_motors(self) -> bool:
        """Enable all steering motors"""
        success = True
        for motor_id in self._motor_ids.steering_motors:
            if not self._motor_interface.enable_motor(motor_id):
                success = False
        return success
    
    def disable_steering_motors(self) -> bool:
        """Disable all steering motors"""
        success = True
        for motor_id in self._motor_ids.steering_motors:
            if not self._motor_interface.disable_motor(motor_id):
                success = False
        return success
    
    def stop_all_motors(self) -> bool:
        """Stop all motors (set velocity to 0)"""
        success = True
        for motor_id in self._motor_ids.all_motors:
            if not self._motor_interface.set_velocity(motor_id, 0.0):
                success = False
        return success
    
    def _get_motor_position(self, motor_id: int) -> float:
        """Get current motor position"""
        status = self._motor_interface.get_status(motor_id)
        with self._state_lock:
            self._motor_states[motor_id] = status
        return status.position
    
    def get_motor_status(self, motor_id: int) -> MotorStatus:
        """Get motor status with caching"""
        status = self._motor_interface.get_status(motor_id)
        with self._state_lock:
            self._motor_states[motor_id] = status
        return status
    
    def check_motor_errors(self) -> Dict[int, int]:
        """Check all motors for errors"""
        errors = {}
        for motor_id in self._motor_ids.all_motors:
            try:
                status = self.get_motor_status(motor_id)
                if status.error_code != 0:
                    errors[motor_id] = status.error_code
            except Exception as e:
                self._logger.error(f"Failed to check motor {motor_id}: {e}")
                errors[motor_id] = -1  # Communication error
        return errors
    
    # Advanced Steering Methods
    def set_ackermann_steering(self, input_rotation: float) -> bool:
        """Apply Ackermann steering geometry"""
        self._check_safety()
        return self._steering_controller.apply_ackermann_steering(input_rotation)
    
    def set_three_wheel_ackermann_steering(self, input_rotation: float) -> bool:
        """Apply three-wheel Ackermann steering geometry"""
        self._check_safety()
        return self._steering_controller.apply_three_wheel_ackermann_steering(input_rotation)
    
    def move_steering_to_90_degrees_left(self) -> bool:
        """Move all steering motors to 90-degree left position"""
        self._check_safety()
        return self._steering_controller.move_steering_to_90_degrees("left")
    
    def move_steering_to_90_degrees_right(self) -> bool:
        """Move all steering motors to 90-degree right position"""
        self._check_safety()
        return self._steering_controller.move_steering_to_90_degrees("right")
    
    def move_steering_to_center(self) -> bool:
        """Move all steering motors to center (0-degree) position"""
        self._check_safety()
        return self._steering_controller.move_steering_to_90_degrees("center")
    
    def automatic_straighten_steering(self, back_rotation: float = 0.0) -> bool:
        """Automatically straighten steering after a turn"""
        self._check_safety()
        return self._steering_controller.automatic_straighten_steering(back_rotation)
