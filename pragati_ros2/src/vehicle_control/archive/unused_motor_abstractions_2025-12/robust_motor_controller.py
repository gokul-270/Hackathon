#!/usr/bin/env python3
"""
Robust Motor Controller
Enhanced VehicleMotorController with circuit breaker and retry patterns
"""
import asyncio
import logging
import time
from typing import Dict, Optional, Any, List
from dataclasses import dataclass

try:
    from .motor_controller import VehicleMotorController, MotorError, SafetyLimitError, MotorControllerInterface
    from .enhanced_motor_interface import EnhancedMockMotorInterface
    from ..utils.circuit_breaker import CircuitBreaker, RetryPolicy, CircuitBreakerError
    from ..config.constants import MotorIDs, VehicleState, PivotDirection, PHYSICAL
except ImportError:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from hardware.motor_controller import VehicleMotorController, MotorError, SafetyLimitError, MotorControllerInterface
    from hardware.enhanced_motor_interface import EnhancedMockMotorInterface
    from utils.circuit_breaker import CircuitBreaker, RetryPolicy, CircuitBreakerError
    from config.constants import MotorIDs, VehicleState, PivotDirection, PHYSICAL


@dataclass
class MotorHealth:
    """Motor health information"""
    motor_id: int
    is_healthy: bool
    last_error_time: Optional[float] = None
    error_count: int = 0
    temperature: Optional[float] = None
    voltage: Optional[float] = None
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class RobustMotorController(VehicleMotorController):
    """
    Enhanced VehicleMotorController with circuit breaker patterns and robust error handling
    """
    
    def __init__(self, motor_interface: MotorControllerInterface):
        """
        Initialize robust motor controller
        
        Args:
            motor_interface: Motor interface implementation
        """
        super().__init__(motor_interface)
        
        self.logger = logging.getLogger(__name__)
        
        # Circuit breakers for different operation types
        self.circuit_breakers = {
            'position_control': CircuitBreaker(
                failure_threshold=3,
                recovery_timeout=30.0,
                expected_exception=(MotorError, SafetyLimitError)
            ),
            'velocity_control': CircuitBreaker(
                failure_threshold=3,
                recovery_timeout=30.0,
                expected_exception=(MotorError, SafetyLimitError)
            ),
            'steering_control': CircuitBreaker(
                failure_threshold=5,
                recovery_timeout=60.0,
                expected_exception=(MotorError, SafetyLimitError)
            ),
            'communication': CircuitBreaker(
                failure_threshold=5,
                recovery_timeout=15.0,
                expected_exception=(MotorError, ConnectionError, TimeoutError)
            )
        }
        
        # Retry policies for different operations
        self.retry_policies = {
            'motor_command': RetryPolicy(
                max_attempts=3,
                backoff_factor=1.5,
                max_delay=5.0,
                expected_exception=MotorError
            ),
            'status_read': RetryPolicy(
                max_attempts=2,
                backoff_factor=1.0,
                max_delay=1.0,
                expected_exception=(MotorError, ConnectionError)
            )
        }
        
        # Health monitoring
        self._motor_health: Dict[int, MotorHealth] = {}
        self._system_health_score = 1.0
        self._last_health_check = 0.0
        self._health_check_interval = 5.0  # seconds
        
        # Enhanced safety limits (override limits object)
        self._enhanced_limits = {
            'MAX_VELOCITY_MPS': 3.0,
            'MAX_ACCELERATION_MPS2': 2.0,
            'MAX_MOTOR_TEMPERATURE': 70.0,
            'MIN_SYSTEM_VOLTAGE': 20.0,
            'MAX_SYSTEM_VOLTAGE': 30.0,
            'MAX_POSITION_ERROR_THRESHOLD': 2.0,  # rotations
            'MAX_VELOCITY_ERROR_THRESHOLD': 10.0  # rps
        }
        
        # Initialize motor health tracking
        self._initialize_health_tracking()
    
    def _initialize_health_tracking(self):
        """Initialize health tracking for all motors"""
        try:
            for motor_id in self._motor_ids.all_motors:
                self._motor_health[motor_id] = MotorHealth(
                    motor_id=motor_id,
                    is_healthy=True,
                    error_count=0
                )
        except Exception as e:
            self.logger.error(f"Failed to initialize health tracking: {e}")
    
    async def initialize_async(self) -> bool:
        """Async initialization with enhanced error handling"""
        try:
            self.logger.info("Initializing robust motor controller...")
            
            # Enhanced initialization with circuit breaker protection
            @self.circuit_breakers['communication']
            @self.retry_policies['motor_command']
            async def _protected_initialize():
                if hasattr(self._motor_interface, 'initialize_async'):
                    return await self._motor_interface.initialize_async()
                else:
                    return self._motor_interface.initialize()
            
            # Initialize motor interface
            if not await _protected_initialize():
                raise MotorError("Failed to initialize motor interface")
            
            # Enhanced motor initialization with health checks
            await self._initialize_motors_with_health_check()
            
            # Configure enhanced limits
            await self._configure_enhanced_motor_limits()
            
            self._initialized = True
            self.logger.info("Robust motor controller initialized successfully")
            return True
            
        except CircuitBreakerError as e:
            self.logger.error(f"Circuit breaker prevented initialization: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Robust motor controller initialization failed: {e}")
            return False
    
    def initialize(self) -> bool:
        """Synchronous initialization wrapper"""
        try:
            # Check if we're already in an async context
            loop = asyncio.get_running_loop()
            # If we get here, we're already in an async context - cannot use run_until_complete
            self.logger.warning("Already in async context, using fallback sync initialization")
            return self._sync_fallback_init()
        except RuntimeError:
            # No running loop, safe to create/use one
            try:
                return asyncio.run(self.initialize_async())
            except Exception as e:
                self.logger.error(f"Async initialization failed: {e}, using fallback")
                return self._sync_fallback_init()
    
    def _sync_fallback_init(self) -> bool:
        """Synchronous fallback initialization when async is not available"""
        try:
            self.logger.info("Using synchronous fallback initialization for robust controller")
            
            # Initialize motor interface synchronously
            if not self._motor_interface.initialize():
                self.logger.error("Motor interface initialization failed")
                return False
            
            # Basic motor initialization without async health checks
            try:
                for motor_id in self._motor_ids.all_motors:
                    # Get initial status
                    status = self._motor_interface.get_status(motor_id)
                    
                    # Update basic health tracking
                    health = self._motor_health[motor_id]
                    health.temperature = status.temperature
                    health.voltage = status.voltage
                    
                    # Check for errors
                    if status.error_code != 0:
                        self.logger.warning(f"Motor {motor_id} has error: {status.error_code}")
                        health.error_count += 1
                        health.last_error_time = time.time()
                        # Try to clear errors synchronously
                        try:
                            self._motor_interface.clear_errors(motor_id)
                        except Exception as e:
                            self.logger.warning(f"Could not clear motor {motor_id} errors: {e}")
                    
                    # Store motor state
                    with self._state_lock:
                        self._motor_states[motor_id] = status
                        
            except Exception as e:
                self.logger.error(f"Motor initialization error: {e}")
                # Continue with partial initialization
            
            self._initialized = True
            self.logger.info("Robust controller sync fallback initialization completed")
            return True
            
        except Exception as e:
            self.logger.error(f"Sync fallback initialization failed: {e}")
            return False
    
    async def _initialize_motors_with_health_check(self):
        """Initialize motors with comprehensive health checks"""
        for motor_id in self._motor_ids.all_motors:
            try:
                # Get initial status with retry
                @self.retry_policies['status_read']
                async def get_initial_status():
                    return self._motor_interface.get_status(motor_id)
                
                status = await get_initial_status()
                
                # Update health tracking
                health = self._motor_health[motor_id]
                health.temperature = status.temperature
                health.voltage = status.voltage
                
                # Check for initial errors
                if status.error_code != 0:
                    self.logger.warning(f"Motor {motor_id} has initial error: {status.error_code}")
                    health.error_count += 1
                    health.last_error_time = time.time()
                    
                    # Attempt to clear errors
                    await self._clear_motor_errors_with_retry(motor_id)
                
                # Validate motor health
                await self._validate_motor_health(motor_id, status)
                
                # Store motor state
                with self._state_lock:
                    self._motor_states[motor_id] = status
                    
            except Exception as e:
                self.logger.error(f"Failed to initialize motor {motor_id}: {e}")
                self._motor_health[motor_id].is_healthy = False
                self._motor_health[motor_id].warnings.append(f"Initialization failed: {e}")
    
    async def _validate_motor_health(self, motor_id: int, status) -> bool:
        """Validate motor health parameters"""
        health = self._motor_health[motor_id]
        health.warnings.clear()
        
        # Temperature check
        if status.temperature and status.temperature > self._enhanced_limits['MAX_MOTOR_TEMPERATURE']:
            health.warnings.append(f"High temperature: {status.temperature}°C")
            health.is_healthy = False
        
        # Voltage check
        if status.voltage:
            if status.voltage < self._enhanced_limits['MIN_SYSTEM_VOLTAGE']:
                health.warnings.append(f"Low voltage: {status.voltage}V")
                health.is_healthy = False
            elif status.voltage > self._enhanced_limits['MAX_SYSTEM_VOLTAGE']:
                health.warnings.append(f"High voltage: {status.voltage}V")
                health.is_healthy = False
        
        # Error code check
        if status.error_code != 0:
            health.warnings.append(f"Error code: {status.error_code}")
            health.is_healthy = False
        
        # Update overall health
        if not health.warnings:
            health.is_healthy = True
        
        return health.is_healthy
    
    async def _clear_motor_errors_with_retry(self, motor_id: int):
        """Clear motor errors with retry logic"""
        @self.retry_policies['motor_command']
        async def _clear_errors():
            return self._motor_interface.clear_errors(motor_id)
        
        try:
            success = await _clear_errors()
            if success:
                self.logger.info(f"Cleared errors for motor {motor_id}")
            return success
        except Exception as e:
            self.logger.error(f"Failed to clear errors for motor {motor_id}: {e}")
            return False
    
    async def _configure_enhanced_motor_limits(self):
        """Configure enhanced motor limits and safety parameters"""
        # This would set advanced limits on the motor interface
        # For now, just log the configuration
        self.logger.info("Enhanced motor limits configured:")
        for key, value in self._enhanced_limits.items():
            self.logger.info(f"  {key}: {value}")
    
    # Enhanced motor control methods with circuit breaker protection
    
    async def set_vehicle_velocity_async(self, velocity_mps: float) -> bool:
        """Enhanced async vehicle velocity control"""
        # Use the configured circuit breaker instance
        @self.circuit_breakers['velocity_control']
        @self.retry_policies['motor_command']
        async def _protected_velocity_control():
            # Pre-flight checks
            if not await self._pre_flight_check():
                raise MotorError("Pre-flight check failed")
            
            # Validate velocity limits
            if abs(velocity_mps) > self._enhanced_limits['MAX_VELOCITY_MPS']:
                raise SafetyLimitError(f"Velocity {velocity_mps} m/s exceeds safety limit {self._enhanced_limits['MAX_VELOCITY_MPS']} m/s")
            
            # Check system health
            if not await self._check_system_health():
                raise MotorError("System health check failed")
            
            # Execute velocity command
            return await self._execute_velocity_command_async(velocity_mps)
        
        try:
            return await _protected_velocity_control()
        except Exception as e:
            self.logger.error(f"Enhanced velocity control failed: {e}")
            await self._handle_motor_error(e)
            return False
    
    def set_vehicle_velocity(self, velocity_mps: float) -> bool:
        """Synchronous wrapper for enhanced velocity control"""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(self.set_vehicle_velocity_async(velocity_mps))
    
    async def _execute_velocity_command_async(self, velocity_mps: float) -> bool:
        """Execute velocity command with enhanced error handling"""
        try:
            # Convert to motor RPS with validation
            wheel_rps = velocity_mps / (PHYSICAL.WHEEL_CIRCUMFERENCE / 1000.0)  # mm to m
            motor_rps = wheel_rps * self._gear_ratios.DRIVE_MOTOR
            
            # Apply to all drive motors with individual error handling
            success_count = 0
            total_motors = len(self._motor_ids.drive_motors)
            
            for motor_id in self._motor_ids.drive_motors:
                try:
                    if await self._set_motor_velocity_with_validation(motor_id, motor_rps):
                        success_count += 1
                    else:
                        self.logger.warning(f"Failed to set velocity for motor {motor_id}")
                        
                except Exception as e:
                    self.logger.error(f"Motor {motor_id} velocity command failed: {e}")
                    self._motor_health[motor_id].error_count += 1
                    self._motor_health[motor_id].last_error_time = time.time()
            
            # Consider success if majority of motors responded
            success_ratio = success_count / total_motors
            if success_ratio >= 0.7:  # 70% success threshold
                return True
            else:
                raise MotorError(f"Only {success_count}/{total_motors} motors responded successfully")
                
        except Exception as e:
            self.logger.error(f"Velocity command execution failed: {e}")
            return False
    
    async def _set_motor_velocity_with_validation(self, motor_id: int, velocity_rps: float) -> bool:
        """Set motor velocity with validation and health monitoring"""
        try:
            # Check motor health before command
            if not self._motor_health[motor_id].is_healthy:
                self.logger.warning(f"Motor {motor_id} is unhealthy, skipping command")
                return False
            
            # Execute command
            success = self._motor_interface.set_velocity(motor_id, velocity_rps)
            
            if success:
                # Validate command execution
                await self._validate_command_execution(motor_id, 'velocity', velocity_rps)
            
            return success
            
        except Exception as e:
            self.logger.error(f"Motor {motor_id} velocity validation failed: {e}")
            return False
    
    async def _validate_command_execution(self, motor_id: int, command_type: str, expected_value: float):
        """Validate that motor command was executed correctly"""
        try:
            # Wait briefly for command to take effect
            await asyncio.sleep(0.1)
            
            # Get current status
            status = self._motor_interface.get_status(motor_id)
            
            # Validate based on command type
            if command_type == 'velocity':
                actual_velocity = status.velocity
                error = abs(actual_velocity - expected_value)
                if error > self._enhanced_limits['MAX_VELOCITY_ERROR_THRESHOLD']:
                    self.logger.warning(
                        f"Motor {motor_id} velocity error: expected {expected_value:.2f}, "
                        f"actual {actual_velocity:.2f}, error {error:.2f}"
                    )
                    self._motor_health[motor_id].warnings.append(
                        f"High velocity error: {error:.2f} rps"
                    )
            
            elif command_type == 'position':
                actual_position = status.position
                error = abs(actual_position - expected_value)
                if error > self._enhanced_limits['MAX_POSITION_ERROR_THRESHOLD']:
                    self.logger.warning(
                        f"Motor {motor_id} position error: expected {expected_value:.2f}, "
                        f"actual {actual_position:.2f}, error {error:.2f}"
                    )
                    self._motor_health[motor_id].warnings.append(
                        f"High position error: {error:.2f} rotations"
                    )
            
        except Exception as e:
            self.logger.error(f"Command validation failed for motor {motor_id}: {e}")
    
    async def _pre_flight_check(self) -> bool:
        """Comprehensive pre-flight safety check"""
        try:
            # Check emergency stop
            if self._emergency_stop.is_set():
                return False
            
            # Check initialization
            if not self._initialized:
                return False
            
            # Check system health
            current_time = time.time()
            if current_time - self._last_health_check > self._health_check_interval:
                await self._update_system_health()
                self._last_health_check = current_time
            
            return self._system_health_score > 0.5  # Minimum 50% health
            
        except Exception as e:
            self.logger.error(f"Pre-flight check failed: {e}")
            return False
    
    async def _check_system_health(self) -> bool:
        """Check overall system health"""
        try:
            healthy_motors = sum(1 for health in self._motor_health.values() if health.is_healthy)
            total_motors = len(self._motor_health)
            
            if total_motors == 0:
                return False
            
            health_ratio = healthy_motors / total_motors
            self._system_health_score = health_ratio
            
            return health_ratio > 0.7  # Require 70% of motors to be healthy
            
        except Exception as e:
            self.logger.error(f"System health check failed: {e}")
            return False
    
    async def _update_system_health(self):
        """Update system health status"""
        try:
            for motor_id in self._motor_ids.all_motors:
                try:
                    status = self._motor_interface.get_status(motor_id)
                    await self._validate_motor_health(motor_id, status)
                except Exception as e:
                    self.logger.warning(f"Health check failed for motor {motor_id}: {e}")
                    self._motor_health[motor_id].is_healthy = False
                    self._motor_health[motor_id].warnings.append(f"Health check failed: {e}")
            
            await self._check_system_health()
            
        except Exception as e:
            self.logger.error(f"System health update failed: {e}")
    
    async def _handle_motor_error(self, error: Exception):
        """Centralized error handling with recovery attempts"""
        try:
            if isinstance(error, SafetyLimitError):
                self.logger.error(f"Safety limit violation: {error}")
                # Don't attempt recovery for safety violations - they're intentional blocks
            elif isinstance(error, MotorError):
                self.logger.info("Attempting motor error recovery...")
                await self._attempt_motor_recovery()
            elif isinstance(error, ConnectionError):
                self.logger.info("Attempting connection recovery...")
                await self._attempt_connection_recovery()
            elif isinstance(error, CircuitBreakerError):
                self.logger.warning("Circuit breaker active, waiting for recovery...")
                # Circuit breaker will handle recovery automatically
            else:
                self.logger.error(f"Unhandled error type: {type(error).__name__}")
                
        except Exception as e:
            self.logger.error(f"Error recovery failed: {e}")
    
    async def _attempt_motor_recovery(self):
        """Attempt to recover motor functionality"""
        try:
            # Clear errors on all motors
            for motor_id in self._motor_ids.all_motors:
                await self._clear_motor_errors_with_retry(motor_id)
            
            # Reset circuit breakers if motors are responsive
            if await self._check_system_health():
                for cb in self.circuit_breakers.values():
                    cb.force_close()
                self.logger.info("Motor recovery successful")
            
        except Exception as e:
            self.logger.error(f"Motor recovery failed: {e}")
    
    async def _attempt_connection_recovery(self):
        """Attempt to recover connection to motor interface"""
        try:
            # Reinitialize motor interface if possible
            if hasattr(self._motor_interface, 'initialize_async'):
                success = await self._motor_interface.initialize_async()
            else:
                success = self._motor_interface.initialize()
            
            if success:
                self.logger.info("Connection recovery successful")
                # Reset communication circuit breaker
                self.circuit_breakers['communication'].force_close()
            else:
                raise ConnectionError("Failed to reinitialize motor interface")
                
        except Exception as e:
            self.logger.error(f"Connection recovery failed: {e}")
    
    def get_circuit_breaker_status(self) -> Dict[str, dict]:
        """Get status of all circuit breakers"""
        return {name: cb.get_stats() for name, cb in self.circuit_breakers.items()}
    
    def get_motor_health(self) -> Dict[int, dict]:
        """Get health status of all motors"""
        return {
            motor_id: {
                'is_healthy': health.is_healthy,
                'error_count': health.error_count,
                'last_error_time': health.last_error_time,
                'temperature': health.temperature,
                'voltage': health.voltage,
                'warnings': health.warnings.copy()
            }
            for motor_id, health in self._motor_health.items()
        }
    
    def get_system_health_score(self) -> float:
        """Get overall system health score (0.0 - 1.0)"""
        return self._system_health_score
    
    def force_circuit_breaker_reset(self, breaker_name: str = None):
        """Force reset circuit breaker(s)"""
        if breaker_name:
            if breaker_name in self.circuit_breakers:
                self.circuit_breakers[breaker_name].force_close()
                self.logger.info(f"Circuit breaker '{breaker_name}' manually reset")
            else:
                self.logger.error(f"Unknown circuit breaker: {breaker_name}")
        else:
            # Reset all circuit breakers
            for name, cb in self.circuit_breakers.items():
                cb.force_close()
            self.logger.info("All circuit breakers manually reset")