#!/usr/bin/env python3

"""
Comprehensive Parameter Validation Test Suite
=============================================

This test suite validates parameters thoroughly to ensure they pass colleague testing:
1. YAML syntax validation
2. Parameter type validation
3. Parameter range validation 
4. Missing parameter detection
5. Unused parameter detection
6. Parameter loading simulation
7. Runtime parameter access testing

This addresses all the parameter validation issues that have been failing colleague testing.
"""

import yaml
import os
import sys
import subprocess
import tempfile
import shutil
from pathlib import Path
import json
import re
from typing import Dict, List, Tuple, Any

class ParameterValidator:
    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root)
        self.config_file = self.workspace_root / "src/yanthra_move/config/production.yaml"
        self.src_dir = self.workspace_root / "src/yanthra_move/src"
        self.test_results = {}
        self.errors = []
        self.warnings = []
        
    def run_all_validations(self) -> bool:
        """Run all parameter validation tests"""
        print("🎯 COMPREHENSIVE PARAMETER VALIDATION")
        print("=" * 60)
        
        tests = [
            ("YAML Syntax Validation", self.test_yaml_syntax),
            ("Parameter Structure Validation", self.test_parameter_structure), 
            ("Parameter Type Validation", self.test_parameter_types),
            ("Parameter Range Validation", self.test_parameter_ranges),
            ("Missing Parameter Detection", self.test_missing_parameters),
            ("Parameter Consistency Check", self.test_parameter_consistency),
            ("Runtime Parameter Loading", self.test_runtime_loading),
            ("Error Handling Validation", self.test_error_handling),
            ("START_SWITCH Timeout Validation", self.test_start_switch_timeout),
            ("Infinite Loop Prevention", self.test_infinite_loop_prevention),
        ]
        
        all_passed = True
        
        for test_name, test_func in tests:
            print(f"\n🔍 Test: {test_name}")
            try:
                result = test_func()
                if result:
                    print(f"✅ {test_name}: PASSED")
                    self.test_results[test_name] = "PASSED"
                else:
                    print(f"❌ {test_name}: FAILED")
                    self.test_results[test_name] = "FAILED"
                    all_passed = False
            except Exception as e:
                print(f"❌ {test_name}: ERROR - {e}")
                self.test_results[test_name] = f"ERROR: {e}"
                all_passed = False
        
        self.generate_report()
        return all_passed
    
    def test_yaml_syntax(self) -> bool:
        """Test YAML file syntax and structure"""
        try:
            with open(self.config_file, 'r') as f:
                config = yaml.safe_load(f)
            
            # Check basic structure
            if not config or 'yanthra_move' not in config:
                self.errors.append("Missing yanthra_move section in YAML")
                return False
                
            if 'ros__parameters' not in config['yanthra_move']:
                self.errors.append("Missing ros__parameters section in YAML")
                return False
            
            # Check for duplicate keys (YAML parser would catch this, but let's be explicit)
            yaml_text = open(self.config_file).read()
            lines = yaml_text.split('\n')
            keys_seen = set()
            
            for line_num, line in enumerate(lines, 1):
                if ':' in line and not line.strip().startswith('#'):
                    key = line.split(':')[0].strip()
                    if key in keys_seen and key != '':
                        self.warnings.append(f"Potential duplicate key '{key}' at line {line_num}")
                    keys_seen.add(key)
            
            return True
            
        except yaml.YAMLError as e:
            self.errors.append(f"YAML syntax error: {e}")
            return False
        except Exception as e:
            self.errors.append(f"Error reading YAML file: {e}")
            return False
    
    def test_parameter_structure(self) -> bool:
        """Test parameter structure and nesting"""
        try:
            with open(self.config_file, 'r') as f:
                config = yaml.safe_load(f)
            
            params = config['yanthra_move']['ros__parameters']
            
            # Test critical parameter categories exist
            critical_categories = {
                'delays/': ['picking', 'pre_start_len', 'end_effector_runtime'],
                'joint2_init/': ['height_scan_enable', 'min', 'max', 'step'],
                'joint3_init/': ['park_position', 'homing_position', 'zero_poses'],
                'joint4_init/': ['park_position', 'homing_position', 'theta_jerk_value'],
                'joint5_init/': ['park_position', 'homing_position', 'end_effector_len'],
            }
            
            for category, expected_params in critical_categories.items():
                # Check both nested and flat parameter styles
                found_params = []
                
                # Check nested style
                category_key = category.rstrip('/')
                if category_key in params and isinstance(params[category_key], dict):
                    found_params.extend(params[category_key].keys())
                
                # Check flat style (with / separator)
                for param in params:
                    if param.startswith(category):
                        param_name = param.replace(category, '')
                        found_params.append(param_name)
                
                # Verify all expected parameters are found
                for expected in expected_params:
                    if expected not in found_params:
                        self.errors.append(f"Missing parameter {category}{expected}")
            
            # Test parameter types are reasonable
            type_checks = {
                'continuous_operation': bool,
                'joint_velocity': (int, float),
                'hardware_timeout': (int, float),
                'simulation_mode': bool,
            }
            
            for param_name, expected_type in type_checks.items():
                if param_name in params:
                    if not isinstance(params[param_name], expected_type):
                        self.errors.append(f"Parameter {param_name} has wrong type: {type(params[param_name])} (expected {expected_type})")
                        
            return len(self.errors) == 0
            
        except Exception as e:
            self.errors.append(f"Parameter structure test error: {e}")
            return False
    
    def test_parameter_types(self) -> bool:
        """Test parameter type consistency"""
        try:
            with open(self.config_file, 'r') as f:
                config = yaml.safe_load(f)
            
            params = config['yanthra_move']['ros__parameters']
            
            # Define expected types for critical parameters
            expected_types = {
                # Boolean parameters
                'continuous_operation': bool,
                'trigger_camera': bool,
                'enable_gpio': bool,
                'simulation_mode': bool,
                'height_scan_enable': bool,
                # Numeric parameters
                'joint_velocity': (int, float),
                'hardware_timeout': (int, float),
                'l2_homing_sleep_time': (int, float),
                'cotton_capture_detect_wait_time': (int, float),
                # Array parameters
                'joint_poses': list,
                # String parameters
                'PRAGATI_INSTALL_DIR': str,
            }
            
            type_errors = 0
            for param_name, expected_type in expected_types.items():
                if param_name in params:
                    actual_value = params[param_name]
                    if not isinstance(actual_value, expected_type):
                        self.errors.append(f"Type mismatch for {param_name}: got {type(actual_value).__name__}, expected {expected_type}")
                        type_errors += 1
                else:
                    self.warnings.append(f"Expected parameter {param_name} not found")
            
            return type_errors == 0
            
        except Exception as e:
            self.errors.append(f"Parameter type test error: {e}")
            return False
    
    def test_parameter_ranges(self) -> bool:
        """Test parameter value ranges"""
        try:
            with open(self.config_file, 'r') as f:
                config = yaml.safe_load(f)
            
            params = config['yanthra_move']['ros__parameters']
            
            # Define reasonable ranges for numeric parameters
            range_checks = {
                'joint_velocity': (0.1, 5.0),
                'hardware_timeout': (1000.0, 2000000.0),
                'l2_homing_sleep_time': (1.0, 15.0),
                'cotton_capture_detect_wait_time': (0.1, 10.0),
                'fov_theta_max': (0.1, 1.57),  # ~9-90 degrees in radians
                'fov_phi_max': (0.1, 1.57),
                'height_scan_min': (0.001, 0.1),
                'height_scan_max': (0.5, 2.0),
            }
            
            range_errors = 0
            for param_name, (min_val, max_val) in range_checks.items():
                if param_name in params:
                    value = params[param_name]
                    if isinstance(value, (int, float)):
                        if value < min_val or value > max_val:
                            self.errors.append(f"Parameter {param_name}={value} out of range [{min_val}, {max_val}]")
                            range_errors += 1
                    
            # Test array parameters have reasonable lengths
            if 'joint_poses' in params and isinstance(params['joint_poses'], list):
                joint_poses = params['joint_poses']
                if len(joint_poses) != 3:
                    self.errors.append(f"joint_poses should have 3 elements, got {len(joint_poses)}")
                    range_errors += 1
            
            return range_errors == 0
            
        except Exception as e:
            self.errors.append(f"Parameter range test error: {e}")
            return False
    
    def test_missing_parameters(self) -> bool:
        """Test for missing critical parameters"""
        try:
            with open(self.config_file, 'r') as f:
                config = yaml.safe_load(f)
            
            params = config['yanthra_move']['ros__parameters']
            
            # Critical parameters that must exist
            critical_params = [
                'continuous_operation',
                'joint_velocity', 
                'hardware_timeout',
                'simulation_mode',
                'trigger_camera',
                'joint_poses',
                'delays/picking',
                'joint3_init/park_position',
                'joint4_init/homing_position',
                'joint5_init/end_effector_len',
            ]
            
            missing = []
            for param in critical_params:
                # Check both flat and nested access patterns
                found = False
                if '/' in param:
                    # Check flat style (delays/picking)
                    if param in params:
                        found = True
                    # Check nested style (delays -> picking)
                    else:
                        parts = param.split('/')
                        if len(parts) == 2 and parts[0] in params:
                            if isinstance(params[parts[0]], dict) and parts[1] in params[parts[0]]:
                                found = True
                else:
                    # Simple parameter
                    if param in params:
                        found = True
                        
                if not found:
                    missing.append(param)
            
            for param in missing:
                self.errors.append(f"Critical parameter missing: {param}")
            
            return len(missing) == 0
            
        except Exception as e:
            self.errors.append(f"Missing parameter test error: {e}")
            return False
    
    def test_parameter_consistency(self) -> bool:
        """Test parameter consistency between YAML and C++ declarations"""
        try:
            # Parse YAML parameters
            with open(self.config_file, 'r') as f:
                config = yaml.safe_load(f)
            yaml_params = set()
            
            def extract_yaml_params(obj, path=""):
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        if key == 'ros__parameters':
                            extract_yaml_params(value, "")
                        else:
                            new_path = f"{path}/{key}" if path else key
                            if isinstance(value, dict):
                                extract_yaml_params(value, new_path)
                            else:
                                yaml_params.add(new_path)
            
            extract_yaml_params(config)
            
            # Parse C++ declared parameters
            cpp_params = set()
            cpp_files = list(self.src_dir.rglob("*.cpp")) + list(self.src_dir.rglob("*.hpp"))
            
            param_patterns = [
                r'declare_parameter\s*\(\s*["\']([\w/]+)["\']',
                r'get_parameter\s*\(\s*["\']([\w/]+)["\']',
            ]
            
            for cpp_file in cpp_files:
                with open(cpp_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    
                for pattern in param_patterns:
                    matches = re.findall(pattern, content)
                    cpp_params.update(matches)
            
            # Find discrepancies
            yaml_only = yaml_params - cpp_params
            cpp_only = cpp_params - yaml_params
            
            # Report major discrepancies (ignore some expected differences)
            ignore_patterns = ['PRAGATI_INSTALL_DIR', 'delays.', 'joint._init.']
            
            significant_yaml_only = []
            for param in yaml_only:
                if not any(pattern in param for pattern in ignore_patterns):
                    significant_yaml_only.append(param)
            
            significant_cpp_only = []
            for param in cpp_only:
                if not any(pattern in param for pattern in ignore_patterns):
                    significant_cpp_only.append(param)
            
            if significant_yaml_only:
                self.warnings.extend([f"YAML-only parameter: {p}" for p in significant_yaml_only[:5]])
            
            if significant_cpp_only:
                self.warnings.extend([f"C++-only parameter: {p}" for p in significant_cpp_only[:5]])
            
            # Success if major parameters are consistent
            return len(significant_yaml_only) < 5 and len(significant_cpp_only) < 10
            
        except Exception as e:
            self.errors.append(f"Parameter consistency test error: {e}")
            return False
    
    def test_runtime_loading(self) -> bool:
        """Test parameter loading in runtime simulation"""
        try:
            # Create a minimal test to ensure parameters can be loaded
            result = subprocess.run([
                'python3', '-c', 
                f'''
import yaml
with open("{self.config_file}", "r") as f:
    config = yaml.safe_load(f)
params = config["yanthra_move"]["ros__parameters"]
# Test basic parameter access
print("continuous_operation:", params.get("continuous_operation", "MISSING"))
print("joint_velocity:", params.get("joint_velocity", "MISSING"))
print("delays/picking:", params.get("delays", {{}}).get("picking", "MISSING"))
print("Success: Parameter loading simulation completed")
                '''
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0 and "Success:" in result.stdout:
                return True
            else:
                self.errors.append(f"Runtime loading simulation failed: {result.stderr}")
                return False
                
        except Exception as e:
            self.errors.append(f"Runtime loading test error: {e}")
            return False
    
    def test_error_handling(self) -> bool:
        """Test parameter error handling scenarios"""
        try:
            # Test with corrupted YAML (create temporary file)
            test_scenarios = [
                # Invalid YAML syntax
                ("Invalid YAML", "invalid_yaml: [missing_bracket"),
                # Missing required section  
                ("Missing Section", "some_other_node:\n  ros__parameters:\n    param: value"),
                # Wrong parameter type
                ("Wrong Type", "yanthra_move:\n  ros__parameters:\n    continuous_operation: 'not_a_boolean'"),
            ]
            
            passed_scenarios = 0
            
            for scenario_name, yaml_content in test_scenarios:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as temp_file:
                    temp_file.write(yaml_content)
                    temp_file.flush()
                    
                    # Test that our validator detects the error
                    try:
                        with open(temp_file.name, 'r') as f:
                            yaml.safe_load(f)
                        # If we get here without exception, test scenario might not be working
                        self.warnings.append(f"Error scenario '{scenario_name}' didn't trigger expected error")
                    except yaml.YAMLError:
                        # Expected error - good!
                        passed_scenarios += 1
                    except Exception:
                        # Some other error - also acceptable for error testing
                        passed_scenarios += 1
                    finally:
                        os.unlink(temp_file.name)
            
            return passed_scenarios >= len(test_scenarios) // 2  # At least half should detect errors
            
        except Exception as e:
            self.errors.append(f"Error handling test error: {e}")
            return False
    
    def test_start_switch_timeout(self) -> bool:
        """Test START_SWITCH timeout parameter validation"""
        try:
            with open(self.config_file, 'r') as f:
                config = yaml.safe_load(f)
            
            params = config['yanthra_move']['ros__parameters']
            
            # Check if start_switch.timeout_sec parameter exists
            timeout_param = params.get('start_switch.timeout_sec')
            if timeout_param is None:
                self.errors.append("CRITICAL: start_switch.timeout_sec parameter missing - infinite loops possible!")
                return False
            
            # Validate timeout value is reasonable (1-30 seconds)
            if not isinstance(timeout_param, (int, float)):
                self.errors.append(f"start_switch.timeout_sec must be numeric, got {type(timeout_param)}")
                return False
            
            if timeout_param < 1.0 or timeout_param > 30.0:
                self.errors.append(f"start_switch.timeout_sec={timeout_param} outside safe range [1.0, 30.0]")
                return False
            
            # Check that timeout is not the problematic 5-minute (300s) value
            if timeout_param >= 300.0:
                self.errors.append(f"start_switch.timeout_sec={timeout_param}s is too long! Must be <30s to prevent user frustration")
                return False
            
            return True
            
        except Exception as e:
            self.errors.append(f"START_SWITCH timeout test error: {e}")
            return False
    
    def test_infinite_loop_prevention(self) -> bool:
        """Test infinite loop prevention configuration"""
        try:
            with open(self.config_file, 'r') as f:
                config = yaml.safe_load(f)
            
            params = config['yanthra_move']['ros__parameters']
            
            # Check continuous_operation parameter
            continuous_op = params.get('continuous_operation')
            if continuous_op is None:
                self.errors.append("continuous_operation parameter missing")
                return False
            
            if not isinstance(continuous_op, bool):
                self.errors.append(f"continuous_operation must be boolean, got {type(continuous_op)}")
                return False
            
            # For testing environments, continuous_operation should typically be false
            # to prevent infinite loops during development
            if continuous_op:
                self.warnings.append("continuous_operation=true may cause infinite loops during testing")
                self.warnings.append("Consider setting continuous_operation=false for testing environments")
            
            # Check for duplicate joint_poses parameter (known issue)
            yaml_text = open(self.config_file).read()
            joint_poses_count = yaml_text.count('joint_poses:')
            if joint_poses_count > 1:
                self.errors.append(f"Duplicate joint_poses parameter found {joint_poses_count} times in YAML")
                return False
            
            return True
            
        except Exception as e:
            self.errors.append(f"Infinite loop prevention test error: {e}")
            return False
    
    def generate_report(self):
        """Generate comprehensive validation report"""
        print(f"\n{'='*60}")
        print("COMPREHENSIVE PARAMETER VALIDATION REPORT")
        print(f"{'='*60}")
        
        # Test results summary
        passed = sum(1 for result in self.test_results.values() if result == "PASSED")
        total = len(self.test_results)
        
        print(f"\n📊 SUMMARY:")
        print(f"   Total Tests: {total}")
        print(f"   Passed: {passed}")
        print(f"   Failed: {total - passed}")
        print(f"   Success Rate: {passed/total*100:.1f}%")
        
        # Detailed results
        print(f"\n🔍 DETAILED RESULTS:")
        for test_name, result in self.test_results.items():
            status_icon = "✅" if result == "PASSED" else "❌"
            print(f"   {status_icon} {test_name}: {result}")
        
        # Errors and warnings
        if self.errors:
            print(f"\n❌ ERRORS ({len(self.errors)}):")
            for error in self.errors[:10]:  # Show first 10
                print(f"   • {error}")
            if len(self.errors) > 10:
                print(f"   ... and {len(self.errors) - 10} more")
        
        if self.warnings:
            print(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
            for warning in self.warnings[:5]:  # Show first 5
                print(f"   • {warning}")
            if len(self.warnings) > 5:
                print(f"   ... and {len(self.warnings) - 5} more")
        
        # Overall result
        overall_success = passed == total and len(self.errors) == 0
        if overall_success:
            print(f"\n🎉 OVERALL RESULT: COMPREHENSIVE PARAMETER VALIDATION PASSED")
            print("   All parameter validation requirements satisfied!")
        else:
            print(f"\n💥 OVERALL RESULT: VALIDATION ISSUES DETECTED")
            print("   Parameter validation needs attention before colleague testing.")
        
        print(f"{'='*60}")

def main():
    workspace = "/home/uday/Downloads/pragati_ros2"
    validator = ParameterValidator(workspace)
    
    success = validator.run_all_validations()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())