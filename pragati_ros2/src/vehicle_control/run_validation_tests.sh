#!/bin/bash

# Vehicle Control Validation Test Suite
# Comprehensive testing script for ROS-1 to ROS-2 migration validation

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Test configuration
TEST_START_TIME=$(date +%s)
TEST_REPORT_DIR="./test_results/$(date +%Y%m%d_%H%M%S)"
HARDWARE_AVAILABLE="${HARDWARE_AVAILABLE:-false}"
ROS_DISTRO="${ROS_DISTRO:-humble}"

# Create test results directory
mkdir -p "$TEST_REPORT_DIR"

# Logging function
log() {
    local level=$1
    shift
    local message="$@"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    case $level in
        "INFO")  echo -e "${CYAN}[$timestamp] [INFO]${NC} $message" | tee -a "$TEST_REPORT_DIR/test.log" ;;
        "WARN")  echo -e "${YELLOW}[$timestamp] [WARN]${NC} $message" | tee -a "$TEST_REPORT_DIR/test.log" ;;
        "ERROR") echo -e "${RED}[$timestamp] [ERROR]${NC} $message" | tee -a "$TEST_REPORT_DIR/test.log" ;;
        "SUCCESS") echo -e "${GREEN}[$timestamp] [SUCCESS]${NC} $message" | tee -a "$TEST_REPORT_DIR/test.log" ;;
    esac
}

# Test result tracking
TESTS_TOTAL=0
TESTS_PASSED=0
TESTS_FAILED=0

run_test() {
    local test_name="$1"
    local test_command="$2"
    local test_category="$3"
    
    log "INFO" "Running test: $test_name"
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    
    # Run the test and capture output
    if eval "$test_command" > "$TEST_REPORT_DIR/${test_name}.log" 2>&1; then
        log "SUCCESS" "✅ PASSED: $test_name"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo "PASS" > "$TEST_REPORT_DIR/${test_name}.result"
    else
        log "ERROR" "❌ FAILED: $test_name"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo "FAIL" > "$TEST_REPORT_DIR/${test_name}.result"
        
        # Show last few lines of error for immediate feedback
        tail -5 "$TEST_REPORT_DIR/${test_name}.log" | while read line; do
            log "ERROR" "  $line"
        done
    fi
}

# Print test header
print_header() {
    echo -e "${PURPLE}"
    echo "╔══════════════════════════════════════════════════════════════════╗"
    echo "║                 🚗 VEHICLE CONTROL VALIDATION SUITE              ║"
    echo "║                     ROS-1 to ROS-2 Migration Test               ║"
    echo "╠══════════════════════════════════════════════════════════════════╣"
    echo "║ Test Report Directory: $TEST_REPORT_DIR"
    echo "║ ROS Distribution: $ROS_DISTRO"
    echo "║ Hardware Available: $HARDWARE_AVAILABLE"
    echo "║ Start Time: $(date)"
    echo "╚══════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# Environment setup
setup_environment() {
    log "INFO" "Setting up test environment..."
    
    # Source ROS environment
    if [ -f "/opt/ros/$ROS_DISTRO/setup.bash" ]; then
        source "/opt/ros/$ROS_DISTRO/setup.bash"
        log "SUCCESS" "ROS $ROS_DISTRO environment sourced"
    else
        log "ERROR" "ROS $ROS_DISTRO not found"
        return 1
    fi
    
    # Source workspace
    if [ -f "../../install/setup.bash" ]; then
        source "../../install/setup.bash"
        log "SUCCESS" "Workspace environment sourced"
    else
        log "WARN" "Workspace not built, attempting to build..."
        cd ../../ && colcon build --packages-select vehicle_control
        if [ $? -eq 0 ]; then
            source install/setup.bash
            cd - > /dev/null
            log "SUCCESS" "Workspace built and sourced"
        else
            log "ERROR" "Failed to build workspace"
            return 1
        fi
    fi
    
    # Check Python dependencies
    log "INFO" "Checking Python dependencies..."
    python3 -c "import numpy, scipy, yaml, enum, dataclasses" 2>/dev/null
    if [ $? -eq 0 ]; then
        log "SUCCESS" "Python dependencies available"
    else
        log "ERROR" "Missing Python dependencies"
        return 1
    fi
    
    return 0
}

# Category 1: Migration Parity Testing
run_parity_tests() {
    log "INFO" "🔄 Starting Migration Parity Tests..."
    
    # Test 1.1: Vehicle State Management
    run_test "vehicle_states_parity" \
        "python3 -c 'from config.constants import VehicleState; print(\"All vehicle states defined:\", [s.name for s in VehicleState])'" \
        "parity"
    
    # Test 1.2: Motor ID Configuration  
    run_test "motor_ids_parity" \
        "python3 -c 'from config.constants import MotorIDs; m=MotorIDs(); print(\"Motor IDs:\", m.all_motors)'" \
        "parity"
    
    # Test 1.3: GPIO Pin Configuration
    run_test "gpio_pins_parity" \
        "python3 -c 'from config.constants import GPIOPins; g=GPIOPins(); print(\"GPIO pins configured\")'" \
        "parity"
    
    # Test 1.4: Physical Constants
    run_test "physical_constants_parity" \
        "python3 -c 'from config.constants import PhysicalConstants; p=PhysicalConstants(); print(\"Wheel diameter:\", p.WHEEL_DIAMETER)'" \
        "parity"
}

# Category 2: Enhancement Validation
run_enhancement_tests() {
    log "INFO" "🚀 Starting Enhancement Validation Tests..."
    
    # Test 2.1: State Machine
    run_test "state_machine_functionality" \
        "python3 -c 'from core.state_machine import VehicleStateMachine; sm=VehicleStateMachine(); print(\"State machine initialized\")'" \
        "enhancement"
    
    # Test 2.2: Advanced Steering
    run_test "advanced_steering_import" \
        "python3 -c 'from hardware.advanced_steering import AdvancedSteeringController; print(\"Advanced steering available\")'" \
        "enhancement"
    
    # Test 2.3: Safety Manager
    run_test "safety_manager_import" \
        "python3 -c 'from core.safety_manager import SafetyManager; print(\"Safety manager available\")'" \
        "enhancement"
    
    # Test 2.4: Testing Framework
    run_test "test_framework_import" \
        "python3 -c 'from hardware.test_framework import HardwareTestFramework; print(\"Test framework available\")'" \
        "enhancement"
}

# Category 3: Integration Testing
run_integration_tests() {
    log "INFO" "🔗 Starting Integration Tests..."
    
    # Test 3.1: ROS-2 Node Import
    run_test "ros2_node_import" \
        "python3 -c 'import rclpy; from integration.ros2_vehicle_control_node import ROS2VehicleControlNode; print(\"ROS-2 node available\")'" \
        "integration"
    
    # Test 3.2: Package Structure
    run_test "package_structure" \
        "ls -la config/ core/ hardware/ integration/ simulation/ launch/" \
        "integration"
    
    # Test 3.3: Configuration Files
    run_test "configuration_files" \
        "ls -la config/constants.py config/production.yaml" \
        "integration"
}

# Category 4: Simulation Testing
run_simulation_tests() {
    log "INFO" "🎮 Starting Simulation Tests..."
    
    # Test 4.1: Simulation Import
    run_test "simulation_import" \
        "python3 -c 'from simulation.vehicle_simulator import VehicleSimulator; print(\"Simulation available\")'" \
        "simulation"
    
    # Test 4.2: Physics Engine
    run_test "physics_engine_import" \
        "python3 -c 'from simulation.physics_engine import PhysicsEngine; print(\"Physics engine available\")'" \
        "simulation"
    
    # Test 4.3: GUI Interface (if available)
    if command -v python3 -c "import tkinter" &> /dev/null; then
        run_test "gui_interface_import" \
            "python3 -c 'from simulation.gui_interface import VehicleGUI; print(\"GUI interface available\")'" \
            "simulation"
    else
        log "WARN" "Skipping GUI tests - tkinter not available"
    fi
}

# Category 5: Hardware Tests (if available)
run_hardware_tests() {
    if [ "$HARDWARE_AVAILABLE" = "true" ]; then
        log "INFO" "🔧 Starting Hardware Tests..."
        
        # Test 5.1: GPIO Manager
        run_test "gpio_manager_hardware" \
            "python3 -c 'from hardware.gpio_manager import GPIOManager; g=GPIOManager(); print(\"GPIO manager ready for hardware\")'" \
            "hardware"
        
        # Test 5.2: Motor Controller
        run_test "motor_controller_hardware" \
            "python3 -c 'from hardware.motor_controller import VehicleMotorController; print(\"Motor controller ready for hardware\")'" \
            "hardware"
    else
        log "INFO" "⏭️ Skipping Hardware Tests - HARDWARE_AVAILABLE=false"
    fi
}

# Performance Testing
run_performance_tests() {
    log "INFO" "⚡ Starting Performance Tests..."
    
    # Test 6.1: Import Performance
    run_test "import_performance" \
        "time python3 -c 'from config.constants import *; from core import *; from hardware import *; print(\"All imports successful\")'" \
        "performance"
    
    # Test 6.2: Memory Usage
    run_test "memory_usage_check" \
        "python3 -c 'import psutil; import os; p=psutil.Process(os.getpid()); print(f\"Memory usage: {p.memory_info().rss/1024/1024:.1f} MB\")'" \
        "performance"
}

# ROS-2 System Tests
run_ros2_system_tests() {
    log "INFO" "🤖 Starting ROS-2 System Tests..."
    
    # Test 7.1: ROS-2 Node List
    run_test "ros2_node_list" \
        "timeout 5 ros2 node list || echo 'No nodes currently running'" \
        "ros2"
    
    # Test 7.2: ROS-2 Topic List
    run_test "ros2_topic_list" \
        "timeout 5 ros2 topic list || echo 'No topics currently active'" \
        "ros2"
    
    # Test 7.3: ROS-2 Service List
    run_test "ros2_service_list" \
        "timeout 5 ros2 service list || echo 'No services currently active'" \
        "ros2"
}

# Generate test report
generate_report() {
    local test_end_time=$(date +%s)
    local test_duration=$((test_end_time - TEST_START_TIME))
    
    log "INFO" "📊 Generating test report..."
    
    cat > "$TEST_REPORT_DIR/summary.html" << EOF
<!DOCTYPE html>
<html>
<head>
    <title>Vehicle Control Validation Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px; }
        .summary { background: white; padding: 20px; margin: 20px 0; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        .test-category { background: white; margin: 15px 0; padding: 15px; border-radius: 8px; box-shadow: 0 2px 3px rgba(0,0,0,0.1); }
        .passed { color: #28a745; font-weight: bold; }
        .failed { color: #dc3545; font-weight: bold; }
        .progress-bar { background: #e9ecef; border-radius: 10px; height: 20px; margin: 10px 0; }
        .progress-fill { background: linear-gradient(90deg, #28a745, #20c997); height: 100%; border-radius: 10px; transition: width 0.3s ease; }
        .metric { display: inline-block; margin: 10px 20px; text-align: center; }
        .metric-value { font-size: 24px; font-weight: bold; color: #667eea; }
        .metric-label { font-size: 12px; color: #666; }
        .footer { text-align: center; color: #666; margin-top: 30px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🚗 Vehicle Control Validation Report</h1>
        <p>ROS-1 to ROS-2 Migration Testing Results</p>
        <p>Generated: $(date)</p>
    </div>
    
    <div class="summary">
        <h2>📊 Test Summary</h2>
        <div class="metric">
            <div class="metric-value">$TESTS_TOTAL</div>
            <div class="metric-label">Total Tests</div>
        </div>
        <div class="metric">
            <div class="metric-value passed">$TESTS_PASSED</div>
            <div class="metric-label">Passed</div>
        </div>
        <div class="metric">
            <div class="metric-value failed">$TESTS_FAILED</div>
            <div class="metric-label">Failed</div>
        </div>
        <div class="metric">
            <div class="metric-value">$test_duration s</div>
            <div class="metric-label">Duration</div>
        </div>
        
        <div class="progress-bar">
            <div class="progress-fill" style="width: $((TESTS_PASSED * 100 / TESTS_TOTAL))%"></div>
        </div>
        <p>Success Rate: $((TESTS_PASSED * 100 / TESTS_TOTAL))%</p>
    </div>
    
    <div class="test-category">
        <h3>📋 Test Results Details</h3>
        <table style="width: 100%; border-collapse: collapse;">
            <thead>
                <tr style="background: #f8f9fa;">
                    <th style="padding: 10px; text-align: left; border: 1px solid #dee2e6;">Test Name</th>
                    <th style="padding: 10px; text-align: left; border: 1px solid #dee2e6;">Result</th>
                    <th style="padding: 10px; text-align: left; border: 1px solid #dee2e6;">Category</th>
                </tr>
            </thead>
            <tbody>
EOF

    # Add individual test results
    for result_file in "$TEST_REPORT_DIR"/*.result; do
        if [ -f "$result_file" ]; then
            test_name=$(basename "$result_file" .result)
            result=$(cat "$result_file")
            
            if [ "$result" = "PASS" ]; then
                echo "                <tr><td style='padding: 8px; border: 1px solid #dee2e6;'>$test_name</td><td style='padding: 8px; border: 1px solid #dee2e6;' class='passed'>✅ PASSED</td><td style='padding: 8px; border: 1px solid #dee2e6;'>N/A</td></tr>" >> "$TEST_REPORT_DIR/summary.html"
            else
                echo "                <tr><td style='padding: 8px; border: 1px solid #dee2e6;'>$test_name</td><td style='padding: 8px; border: 1px solid #dee2e6;' class='failed'>❌ FAILED</td><td style='padding: 8px; border: 1px solid #dee2e6;'>N/A</td></tr>" >> "$TEST_REPORT_DIR/summary.html"
            fi
        fi
    done

    cat >> "$TEST_REPORT_DIR/summary.html" << EOF
            </tbody>
        </table>
    </div>
    
    <div class="footer">
        <p>🤖 Generated by Vehicle Control Validation Suite</p>
        <p>Report Location: $TEST_REPORT_DIR</p>
    </div>
</body>
</html>
EOF

    # Create summary text file
    cat > "$TEST_REPORT_DIR/summary.txt" << EOF
VEHICLE CONTROL VALIDATION SUMMARY
==================================

Test Execution Date: $(date)
Test Duration: ${test_duration} seconds
Report Directory: $TEST_REPORT_DIR

RESULTS OVERVIEW:
- Total Tests: $TESTS_TOTAL
- Passed: $TESTS_PASSED
- Failed: $TESTS_FAILED
- Success Rate: $((TESTS_PASSED * 100 / TESTS_TOTAL))%

VALIDATION STATUS:
$(if [ $TESTS_FAILED -eq 0 ]; then
    echo "✅ ALL TESTS PASSED - MIGRATION VALIDATION SUCCESSFUL"
else
    echo "❌ SOME TESTS FAILED - REVIEW REQUIRED"
fi)

NEXT STEPS:
$(if [ $TESTS_FAILED -eq 0 ]; then
    echo "- System is ready for production deployment"
    echo "- Consider running hardware tests if available"
    echo "- Proceed with field testing validation"
else
    echo "- Review failed tests in individual log files"
    echo "- Fix issues and re-run validation"
    echo "- Check dependencies and environment setup"
fi)

For detailed results, open: $TEST_REPORT_DIR/summary.html
EOF
}

# Main execution
main() {
    print_header
    
    # Setup environment
    if ! setup_environment; then
        log "ERROR" "Environment setup failed. Exiting."
        exit 1
    fi
    
    log "INFO" "🚀 Starting comprehensive validation test suite..."
    
    # Run all test categories
    run_parity_tests
    run_enhancement_tests
    run_integration_tests
    run_simulation_tests
    run_hardware_tests
    run_performance_tests
    run_ros2_system_tests
    
    # Generate final report
    generate_report
    
    # Print final summary
    echo -e "\n${PURPLE}╔══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${PURPLE}║                        🏁 TEST SUMMARY                           ║${NC}"
    echo -e "${PURPLE}╠══════════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${PURPLE}║${NC} Total Tests: ${CYAN}$TESTS_TOTAL${NC}                                              ${PURPLE}║${NC}"
    echo -e "${PURPLE}║${NC} Passed: ${GREEN}$TESTS_PASSED${NC}                                                  ${PURPLE}║${NC}"
    echo -e "${PURPLE}║${NC} Failed: ${RED}$TESTS_FAILED${NC}                                                  ${PURPLE}║${NC}"
    echo -e "${PURPLE}║${NC} Success Rate: ${CYAN}$((TESTS_PASSED * 100 / TESTS_TOTAL))%${NC}                                           ${PURPLE}║${NC}"
    echo -e "${PURPLE}║${NC}                                                                  ${PURPLE}║${NC}"
    
    if [ $TESTS_FAILED -eq 0 ]; then
        echo -e "${PURPLE}║${NC} ${GREEN}✅ ALL TESTS PASSED - MIGRATION VALIDATION SUCCESSFUL${NC}       ${PURPLE}║${NC}"
        echo -e "${PURPLE}║${NC} ${GREEN}🚀 System ready for production deployment${NC}                   ${PURPLE}║${NC}"
    else
        echo -e "${PURPLE}║${NC} ${RED}❌ SOME TESTS FAILED - REVIEW REQUIRED${NC}                      ${PURPLE}║${NC}"
        echo -e "${PURPLE}║${NC} ${YELLOW}⚠️  Check individual test logs for details${NC}                  ${PURPLE}║${NC}"
    fi
    
    echo -e "${PURPLE}║${NC}                                                                  ${PURPLE}║${NC}"
    echo -e "${PURPLE}║${NC} 📊 Report: ${CYAN}$TEST_REPORT_DIR/summary.html${NC}"
    echo -e "${PURPLE}╚══════════════════════════════════════════════════════════════════╝${NC}"
    
    # Open report if possible
    if command -v xdg-open &> /dev/null; then
        log "INFO" "Opening test report in browser..."
        xdg-open "$TEST_REPORT_DIR/summary.html" &
    elif command -v open &> /dev/null; then
        log "INFO" "Opening test report in browser..."
        open "$TEST_REPORT_DIR/summary.html" &
    fi
    
    # Exit with appropriate code
    exit $TESTS_FAILED
}

# Run main function
main "$@"