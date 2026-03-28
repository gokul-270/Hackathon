#!/usr/bin/env python3
"""
Comprehensive Test Suite for Enhanced Vehicle Control System
Tests all new components including circuit breakers, diagnostics, and configuration management
"""
import asyncio
import pytest
import logging
import tempfile
import yaml
import json
import time
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path

# Import our enhanced components
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from vehicle_control.utils.circuit_breaker import CircuitBreaker, RetryPolicy, CircuitBreakerError
from vehicle_control.hardware.enhanced_motor_interface import EnhancedMockMotorInterface, HardwareState
from vehicle_control.hardware.robust_motor_controller import RobustMotorController
from vehicle_control.integration.system_diagnostics import VehicleSystemDiagnostics, HealthStatus, DiagnosticLevel
from vehicle_control.utils.configuration_manager import ConfigurationManager, ValidationResult, ConfigType


class TestCircuitBreaker:
    """Test circuit breaker functionality"""
    
    def test_circuit_breaker_basic_functionality(self):
        """Test basic circuit breaker operation"""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
        
        # Test successful operation
        @cb
        def successful_function():
            return "success"
        
        assert successful_function() == "success"
        
        # Test failure triggering circuit breaker
        failure_count = 0
        
        @cb
        def failing_function():
            nonlocal failure_count
            failure_count += 1
            raise Exception("Test failure")
        
        # First few failures should pass through
        with pytest.raises(Exception, match="Test failure"):
            failing_function()
        
        with pytest.raises(Exception, match="Test failure"):
            failing_function()
        
        # Circuit breaker should now be open
        with pytest.raises(CircuitBreakerError):
            failing_function()
        
        assert failure_count == 2
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_async(self):
        """Test circuit breaker with async functions"""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
        
        @cb
        async def async_function(should_fail=False):
            await asyncio.sleep(0.01)
            if should_fail:
                raise Exception("Async failure")
            return "async success"
        
        # Test success
        result = await async_function(False)
        assert result == "async success"
        
        # Test failure
        with pytest.raises(Exception, match="Async failure"):
            await async_function(True)
        
        # Circuit should be open now
        with pytest.raises(CircuitBreakerError):
            await async_function(False)
    
    def test_circuit_breaker_recovery(self):
        """Test circuit breaker recovery after timeout"""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01, success_threshold=1)
        
        @cb
        def test_function(should_fail=False):
            if should_fail:
                raise Exception("Test failure")
            return "success"
        
        # Trigger circuit breaker
        with pytest.raises(Exception):
            test_function(True)
        
        # Should be open
        with pytest.raises(CircuitBreakerError):
            test_function(False)
        
        # Wait for recovery timeout
        time.sleep(0.02)
        
        # Should allow one test call (half-open)
        result = test_function(False)
        assert result == "success"
        
        # Should be closed again
        result = test_function(False)
        assert result == "success"
    
    def test_retry_policy(self):
        """Test retry policy functionality"""
        retry = RetryPolicy(max_attempts=3, backoff_factor=1.0, max_delay=0.01)
        
        attempt_count = 0
        
        @retry
        def flaky_function():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise Exception(f"Attempt {attempt_count} failed")
            return f"Success on attempt {attempt_count}"
        
        result = flaky_function()
        assert result == "Success on attempt 3"
        assert attempt_count == 3
    
    @pytest.mark.asyncio
    async def test_retry_policy_async(self):
        """Test retry policy with async functions"""
        retry = RetryPolicy(max_attempts=2, backoff_factor=1.0, max_delay=0.01)
        
        attempt_count = 0
        
        @retry
        async def async_flaky_function():
            nonlocal attempt_count
            attempt_count += 1
            await asyncio.sleep(0.001)
            if attempt_count < 2:
                raise Exception(f"Async attempt {attempt_count} failed")
            return f"Async success on attempt {attempt_count}"
        
        result = await async_flaky_function()
        assert result == "Async success on attempt 2"
        assert attempt_count == 2


class TestEnhancedMotorInterface:
    """Test enhanced motor interface"""
    
    @pytest.fixture
    def motor_interface(self):
        return EnhancedMockMotorInterface(detection_timeout=0.1)
    
    @pytest.mark.asyncio
    async def test_async_initialization(self, motor_interface):
        """Test async initialization with hardware detection"""
        success = await motor_interface.initialize_async()
        assert success
        assert motor_interface.hardware_info.state in [HardwareState.MOCK, HardwareState.DETECTED]
        assert motor_interface._initialized
    
    def test_sync_initialization(self, motor_interface):
        """Test synchronous initialization wrapper"""
        success = motor_interface.initialize()
        assert success
        assert motor_interface._initialized
    
    def test_motor_operations(self, motor_interface):
        """Test basic motor operations"""
        motor_interface.initialize()
        
        # Test motor control
        assert motor_interface.enable_motor(0)
        assert motor_interface.move_to_position(0, 1.5)
        assert motor_interface.set_velocity(0, 10.0)
        
        # Allow time for async command processing
        time.sleep(0.1)
        
        # Test status retrieval
        status = motor_interface.get_status(0)
        assert status.motor_id == 0
        assert status.is_enabled
    
    def test_command_processing(self, motor_interface):
        """Test background command processing"""
        motor_interface.initialize()
        
        # Commands should be processed asynchronously
        motor_interface.move_to_position(0, 2.0)
        
        # Give command processor time to work
        time.sleep(0.1)
        
        # Check command queue processing
        diagnostics = motor_interface.get_diagnostics()
        assert diagnostics['processing_commands']
        assert diagnostics['initialized']
    
    def test_hardware_info(self, motor_interface):
        """Test hardware detection information"""
        motor_interface.initialize()
        
        hardware_info = motor_interface.get_hardware_info()
        assert hardware_info.state in [HardwareState.MOCK, HardwareState.DETECTED, HardwareState.FAILED]
        assert hardware_info.detection_time >= 0


class TestRobustMotorController:
    """Test robust motor controller"""
    
    @pytest.fixture
    def mock_interface(self):
        interface = Mock()
        interface.initialize.return_value = True
        interface.initialize_async = AsyncMock(return_value=True)
        
        # Create a mock status object
        mock_status = Mock(
            motor_id=0,
            position=0.0,
            velocity=0.0,
            torque=0.0,
            error_code=0,
            is_enabled=True,
            temperature=25.0,
            voltage=24.0
        )
        interface.get_status.return_value = mock_status
        interface.clear_errors.return_value = True
        interface.clear_errors = AsyncMock(return_value=True)
        interface.set_velocity.return_value = True
        interface.move_to_position.return_value = True
        return interface
    
    @pytest.fixture
    def robust_controller(self, mock_interface):
        return RobustMotorController(mock_interface)
    
    def test_initialization(self, robust_controller):
        """Test robust controller initialization"""
        success = robust_controller.initialize()
        assert success
        assert robust_controller._initialized
    
    @pytest.mark.asyncio
    async def test_async_initialization(self, robust_controller):
        """Test async initialization"""
        success = await robust_controller.initialize_async()
        assert success
        assert robust_controller._initialized
    
    def test_circuit_breaker_integration(self, robust_controller):
        """Test circuit breaker integration"""
        robust_controller.initialize()
        
        # Test successful operation
        success = robust_controller.set_vehicle_velocity(1.0)
        assert success
        
        # Get circuit breaker status
        cb_status = robust_controller.get_circuit_breaker_status()
        assert 'velocity_control' in cb_status
        assert cb_status['velocity_control']['state'] == 'CLOSED'
    
    def test_motor_health_tracking(self, robust_controller):
        """Test motor health tracking"""
        robust_controller.initialize()
        
        # Get motor health information
        health = robust_controller.get_motor_health()
        assert isinstance(health, dict)
        
        # Check system health score
        score = robust_controller.get_system_health_score()
        assert 0.0 <= score <= 1.0
    
    def test_circuit_breaker_reset(self, robust_controller):
        """Test manual circuit breaker reset"""
        robust_controller.initialize()
        
        # Force open a circuit breaker
        robust_controller.circuit_breakers['velocity_control'].force_open()
        
        # Reset it
        robust_controller.force_circuit_breaker_reset('velocity_control')
        
        # Check that it's closed
        status = robust_controller.get_circuit_breaker_status()
        assert status['velocity_control']['state'] == 'CLOSED'


class TestSystemDiagnostics:
    """Test system diagnostics"""
    
    @pytest.fixture
    def mock_motor_controller(self):
        controller = Mock()
        controller._motor_interface = Mock()
        controller._motor_interface.get_status.return_value = Mock(
            motor_id=0,
            temperature=30.0,
            voltage=24.0,
            position=0.0,
            velocity=0.0,
            error_code=0,
            is_enabled=True
        )
        controller._motor_ids = Mock()
        controller._motor_ids.all_motors = [0, 1, 2]
        return controller
    
    @pytest.fixture
    def mock_gpio_manager(self):
        gpio = Mock()
        gpio.read_all_inputs.return_value = {16: False, 18: False}
        gpio.is_emergency_stop_active.return_value = False
        return gpio
    
    @pytest.fixture
    def diagnostics(self, mock_motor_controller, mock_gpio_manager):
        return VehicleSystemDiagnostics(
            mock_motor_controller,
            mock_gpio_manager,
            DiagnosticLevel.DETAILED
        )
    
    @pytest.mark.asyncio
    async def test_system_health_check(self, diagnostics):
        """Test complete system health check"""
        report = await diagnostics.perform_system_health_check()
        
        assert report.overall_status in [status for status in HealthStatus]
        assert 0.0 <= report.system_score <= 1.0
        assert 'motors' in report.subsystems
        assert 'gpio' in report.subsystems
        assert 'communication' in report.subsystems
    
    @pytest.mark.asyncio
    async def test_motor_subsystem_diagnostics(self, diagnostics):
        """Test motor subsystem diagnostics"""
        subsystem = await diagnostics._check_motor_subsystem()
        
        assert subsystem.name == "motors"
        assert subsystem.status in [status for status in HealthStatus]
        assert len(subsystem.diagnostics) > 0
        assert 'health_ratio' in subsystem.metrics
    
    @pytest.mark.asyncio
    async def test_gpio_subsystem_diagnostics(self, diagnostics):
        """Test GPIO subsystem diagnostics"""
        subsystem = await diagnostics._check_gpio_subsystem()
        
        assert subsystem.name == "gpio"
        assert subsystem.status in [status for status in HealthStatus]
        assert 'emergency_stop' in subsystem.metrics
    
    @pytest.mark.asyncio
    async def test_communication_diagnostics(self, diagnostics):
        """Test communication diagnostics"""
        subsystem = await diagnostics._check_communication_subsystem()
        
        assert subsystem.name == "communication"
        assert subsystem.status in [status for status in HealthStatus]
    
    def test_continuous_diagnostics(self, diagnostics):
        """Test continuous diagnostic monitoring"""
        # Start continuous diagnostics
        diagnostics.start_continuous_diagnostics(interval=0.1)
        assert diagnostics._running
        
        # Let it run for a short time
        time.sleep(0.2)
        
        # Stop diagnostics
        diagnostics.stop_continuous_diagnostics()
        assert not diagnostics._running
        
        # Check that reports were generated
        history = diagnostics.get_health_history()
        assert len(history) > 0
    
    def test_diagnostic_callbacks(self, diagnostics):
        """Test diagnostic result callbacks"""
        callback_results = []
        
        def test_callback(report):
            callback_results.append(report)
        
        diagnostics.add_diagnostic_callback(test_callback)
        
        # Run diagnostics
        diagnostics.start_continuous_diagnostics(interval=0.1)
        time.sleep(0.15)
        diagnostics.stop_continuous_diagnostics()
        
        # Check callback was called
        assert len(callback_results) > 0
        
        # Remove callback
        diagnostics.remove_diagnostic_callback(test_callback)
    
    def test_report_export(self, diagnostics):
        """Test health report export"""
        # Generate a report first and manually add it to history
        report = asyncio.run(diagnostics.perform_system_health_check())
        diagnostics._health_history.append(report)  # Manually add to history for testing
        
        # Export to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
        
        try:
            diagnostics.export_health_report(temp_path, format="json")
            
            # Verify file was created and contains valid JSON
            assert os.path.exists(temp_path)
            
            with open(temp_path, 'r') as f:
                report_data = json.load(f)
            
            assert 'timestamp' in report_data
            assert 'overall_status' in report_data
            assert 'subsystems' in report_data
            
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


class TestConfigurationManager:
    """Test configuration management and validation"""
    
    @pytest.fixture
    def config_manager(self):
        return ConfigurationManager()
    
    def test_schema_validation(self, config_manager):
        """Test configuration schema validation"""
        # Test valid configuration
        valid_config = {
            'joint_names': ['joint2', 'joint3', 'joint4'],
            'control_frequency': 100.0,
            'cmd_vel_timeout': 1.5,
            'physical_params': {
                'wheel_diameter': 0.15,
                'driving_gear_ratio': 5.0,
                'steering_gear_ratio': 10.0,
                'steering_limits': {
                    'min': -45.0,
                    'max': 45.0
                }
            }
        }
        
        result = config_manager.validate_configuration(valid_config)
        assert result.is_valid
        assert len(result.errors) == 0
    
    def test_invalid_configuration(self, config_manager):
        """Test validation of invalid configuration"""
        invalid_config = {
            'joint_names': [],  # Empty list (min_length = 1)
            'control_frequency': -10.0,  # Below minimum
            'cmd_vel_timeout': 15.0,  # Above maximum
            'physical_params': {
                'wheel_diameter': "invalid",  # Wrong type
                'steering_limits': {
                    'min': 50.0,  # Above maximum for min
                    'max': -30.0   # Below minimum for max
                }
            }
        }
        
        result = config_manager.validate_configuration(invalid_config)
        assert not result.is_valid
        assert len(result.errors) > 0
    
    def test_default_configuration(self, config_manager):
        """Test default configuration generation"""
        defaults = config_manager.get_default_configuration()
        
        assert 'joint_names' in defaults
        assert 'control_frequency' in defaults
        assert 'physical_params' in defaults
        
        # Validate that defaults are valid
        result = config_manager.validate_configuration(defaults)
        assert result.is_valid
    
    def test_configuration_loading(self, config_manager):
        """Test loading configuration from file"""
        # Create temporary config file
        test_config = {
            'vehicle_control': {
                'ros__parameters': {
                    'joint_names': ['test_joint'],
                    'control_frequency': 50.0,
                    'physical_params': {
                        'wheel_diameter': 0.2,
                        'driving_gear_ratio': 3.0,
                        'steering_gear_ratio': 8.0,
                        'steering_limits': {
                            'min': -30.0,
                            'max': 30.0
                        }
                    }
                }
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(test_config, f)
            temp_path = f.name
        
        try:
            result = config_manager.load_configuration(temp_path)
            assert result.is_valid
            
            # Check loaded values
            assert config_manager.get_parameter('joint_names') == ['test_joint']
            assert config_manager.get_parameter('control_frequency') == 50.0
            assert config_manager.get_parameter('physical_params.wheel_diameter') == 0.2
            
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def test_parameter_access(self, config_manager):
        """Test parameter getting and setting"""
        # Load default configuration
        config_manager._config = config_manager.get_default_configuration()
        
        # Test getting parameters
        joint_names = config_manager.get_parameter('joint_names')
        assert isinstance(joint_names, list)
        
        wheel_diameter = config_manager.get_parameter('physical_params.wheel_diameter')
        assert isinstance(wheel_diameter, float)
        
        # Test setting parameters
        success = config_manager.set_parameter('control_frequency', 75.0)
        assert success
        
        assert config_manager.get_parameter('control_frequency') == 75.0
        
        # Test setting invalid parameter
        success = config_manager.set_parameter('control_frequency', -50.0)  # Below minimum
        assert not success
    
    def test_configuration_export(self, config_manager):
        """Test configuration export"""
        config_manager._config = config_manager.get_default_configuration()
        
        # Test YAML export
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml_path = f.name
        
        try:
            success = config_manager.export_configuration(yaml_path, format='yaml')
            assert success
            assert os.path.exists(yaml_path)
            
            # Verify exported content
            with open(yaml_path, 'r') as f:
                exported_config = yaml.safe_load(f)
            
            assert 'joint_names' in exported_config
            
        finally:
            if os.path.exists(yaml_path):
                os.unlink(yaml_path)
    
    def test_schema_documentation(self, config_manager):
        """Test schema documentation generation"""
        docs = config_manager.get_schema_documentation()
        
        assert isinstance(docs, str)
        assert 'joint_names' in docs
        assert 'control_frequency' in docs
        assert 'REQUIRED' in docs
        assert 'OPTIONAL' in docs
    
    def test_default_config_file_creation(self, config_manager):
        """Test default configuration file creation"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            temp_path = f.name
        
        try:
            success = config_manager.create_default_config_file(temp_path)
            assert success
            assert os.path.exists(temp_path)
            
            # Verify structure
            with open(temp_path, 'r') as f:
                config_data = yaml.safe_load(f)
            
            assert 'vehicle_control' in config_data
            assert 'ros__parameters' in config_data['vehicle_control']
            
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


class TestIntegration:
    """Integration tests for all enhanced components"""
    
    @pytest.mark.asyncio
    async def test_full_system_integration(self):
        """Test integration of all enhanced components"""
        # Create enhanced motor interface
        motor_interface = EnhancedMockMotorInterface(detection_timeout=0.1)
        await motor_interface.initialize_async()
        
        # Create robust motor controller
        robust_controller = RobustMotorController(motor_interface)
        await robust_controller.initialize_async()
        
        # Create system diagnostics
        diagnostics = VehicleSystemDiagnostics(
            robust_controller,
            None,  # No GPIO manager for this test
            DiagnosticLevel.DETAILED
        )
        
        # Create configuration manager
        config_manager = ConfigurationManager()
        
        # Test that all components work together
        health_report = await diagnostics.perform_system_health_check()
        assert health_report.overall_status in [status for status in HealthStatus]
        
        # Test motor operations with circuit breaker protection
        success = await robust_controller.set_vehicle_velocity_async(1.0)
        assert success
        
        # Test configuration validation
        default_config = config_manager.get_default_configuration()
        validation_result = config_manager.validate_configuration(default_config)
        assert validation_result.is_valid
        
        # Cleanup
        motor_interface.shutdown()
    
    def test_error_propagation(self):
        """Test error handling and propagation through the system"""
        # Create failing motor interface
        failing_interface = Mock()
        failing_interface.initialize.return_value = False
        failing_interface.initialize_async = AsyncMock(return_value=False)
        failing_interface.get_status.side_effect = Exception("Motor communication failed")
        failing_interface.clear_errors = Mock(return_value=False)
        
        # Test that robust controller handles failures gracefully
        controller = RobustMotorController(failing_interface)
        success = controller.initialize()
        assert not success  # Should fail gracefully
        
        # Test that diagnostics detect the failure
        diagnostics = VehicleSystemDiagnostics(controller)
        
        # Run health check (should handle exceptions)
        report = asyncio.run(diagnostics.perform_system_health_check())
        assert report.overall_status in [HealthStatus.ERROR, HealthStatus.CRITICAL]


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "--tb=short"])