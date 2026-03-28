#!/usr/bin/env python3
"""
IMU Interface Adapter
Bridges refactored system with existing IMU functionality
"""

import logging
import time
import math
from typing import Optional, Tuple
from dataclasses import dataclass

# NOTE (Long-term fix): vehicle_control should NOT depend on legacy ROS1 code or ODrive.
# The previous implementation imported a legacy module that ran odrive.find_any() at import-time,
# which blocks node startup on machines without hardware.
#
# This adapter now provides a clean, optional IMU interface:
# - default: disabled (no hardware access)
# - mock: simulated yaw for testing
#
# When IMU is ready for field use, implement a proper serial-based reader here
# using the parameters in vehicle_control/config/production.yaml.

SERIAL_AVAILABLE = False
try:
    import serial  # type: ignore

    SERIAL_AVAILABLE = True
except Exception:
    SERIAL_AVAILABLE = False


def _safe_float(s: str) -> Optional[float]:
    try:
        return float(s)
    except Exception:
        return None


@dataclass
class IMUReading:
    """IMU sensor reading data"""

    yaw_deg: float
    pitch_deg: float = 0.0
    roll_deg: float = 0.0
    timestamp: float = 0.0
    valid: bool = True


class IMUInterface:
    """IMU interface (optional).

    This is intentionally conservative:
    - If IMU is disabled, it performs no hardware access and returns 0 yaw.
    - If IMU is enabled in mock mode, it returns a slowly varying yaw for testing.

    Serial IMU support can be added later (field trial), without introducing ODrive.
    """

    def __init__(
        self,
        enabled: bool = False,
        mode: str = "disabled",  # disabled | mock | serial (reserved)
        serial_port: str = "",
        baud_rate: int = 9600,
        timeout: float = 0.5,
    ):
        self.logger = logging.getLogger(__name__)
        self._initialized = False
        self._use_mock = False
        self._enabled = enabled
        self._mode = mode

        # Serial settings (reserved for future)
        self._serial_port = serial_port
        self._baud_rate = baud_rate
        self._timeout = timeout
        self._serial = None

        self._last_reading: Optional[IMUReading] = None
        self._calibration_offset = 0.0
        self._calibrated = False

    def initialize(self) -> bool:
        """Initialize IMU system.

        Returns True when disabled/mock so the rest of the node can continue.
        """
        try:
            if not self._enabled or self._mode == "disabled":
                self._initialized = True
                self.logger.warning("⚠️ IMU disabled (enable_imu=false) - continuing without IMU")
                return True

            if self._mode == "mock":
                self._initialized = True
                self._use_mock = True
                self.logger.warning("⚠️ IMU enabled in MOCK mode - yaw will be simulated")
                return True

            if self._mode == "serial":
                # Reserved for later implementation.
                if not SERIAL_AVAILABLE:
                    self.logger.error("IMU serial mode requested but pyserial is not available")
                    return False
                self.logger.error("IMU serial mode is not implemented yet (field-trial TODO)")
                return False

            self.logger.error(f"Unknown IMU mode: {self._mode}")
            return False

        except Exception as e:
            self.logger.error(f"IMU initialization failed: {e}")
            return False

    def read_yaw(self) -> float:
        """Read yaw angle in degrees"""
        try:
            if not self._initialized:
                return 0.0

            # Use mock if hardware not available or not responding
            if self._use_mock:
                # Mock IMU reading - return slowly changing value for testing
                mock_yaw = (time.time() % 360) - 180  # Slowly rotating mock value
                return mock_yaw

            # Serial IMU support not implemented yet.
            # If enabled without a supported mode, just return 0.
            return 0.0

        except Exception as e:
            self.logger.error(f"Failed to read yaw: {e}")
            return 0.0

    def read_complete(self) -> IMUReading:
        """Read complete IMU data"""
        try:
            yaw = self.read_yaw()

            reading = IMUReading(yaw_deg=yaw, timestamp=time.time(), valid=True)

            self._last_reading = reading
            return reading

        except Exception as e:
            self.logger.error(f"Failed to read IMU: {e}")
            return IMUReading(yaw_deg=0.0, timestamp=time.time(), valid=False)

    def calibrate(self, samples: int = 100) -> bool:
        """
        Calibrate IMU - vehicle should be pointing straight ahead
        """
        try:
            self.logger.info(f"Calibrating IMU with {samples} samples...")

            yaw_values = []
            for _ in range(samples):
                yaw = self.read_yaw()
                yaw_values.append(yaw)
                time.sleep(
                    0.01
                )  # BLOCKING_SLEEP_OK: calibration ADC sampling — startup-only, not in executor context — reviewed 2026-03-14
            # Calculate calibration offset (average of readings)
            if yaw_values:
                self._calibration_offset = sum(yaw_values) / len(yaw_values)
                self._calibrated = True

                self.logger.info(
                    f"IMU calibration complete. Offset: {self._calibration_offset:.2f} degrees"
                )
                return True
            else:
                self.logger.error("No IMU readings for calibration")
                return False

        except Exception as e:
            self.logger.error(f"IMU calibration failed: {e}")
            return False

    def convert_yaw_to_steering_rotation(
        self, current_yaw_deg: float, target_yaw_deg: float = 0.0
    ) -> float:
        """
        Convert yaw angle difference to steering motor rotation
        Uses the same logic as the original DynamicSteeringWithIMU
        """
        try:
            # Calculate correction angle
            correction_angle = target_yaw_deg - current_yaw_deg

            # Normalize correction angle
            if correction_angle > 180:
                correction_angle -= 360
            elif correction_angle < -180:
                correction_angle += 360

            # Apply limits from original code
            max_steer_limit = 45.0  # degrees
            min_steer_limit = 3.0  # degrees (dead zone)

            # Apply dead zone
            if abs(correction_angle) <= min_steer_limit:
                correction_angle = 0.0

            # Apply maximum limits
            if correction_angle > max_steer_limit:
                correction_angle = max_steer_limit
            elif correction_angle < -max_steer_limit:
                correction_angle = -max_steer_limit

            # Convert to motor rotations (steering gear ratio is 50:1)
            steering_gear_ratio = 50.0
            motor_rotation = (correction_angle / 360.0) * steering_gear_ratio

            return motor_rotation

        except Exception as e:
            self.logger.error(f"Failed to convert yaw to steering: {e}")
            return 0.0

    def get_steering_correction(self, target_yaw: float = 0.0) -> float:
        """
        Get steering correction based on current yaw vs target
        Returns motor rotation value for steering correction
        """
        try:
            current_yaw = self.read_yaw()
            return self.convert_yaw_to_steering_rotation(current_yaw, target_yaw)

        except Exception as e:
            self.logger.error(f"Failed to get steering correction: {e}")
            return 0.0

    def is_heading_stable(self, tolerance_deg: float = 2.0, duration_sec: float = 1.0) -> bool:
        """
        Check if heading has been stable within tolerance for duration
        """
        # This would require tracking readings over time
        # For now, return simple check
        try:
            current_yaw = self.read_yaw()
            return abs(current_yaw) < tolerance_deg
        except Exception:
            return False

    def get_last_reading(self) -> Optional[IMUReading]:
        """Get the last IMU reading"""
        return self._last_reading

    def shutdown(self):
        """Shutdown IMU system"""
        try:
            self._initialized = False
            self.logger.info("IMU interface shutdown")
        except Exception as e:
            self.logger.error(f"IMU shutdown error: {e}")


# Convenience function to create IMU interface
def create_imu_interface(config: Optional[dict] = None) -> IMUInterface:
    """Create and return IMU interface.

    Config keys (from vehicle_control/config/production.yaml):
    - enable_imu: bool (default false)
    - imu_mode: str (disabled|mock|serial) (optional)
    - imu_serial_port: str (optional)
    - imu_baud_rate: int (optional)
    - imu_timeout: float (optional)
    """
    config = config or {}
    enabled = bool(config.get('enable_imu', False))
    mode = str(config.get('imu_mode', 'disabled'))
    serial_port = str(config.get('imu_serial_port', ''))
    baud_rate = int(config.get('imu_baud_rate', 9600))
    timeout = float(config.get('imu_timeout', 0.5))

    return IMUInterface(
        enabled=enabled,
        mode=mode,
        serial_port=serial_port,
        baud_rate=baud_rate,
        timeout=timeout,
    )
