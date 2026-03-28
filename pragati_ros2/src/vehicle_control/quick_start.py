#!/usr/bin/env python3
"""
Quick Start Demo
Simple example to get started with the vehicle control system
"""

import sys
import time
from pathlib import Path

# Add the refactored_example directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

print("🚗 Vehicle Control System - Quick Start Demo")
print("=" * 50)

try:
    from hardware.motor_controller import VehicleMotorController
    from hardware.gpio_manager import GPIOManager
    from hardware.test_framework import HardwareTestFramework, TestType
    
    # Mock interface for safe testing without hardware
    class QuickStartMotorInterface:
        def __init__(self):
            self.initialized = False
            
        def initialize(self) -> bool:
            print("✓ Motor interface initialized (mock)")
            self.initialized = True
            return True
            
        def shutdown(self):
            self.initialized = False
            
        def move_to_position(self, motor_id: int, position: float) -> bool:
            if self.initialized:
                print(f"  Motor {motor_id} → position {position:.3f}")
                return True
            return False
            
        def set_velocity(self, motor_id: int, velocity: float) -> bool:
            if self.initialized:
                print(f"  Motor {motor_id} → velocity {velocity:.3f}")
                return True
            return False
            
        def get_position(self, motor_id: int) -> float:
            return 0.0
            
        def get_velocity(self, motor_id: int) -> float:
            return 0.0
            
        def get_status(self, motor_id: int):
            # Mock motor status for initialization
            class MockStatus:
                def __init__(self):
                    self.position = 0.0
                    self.velocity = 0.0
                    self.error_code = 0
                    self.current = 0.0
                    self.temperature = 25.0
            return MockStatus()
    
    print("\n1. Initializing Components...")
    
    # Create motor interface and controller
    motor_interface = QuickStartMotorInterface()
    motor_interface.initialize()
    motor_controller = VehicleMotorController(motor_interface)
    motor_controller.initialize()  # Initialize the motor controller
    print("✓ Motor controller initialized")
    
    # Create GPIO manager
    gpio_manager = GPIOManager()
    print("✓ GPIO manager initialized")
    
    print("\n2. Basic Vehicle Operations...")
    
    # Test basic steering
    print("\n🎯 Testing Basic Steering:")
    motor_controller.set_steering_angle(0.3)
    time.sleep(1)
    motor_controller.set_steering_angle(0.0)
    
    # Test drive motors
    print("\n🚙 Testing Drive Motors:")
    motor_controller.set_drive_velocity(0.5)
    time.sleep(1)
    motor_controller.set_drive_velocity(0.0)
    
    print("\n3. Advanced Steering Demo...")
    
    # Test Ackermann steering
    print("\n🔄 Ackermann Steering Geometry:")
    motor_controller.set_ackermann_steering(0.4)
    time.sleep(1)
    motor_controller.set_ackermann_steering(0.0)
    
    # Test pivot mode
    print("\n🔀 Pivot Mode (Zero-Radius Turn):")
    from config.constants import PivotDirection
    motor_controller.set_pivot_mode(PivotDirection.LEFT)
    time.sleep(1)
    motor_controller.set_pivot_mode(PivotDirection.NONE)
    
    print("\n4. GPIO Status Check...")
    
    # Test GPIO
    print("\n💡 GPIO Status LEDs:")
    gpio_manager.show_status_led("ok")
    print("  ✓ OK status LED")
    time.sleep(0.5)
    
    gpio_manager.show_status_led("warning")
    print("  ⚠ Warning status LED")
    time.sleep(0.5)
    
    gpio_manager.show_status_led("ok")
    print("  ✓ Back to OK status")
    
    # Show safety status
    print(f"\n🛡️ Safety Status:")
    try:
        emergency_stop = gpio_manager.is_emergency_stop_active()
        brake_engaged = gpio_manager.is_brake_engaged()
        direction = gpio_manager.get_direction_command()
        
        print(f"  Emergency Stop: {'ACTIVE' if emergency_stop else 'INACTIVE'}")
        print(f"  Brake Engaged: {'YES' if brake_engaged else 'NO'}")
        print(f"  Direction: {direction}")
    except Exception as e:
        print(f"  Status: Using mock GPIO (hardware methods not available)")
        print(f"  Emergency Stop: INACTIVE (mock)")
        print(f"  Brake Engaged: NO (mock)")
        print(f"  Direction: STRAIGHT (mock)")
    
    print("\n5. Quick Test Suite...")
    
    # Run a quick test
    print("\n🧪 Running Quick Tests (Steering Motors Only):")
    test_framework = HardwareTestFramework(motor_controller, gpio_manager)
    
    start_time = time.time()
    success = test_framework.run_test_suite([TestType.STEERING_MOTOR])
    duration = time.time() - start_time
    
    print(f"\n📊 Quick Test Results:")
    print(f"  Tests Passed: {'YES' if success else 'NO'}")
    print(f"  Duration: {duration:.2f} seconds")
    print(f"  Total Tests: {len(test_framework.test_results)}")
    
    passed = sum(1 for r in test_framework.test_results if r.passed)
    print(f"  Success Rate: {(passed/len(test_framework.test_results)*100):.1f}%")
    
    # Export quick report
    test_framework.export_test_report("quick_start_report.txt")
    print(f"  📄 Report saved: quick_start_report.txt")
    
    print("\n🎉 Quick Start Demo Complete!")
    print("\nNext Steps:")
    print("  1. Run full demo: python demo_complete_functionality.py")
    print("  2. View test report: quick_start_report.txt")
    print("  3. Check README.md for detailed documentation")
    print("  4. Customize config/constants.py for your vehicle")
    
except ImportError as e:
    print(f"❌ Import Error: {e}")
    print("\nPlease install required dependencies:")
    print("  pip install -r requirements.txt")
    
except Exception as e:
    print(f"❌ Error during demo: {e}")
    import traceback
    traceback.print_exc()
    
finally:
    print(f"\n{'='*50}")
    print("Demo completed. Thank you for trying the Vehicle Control System!")
