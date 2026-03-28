"""
Vehicle Control System Constants
Centralized configuration for all system parameters
"""
from enum import IntEnum
from dataclasses import dataclass
from typing import Final


class VehicleState(IntEnum):
    """Vehicle operational states"""
    UNKNOWN = 0x7777
    MANUAL_MODE = 0x1111
    AUTOMATIC_MODE = 0x5555
    STOP_REQUEST = 0x9999
    ERROR = 0x3333
    IDLING = 0x0000
    BUSY = 0xEEEE
    SYSTEM_RESET = 0xDEAD
    MANUAL_LEFT = 0x1114
    MANUAL_RIGHT = 0x1113
    NONBRAKE_MANUAL = 0x1112
    BRAKE_MODE = 0xBBBB


class PivotDirection(IntEnum):
    """Vehicle pivot directions"""
    NONE = 0x0000
    LEFT = 0xAAAA
    RIGHT = 0x5555


class ButtonState(IntEnum):
    """Button press states"""
    PRESSED = 0xABCD
    NOT_PRESSED = 0xDCBA


@dataclass(frozen=True)
class PhysicalConstants:
    """Physical vehicle parameters"""
    # Wheel parameters (in mm)
    WHEEL_DIAMETER: Final[float] = 24 * 25.4  # 24 inch wheel in mm
    WHEEL_CIRCUMFERENCE: Final[float] = 3.141519 * WHEEL_DIAMETER
    
    # Vehicle dimensions (in mm) 
    WHEEL_BASE: Final[float] = 1500.0
    WHEEL_TREAD: Final[float] = 1800.0
    WHEEL_CENTER_DISTANCE: Final[float] = WHEEL_TREAD / 2
    
    # Steering limits
    MAX_STEERING_ANGLE_DEG: Final[float] = 30.0  # degrees
    MAX_STEERING_ROTATION: Final[float] = MAX_STEERING_ANGLE_DEG / 360.0
    MIN_STEERING_ANGLE_RAD: Final[float] = 0.02  # ~7.5 degrees
    
    # Movement limits
    MAX_MOVE_DISTANCE_MM: Final[float] = 3.14 * WHEEL_DIAMETER
    MIN_DISTANCE_RESOLUTION_MM: Final[float] = 100.0
    MAX_VEHICLE_VELOCITY_MH: Final[float] = 5000.0  # mm/hour
    MAX_VEHICLE_TORQUE_NM: Final[float] = 20.0


@dataclass(frozen=True)
class MotorIDs:
    """Motor CAN IDs - Must match vehicle_motors.yaml and production.yaml
    
    Note: MG6010 requires CAN IDs 1-32 (ID 0 is invalid)
    """
    # Steering Motors (CAN IDs from vehicle_motors.yaml)
    # Simplified bring-up mapping: steering=1,2,3 and drive=4,5,6
    STEERING_FRONT: Final[int] = 3          # steering_front
    STEERING_REAR_LEFT: Final[int] = 1      # steering_left
    STEERING_REAR_RIGHT: Final[int] = 2     # steering_right
    
    # Drive Motors (CAN IDs from vehicle_motors.yaml)
    DRIVE_FRONT: Final[int] = 4             # drive_front
    DRIVE_REAR_LEFT: Final[int] = 5         # drive_left_back
    DRIVE_REAR_RIGHT: Final[int] = 6        # drive_right_back
    
    @property
    def all_motors(self) -> list[int]:
        return [
            self.STEERING_FRONT, self.STEERING_REAR_LEFT, self.STEERING_REAR_RIGHT,
            self.DRIVE_FRONT, self.DRIVE_REAR_LEFT, self.DRIVE_REAR_RIGHT
        ]
    
    @property
    def steering_motors(self) -> list[int]:
        return [self.STEERING_FRONT, self.STEERING_REAR_LEFT, self.STEERING_REAR_RIGHT]
    
    @property 
    def drive_motors(self) -> list[int]:
        return [self.DRIVE_FRONT, self.DRIVE_REAR_LEFT, self.DRIVE_REAR_RIGHT]
    
    # Backward compatibility properties
    @property
    def STEERING_LEFT(self) -> int:
        """Backward compatibility: maps to rear left steering"""
        return self.STEERING_REAR_LEFT
    
    @property
    def STEERING_RIGHT(self) -> int:
        """Backward compatibility: maps to rear right steering"""
        return self.STEERING_REAR_RIGHT
    
    @property
    def DRIVE_LEFT(self) -> int:
        """Backward compatibility: maps to rear left drive"""
        return self.DRIVE_REAR_LEFT
    
    @property
    def DRIVE_RIGHT(self) -> int:
        """Backward compatibility: maps to rear right drive"""
        return self.DRIVE_REAR_RIGHT


@dataclass(frozen=True)
class GearRatios:
    """Motor gear ratios"""
    DRIVE_MOTOR: Final[float] = 3 * 5.8462
    STEERING_MOTOR: Final[float] = 50.0


@dataclass(frozen=True)
class GPIOPins:
    """GPIO pin assignments"""
    # Input pins
    DIRECTION_LEFT: Final[int] = 16       # Direction left switch
    DIRECTION_RIGHT: Final[int] = 21      # Direction right switch
    AUTOMATIC_MODE: Final[int] = 20       # Automatic/Manual mode switch
    ARM_START: Final[int] = 6             # Start button
    ARM_SHUTDOWN: Final[int] = 5          # Shutdown button
    SYSTEM_RESET: Final[int] = 4          # Reboot button
    VEHICLE_STOP: Final[int] = 13         # (unused - keeping for compatibility)
    BRAKE_SWITCH: Final[int] = 12         # (unused - keeping for compatibility)
    
    # Output pins
    SOFTWARE_STATUS_LED: Final[int] = 22  # Software Status LED (Green) - ON when software running
    YELLOW_LED: Final[int] = 27           # Orange LED
    RASPBERRY_PI_LED: Final[int] = 17     # Raspberry Pi Power LED (Red) - ON when Pi powered
    GREEN_LED: Final[int] = 22            # Alias for SOFTWARE_STATUS_LED
    RED_LED: Final[int] = 17              # Alias for RASPBERRY_PI_LED
    FAN: Final[int] = 24                  # (unused - keeping for compatibility)
    ERROR_LED: Final[int] = 23            # (unused - keeping for compatibility)
    
    # SPI/ADC pins
    CAN_ENABLE: Final[int] = 8
    ADC_ENABLE: Final[int] = 7


class TestResults:
    """Test result constants"""
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"


@dataclass(frozen=True)
class JoystickConfig:
    """Joystick configuration parameters"""
    X_CHANNEL: Final[int] = 0
    Y_CHANNEL: Final[int] = 1
    MID_VALUE: Final[int] = 512
    MAX_VALUE: Final[int] = 1023
    MIN_VALUE: Final[int] = 0

    # Deadband around MID_VALUE (ADC counts). Lower values make /joy respond to smaller movements.
    RESOLUTION: Final[int] = 50

    IDLE_TIMEOUT_SEC: Final[float] = 0.5


@dataclass(frozen=True) 
class MotorLimits:
    """Motor operational limits"""
    CURRENT_LIMIT_A: Final[float] = 50.0
    VELOCITY_LIMIT_RPS: Final[float] = 8.0
    
    # Speed profiles
    LOW_SPEED_RPS: Final[float] = 2.0
    HIGH_SPEED_RPS: Final[float] = 3.5
    
    # Acceleration profiles
    LOW_ACCEL: Final[float] = 0.5
    HIGH_ACCEL: Final[float] = 1.0
    LOW_DECEL: Final[float] = 0.5
    HIGH_DECEL: Final[float] = 1.0
    
    # Steering limits
    STEERING_VELOCITY_LIMIT: Final[float] = 5.0
    STEERING_ACCEL_LIMIT: Final[float] = 2.0
    STEERING_DECEL_LIMIT: Final[float] = 2.0


@dataclass(frozen=True)
class CANConfig:
    """CAN bus configuration"""
    INTERFACE: Final[str] = 'can0'
    BITRATE: Final[int] = 500000
    TIMEOUT_SEC: Final[float] = 1.0
    TX_QUEUE_LENGTH: Final[int] = 1000
    DBC_FILE: Final[str] = "odrive-cansimple.dbc"


@dataclass(frozen=True)
class LoggingConfig:
    """Logging configuration"""
    LOG_LEVEL: Final[str] = "INFO"
    LOG_FILE: Final[str] = "/tmp/VehicleControl.log"
    LOG_FORMAT: Final[str] = '%(asctime)s %(name)s %(levelname)s : %(message)s'
    DATE_FORMAT: Final[str] = '%d-%b-%Y:%H:%M:%S'


# Create singleton instances
PHYSICAL = PhysicalConstants()
MOTOR_IDS = MotorIDs()
GEAR_RATIOS = GearRatios()
GPIO_PINS = GPIOPins()
JOYSTICK_CONFIG = JoystickConfig()  # Fixed name for consistency
JOYSTICK = JOYSTICK_CONFIG  # Alias for backward compatibility
MOTOR_LIMITS = MotorLimits()
CAN_CONFIG = CANConfig()
LOGGING_CONFIG = LoggingConfig()
