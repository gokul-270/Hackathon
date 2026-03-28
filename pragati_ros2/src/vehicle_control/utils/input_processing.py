"""
Input Processing and Filtering
Handles joystick, GPIO, and other input processing with filtering
"""

import logging
import time
import statistics
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Tuple, Callable
from collections import deque
from threading import Lock
import numpy as np

try:
    from config.constants import JOYSTICK, GPIO_PINS, VehicleState
except ImportError:
    # Handle imports for direct execution
    import sys
    import os

    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from config.constants import JOYSTICK, GPIO_PINS, VehicleState


@dataclass
class JoystickInput:
    """Joystick input data"""

    x_value: int
    y_value: int
    timestamp: float

    @property
    def is_centered(self) -> bool:
        """Check if joystick is in center position"""
        return (
            abs(self.x_value - JOYSTICK.MID_VALUE) < JOYSTICK.RESOLUTION
            and abs(self.y_value - JOYSTICK.MID_VALUE) < JOYSTICK.RESOLUTION
        )


@dataclass
class GPIOInputState:
    """GPIO input state"""

    direction_left: bool
    direction_right: bool
    automatic_mode: bool
    vehicle_stop: bool
    system_reset: bool
    arm_shutdown: bool
    arm_start: bool
    brake_switch: bool
    timestamp: float


class InputFilter(ABC):
    """Abstract base class for input filters"""

    @abstractmethod
    def add_sample(self, value) -> None:
        """Add a new sample to the filter"""
        pass

    @abstractmethod
    def get_filtered_value(self):
        """Get the current filtered value"""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset the filter state"""
        pass


class MedianFilter(InputFilter):
    """Median filter for removing outliers"""

    def __init__(self, window_size: int = 5):
        self.window_size = window_size
        self.samples: deque = deque(maxlen=window_size)
        self.lock = Lock()

    def add_sample(self, value) -> None:
        with self.lock:
            self.samples.append(value)

    def get_filtered_value(self):
        with self.lock:
            if not self.samples:
                return None
            return statistics.median(self.samples)

    def reset(self) -> None:
        with self.lock:
            self.samples.clear()


class MovingAverageFilter(InputFilter):
    """Moving average filter for smoothing"""

    def __init__(self, window_size: int = 10):
        self.window_size = window_size
        self.samples: deque = deque(maxlen=window_size)
        self.lock = Lock()

    def add_sample(self, value) -> None:
        with self.lock:
            self.samples.append(value)

    def get_filtered_value(self):
        with self.lock:
            if not self.samples:
                return None
            return sum(self.samples) / len(self.samples)

    def reset(self) -> None:
        with self.lock:
            self.samples.clear()


class OutlierRejectFilter(InputFilter):
    """Filter that rejects outliers beyond threshold"""

    def __init__(self, threshold_std: float = 2.0, window_size: int = 20):
        self.threshold_std = threshold_std
        self.window_size = window_size
        self.samples: deque = deque(maxlen=window_size)
        self.lock = Lock()

    def add_sample(self, value) -> None:
        with self.lock:
            if len(self.samples) < 3:
                # Not enough samples for outlier detection
                self.samples.append(value)
                return

            # Calculate statistics
            mean_val = statistics.mean(self.samples)
            std_val = statistics.stdev(self.samples)

            # Check if value is an outlier
            if abs(value - mean_val) <= self.threshold_std * std_val:
                self.samples.append(value)
            # If outlier, don't add to samples (effectively rejected)

    def get_filtered_value(self):
        with self.lock:
            if not self.samples:
                return None
            return statistics.mean(self.samples)

    def reset(self) -> None:
        with self.lock:
            self.samples.clear()


class VotingFilter(InputFilter):
    """Voting filter that takes most common value"""

    def __init__(self, window_size: int = 5):
        self.window_size = window_size
        self.samples: deque = deque(maxlen=window_size)
        self.lock = Lock()

    def add_sample(self, value) -> None:
        with self.lock:
            self.samples.append(value)

    def get_filtered_value(self):
        with self.lock:
            if not self.samples:
                return None

            # Find most common value
            from collections import Counter

            counts = Counter(self.samples)
            return counts.most_common(1)[0][0]

    def reset(self) -> None:
        with self.lock:
            self.samples.clear()


class JoystickProcessor:
    """
    Joystick input processor with filtering and dead zone handling.

    Note:
    - Joysticks can legitimately change rapidly. An outlier-rejecting filter that *drops*
      large deltas can lock the output at the initial value (common if the stick is held
      centered on startup).
    - We therefore use a light smoothing filter only.
    """

    def __init__(self, joystick_interface):
        self.joystick_interface = joystick_interface
        self.logger = logging.getLogger(__name__)

        # Smoothing filters for X and Y channels
        self.x_filter = MovingAverageFilter(window_size=5)
        self.y_filter = MovingAverageFilter(window_size=5)

        # Calibration
        self.x_calibration_offset = 0
        self.y_calibration_offset = 0
        self.calibrated = False

        # State tracking
        self.last_input: Optional[JoystickInput] = None
        self.idle_start_time: Optional[float] = None

    def calibrate(self, samples: int = 100) -> bool:
        """
        Calibrate joystick center position
        Joystick should be centered during calibration
        """
        try:
            self.logger.info(f"Calibrating joystick with {samples} samples...")

            x_values = []
            y_values = []

            for _ in range(samples):
                x, y = self.joystick_interface.read_raw()
                x_values.append(x)
                y_values.append(y)
                time.sleep(
                    0.01
                )  # BLOCKING_SLEEP_OK: calibration ADC sampling — startup-only, not in executor context — reviewed 2026-03-14

            # Calculate calibration offsets
            self.x_calibration_offset = statistics.mean(x_values) - JOYSTICK.MID_VALUE
            self.y_calibration_offset = statistics.mean(y_values) - JOYSTICK.MID_VALUE

            self.calibrated = True
            self.logger.info(
                f"Joystick calibration complete. "
                f"X offset: {self.x_calibration_offset:.2f}, "
                f"Y offset: {self.y_calibration_offset:.2f}"
            )
            return True

        except Exception as e:
            self.logger.error(f"Joystick calibration failed: {e}")
            return False

    def read_filtered(self) -> JoystickInput:
        """Read and lightly smooth joystick input."""
        try:
            # Read raw values
            x_raw, y_raw = self.joystick_interface.read_raw()

            # Apply calibration
            if self.calibrated:
                x_raw -= self.x_calibration_offset
                y_raw -= self.y_calibration_offset

            # Smooth (do not drop large deltas; joystick movement is not an outlier)
            self.x_filter.add_sample(x_raw)
            self.y_filter.add_sample(y_raw)

            x_final = self.x_filter.get_filtered_value()
            y_final = self.y_filter.get_filtered_value()

            # Use raw values if filters not ready
            if x_final is None:
                x_final = x_raw
            if y_final is None:
                y_final = y_raw

            # Clamp to valid range
            x_final = max(JOYSTICK.MIN_VALUE, min(JOYSTICK.MAX_VALUE, int(round(x_final))))
            y_final = max(JOYSTICK.MIN_VALUE, min(JOYSTICK.MAX_VALUE, int(round(y_final))))

            # Apply dead zone
            if abs(x_final - JOYSTICK.MID_VALUE) < JOYSTICK.RESOLUTION:
                x_final = JOYSTICK.MID_VALUE
            if abs(y_final - JOYSTICK.MID_VALUE) < JOYSTICK.RESOLUTION:
                y_final = JOYSTICK.MID_VALUE

            input_data = JoystickInput(x_value=x_final, y_value=y_final, timestamp=time.time())

            self.last_input = input_data
            return input_data

        except Exception as e:
            self.logger.error(f"Failed to read joystick: {e}")
            # Return centered position on error
            return JoystickInput(
                x_value=JOYSTICK.MID_VALUE, y_value=JOYSTICK.MID_VALUE, timestamp=time.time()
            )

    def is_idle(self) -> bool:
        """Check if joystick has been idle for timeout period"""
        if not self.last_input or not self.last_input.is_centered:
            self.idle_start_time = None
            return False

        if self.idle_start_time is None:
            self.idle_start_time = time.time()
            return False

        return (time.time() - self.idle_start_time) > JOYSTICK.IDLE_TIMEOUT_SEC

    def convert_to_motion(self, input_data: JoystickInput) -> Tuple[float, float]:
        """
        Convert joystick input to motion parameters

        Returns:
            (distance_mm, steering_angle_deg)
        """
        # Convert Y axis to distance (forward/backward)
        y_normalized = (input_data.y_value - JOYSTICK.MID_VALUE) / JOYSTICK.MID_VALUE
        max_distance = 1000.0  # mm
        distance_mm = y_normalized * max_distance

        # Convert X axis to steering angle
        x_normalized = (input_data.x_value - JOYSTICK.MID_VALUE) / JOYSTICK.MID_VALUE
        max_steering_deg = 30.0  # degrees
        steering_angle_deg = x_normalized * max_steering_deg

        return distance_mm, steering_angle_deg


class GPIOProcessor:
    """
    GPIO input processor with debouncing and filtering
    """

    def __init__(self, gpio_interface):
        self.gpio_interface = gpio_interface
        self.logger = logging.getLogger(__name__)

        # Throttle repeated read errors (avoid log spam if GPIO is disabled/unavailable)
        self._last_gpio_error_time = 0.0
        self._gpio_error_min_interval_s = 5.0

        # Filters for each input
        self.filters = {
            'direction_left': VotingFilter(window_size=3),
            'direction_right': VotingFilter(window_size=3),
            'automatic_mode': VotingFilter(window_size=5),
            'vehicle_stop': VotingFilter(window_size=3),
            'system_reset': VotingFilter(window_size=3),
            'arm_shutdown': VotingFilter(window_size=3),
            'arm_start': VotingFilter(window_size=3),
            'brake_switch': VotingFilter(window_size=3),
        }

        # State tracking
        self.last_state: Optional[GPIOInputState] = None

    def read_filtered(self) -> GPIOInputState:
        """Read and filter GPIO inputs"""
        now = time.time()

        # If GPIO is disabled/uninitialized, return safe defaults without spamming logs.
        if self.gpio_interface is None:
            if (now - self._last_gpio_error_time) > self._gpio_error_min_interval_s:
                self.logger.warning(
                    "GPIO interface is None (GPIO disabled or not initialized) - using safe defaults"
                )
                self._last_gpio_error_time = now
            return GPIOInputState(
                direction_left=False,
                direction_right=False,
                automatic_mode=False,
                vehicle_stop=True,  # Safe default is stopped
                system_reset=False,
                arm_shutdown=True,  # Safe default is shutdown
                arm_start=False,
                brake_switch=True,  # Safe default is brakes on
                timestamp=now,
            )

        try:
            # Read raw GPIO states
            raw_state = self.gpio_interface.read_all()

            # Add samples to filters
            self.filters['direction_left'].add_sample(raw_state.direction_left)
            self.filters['direction_right'].add_sample(raw_state.direction_right)
            self.filters['automatic_mode'].add_sample(raw_state.automatic_mode)
            self.filters['vehicle_stop'].add_sample(raw_state.vehicle_stop)
            self.filters['system_reset'].add_sample(raw_state.system_reset)
            self.filters['arm_shutdown'].add_sample(raw_state.arm_shutdown)
            self.filters['arm_start'].add_sample(raw_state.arm_start)
            self.filters['brake_switch'].add_sample(raw_state.brake_switch)

            # Get filtered values
            filtered_state = GPIOInputState(
                direction_left=self.filters['direction_left'].get_filtered_value() or False,
                direction_right=self.filters['direction_right'].get_filtered_value() or False,
                automatic_mode=self.filters['automatic_mode'].get_filtered_value() or False,
                vehicle_stop=self.filters['vehicle_stop'].get_filtered_value() or False,
                system_reset=self.filters['system_reset'].get_filtered_value() or False,
                arm_shutdown=self.filters['arm_shutdown'].get_filtered_value() or False,
                arm_start=self.filters['arm_start'].get_filtered_value() or False,
                brake_switch=self.filters['brake_switch'].get_filtered_value() or False,
                timestamp=now,
            )

            self.last_state = filtered_state
            return filtered_state

        except Exception as e:
            if (now - self._last_gpio_error_time) > self._gpio_error_min_interval_s:
                self.logger.error(f"Failed to read GPIO: {e}")
                self._last_gpio_error_time = now
            # Return safe default state
            return GPIOInputState(
                direction_left=False,
                direction_right=False,
                automatic_mode=False,
                vehicle_stop=True,  # Safe default is stopped
                system_reset=False,
                arm_shutdown=True,  # Safe default is shutdown
                arm_start=False,
                brake_switch=True,  # Safe default is brakes on
                timestamp=now,
            )

    def get_vehicle_mode(self, gpio_state: GPIOInputState) -> VehicleState:
        """Determine vehicle mode from GPIO state"""
        # Priority: System reset > Stop > Automatic > Manual modes

        if gpio_state.system_reset:
            return VehicleState.SYSTEM_RESET

        if gpio_state.vehicle_stop:
            return VehicleState.STOP_REQUEST

        if gpio_state.automatic_mode:
            return VehicleState.AUTOMATIC_MODE

        # Manual mode variations
        if gpio_state.direction_left and gpio_state.direction_right:
            # Both directions - invalid state, default to stop
            return VehicleState.STOP_REQUEST
        elif gpio_state.direction_left:
            return VehicleState.MANUAL_LEFT
        elif gpio_state.direction_right:
            return VehicleState.MANUAL_RIGHT
        else:
            return VehicleState.NONBRAKE_MANUAL

    def has_state_changed(self, new_state: GPIOInputState) -> bool:
        """Check if GPIO state has changed significantly"""
        if not self.last_state:
            return True

        # Check for any changes in critical inputs
        return (
            new_state.direction_left != self.last_state.direction_left
            or new_state.direction_right != self.last_state.direction_right
            or new_state.automatic_mode != self.last_state.automatic_mode
            or new_state.vehicle_stop != self.last_state.vehicle_stop
            or new_state.system_reset != self.last_state.system_reset
        )
