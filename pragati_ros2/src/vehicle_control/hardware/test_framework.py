#!/usr/bin/env python3
"""
Hardware Test Framework
Provides structured testing capabilities for vehicle control hardware
"""

import time
import logging
from enum import Enum
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestType(Enum):
    """Types of hardware tests"""
    STEERING_MOTOR = "steering_motor"
    DRIVE_MOTORS = "drive_motors"
    OUTPUT_PINS = "output_pins"
    INPUT_PINS = "input_pins"
    EMERGENCY_STOP = "emergency_stop"
    FULL_SYSTEM = "full_system"

@dataclass
class TestResult:
    """Results from a hardware test"""
    test_name: str
    test_type: TestType
    passed: bool
    duration: float
    message: str
    timestamp: datetime
    details: Dict[str, Any] = None

class HardwareTestFramework:
    """Framework for testing vehicle control hardware"""
    
    def __init__(self, motor_controller=None, gpio_manager=None):
        self.motor_controller = motor_controller
        self.gpio_manager = gpio_manager
        self.test_results: List[TestResult] = []
        
    def test_steering_motors(self) -> bool:
        """Test steering motor functionality"""
        start_time = time.time()
        
        try:
            logger.info("Testing steering motors...")
            
            if not self.motor_controller:
                raise Exception("Motor controller not available")
            
            # Test steering motor positions
            test_positions = [0.0, 0.2, -0.2, 0.0]
            
            for position in test_positions:
                logger.info(f"Testing steering position: {position}")
                success = self.motor_controller.set_ackermann_steering(position)
                if not success:
                    self._record_result("steering_motors", TestType.STEERING_MOTOR, 
                                      False, time.time() - start_time,
                                      f"Failed to set steering position {position}")
                    return False
                time.sleep(0.1)
            
            duration = time.time() - start_time
            self._record_result("steering_motors", TestType.STEERING_MOTOR, 
                              True, duration, "All steering tests passed")
            return True
            
        except Exception as e:
            duration = time.time() - start_time
            self._record_result("steering_motors", TestType.STEERING_MOTOR, 
                              False, duration, f"Exception: {str(e)}")
            return False
    
    def test_drive_motors(self) -> bool:
        """Test drive motor functionality"""
        start_time = time.time()
        
        try:
            logger.info("Testing drive motors...")
            
            if not self.motor_controller:
                raise Exception("Motor controller not available")
            
            # Test drive motor velocities
            test_velocities = [0.0, 0.1, -0.1, 0.0]
            
            for velocity in test_velocities:
                logger.info(f"Testing drive velocity: {velocity}")
                # Test each drive motor
                for motor_id in [0, 1]:  # Drive motors
                    success = self.motor_controller.set_motor_velocity(motor_id, velocity)
                    if not success:
                        self._record_result("drive_motors", TestType.DRIVE_MOTORS,
                                          False, time.time() - start_time,
                                          f"Failed to set velocity {velocity} for motor {motor_id}")
                        return False
                time.sleep(0.1)
            
            duration = time.time() - start_time
            self._record_result("drive_motors", TestType.DRIVE_MOTORS,
                              True, duration, "All drive motor tests passed")
            return True
            
        except Exception as e:
            duration = time.time() - start_time
            self._record_result("drive_motors", TestType.DRIVE_MOTORS,
                              False, duration, f"Exception: {str(e)}")
            return False
    
    def test_output_pins(self) -> bool:
        """Test GPIO output pin functionality"""
        start_time = time.time()
        
        try:
            logger.info("Testing GPIO output pins...")
            
            if not self.gpio_manager:
                raise Exception("GPIO manager not available")
            
            # Test status LED outputs
            statuses = ["OK", "WARNING", "ERROR"]
            for status in statuses:
                logger.info(f"Testing status LED: {status}")
                self.gpio_manager.show_status_led(status)
                time.sleep(0.2)
            
            duration = time.time() - start_time
            self._record_result("output_pins", TestType.OUTPUT_PINS,
                              True, duration, "All output pin tests passed")
            return True
            
        except Exception as e:
            duration = time.time() - start_time
            self._record_result("output_pins", TestType.OUTPUT_PINS,
                              False, duration, f"Exception: {str(e)}")
            return False
    
    def test_input_pins(self) -> bool:
        """Test GPIO input pin functionality"""
        start_time = time.time()
        
        try:
            logger.info("Testing GPIO input pins...")
            
            if not self.gpio_manager:
                raise Exception("GPIO manager not available")
            
            # Test reading input pins
            inputs = self.gpio_manager.read_all_inputs()
            logger.info(f"Read {len(inputs)} input pins")
            
            # Test specific safety inputs
            emergency_stop = self.gpio_manager.is_emergency_stop_active()
            brake_engaged = self.gpio_manager.is_brake_engaged()
            direction = self.gpio_manager.get_direction_command()
            auto_mode = self.gpio_manager.is_automatic_mode_selected()
            
            logger.info(f"Emergency stop: {emergency_stop}")
            logger.info(f"Brake engaged: {brake_engaged}")
            logger.info(f"Direction: {direction}")
            logger.info(f"Auto mode: {auto_mode}")
            
            duration = time.time() - start_time
            self._record_result("input_pins", TestType.INPUT_PINS,
                              True, duration, "All input pin tests passed")
            return True
            
        except Exception as e:
            duration = time.time() - start_time
            self._record_result("input_pins", TestType.INPUT_PINS,
                              False, duration, f"Exception: {str(e)}")
            return False
    
    def test_emergency_stop(self) -> bool:
        """Test emergency stop functionality"""
        start_time = time.time()
        
        try:
            logger.info("Testing emergency stop functionality...")
            
            if not self.gpio_manager:
                raise Exception("GPIO manager not available")
            
            # Test emergency stop reading
            is_active = self.gpio_manager.is_emergency_stop_active()
            logger.info(f"Emergency stop active: {is_active}")
            
            duration = time.time() - start_time
            self._record_result("emergency_stop", TestType.EMERGENCY_STOP,
                              True, duration, "Emergency stop test passed")
            return True
            
        except Exception as e:
            duration = time.time() - start_time
            self._record_result("emergency_stop", TestType.EMERGENCY_STOP,
                              False, duration, f"Exception: {str(e)}")
            return False
    
    def run_test_suite(self, test_types: List[TestType] = None) -> bool:
        """Run a suite of tests"""
        if test_types is None:
            test_types = [TestType.STEERING_MOTOR, TestType.DRIVE_MOTORS, 
                         TestType.OUTPUT_PINS, TestType.INPUT_PINS]
        
        logger.info(f"Running test suite with {len(test_types)} test types")
        overall_success = True
        
        for test_type in test_types:
            if test_type == TestType.STEERING_MOTOR:
                success = self.test_steering_motors()
            elif test_type == TestType.DRIVE_MOTORS:
                success = self.test_drive_motors()
            elif test_type == TestType.OUTPUT_PINS:
                success = self.test_output_pins()
            elif test_type == TestType.INPUT_PINS:
                success = self.test_input_pins()
            elif test_type == TestType.EMERGENCY_STOP:
                success = self.test_emergency_stop()
            else:
                logger.warning(f"Unknown test type: {test_type}")
                continue
            
            if not success:
                overall_success = False
                logger.error(f"Test {test_type} failed")
            else:
                logger.info(f"Test {test_type} passed")
        
        return overall_success
    
    def get_test_results(self) -> List[TestResult]:
        """Get all test results"""
        return self.test_results.copy()
    
    def export_test_report(self, filename: str = "test_report.txt"):
        """Export test results to a file"""
        try:
            with open(filename, 'w') as f:
                f.write("Hardware Test Report\n")
                f.write("=" * 50 + "\n")
                f.write(f"Generated: {datetime.now().isoformat()}\n\n")
                
                total_tests = len(self.test_results)
                passed_tests = sum(1 for r in self.test_results if r.passed)
                
                f.write(f"Total Tests: {total_tests}\n")
                f.write(f"Passed: {passed_tests}\n")
                f.write(f"Failed: {total_tests - passed_tests}\n")
                f.write(f"Success Rate: {(passed_tests/total_tests*100):.1f}%\n\n")
                
                for result in self.test_results:
                    f.write(f"Test: {result.test_name}\n")
                    f.write(f"  Type: {result.test_type.value}\n")
                    f.write(f"  Status: {'PASSED' if result.passed else 'FAILED'}\n")
                    f.write(f"  Duration: {result.duration:.3f}s\n")
                    f.write(f"  Message: {result.message}\n")
                    f.write(f"  Timestamp: {result.timestamp.isoformat()}\n\n")
            
            logger.info(f"Test report exported to {filename}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export test report: {e}")
            return False
    
    def _record_result(self, test_name: str, test_type: TestType, 
                      passed: bool, duration: float, message: str):
        """Record a test result"""
        result = TestResult(
            test_name=test_name,
            test_type=test_type,
            passed=passed,
            duration=duration,
            message=message,
            timestamp=datetime.now()
        )
        self.test_results.append(result)
        
        if passed:
            logger.info(f"✅ {test_name}: {message} ({duration:.3f}s)")
        else:
            logger.error(f"❌ {test_name}: {message} ({duration:.3f}s)")