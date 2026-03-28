"""
Main Vehicle Controller
Orchestrates all vehicle systems and control logic
"""

import logging
import time
import threading
from typing import Optional, Callable, Dict
from dataclasses import dataclass

try:
    from config.constants import VehicleState, PivotDirection, JOYSTICK
    from core.state_machine import VehicleStateMachine, StateTransition
    from core.safety_manager import SafetyManager, SafetyLevel, SafetyViolation
    from hardware.motor_controller import VehicleMotorController
    from utils.input_processing import JoystickProcessor, GPIOProcessor
except ImportError:
    # Handle imports for direct execution
    import sys
    import os

    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from config.constants import VehicleState, PivotDirection, JOYSTICK
    from core.state_machine import VehicleStateMachine, StateTransition
    from core.safety_manager import SafetyManager, SafetyLevel, SafetyViolation
    from hardware.motor_controller import VehicleMotorController
    from utils.input_processing import JoystickProcessor, GPIOProcessor


@dataclass
class ControlLoopStats:
    """Control loop performance statistics"""

    loop_count: int = 0
    avg_loop_time_ms: float = 0.0
    max_loop_time_ms: float = 0.0
    missed_deadlines: int = 0


class VehicleController:
    """
    Main vehicle controller class
    Coordinates all subsystems and implements control logic
    """

    def __init__(
        self,
        motor_controller: VehicleMotorController,
        joystick_processor: JoystickProcessor,
        gpio_processor: GPIOProcessor,
    ):

        self.motor_controller = motor_controller
        self.joystick_processor = joystick_processor
        self.gpio_processor = gpio_processor

        # Core systems
        self.state_machine = VehicleStateMachine()
        self.safety_manager = SafetyManager(motor_controller)

        # Control loop
        self.control_thread: Optional[threading.Thread] = None
        self.running = False
        self.control_rate_hz = 20  # 20Hz control loop
        self.loop_period_sec = 1.0 / self.control_rate_hz

        # Statistics
        self.stats = ControlLoopStats()

        # Logger
        self.logger = logging.getLogger(__name__)

        # Initialize state machine callbacks
        self._setup_state_callbacks()

        # Mode-specific parameters
        self.automatic_mode_params = {
            'forward_distance_mm': 500,
            'backward_distance_mm': -500,
            'move_timeout_sec': 10.0,
        }

        self.manual_mode_params = {
            'max_single_move_mm': 2000,
            'velocity_mode': False,  # Use position mode by default
        }

        # Degraded operation flag — set True when motor commands fail
        self._degraded = False

    def _setup_state_callbacks(self):
        """Setup state machine entry/exit callbacks"""
        # Entry callbacks
        self.state_machine.register_entry_callback(
            VehicleState.MANUAL_MODE, self._enter_manual_mode
        )
        self.state_machine.register_entry_callback(
            VehicleState.AUTOMATIC_MODE, self._enter_automatic_mode
        )
        self.state_machine.register_entry_callback(VehicleState.IDLING, self._enter_idle_mode)
        self.state_machine.register_entry_callback(VehicleState.ERROR, self._enter_error_mode)

        # Exit callbacks
        self.state_machine.register_exit_callback(VehicleState.IDLING, self._exit_idle_mode)

    def initialize(self) -> bool:
        """Initialize vehicle controller"""
        try:
            self.logger.info("Initializing vehicle controller...")

            # Initialize motor controller
            if not self.motor_controller.initialize():
                raise RuntimeError("Failed to initialize motor controller")

            # Calibrate joystick
            if not self.joystick_processor.calibrate():
                self.logger.warning("Joystick calibration failed, continuing anyway")

            # Start safety monitoring
            self.safety_manager.start_monitoring()

            # Register safety callbacks
            self.safety_manager.register_alert_callback(
                SafetyLevel.EMERGENCY, self._handle_emergency_alert
            )

            # Set initial state
            self.state_machine.transition_to(
                VehicleState.MANUAL_MODE, StateTransition.MODE_SWITCH_MANUAL
            )

            self.logger.info("Vehicle controller initialized successfully")
            return True

        except Exception as e:
            self.logger.error(f"Vehicle controller initialization failed: {e}")
            return False

    def start(self):
        """Start vehicle control system"""
        if self.running:
            return

        self.running = True
        self.control_thread = threading.Thread(
            target=self._control_loop, name="VehicleControl", daemon=True
        )
        self.control_thread.start()
        self.logger.info("Vehicle control system started")

    def stop(self):
        """Stop vehicle control system"""
        if not self.running:
            return

        self.running = False
        if self.control_thread:
            self.control_thread.join(timeout=2.0)

        # Stop all motors
        self.motor_controller.stop_all_motors()

        # Stop safety monitoring
        self.safety_manager.stop_monitoring()

        self.logger.info("Vehicle control system stopped")

    def _control_loop(self):
        """Main control loop"""
        self.logger.info(f"Starting control loop at {self.control_rate_hz}Hz")

        loop_times = []
        next_loop_time = time.time()

        while self.running:
            loop_start = time.time()

            try:
                # Update safety watchdog
                self.safety_manager.update_watchdog()

                # Read inputs
                gpio_state = self.gpio_processor.read_filtered()
                joystick_input = self.joystick_processor.read_filtered()

                # Process state changes
                self._process_state_changes(gpio_state)

                # Execute current state logic
                self._execute_current_state(gpio_state, joystick_input)

                # Update statistics
                loop_time_ms = (time.time() - loop_start) * 1000.0
                loop_times.append(loop_time_ms)

                if len(loop_times) > 100:  # Keep running average
                    loop_times.pop(0)

                self.stats.loop_count += 1
                self.stats.avg_loop_time_ms = sum(loop_times) / len(loop_times)
                self.stats.max_loop_time_ms = max(self.stats.max_loop_time_ms, loop_time_ms)

                # Sleep until next loop iteration
                next_loop_time += self.loop_period_sec
                sleep_time = next_loop_time - time.time()

                if sleep_time < 0:
                    self.stats.missed_deadlines += 1
                    next_loop_time = time.time()  # Reset timing
                else:
                    time.sleep(
                        sleep_time
                    )  # BLOCKING_SLEEP_OK: control loop timing — dedicated controller thread — reviewed 2026-03-14

            except Exception as e:
                self.logger.error(f"Control loop error: {e}")
                time.sleep(
                    0.1
                )  # BLOCKING_SLEEP_OK: error recovery throttle — dedicated controller thread — reviewed 2026-03-14

    def _process_state_changes(self, gpio_state):
        """Process potential state changes based on inputs"""
        current_state = self.state_machine.current_state
        new_vehicle_mode = self.gpio_processor.get_vehicle_mode(gpio_state)

        # Check for state transitions
        if new_vehicle_mode != current_state:
            transition_map = {
                VehicleState.SYSTEM_RESET: StateTransition.SYSTEM_RESET,
                VehicleState.STOP_REQUEST: StateTransition.STOP_REQUESTED,
                VehicleState.AUTOMATIC_MODE: StateTransition.MODE_SWITCH_AUTO,
                VehicleState.MANUAL_MODE: StateTransition.MODE_SWITCH_MANUAL,
                VehicleState.MANUAL_LEFT: StateTransition.DIRECTION_LEFT,
                VehicleState.MANUAL_RIGHT: StateTransition.DIRECTION_RIGHT,
                VehicleState.NONBRAKE_MANUAL: StateTransition.DIRECTION_NEUTRAL,
            }

            if new_vehicle_mode in transition_map:
                self.logger.info(
                    "[STATE] %s → %s (transition: %s)",
                    current_state.name,
                    new_vehicle_mode.name,
                    transition_map[new_vehicle_mode].name,
                )
                self.state_machine.transition_to(new_vehicle_mode, transition_map[new_vehicle_mode])

    def _execute_current_state(self, gpio_state, joystick_input):
        """Execute logic for current state"""
        current_state = self.state_machine.current_state

        if current_state == VehicleState.MANUAL_MODE:
            self._handle_manual_mode(joystick_input)
        elif current_state == VehicleState.AUTOMATIC_MODE:
            self._handle_automatic_mode(gpio_state)
        elif current_state in [VehicleState.MANUAL_LEFT, VehicleState.MANUAL_RIGHT]:
            self._handle_manual_directional_mode(current_state, joystick_input)
        elif current_state == VehicleState.NONBRAKE_MANUAL:
            self._handle_nonbrake_manual_mode(joystick_input)
        elif current_state == VehicleState.STOP_REQUEST:
            self._handle_stop_mode()
        elif current_state == VehicleState.SYSTEM_RESET:
            self._handle_system_reset()
        elif current_state == VehicleState.ERROR:
            self._handle_error_mode()
        # IDLING state is handled by entry/exit callbacks

    def _handle_manual_mode(self, joystick_input):
        """Handle manual mode control"""
        if joystick_input.is_centered:
            if self.joystick_processor.is_idle():
                self.state_machine.transition_to(VehicleState.IDLING, StateTransition.IDLE_TIMEOUT)
            return

        # Convert joystick input to motion
        distance_mm, steering_angle_deg = self.joystick_processor.convert_to_motion(joystick_input)

        self.logger.info(
            "[JOYSTICK] x=%.3f y=%.3f → dist=%.1f mm, steer=%.2f deg",
            joystick_input.x_value,
            joystick_input.y_value,
            distance_mm,
            steering_angle_deg,
        )

        try:
            # Validate command with safety manager
            self.safety_manager.validate_vehicle_command(
                "move", {"distance_mm": distance_mm, "steering_angle_deg": steering_angle_deg}
            )

            # Execute movement
            self.motor_controller.move_vehicle_distance(distance_mm, steering_angle_deg)

        except SafetyViolation as e:
            self.logger.warning(f"_handle_manual_mode: command rejected by safety manager: {e}")
        except RuntimeError as e:
            self.logger.error(f"_handle_manual_mode: motor command failed: {e}")
            self._degraded = True
        except Exception as e:
            self.logger.error(f"_handle_manual_mode: unexpected error: {e}")

    def _handle_automatic_mode(self, gpio_state):
        """Handle automatic mode control"""
        # Check for arm start button
        if not gpio_state.arm_start:
            return  # Wait for button press

        # Determine movement direction
        if gpio_state.direction_left:
            distance = self.automatic_mode_params['backward_distance_mm']
            self.logger.info("Automatic mode: Moving backward")
        else:
            distance = self.automatic_mode_params['forward_distance_mm']
            self.logger.info("Automatic mode: Moving forward")

        try:
            # Validate command
            self.safety_manager.validate_vehicle_command("move", {"distance_mm": distance})

            # Execute automatic movement
            success = self.motor_controller.move_vehicle_distance(distance)

            if not success:
                self.logger.error("Automatic movement failed")
                self._degraded = True
                self.state_machine.transition_to(VehicleState.ERROR, StateTransition.ERROR_OCCURRED)

        except SafetyViolation as e:
            self.logger.warning(f"_handle_automatic_mode: command rejected by safety manager: {e}")
        except RuntimeError as e:
            self.logger.error(f"_handle_automatic_mode: motor command failed: {e}")
            self._degraded = True
            self.state_machine.transition_to(VehicleState.ERROR, StateTransition.ERROR_OCCURRED)
        except Exception as e:
            self.logger.error(f"_handle_automatic_mode: unexpected error: {e}")
            self.state_machine.transition_to(VehicleState.ERROR, StateTransition.ERROR_OCCURRED)

    def _handle_manual_directional_mode(self, state, joystick_input):
        """Handle manual left/right directional modes"""
        pivot_direction = (
            PivotDirection.LEFT if state == VehicleState.MANUAL_LEFT else PivotDirection.RIGHT
        )

        if joystick_input.is_centered:
            if self.joystick_processor.is_idle():
                self.state_machine.transition_to(VehicleState.IDLING, StateTransition.IDLE_TIMEOUT)
            return

        # In directional mode, only use Y-axis for movement
        distance_mm = (joystick_input.y_value - JOYSTICK.MID_VALUE) / JOYSTICK.MID_VALUE * 1000.0

        try:
            self.safety_manager.validate_vehicle_command("move", {"distance_mm": distance_mm})

            # Move drive motors only (steering is set by pivot mode)
            # This would need implementation in motor controller
            self.motor_controller.move_vehicle_distance(distance_mm, 0)

        except SafetyViolation as e:
            self.logger.warning(
                f"_handle_manual_directional_mode: command rejected by safety manager: {e}"
            )
        except RuntimeError as e:
            self.logger.error(f"_handle_manual_directional_mode: motor command failed: {e}")
            self._degraded = True
        except Exception as e:
            self.logger.error(f"_handle_manual_directional_mode: unexpected error: {e}")

    def _handle_nonbrake_manual_mode(self, joystick_input):
        """Handle non-brake manual mode (normal joystick control)"""
        # Same as regular manual mode
        self._handle_manual_mode(joystick_input)

    def _handle_stop_mode(self):
        """Handle stop request"""
        try:
            self.motor_controller.stop_all_motors()
            # Transition back to appropriate mode based on inputs
            # This will be handled by the state processing
        except RuntimeError as e:
            self.logger.error(f"_handle_stop_mode: motor stop failed: {e}")
            self._degraded = True
        except Exception as e:
            self.logger.error(f"_handle_stop_mode: unexpected error: {e}")

    def _handle_system_reset(self):
        """Handle system reset"""
        try:
            self.logger.info("System reset requested")
            self.motor_controller.stop_all_motors()

            # Clear any errors
            motor_errors = self.motor_controller.check_motor_errors()
            for motor_id in motor_errors:
                self.motor_controller._motor_interface.clear_errors(motor_id)

            # Clear degraded state on successful reset
            self._degraded = False

            # Transition to manual mode
            self.state_machine.transition_to(
                VehicleState.MANUAL_MODE, StateTransition.MODE_SWITCH_MANUAL
            )

        except RuntimeError as e:
            self.logger.error(f"_handle_system_reset: motor command failed: {e}")
            self._degraded = True
        except Exception as e:
            self.logger.error(f"_handle_system_reset: unexpected error: {e}")

    def _handle_error_mode(self):
        """Handle error state"""
        # Keep motors stopped and wait for manual intervention
        try:
            self.motor_controller.stop_all_motors()
        except RuntimeError as e:
            self.logger.error(f"_handle_error_mode: motor stop failed: {e}")
            self._degraded = True
        except Exception as e:
            self.logger.error(f"_handle_error_mode: unexpected error: {e}")

    # State callback implementations
    def _enter_manual_mode(self):
        """Called when entering manual mode"""
        self.logger.info("Entering manual mode")
        self.motor_controller.enable_drive_motors()
        self.motor_controller.enable_steering_motors()
        self.motor_controller.straighten_steering()

    def _enter_automatic_mode(self):
        """Called when entering automatic mode"""
        self.logger.info("Entering automatic mode")
        self.motor_controller.enable_drive_motors()
        self.motor_controller.enable_steering_motors()
        # Set appropriate trap trajectory values for automatic mode
        # This would need implementation in motor controller

    def _enter_idle_mode(self):
        """Called when entering idle mode"""
        self.logger.info("Vehicle entering idle mode")
        self.motor_controller.stop_all_motors()
        # Don't disable motors, just stop them

    def _exit_idle_mode(self):
        """Called when exiting idle mode"""
        self.logger.info("Vehicle exiting idle mode")
        self.motor_controller.enable_drive_motors()
        self.motor_controller.enable_steering_motors()

    def _enter_error_mode(self):
        """Called when entering error mode"""
        self.logger.error("Vehicle entering error mode")
        self.motor_controller.stop_all_motors()

    def _handle_emergency_alert(self, alert):
        """Handle emergency safety alert"""
        self.logger.critical(f"Emergency alert: {alert.message}")
        self.state_machine.transition_to(VehicleState.ERROR, StateTransition.ERROR_OCCURRED)

    # Public interface methods
    def get_status(self) -> Dict:
        """Get vehicle status information"""
        return {
            'state': self.state_machine.current_state.name,
            'previous_state': self.state_machine.previous_state.name,
            'safety_ok': self.safety_manager.is_safe_to_operate,
            'emergency_stop': self.safety_manager.is_emergency_stop_active,
            'loop_stats': {
                'loop_count': self.stats.loop_count,
                'avg_loop_time_ms': self.stats.avg_loop_time_ms,
                'max_loop_time_ms': self.stats.max_loop_time_ms,
                'missed_deadlines': self.stats.missed_deadlines,
            },
        }

    def emergency_stop(self, reason: str = "Manual emergency stop"):
        """Trigger emergency stop"""
        self.safety_manager.emergency_stop(reason)

    def clear_emergency_stop(self) -> bool:
        """Clear emergency stop condition"""
        return self.safety_manager.clear_emergency_stop()
