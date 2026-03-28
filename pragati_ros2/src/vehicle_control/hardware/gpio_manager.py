"""
GPIO Manager for Vehicle Control System
Handles all GPIO input/output operations via pigpiod daemon.

Uses pigpio library to connect to pigpiod daemon (same as yanthra_move),
which doesn't require root access since pigpiod runs as a service.
"""

import time
import logging
from typing import Dict, List, Optional, Callable
from enum import Enum

try:
    import pigpio

    PIGPIO_AVAILABLE = True
except ImportError:
    PIGPIO_AVAILABLE = False

try:
    from ..config.constants import GPIO_PINS
except ImportError:
    import sys
    import os

    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from config.constants import GPIO_PINS


class GPIOError(Exception):
    """GPIO operation error"""

    pass


class GPIOState:
    """Simple class to hold GPIO state with attribute access"""

    def __init__(
        self,
        direction_left=False,
        direction_right=False,
        automatic_mode=False,
        vehicle_stop=False,
        system_reset=False,
        arm_shutdown=False,
        arm_start=False,
        brake_switch=False,
    ):
        self.direction_left = direction_left
        self.direction_right = direction_right
        self.automatic_mode = automatic_mode
        self.vehicle_stop = vehicle_stop
        self.system_reset = system_reset
        self.arm_shutdown = arm_shutdown
        self.arm_start = arm_start
        self.brake_switch = brake_switch


class GPIODirection(Enum):
    """GPIO pin directions"""

    INPUT = "input"
    OUTPUT = "output"


class GPIOEdge(Enum):
    """GPIO edge detection types"""

    RISING = "rising"
    FALLING = "falling"
    BOTH = "both"


class GPIOManager:
    """Manages all GPIO operations for the vehicle control system via pigpiod daemon."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._initialized = False
        self._output_states: Dict[int, bool] = {}
        self._input_callbacks: Dict[int, object] = {}  # Store pigpio callback objects
        self._pi = None  # pigpio connection handle
        # Bank read optimization: read all GPIO 0-31 in one IPC call.
        # Falls back to individual reads if pigpiod doesn't support it.
        self._bank_read_available = True
        self._bank_read_warned = False

        if not PIGPIO_AVAILABLE:
            self.logger.warning("pigpio not available - GPIO functions will not work")

    def initialize(self) -> bool:
        """Initialize GPIO system by connecting to pigpiod daemon"""
        if not PIGPIO_AVAILABLE:
            raise GPIOError("pigpio library not installed")

        try:
            # Connect to pigpiod daemon (same approach as yanthra_move)
            self._pi = pigpio.pi()

            if not self._pi.connected:
                raise GPIOError("Failed to connect to pigpiod daemon. Is it running?")

            self.logger.info("Connected to pigpiod daemon")

            # Setup input pins with pull resistors
            input_pins = {
                GPIO_PINS.DIRECTION_LEFT: pigpio.PUD_DOWN,
                GPIO_PINS.DIRECTION_RIGHT: pigpio.PUD_DOWN,
                GPIO_PINS.AUTOMATIC_MODE: pigpio.PUD_DOWN,
                GPIO_PINS.VEHICLE_STOP: pigpio.PUD_DOWN,
                GPIO_PINS.SYSTEM_RESET: pigpio.PUD_DOWN,
                GPIO_PINS.ARM_SHUTDOWN: pigpio.PUD_UP,  # Pull-up for safety
                GPIO_PINS.ARM_START: pigpio.PUD_DOWN,
                GPIO_PINS.BRAKE_SWITCH: pigpio.PUD_UP,  # Pull-up for safety
            }

            for pin, pull in input_pins.items():
                self._pi.set_mode(pin, pigpio.INPUT)
                self._pi.set_pull_up_down(pin, pull)
                self.logger.debug(f"Setup input pin {pin} with pull {pull}")

            # Setup output pins
            output_pins = [
                GPIO_PINS.GREEN_LED,
                GPIO_PINS.YELLOW_LED,
                GPIO_PINS.RED_LED,
                GPIO_PINS.FAN,
                GPIO_PINS.ERROR_LED,
            ]

            for pin in output_pins:
                self._pi.set_mode(pin, pigpio.OUTPUT)
                self._pi.write(pin, 0)  # Start with outputs off
                self._output_states[pin] = False
                self.logger.debug(f"Setup output pin {pin}")

            self._initialized = True
            self.logger.info("GPIO system initialized successfully via pigpiod")
            return True

        except Exception as e:
            self.logger.error(f"Failed to initialize GPIO: {e}")
            if self._pi is not None and self._pi.connected:
                self._pi.stop()
            raise GPIOError(f"GPIO initialization failed: {e}")

    def cleanup(self):
        """Cleanup GPIO resources and disconnect from pigpiod"""
        try:
            if self._initialized and self._pi is not None and self._pi.connected:
                # Turn off all outputs
                for pin in self._output_states:
                    try:
                        self._pi.write(pin, 0)
                    except Exception:
                        pass  # Best-effort cleanup — pin may already be released

                # Cancel all callbacks
                for pin, cb in self._input_callbacks.items():
                    try:
                        cb.cancel()
                    except Exception:
                        pass  # Best-effort cleanup — pin may already be released
                self._input_callbacks.clear()

                # Disconnect from pigpiod
                self._pi.stop()
                self._pi = None
                self._initialized = False
                self.logger.info("GPIO cleanup completed")

        except Exception as e:
            self.logger.error(f"GPIO cleanup error: {e}")

    def set_output(self, pin: int, value: bool) -> bool:
        """Set output pin state"""
        try:
            if not self._initialized or self._pi is None:
                raise GPIOError("GPIO not initialized")

            self._pi.write(pin, 1 if value else 0)
            self._output_states[pin] = value
            self.logger.debug(f"Set output pin {pin} to {value}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to set output pin {pin}: {e}")
            raise GPIOError(f"Output operation failed: {e}")

    def read_input(self, pin: int) -> bool:
        """Read input pin state"""
        try:
            if not self._initialized or self._pi is None:
                raise GPIOError("GPIO not initialized")

            value = self._pi.read(pin)
            self.logger.debug(f"Read input pin {pin}: {value}")
            return bool(value)

        except Exception as e:
            self.logger.error(f"Failed to read input pin {pin}: {e}")
            raise GPIOError(f"Input operation failed: {e}")

    def toggle_output(self, pin: int) -> bool:
        """Toggle output pin state"""
        try:
            current_state = self._output_states.get(pin, False)
            return self.set_output(pin, not current_state)

        except Exception as e:
            self.logger.error(f"Failed to toggle output pin {pin}: {e}")
            raise GPIOError(f"Toggle operation failed: {e}")

    def pulse_output(self, pin: int, duration: float = 0.5) -> bool:
        """Pulse output pin high for specified duration"""
        try:
            self.set_output(pin, True)
            time.sleep(
                duration
            )  # BLOCKING_SLEEP_OK: GPIO pulse timing — dedicated caller thread, not executor — reviewed 2026-03-14
            self.set_output(pin, False)
            return True

        except Exception as e:
            self.logger.error(f"Failed to pulse output pin {pin}: {e}")
            raise GPIOError(f"Pulse operation failed: {e}")

    def add_input_callback(
        self,
        pin: int,
        callback: Callable,
        edge: GPIOEdge = GPIOEdge.BOTH,
        bouncetime: int = 200,
    ) -> bool:
        """Add callback for input pin edge detection

        Note: pigpio handles debouncing internally via glitch filter.
        bouncetime is converted to microseconds for the glitch filter.
        """
        try:
            if not self._initialized or self._pi is None:
                raise GPIOError("GPIO not initialized")

            # Map edge enum to pigpio constants
            edge_map = {
                GPIOEdge.RISING: pigpio.RISING_EDGE,
                GPIOEdge.FALLING: pigpio.FALLING_EDGE,
                GPIOEdge.BOTH: pigpio.EITHER_EDGE,
            }

            # Set glitch filter for debouncing (bouncetime in ms -> us)
            self._pi.set_glitch_filter(pin, bouncetime * 1000)

            # Create callback (pigpio callback signature: gpio, level, tick)
            # Wrap user callback to match expected signature
            def pigpio_callback_wrapper(gpio, level, tick):
                callback(gpio)

            cb = self._pi.callback(pin, edge_map[edge], pigpio_callback_wrapper)
            self._input_callbacks[pin] = cb
            self.logger.debug(f"Added callback for pin {pin}, edge {edge.value}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to add callback for pin {pin}: {e}")
            raise GPIOError(f"Callback setup failed: {e}")

    def remove_input_callback(self, pin: int) -> bool:
        """Remove callback for input pin"""
        try:
            if pin in self._input_callbacks:
                self._input_callbacks[pin].cancel()
                del self._input_callbacks[pin]
                # Remove glitch filter
                if self._pi is not None and self._pi.connected:
                    self._pi.set_glitch_filter(pin, 0)
                self.logger.debug(f"Removed callback for pin {pin}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to remove callback for pin {pin}: {e}")
            raise GPIOError(f"Callback removal failed: {e}")

    def read_all_inputs(self) -> Dict[int, bool]:
        """Read all input pins.

        Uses pigpio read_bank1() to read all GPIO 0-31 in a single IPC call,
        then extracts individual pin values via bitmask.  Falls back to
        individual read() calls if bank read is not available.
        """
        input_pins = [
            GPIO_PINS.DIRECTION_LEFT,
            GPIO_PINS.DIRECTION_RIGHT,
            GPIO_PINS.AUTOMATIC_MODE,
            GPIO_PINS.VEHICLE_STOP,
            GPIO_PINS.SYSTEM_RESET,
            GPIO_PINS.ARM_SHUTDOWN,
            GPIO_PINS.ARM_START,
            GPIO_PINS.BRAKE_SWITCH,
        ]

        # Try bank read first (single IPC round-trip)
        if self._bank_read_available and self._pi is not None:
            try:
                bank1 = self._pi.read_bank1()
                results = {}
                for pin in input_pins:
                    results[pin] = bool((bank1 >> pin) & 1)
                return results
            except Exception as e:
                # Bank read failed — fall back and disable for future calls
                self._bank_read_available = False
                if not self._bank_read_warned:
                    self.logger.warning(
                        f"read_bank1() failed, falling back to individual reads: {e}"
                    )
                    self._bank_read_warned = True

        # Fallback: individual reads
        results = {}
        for pin in input_pins:
            try:
                results[pin] = self.read_input(pin)
            except GPIOError:
                results[pin] = False  # Default to safe state

        return results

    def read_all(self):
        """Read all GPIO inputs and return as object with attribute access.

        Uses batched bank read when available for reduced IPC overhead.
        """
        try:
            # Use read_all_inputs() which handles bank read optimization
            raw = self.read_all_inputs()
            return GPIOState(
                direction_left=raw.get(GPIO_PINS.DIRECTION_LEFT, False),
                direction_right=raw.get(GPIO_PINS.DIRECTION_RIGHT, False),
                automatic_mode=raw.get(GPIO_PINS.AUTOMATIC_MODE, False),
                vehicle_stop=raw.get(GPIO_PINS.VEHICLE_STOP, False),
                system_reset=raw.get(GPIO_PINS.SYSTEM_RESET, False),
                arm_shutdown=raw.get(GPIO_PINS.ARM_SHUTDOWN, False),
                arm_start=raw.get(GPIO_PINS.ARM_START, False),
                brake_switch=raw.get(GPIO_PINS.BRAKE_SWITCH, False),
            )
        except Exception:
            # Return safe defaults on error
            return GPIOState(
                vehicle_stop=True,
                arm_shutdown=True,
                brake_switch=True,
            )

    def set_all_outputs(self, state: bool) -> bool:
        """Set all output pins to specified state"""
        try:
            output_pins = [
                GPIO_PINS.GREEN_LED,
                GPIO_PINS.YELLOW_LED,
                GPIO_PINS.RED_LED,
                GPIO_PINS.FAN,
                GPIO_PINS.ERROR_LED,
            ]

            success = True
            for pin in output_pins:
                if not self.set_output(pin, state):
                    success = False

            return success

        except Exception as e:
            self.logger.error(f"Failed to set all outputs: {e}")
            return False

    def get_output_states(self) -> Dict[int, bool]:
        """Get current output states"""
        return self._output_states.copy()

    def is_emergency_stop_active(self) -> bool:
        """Check if emergency stop is active"""
        try:
            # Emergency stop is active if ARM_SHUTDOWN is LOW (pulled up normally)
            return not self.read_input(GPIO_PINS.ARM_SHUTDOWN)
        except GPIOError:
            # If we can't read the pin, assume emergency stop is active for safety
            return True

    def is_brake_engaged(self) -> bool:
        """Check if brake is engaged"""
        try:
            # Brake is engaged if BRAKE_SWITCH is LOW (pulled up normally)
            return not self.read_input(GPIO_PINS.BRAKE_SWITCH)
        except GPIOError:
            # If we can't read the pin, assume brake is engaged for safety
            return True

    def get_direction_command(self) -> str:
        """Get current direction command from switches"""
        try:
            left = self.read_input(GPIO_PINS.DIRECTION_LEFT)
            right = self.read_input(GPIO_PINS.DIRECTION_RIGHT)

            if left and not right:
                return "LEFT"
            elif right and not left:
                return "RIGHT"
            elif not left and not right:
                return "STRAIGHT"
            else:
                # Both switches active - invalid state
                self.logger.warning("Invalid direction state - both switches active")
                return "INVALID"

        except GPIOError:
            return "UNKNOWN"

    def is_automatic_mode_selected(self) -> bool:
        """Check if automatic mode is selected"""
        try:
            return self.read_input(GPIO_PINS.AUTOMATIC_MODE)
        except GPIOError:
            return False  # Default to manual mode if can't read

    def show_status_led(self, status: str):
        """Show system status via LEDs"""
        try:
            # Clear all status LEDs first
            self.set_output(GPIO_PINS.GREEN_LED, False)
            self.set_output(GPIO_PINS.YELLOW_LED, False)
            self.set_output(GPIO_PINS.RED_LED, False)

            if status.upper() == "OK":
                self.set_output(GPIO_PINS.GREEN_LED, True)
            elif status.upper() == "WARNING":
                self.set_output(GPIO_PINS.YELLOW_LED, True)
            elif status.upper() == "ERROR":
                self.set_output(GPIO_PINS.RED_LED, True)
            elif status.upper() == "EMERGENCY":
                # Flash red LED for emergency
                for _ in range(5):
                    self.set_output(GPIO_PINS.RED_LED, True)
                    time.sleep(
                        0.2
                    )  # BLOCKING_SLEEP_OK: LED blink timing — non-critical visual indicator — reviewed 2026-03-14
                    self.set_output(GPIO_PINS.RED_LED, False)
                    time.sleep(
                        0.2
                    )  # BLOCKING_SLEEP_OK: LED blink timing — non-critical visual indicator — reviewed 2026-03-14

        except Exception as e:
            self.logger.error(f"Failed to show status LED: {e}")

    def __enter__(self):
        """Context manager entry"""
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.cleanup()
