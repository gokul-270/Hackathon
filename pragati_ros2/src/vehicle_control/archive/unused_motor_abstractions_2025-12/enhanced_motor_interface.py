#!/usr/bin/env python3
"""
Enhanced Mock Motor Interface
Provides better hardware detection, synchronization, and async support
"""
import asyncio
import logging
import queue
import threading
import time
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, field
from enum import Enum

try:
    from .motor_controller import MotorControllerInterface, ControlMode, MotorStatus, MotorError
    from ..config.constants import MotorIDs
except ImportError:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from hardware.motor_controller import MotorControllerInterface, ControlMode, MotorStatus, MotorError
    from config.constants import MotorIDs


class HardwareState(Enum):
    """Hardware detection states"""
    UNKNOWN = "UNKNOWN"
    DETECTED = "DETECTED" 
    MOCK = "MOCK"
    FAILED = "FAILED"


@dataclass
class MotorCommand:
    """Enhanced motor command with timing"""
    motor_id: int
    command_type: str
    target_value: float
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HardwareInfo:
    """Hardware detection information"""
    state: HardwareState
    detection_time: float
    error_message: Optional[str] = None
    hardware_version: Optional[str] = None
    firmware_version: Optional[str] = None


class EnhancedMockMotorInterface(MotorControllerInterface):
    """
    Enhanced mock motor interface with hardware detection and better synchronization
    """
    
    def __init__(self, detection_timeout: float = 2.0):
        """
        Initialize enhanced mock interface
        
        Args:
            detection_timeout: Timeout for hardware detection (seconds)
        """
        self.logger = logging.getLogger(__name__)
        self.detection_timeout = detection_timeout
        
        # Hardware state
        self.hardware_info = HardwareInfo(
            state=HardwareState.UNKNOWN,
            detection_time=0.0
        )
        
        # Motor state management
        self._motor_states: Dict[int, MotorStatus] = {}
        self._motor_positions: Dict[int, float] = {}
        self._motor_velocities: Dict[int, float] = {}
        self._motor_torques: Dict[int, float] = {}
        self._motor_enabled: Dict[int, bool] = {}
        self._motor_errors: Dict[int, int] = {}
        self._motor_control_modes: Dict[int, ControlMode] = {}
        
        # Command processing
        self._command_queue = queue.Queue()
        self._command_processor_thread: Optional[threading.Thread] = None
        self._processing_commands = False
        
        # Synchronization
        self._state_lock = threading.RLock()
        self._initialized = False
        
        # Simulation parameters
        self._position_noise = 0.001  # Small position noise for realism
        self._velocity_response_time = 0.1  # Seconds to reach target velocity
        self._last_update_time = time.time()
        
        # Initialize motor IDs
        try:
            motor_ids = MotorIDs()
            self._all_motors = motor_ids.all_motors
        except:
            # Fallback motor IDs
            self._all_motors = [0, 1, 2, 3, 4, 5]
            
        # Initialize default states
        self._initialize_default_states()
    
    def _initialize_default_states(self):
        """Initialize default motor states"""
        for motor_id in self._all_motors:
            self._motor_positions[motor_id] = 0.0
            self._motor_velocities[motor_id] = 0.0
            self._motor_torques[motor_id] = 0.0
            self._motor_enabled[motor_id] = False
            self._motor_errors[motor_id] = 0
            self._motor_control_modes[motor_id] = ControlMode.IDLE
            
            # Create initial status
            self._motor_states[motor_id] = MotorStatus(
                motor_id=motor_id,
                position=0.0,
                velocity=0.0,
                torque=0.0,
                error_code=0,
                control_mode=ControlMode.IDLE,
                is_enabled=False,
                temperature=25.0,  # Room temperature
                voltage=24.0       # Typical system voltage
            )
    
    async def initialize_async(self) -> bool:
        """Async initialization with hardware detection"""
        try:
            self.logger.info("Starting enhanced motor interface initialization...")
            
            # Attempt hardware detection with timeout
            self.hardware_info = await self._detect_hardware()
            
            if self.hardware_info.state == HardwareState.DETECTED:
                self.logger.info("Real hardware detected, initializing hardware interface")
                success = await self._initialize_hardware()
            else:
                self.logger.info("No hardware detected, using enhanced mock interface")
                success = self._initialize_mock()
            
            if success:
                # Start command processor
                self._start_command_processor()
                self._initialized = True
                self.logger.info("Enhanced motor interface initialized successfully")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Enhanced motor interface initialization failed: {e}")
            self.hardware_info.state = HardwareState.FAILED
            self.hardware_info.error_message = str(e)
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
            self.logger.info("Using synchronous fallback initialization")
            
            # Set hardware info to mock since we can't do async detection
            self.hardware_info = HardwareInfo(
                state=HardwareState.MOCK,
                detection_time=0.0,
                error_message="Sync fallback - no hardware detection"
            )
            
            # Initialize mock interface
            success = self._initialize_mock()
            
            if success:
                self._start_command_processor()
                self._initialized = True
                self.logger.info("Sync fallback initialization completed")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Sync fallback initialization failed: {e}")
            return False
    
    async def _detect_hardware(self) -> HardwareInfo:
        """Attempt to detect real hardware"""
        detection_start = time.time()
        
        try:
            # Try multiple detection methods
            detection_tasks = [
                self._detect_can_bus(),
                self._detect_serial_interface(),
                self._detect_usb_interface()
            ]
            
            # Wait for any detection method to succeed (using asyncio.wait_for for compatibility)
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*detection_tasks, return_exceptions=True),
                    timeout=self.detection_timeout
                )
                
                # Check if any detection succeeded
                for result in results:
                    if isinstance(result, HardwareInfo) and result.state == HardwareState.DETECTED:
                        return result
                
                # No hardware detected
                return HardwareInfo(
                    state=HardwareState.MOCK,
                    detection_time=time.time() - detection_start,
                    error_message="No hardware detected"
                )
                
            except asyncio.TimeoutError:
                return HardwareInfo(
                    state=HardwareState.MOCK,
                    detection_time=time.time() - detection_start,
                    error_message="Hardware detection timeout"
                )
        except Exception as e:
            return HardwareInfo(
                state=HardwareState.FAILED,
                detection_time=time.time() - detection_start,
                error_message=f"Detection failed: {e}"
            )
    
    async def _detect_can_bus(self) -> HardwareInfo:
        """Attempt to detect CAN bus interface"""
        try:
            # Simulate CAN bus detection
            await asyncio.sleep(0.1)  # Simulate detection time
            
            # Try to import and initialize CAN interface
            try:
                import can
                # Attempt to create CAN bus interface
                # This would be replaced with actual CAN detection logic
                raise Exception("CAN hardware not available")
            except ImportError:
                raise Exception("CAN library not available")
            except Exception:
                raise Exception("CAN hardware not detected")
                
        except Exception as e:
            raise Exception(f"CAN detection failed: {e}")
    
    async def _detect_serial_interface(self) -> HardwareInfo:
        """Attempt to detect serial interface"""
        try:
            await asyncio.sleep(0.1)  # Simulate detection time
            
            try:
                import serial
                import serial.tools.list_ports
                
                # Look for ODrive-like devices
                ports = serial.tools.list_ports.comports()
                for port in ports:
                    if 'odrive' in port.description.lower():
                        return HardwareInfo(
                            state=HardwareState.DETECTED,
                            detection_time=time.time(),
                            hardware_version="ODrive v3.6",
                            firmware_version="0.5.4"
                        )
                
                raise Exception("No ODrive serial devices found")
                
            except ImportError:
                raise Exception("Serial library not available")
                
        except Exception as e:
            raise Exception(f"Serial detection failed: {e}")
    
    async def _detect_usb_interface(self) -> HardwareInfo:
        """Attempt to detect USB interface"""
        try:
            await asyncio.sleep(0.1)  # Simulate detection time
            
            try:
                import usb.core
                
                # Look for ODrive USB devices
                devices = usb.core.find(find_all=True)
                for device in devices:
                    # ODrive vendor/product IDs would go here
                    if device.idVendor == 0x1209 and device.idProduct == 0x0D32:  # Example ODrive IDs
                        return HardwareInfo(
                            state=HardwareState.DETECTED,
                            detection_time=time.time(),
                            hardware_version="ODrive v3.6",
                            firmware_version="0.5.4"
                        )
                
                raise Exception("No ODrive USB devices found")
                
            except ImportError:
                raise Exception("USB library not available")
                
        except Exception as e:
            raise Exception(f"USB detection failed: {e}")
    
    async def _initialize_hardware(self) -> bool:
        """Initialize real hardware interface"""
        # This would contain actual hardware initialization
        # For now, fall back to mock
        self.logger.warning("Real hardware initialization not implemented, using mock")
        return self._initialize_mock()
    
    def _initialize_mock(self) -> bool:
        """Initialize mock interface with enhanced simulation"""
        try:
            with self._state_lock:
                # Initialize all motors to known state
                for motor_id in self._all_motors:
                    self._motor_enabled[motor_id] = False
                    self._motor_errors[motor_id] = 0
                    
                self.logger.info(f"Mock interface initialized for {len(self._all_motors)} motors")
                return True
                
        except Exception as e:
            self.logger.error(f"Mock initialization failed: {e}")
            return False
    
    def _start_command_processor(self):
        """Start background command processing thread"""
        if self._command_processor_thread is None:
            self._processing_commands = True
            self._command_processor_thread = threading.Thread(
                target=self._process_commands,
                daemon=True
            )
            self._command_processor_thread.start()
            self.logger.debug("Command processor thread started")
    
    def _process_commands(self):
        """Background command processing"""
        while self._processing_commands:
            try:
                # Process commands with timeout
                command = self._command_queue.get(timeout=0.1)
                self._execute_command(command)
                self._command_queue.task_done()
                
            except queue.Empty:
                # Update motor simulation
                self._update_motor_simulation()
                continue
            except Exception as e:
                self.logger.error(f"Command processing error: {e}")
    
    def _execute_command(self, command: MotorCommand):
        """Execute a motor command"""
        try:
            with self._state_lock:
                motor_id = command.motor_id
                
                if command.command_type == "move_to_position":
                    self._motor_positions[motor_id] = command.target_value
                    self._motor_control_modes[motor_id] = ControlMode.POSITION
                    
                elif command.command_type == "set_velocity":
                    self._motor_velocities[motor_id] = command.target_value
                    self._motor_control_modes[motor_id] = ControlMode.VELOCITY
                    
                elif command.command_type == "set_torque":
                    self._motor_torques[motor_id] = command.target_value
                    self._motor_control_modes[motor_id] = ControlMode.TORQUE
                    
                elif command.command_type == "enable":
                    self._motor_enabled[motor_id] = True
                    
                elif command.command_type == "disable":
                    self._motor_enabled[motor_id] = False
                    self._motor_control_modes[motor_id] = ControlMode.IDLE
                    
                # Update motor status
                self._update_motor_status(motor_id)
                
        except Exception as e:
            self.logger.error(f"Command execution failed: {e}")
    
    def _update_motor_simulation(self):
        """Update motor simulation physics"""
        current_time = time.time()
        dt = current_time - self._last_update_time
        self._last_update_time = current_time
        
        with self._state_lock:
            for motor_id in self._all_motors:
                if not self._motor_enabled[motor_id]:
                    continue
                
                # Simulate velocity response for position control
                if self._motor_control_modes[motor_id] == ControlMode.POSITION:
                    target_pos = self._motor_positions[motor_id]
                    current_pos = self._motor_states[motor_id].position
                    
                    # Simple PID-like response
                    error = target_pos - current_pos
                    max_velocity = 10.0  # rad/s
                    velocity = max(-max_velocity, min(max_velocity, error * 5.0))
                    
                    # Update position
                    new_position = current_pos + velocity * dt
                    self._motor_states[motor_id].position = new_position
                    self._motor_states[motor_id].velocity = velocity
                
                # Add small amount of noise for realism
                if self._position_noise > 0:
                    import random
                    noise = random.uniform(-self._position_noise, self._position_noise)
                    self._motor_states[motor_id].position += noise
                
                # Update temperature simulation
                if self._motor_enabled[motor_id]:
                    # Simulate heating when active
                    current_temp = self._motor_states[motor_id].temperature or 25.0
                    self._motor_states[motor_id].temperature = min(
                        current_temp + dt * 0.5,  # Slow heating
                        50.0  # Max temperature
                    )
    
    def _update_motor_status(self, motor_id: int):
        """Update motor status object"""
        if motor_id in self._motor_states:
            status = self._motor_states[motor_id]
            status.position = self._motor_positions.get(motor_id, 0.0)
            status.velocity = self._motor_velocities.get(motor_id, 0.0)
            status.torque = self._motor_torques.get(motor_id, 0.0)
            status.error_code = self._motor_errors.get(motor_id, 0)
            status.control_mode = self._motor_control_modes.get(motor_id, ControlMode.IDLE)
            status.is_enabled = self._motor_enabled.get(motor_id, False)
    
    # MotorControllerInterface implementation
    def set_control_mode(self, motor_id: int, mode: ControlMode) -> bool:
        """Set motor control mode"""
        if not self._initialized:
            raise MotorError("Interface not initialized")
            
        try:
            command = MotorCommand(
                motor_id=motor_id,
                command_type="set_control_mode", 
                target_value=float(mode.value),
                timestamp=time.time(),
                metadata={"mode": mode}
            )
            self._command_queue.put(command)
            return True
        except Exception as e:
            self.logger.error(f"Failed to set control mode for motor {motor_id}: {e}")
            return False
    
    def move_to_position(self, motor_id: int, position: float) -> bool:
        """Move motor to absolute position"""
        if not self._initialized:
            raise MotorError("Interface not initialized")
            
        try:
            command = MotorCommand(
                motor_id=motor_id,
                command_type="move_to_position",
                target_value=position,
                timestamp=time.time()
            )
            self._command_queue.put(command)
            return True
        except Exception as e:
            self.logger.error(f"Failed to move motor {motor_id} to position {position}: {e}")
            return False
    
    def set_velocity(self, motor_id: int, velocity: float) -> bool:
        """Set motor velocity"""
        if not self._initialized:
            raise MotorError("Interface not initialized")
            
        try:
            command = MotorCommand(
                motor_id=motor_id,
                command_type="set_velocity",
                target_value=velocity,
                timestamp=time.time()
            )
            self._command_queue.put(command)
            return True
        except Exception as e:
            self.logger.error(f"Failed to set velocity for motor {motor_id}: {e}")
            return False
    
    def set_torque(self, motor_id: int, torque: float) -> bool:
        """Set motor torque"""
        if not self._initialized:
            raise MotorError("Interface not initialized")
            
        try:
            command = MotorCommand(
                motor_id=motor_id,
                command_type="set_torque", 
                target_value=torque,
                timestamp=time.time()
            )
            self._command_queue.put(command)
            return True
        except Exception as e:
            self.logger.error(f"Failed to set torque for motor {motor_id}: {e}")
            return False
    
    def get_status(self, motor_id: int) -> MotorStatus:
        """Get motor status"""
        if not self._initialized:
            raise MotorError("Interface not initialized")
            
        with self._state_lock:
            if motor_id in self._motor_states:
                return self._motor_states[motor_id]
            else:
                raise MotorError(f"Unknown motor ID: {motor_id}")
    
    def enable_motor(self, motor_id: int) -> bool:
        """Enable motor"""
        if not self._initialized:
            raise MotorError("Interface not initialized")
            
        try:
            command = MotorCommand(
                motor_id=motor_id,
                command_type="enable",
                target_value=1.0,
                timestamp=time.time()
            )
            self._command_queue.put(command)
            return True
        except Exception as e:
            self.logger.error(f"Failed to enable motor {motor_id}: {e}")
            return False
    
    def disable_motor(self, motor_id: int) -> bool:
        """Disable motor"""
        if not self._initialized:
            raise MotorError("Interface not initialized")
            
        try:
            command = MotorCommand(
                motor_id=motor_id,
                command_type="disable",
                target_value=0.0,
                timestamp=time.time()
            )
            self._command_queue.put(command)
            return True
        except Exception as e:
            self.logger.error(f"Failed to disable motor {motor_id}: {e}")
            return False
    
    def clear_errors(self, motor_id: int) -> bool:
        """Clear motor errors"""
        if not self._initialized:
            raise MotorError("Interface not initialized")
            
        try:
            with self._state_lock:
                self._motor_errors[motor_id] = 0
                self._update_motor_status(motor_id)
            return True
        except Exception as e:
            self.logger.error(f"Failed to clear errors for motor {motor_id}: {e}")
            return False
    
    def shutdown(self):
        """Shutdown interface"""
        self.logger.info("Shutting down enhanced motor interface...")
        
        # Stop command processing
        self._processing_commands = False
        if self._command_processor_thread:
            self._command_processor_thread.join(timeout=1.0)
        
        # Disable all motors
        with self._state_lock:
            for motor_id in self._all_motors:
                self._motor_enabled[motor_id] = False
                self._motor_control_modes[motor_id] = ControlMode.IDLE
        
        self._initialized = False
        self.logger.info("Enhanced motor interface shutdown complete")
    
    def get_hardware_info(self) -> HardwareInfo:
        """Get hardware detection information"""
        return self.hardware_info
    
    def get_diagnostics(self) -> Dict[str, Any]:
        """Get interface diagnostics"""
        with self._state_lock:
            return {
                'initialized': self._initialized,
                'hardware_state': self.hardware_info.state.value,
                'motor_count': len(self._all_motors),
                'enabled_motors': sum(1 for enabled in self._motor_enabled.values() if enabled),
                'command_queue_size': self._command_queue.qsize(),
                'processing_commands': self._processing_commands,
                'last_update': self._last_update_time
            }