#!/usr/bin/env python3
"""
ROS2 System Validation Test
Tests ROS2 environment and workspace setup
"""

import subprocess
import time
import os
import sys
from typing import Dict, List, Any, Optional

class ROS2SystemValidator:
    """Validate ROS2 system and workspace setup"""
    
    def __init__(self):
        self.test_results = {}
        
    def run_ros2_command(self, cmd: List[str], timeout: float = 10.0) -> Dict[str, Any]:
        """Run a ROS2 command with proper environment setup"""
        # Set up ROS2 environment
        env = os.environ.copy()
        env['ROS_DISTRO'] = 'jazzy'
        
        # Source ROS2 setup
        bash_cmd = f"source /opt/ros/jazzy/setup.bash && {' '.join(cmd)}"
        
        try:
            result = subprocess.run(
                ["bash", "-c", bash_cmd],
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            return {
                'success': result.returncode == 0,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'stdout': '',
                'stderr': f'Command timed out after {timeout}s',
                'returncode': -1
            }
        except Exception as e:
            return {
                'success': False,
                'stdout': '',
                'stderr': str(e),
                'returncode': -1
            }
    
    def test_ros2_installation(self):
        """Test basic ROS2 installation"""
        print("🔍 Testing ROS2 Installation...")
        
        # Test ros2 command availability
        result = self.run_ros2_command(['ros2', '--help'])
        if result['success']:
            print("  ✅ ROS2 command available")
            self.test_results['ros2_available'] = True
        else:
            print(f"  ❌ ROS2 command failed: {result['stderr']}")
            self.test_results['ros2_available'] = False
            return
        
        # Test basic ros2 commands
        commands_to_test = [
            ['ros2', 'pkg', 'list'],
            ['ros2', 'node', 'list'],  
            ['ros2', 'topic', 'list'],
            ['ros2', 'service', 'list']
        ]
        
        working_commands = 0
        for cmd in commands_to_test:
            result = self.run_ros2_command(cmd, timeout=5)
            if result['success']:
                working_commands += 1
                print(f"  ✅ {' '.join(cmd[1:3])} command working")
            else:
                print(f"  ❌ {' '.join(cmd[1:3])} command failed")
        
        self.test_results['basic_commands'] = working_commands == len(commands_to_test)
        print(f"  📊 Basic commands: {working_commands}/{len(commands_to_test)} working")
    
    def test_workspace_build(self):
        """Test if our workspace can be built"""
        print("\n🔨 Testing Workspace Build...")
        
        workspace_root = "/home/uday/Downloads/pragati_ros2"
        
        # Check if workspace structure exists
        if not os.path.exists(os.path.join(workspace_root, "src")):
            print("  ❌ Workspace src directory not found")
            self.test_results['workspace_buildable'] = False
            return
        
        # Check if our package exists
        package_path = os.path.join(workspace_root, "src", "vehicle_control")
        if not os.path.exists(package_path):
            print("  ❌ vehicle_control package not found")
            self.test_results['workspace_buildable'] = False
            return
        
        print(f"  ✅ Workspace structure found: {workspace_root}")
        print(f"  ✅ Package found: {package_path}")
        
        # Test build
        build_cmd = f"cd {workspace_root} && source /opt/ros/jazzy/setup.bash && colcon build --packages-select vehicle_control"
        
        try:
            print("  🔨 Building vehicle_control package...")
            result = subprocess.run(
                ["bash", "-c", build_cmd],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=workspace_root
            )
            
            if result.returncode == 0:
                print("  ✅ Package built successfully")
                self.test_results['workspace_buildable'] = True
                
                # Check if install directory was created
                install_path = os.path.join(workspace_root, "install", "vehicle_control")
                if os.path.exists(install_path):
                    print(f"  ✅ Install directory created: {install_path}")
                    self.test_results['install_created'] = True
                else:
                    print("  ⚠️  Install directory not found")
                    self.test_results['install_created'] = False
                    
            else:
                print(f"  ❌ Build failed with return code: {result.returncode}")
                print(f"  Error output: {result.stderr[:500]}...")
                self.test_results['workspace_buildable'] = False
                
        except subprocess.TimeoutExpired:
            print("  ❌ Build timed out after 60 seconds")
            self.test_results['workspace_buildable'] = False
        except Exception as e:
            print(f"  ❌ Build error: {e}")
            self.test_results['workspace_buildable'] = False
    
    def test_package_discovery(self):
        """Test if our package can be discovered by ROS2"""
        print("\n🔍 Testing Package Discovery...")
        
        workspace_root = "/home/uday/Downloads/pragati_ros2"
        
        # Source workspace and test package discovery
        setup_cmd = f"cd {workspace_root} && source /opt/ros/jazzy/setup.bash && source install/setup.bash && ros2 pkg list | grep vehicle_control"
        
        result = subprocess.run(
            ["bash", "-c", setup_cmd],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0 and 'vehicle_control' in result.stdout:
            print("  ✅ vehicle_control package discovered by ROS2")
            self.test_results['package_discovered'] = True
            
            # Test package info
            info_cmd = f"cd {workspace_root} && source /opt/ros/jazzy/setup.bash && source install/setup.bash && ros2 pkg xml vehicle_control"
            info_result = subprocess.run(
                ["bash", "-c", info_cmd],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if info_result.returncode == 0:
                print("  ✅ Package XML accessible")
                self.test_results['package_xml_valid'] = True
            else:
                print("  ⚠️  Package XML not accessible")
                self.test_results['package_xml_valid'] = False
                
        else:
            print("  ❌ vehicle_control package not discovered")
            self.test_results['package_discovered'] = False
    
    def test_python_modules(self):
        """Test if our Python modules can be imported"""
        print("\n🐍 Testing Python Module Imports...")
        
        workspace_root = "/home/uday/Downloads/pragati_ros2"
        
        # Test if we can import our modules after workspace setup
        import_test = '''
import sys
import os

# Add workspace to path
sys.path.insert(0, "/home/uday/Downloads/pragati_ros2/src/vehicle_control")

try:
    from utils.circuit_breaker import CircuitBreaker
    from hardware.enhanced_motor_interface import EnhancedMockMotorInterface
    from utils.configuration_manager import ConfigurationManager
    from hardware.robust_motor_controller import RobustMotorController
    print("✅ All modules imported successfully")
    success = True
except ImportError as e:
    print(f"❌ Import failed: {e}")
    success = False
    
print(f"IMPORT_SUCCESS={success}")
'''
        
        try:
            result = subprocess.run(
                [sys.executable, "-c", import_test],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if 'IMPORT_SUCCESS=True' in result.stdout:
                print("  ✅ All enhanced modules can be imported")
                self.test_results['modules_importable'] = True
            else:
                print(f"  ❌ Module import issues: {result.stdout}")
                print(f"  Error: {result.stderr}")
                self.test_results['modules_importable'] = False
                
        except Exception as e:
            print(f"  ❌ Module import test failed: {e}")
            self.test_results['modules_importable'] = False
    
    def test_component_functionality(self):
        """Test basic functionality of our components"""
        print("\n⚙️  Testing Component Functionality...")
        
        functionality_test = '''
import sys
sys.path.insert(0, "/home/uday/Downloads/pragati_ros2/src/vehicle_control")

try:
    from utils.circuit_breaker import CircuitBreaker
    from hardware.enhanced_motor_interface import EnhancedMockMotorInterface  
    from utils.configuration_manager import ConfigurationManager
    
    # Test CircuitBreaker
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1.0)
    @cb
    def test_func():
        return "success"
    
    result = test_func()
    assert result == "success"
    print("✅ Circuit Breaker functional")
    
    # Test Enhanced Motor Interface
    motor = EnhancedMockMotorInterface()
    motor.initialize()
    motor.set_velocity(0, 0.5)
    status = motor.get_status(0)
    print("✅ Enhanced Motor Interface functional")
    
    # Test Configuration Manager
    config = ConfigurationManager()
    default_config = config.get_default_configuration()
    assert len(default_config) > 0
    print("✅ Configuration Manager functional")
    
    print("FUNCTIONALITY_SUCCESS=True")
    
except Exception as e:
    print(f"❌ Functionality test failed: {e}")
    print("FUNCTIONALITY_SUCCESS=False")
'''
        
        try:
            result = subprocess.run(
                [sys.executable, "-c", functionality_test],
                capture_output=True,
                text=True,
                timeout=15
            )
            
            if 'FUNCTIONALITY_SUCCESS=True' in result.stdout:
                print("  ✅ All components functionally working")
                self.test_results['components_functional'] = True
            else:
                print(f"  ❌ Component functionality issues:")
                print(f"  Output: {result.stdout}")
                if result.stderr:
                    print(f"  Error: {result.stderr}")
                self.test_results['components_functional'] = False
                
        except Exception as e:
            print(f"  ❌ Component functionality test failed: {e}")
            self.test_results['components_functional'] = False
    
    def generate_summary(self):
        """Generate test summary and assessment"""
        print("\n📊 ROS2 System Validation Summary")
        print("=" * 60)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results.values() if result)
        
        print(f"Tests Passed: {passed_tests}/{total_tests}")
        
        for test_name, result in self.test_results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"  {test_name}: {status}")
        
        if total_tests > 0:
            success_rate = (passed_tests / total_tests) * 100
            print(f"\nOverall Success Rate: {success_rate:.1f}%")
            
            if success_rate >= 80:
                print("✅ ROS2 System Ready for Vehicle Control Operations")
                return True
            elif success_rate >= 60:
                print("⚠️  ROS2 System Partially Ready - Address Failed Tests")
                return False
            else:
                print("❌ ROS2 System Not Ready - Major Issues Detected")
                return False
        else:
            print("❌ No tests completed")
            return False

def main():
    """Run ROS2 system validation"""
    print("🚀 Starting ROS2 System Validation")
    print("=" * 60)
    
    validator = ROS2SystemValidator()
    
    try:
        # Run all validation tests
        validator.test_ros2_installation()
        validator.test_workspace_build()
        validator.test_package_discovery()
        validator.test_python_modules()
        validator.test_component_functionality()
        
        # Generate summary and return result
        return validator.generate_summary()
        
    except KeyboardInterrupt:
        print("\n⏹️  Testing interrupted by user")
        return False
    except Exception as e:
        print(f"\n❌ Testing failed with error: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)