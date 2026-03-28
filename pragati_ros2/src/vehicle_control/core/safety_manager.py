"""
Safety Manager
Implements safety checks and emergency procedures
"""

import json
import logging
import threading
import time
import traceback
from typing import Callable, List, Dict, Optional
from dataclasses import dataclass
from enum import Enum, auto

try:
    from common_utils.consecutive_failure_tracker import ConsecutiveFailureTracker
except ImportError:
    # Fallback: inline minimal implementation when common_utils not on PYTHONPATH

    class ConsecutiveFailureTracker:
        """Minimal fallback when common_utils is not available."""

        def __init__(self, threshold: int = 5):
            self._threshold = threshold
            self._count = 0

        def increment(self) -> bool:
            self._count += 1
            return self._count >= self._threshold

        def reset(self) -> None:
            self._count = 0

        @property
        def count(self) -> int:
            return self._count

        @property
        def threshold(self) -> int:
            return self._threshold


try:
    from config.constants import VehicleState, MOTOR_LIMITS
    from hardware.motor_controller import VehicleMotorController
except ImportError:
    # Handle imports for direct execution
    import sys
    import os

    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from config.constants import VehicleState, MOTOR_LIMITS


class SafetyLevel(Enum):
    """Safety alert levels"""

    INFO = auto()
    WARNING = auto()
    CRITICAL = auto()
    EMERGENCY = auto()


@dataclass
class SafetyAlert:
    """Safety alert structure"""

    level: SafetyLevel
    message: str
    timestamp: float
    source: str
    data: Optional[dict] = None


class SafetyViolation(Exception):
    """Safety violation exception"""

    def __init__(self, alert: SafetyAlert):
        super().__init__(alert.message)
        self.alert = alert


class SafetyManager:
    """
    Centralized safety management system
    Monitors vehicle state and enforces safety constraints
    """

    def __init__(self, motor_controller: VehicleMotorController = None):
        self._motor_controller = motor_controller
        self._logger = logging.getLogger(__name__)

        # Safety state
        self._safety_enabled = True
        self._emergency_stop_active = False
        self._safety_lock = threading.RLock()

        # Alert handling
        self._alerts: List[SafetyAlert] = []
        self._alert_callbacks: Dict[SafetyLevel, List[Callable]] = {
            level: [] for level in SafetyLevel
        }

        # Safety limits
        self._max_velocity_mps = 2.0  # Maximum safe velocity
        self._max_acceleration_mps2 = 1.0  # Maximum acceleration
        self._max_steering_rate_dps = 30.0  # Max steering rate deg/sec
        self._watchdog_timeout_sec = 2.0  # Communications watchdog

        # Monitoring
        self._last_update_time = time.time()
        self._monitoring_active = False
        self._monitor_thread: Optional[threading.Thread] = None

        # [TIMING] Safety check timing stats (task 5.6)
        # GIL-protected: written in monitor thread, read by node's health timer
        self.safety_check_total_time = 0.0
        self.safety_check_max_time = 0.0
        self.safety_check_count = 0

        # Emergency procedures
        self._emergency_procedures: List[Callable[[], None]] = []
        self._estop_incomplete = False

        # Consecutive failure tracking for monitoring loop
        self._safety_failure_tracker = ConsecutiveFailureTracker(threshold=5)

        # Initialization flag
        self._initialized = False

    def initialize(self) -> bool:
        """Initialize safety manager"""
        try:
            self._initialized = True
            self._logger.info("Safety manager initialized successfully")
            return True
        except Exception as e:
            self._logger.error(f"Failed to initialize safety manager: {e}")
            return False

    def set_motor_controller(self, motor_controller: VehicleMotorController):
        """Set the motor controller reference"""
        self._motor_controller = motor_controller

    def enable_safety(self):
        """Enable safety monitoring"""
        with self._safety_lock:
            self._safety_enabled = True
            self._logger.info("Safety monitoring enabled")

    def disable_safety(self):
        """Disable safety monitoring (use with extreme caution)"""
        with self._safety_lock:
            self._safety_enabled = False
            self._logger.warning("SAFETY MONITORING DISABLED - USE WITH CAUTION")

    def start_monitoring(self):
        """Start background safety monitoring"""
        if self._monitoring_active:
            return

        self._monitoring_active = True
        self._safety_failure_tracker.reset()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, name="SafetyMonitor", daemon=True
        )
        self._monitor_thread.start()
        self._logger.info("Safety monitoring started")

    def stop_monitoring(self):
        """Stop background safety monitoring"""
        self._monitoring_active = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=1.0)
        self._logger.info("Safety monitoring stopped")

    def _monitor_loop(self):
        """Background monitoring loop"""
        while self._monitoring_active:
            try:
                t_check_start = time.perf_counter()
                self._perform_safety_checks()
                t_check_end = time.perf_counter()
                # [TIMING] Track safety check iteration time (task 5.6)
                check_time = t_check_end - t_check_start
                self.safety_check_total_time += check_time
                self.safety_check_count += 1
                if check_time > self.safety_check_max_time:
                    self.safety_check_max_time = check_time
                self._safety_failure_tracker.reset()
                time.sleep(
                    0.1
                )  # BLOCKING_SLEEP_OK: safety monitor 10Hz loop rate — dedicated monitoring thread — reviewed 2026-03-14
            except Exception as e:
                self._logger.error(f"Error in safety monitoring: {e}")
                threshold_exceeded = self._safety_failure_tracker.increment()
                if threshold_exceeded:
                    self._logger.critical(
                        f"Safety monitoring has failed "
                        f"{self._safety_failure_tracker.count} consecutive "
                        f"times (threshold={self._safety_failure_tracker.threshold}). "
                        f"System safety may be compromised."
                    )
                time.sleep(
                    0.5
                )  # BLOCKING_SLEEP_OK: safety monitor error recovery throttle — dedicated thread — reviewed 2026-03-14

    def _perform_safety_checks(self):
        """Perform comprehensive safety checks"""
        current_time = time.time()

        # Update watchdog
        if current_time - self._last_update_time > self._watchdog_timeout_sec:
            self._create_alert(
                SafetyLevel.WARNING,
                "Safety watchdog timeout - no recent updates",
                "watchdog",
            )

        # Check motor errors
        self._check_motor_errors()

        # Check velocity limits
        self._check_velocity_limits()

        # Check emergency stop state
        if self._emergency_stop_active:
            self._ensure_emergency_stop()

    def _check_motor_errors(self):
        """Check all motors for error conditions"""
        try:
            motor_errors = self._motor_controller.check_motor_errors()

            for motor_id, error_code in motor_errors.items():
                if error_code != 0:
                    self._create_alert(
                        SafetyLevel.CRITICAL,
                        f"Motor {motor_id} error: {error_code}",
                        "motor_error",
                        {"motor_id": motor_id, "error_code": error_code},
                    )
        except Exception as e:
            self._create_alert(
                SafetyLevel.WARNING,
                f"Failed to check motor errors: {e}",
                "motor_check_failure",
            )

    def _check_velocity_limits(self):
        """Check if vehicle velocity is within safe limits"""
        # This would get actual velocity from motors/sensors
        # For now, just placeholder
        pass

    def emergency_stop(self, reason: str = "Manual emergency stop"):
        """Activate emergency stop with retry on motor stop failure."""
        with self._safety_lock:
            if self._emergency_stop_active:
                return True  # Already in emergency stop

            self._emergency_stop_active = True

            self._create_alert(SafetyLevel.EMERGENCY, f"EMERGENCY STOP: {reason}", "emergency_stop")

            # Execute emergency procedures
            self._execute_emergency_procedures()

            # Stop all motors with retry and exponential backoff
            backoff_times = [0.01, 0.1, 1.0]  # 10ms, 100ms, 1s
            last_error = None

            for attempt, backoff in enumerate(backoff_times):
                try:
                    self._motor_controller.emergency_stop()
                    self._estop_incomplete = False
                    return True
                except Exception as e:
                    last_error = e
                    self._logger.warning(
                        f"E-stop attempt {attempt + 1}/{len(backoff_times)} failed: {e}"
                    )
                    if attempt < len(backoff_times) - 1:
                        time.sleep(
                            backoff
                        )  # BLOCKING_SLEEP_OK: e-stop retry backoff — safety-critical path — reviewed 2026-03-14

            # All attempts exhausted
            self._estop_incomplete = True
            self._logger.critical(
                f"E-STOP INCOMPLETE after {len(backoff_times)} attempts: {last_error}"
            )
            return False

    def clear_emergency_stop(self) -> bool:
        """Clear emergency stop if safe to do so"""
        with self._safety_lock:
            if not self._emergency_stop_active:
                return True

            # Check if it's safe to clear
            if not self._is_safe_to_clear_emergency():
                self._create_alert(
                    SafetyLevel.WARNING,
                    "Cannot clear emergency stop - unsafe conditions",
                    "emergency_clear_denied",
                )
                return False

            self._emergency_stop_active = False
            self._motor_controller.clear_emergency_stop()

            self._create_alert(SafetyLevel.INFO, "Emergency stop cleared", "emergency_clear")

            return True

    def _is_safe_to_clear_emergency(self) -> bool:
        """Check if it's safe to clear emergency stop"""
        # Check for active motor errors
        try:
            motor_errors = self._motor_controller.check_motor_errors()
            if motor_errors:
                return False
        except Exception as e:
            self._logger.error(
                json.dumps(
                    {
                        "event": "safety_check_exception",
                        "component": "safety_manager",
                        "method": "_is_safe_to_clear_emergency",
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "traceback": traceback.format_exc(),
                    }
                )
            )
            return False  # Can't verify motor state

        # Add other safety checks here
        return True

    def _ensure_emergency_stop(self):
        """Ensure emergency stop is maintained — verify all motors are actually stopped."""
        try:
            if self._motor_controller is None:
                return
            motor_errors = self._motor_controller.check_motor_errors()
            # If we can read motor state, re-issue stop if estop was incomplete
            if getattr(self, "_estop_incomplete", False):
                self._logger.warning("E-stop was incomplete, re-issuing motor emergency stop")
                try:
                    self._motor_controller.emergency_stop()
                    self._estop_incomplete = False
                    self._logger.info("Re-issued motor emergency stop succeeded")
                except Exception as retry_err:
                    self._logger.error(f"Re-issued motor emergency stop failed: {retry_err}")
        except Exception as e:
            self._logger.error(f"Failed to verify emergency stop state: {e}")

    def _execute_emergency_procedures(self):
        """Execute all registered emergency procedures"""
        for procedure in self._emergency_procedures:
            try:
                procedure()
            except Exception as e:
                self._logger.error(f"Emergency procedure failed: {e}")

    def register_emergency_procedure(self, procedure: Callable[[], None]):
        """Register an emergency procedure"""
        self._emergency_procedures.append(procedure)

    def validate_vehicle_command(self, command_type: str, parameters: dict) -> bool:
        """
        Validate vehicle command against safety constraints

        Args:
            command_type: Type of command (move, steer, velocity, etc.)
            parameters: Command parameters

        Returns:
            True if command is safe to execute

        Raises:
            SafetyViolation: If command violates safety constraints
        """
        if not self._safety_enabled:
            return True

        with self._safety_lock:
            if self._emergency_stop_active:
                raise SafetyViolation(
                    SafetyAlert(
                        SafetyLevel.EMERGENCY,
                        "Command rejected - emergency stop is active",
                        time.time(),
                        "command_validation",
                    )
                )

            if command_type == "move":
                return self._validate_move_command(parameters)
            elif command_type == "velocity":
                return self._validate_velocity_command(parameters)
            elif command_type == "steer":
                return self._validate_steering_command(parameters)
            else:
                self._logger.warning(f"Unknown command type: {command_type}")
                return True

    def _validate_move_command(self, params: dict) -> bool:
        """Validate movement command"""
        distance = params.get("distance_mm", 0)
        max_distance = 5000.0  # 5m max single move

        if abs(distance) > max_distance:
            raise SafetyViolation(
                SafetyAlert(
                    SafetyLevel.CRITICAL,
                    f"Move distance {distance}mm exceeds maximum {max_distance}mm",
                    time.time(),
                    "move_validation",
                )
            )

        return True

    def _validate_velocity_command(self, params: dict) -> bool:
        """Validate velocity command"""
        velocity = params.get("velocity_mps", 0)

        if abs(velocity) > self._max_velocity_mps:
            raise SafetyViolation(
                SafetyAlert(
                    SafetyLevel.CRITICAL,
                    f"Velocity {velocity}m/s exceeds maximum {self._max_velocity_mps}m/s",
                    time.time(),
                    "velocity_validation",
                )
            )

        return True

    def _validate_steering_command(self, params: dict) -> bool:
        """Validate steering command"""
        angle = params.get("angle_deg", 0)
        max_angle = 45.0  # degrees

        if abs(angle) > max_angle:
            raise SafetyViolation(
                SafetyAlert(
                    SafetyLevel.WARNING,
                    f"Steering angle {angle}° exceeds maximum {max_angle}°",
                    time.time(),
                    "steering_validation",
                )
            )

        return True

    def update_watchdog(self):
        """Update safety watchdog (call from main control loop)"""
        self._last_update_time = time.time()

    def _create_alert(
        self, level: SafetyLevel, message: str, source: str, data: Optional[dict] = None
    ):
        """Create and process safety alert"""
        alert = SafetyAlert(
            level=level,
            message=message,
            timestamp=time.time(),
            source=source,
            data=data,
        )

        # Store alert
        self._alerts.append(alert)

        # Keep only recent alerts (last 1000)
        if len(self._alerts) > 1000:
            self._alerts = self._alerts[-1000:]

        # Log alert
        log_level = {
            SafetyLevel.INFO: logging.INFO,
            SafetyLevel.WARNING: logging.WARNING,
            SafetyLevel.CRITICAL: logging.CRITICAL,
            SafetyLevel.EMERGENCY: logging.CRITICAL,
        }[level]

        self._logger.log(log_level, f"SAFETY [{level.name}]: {message}")

        # Call callbacks
        for callback in self._alert_callbacks[level]:
            try:
                callback(alert)
            except Exception as e:
                self._logger.error(f"Alert callback failed: {e}")

        # Auto-trigger emergency stop for critical alerts
        if level == SafetyLevel.EMERGENCY and not self._emergency_stop_active:
            self.emergency_stop(f"Auto-triggered by: {message}")

    def register_alert_callback(self, level: SafetyLevel, callback: Callable[[SafetyAlert], None]):
        """Register callback for safety alerts of specific level"""
        self._alert_callbacks[level].append(callback)

    def get_recent_alerts(self, count: int = 10) -> List[SafetyAlert]:
        """Get recent safety alerts"""
        return self._alerts[-count:]

    def get_alert_summary(self) -> Dict[SafetyLevel, int]:
        """Get summary of alert counts by level"""
        summary = {level: 0 for level in SafetyLevel}
        for alert in self._alerts:
            summary[alert.level] += 1
        return summary

    @property
    def is_emergency_stop_active(self) -> bool:
        """Check if emergency stop is active"""
        return self._emergency_stop_active

    @property
    def is_safe_to_operate(self) -> bool:
        """Check if vehicle is safe to operate"""
        return (
            self._safety_enabled
            and not self._emergency_stop_active
            and time.time() - self._last_update_time < self._watchdog_timeout_sec
        )
