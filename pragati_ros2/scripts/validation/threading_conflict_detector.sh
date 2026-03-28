#!/bin/bash

################################################################################
# Threading Conflict Detection Script
# 
# This script detects potential ROS2 executor threading conflicts that can
# cause nodes to fail when launched via ROS2 launch system.
################################################################################

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

print_status() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$WORKSPACE_ROOT"

print_status $PURPLE "🔍 THREADING CONFLICT DETECTION"
print_status $PURPLE "================================"
echo ""

# Test counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0
WARNING_TESTS=0

log_test_result() {
    local test_name="$1"
    local result="$2"
    local details="$3"
    
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    
    case "$result" in
        "PASS")
            PASSED_TESTS=$((PASSED_TESTS + 1))
            print_status $GREEN "✅ $test_name"
            ;;
        "FAIL")
            FAILED_TESTS=$((FAILED_TESTS + 1))
            print_status $RED "❌ $test_name"
            ;;
        "WARN")
            WARNING_TESTS=$((WARNING_TESTS + 1))
            print_status $YELLOW "⚠️  $test_name"
            ;;
    esac
    
    if [ -n "$details" ]; then
        echo "   Details: $details"
    fi
}

# Phase 1: Static Analysis - Scan for executor patterns
print_status $BLUE "📊 Phase 1: Static Executor Pattern Analysis"
echo ""

# Find all main functions with potential executor conflicts
conflicting_patterns=()
safe_patterns=()

# Check C++ main functions
for cpp_file in $(find src -name "*.cpp" | grep -v archive | grep -v build); do
    if grep -q "int main" "$cpp_file"; then
        echo "Checking: $cpp_file"
        
        # Check for problematic patterns
        if grep -q "add_node\|MultiThreadedExecutor.*add_node\|SingleThreadedExecutor.*add_node" "$cpp_file"; then
            if grep -q "rclcpp::spin" "$cpp_file"; then
                # Has both patterns - potential conflict
                conflicting_patterns+=("$cpp_file")
                print_status $RED "  ❌ CONFLICT: Has both executor creation and rclcpp::spin"
            else
                # Only has executor management - check if used in launch files
                print_status $YELLOW "  ⚠️  Has executor management - checking launch usage..."
                
                # Extract executable name from CMakeLists.txt or filename
                executable_name=$(basename "$cpp_file" .cpp)
                if grep -r "$executable_name" src/*/launch/ 2>/dev/null | grep -q "Node.*executable.*$executable_name"; then
                    conflicting_patterns+=("$cpp_file")
                    print_status $RED "  ❌ CONFLICT: Executor management + ROS2 launch = CONFLICT"
                else
                    safe_patterns+=("$cpp_file")
                    print_status $GREEN "  ✅ SAFE: Executor management but not launched via ROS2 launch"
                fi
            fi
        elif grep -q "rclcpp::spin" "$cpp_file"; then
            # Standard pattern
            safe_patterns+=("$cpp_file")
            print_status $GREEN "  ✅ SAFE: Standard rclcpp::spin pattern"
        else
            print_status $YELLOW "  ⚠️  No standard ROS2 patterns detected"
        fi
    fi
done

echo ""

# Phase 2: Launch Integration Testing
print_status $BLUE "🚀 Phase 2: Launch Integration Testing"
echo ""

source install/setup.bash 2>/dev/null || {
    log_test_result "Environment Setup" "FAIL" "Could not source install/setup.bash"
    exit 1
}

# Test main system launch
print_status $BLUE "Testing main system launch..."
timeout 15s ros2 launch yanthra_move pragati_complete.launch.py continuous_operation:=false > /tmp/threading_test.log 2>&1
launch_result=$?

if [ $launch_result -eq 124 ]; then
    # Timeout - check if it started successfully before timing out
    if grep -q "YanthraMoveSystem.*initialized successfully" /tmp/threading_test.log; then
        log_test_result "Main System Launch" "PASS" "System started successfully (timeout expected)"
    elif grep -q "executor conflict\|add_node.*twice" /tmp/threading_test.log; then
        log_test_result "Main System Launch" "FAIL" "Executor conflict detected"
    else
        log_test_result "Main System Launch" "WARN" "Timeout without clear success/failure"
    fi
elif [ $launch_result -eq 0 ]; then
    log_test_result "Main System Launch" "PASS" "System launched and exited cleanly"
else
    # Check for specific error patterns
    if grep -q "executor conflict\|add_node.*twice" /tmp/threading_test.log; then
        log_test_result "Main System Launch" "FAIL" "Executor conflict detected"
    else
        log_test_result "Main System Launch" "FAIL" "Launch failed with exit code $launch_result"
    fi
fi

# Test individual component launches
component_launches=(
    "odrive_control_ros2:control_loop.launch.py"
    "cotton_detection_ros2:cotton_detection.launch.xml"
)

for component in "${component_launches[@]}"; do
    IFS=':' read -r package launch_file <<< "$component"
    
    if [ -f "src/${package}/launch/${launch_file}" ] || [ -f "install/${package}/share/${package}/launch/${launch_file}" ]; then
        print_status $BLUE "Testing $package $launch_file..."
        timeout 10s ros2 launch "$package" "$launch_file" > "/tmp/threading_test_${package}.log" 2>&1
        component_result=$?
        
        if [ $component_result -eq 124 ]; then
            # Check for successful startup
            if grep -q "initialized\|started\|ready" "/tmp/threading_test_${package}.log" && ! grep -q "error\|fail\|conflict" "/tmp/threading_test_${package}.log"; then
                log_test_result "$package Launch" "PASS" "Component started successfully"
            else
                log_test_result "$package Launch" "WARN" "Component status unclear"
            fi
        elif [ $component_result -eq 0 ]; then
            log_test_result "$package Launch" "PASS" "Component launched and exited cleanly"
        else
            if grep -q "executor conflict\|add_node.*twice" "/tmp/threading_test_${package}.log"; then
                log_test_result "$package Launch" "FAIL" "Executor conflict in $package"
            else
                log_test_result "$package Launch" "WARN" "Launch failed - may not be threading related"
            fi
        fi
    else
        log_test_result "$package Launch" "WARN" "Launch file not found"
    fi
done

# Phase 3: Summary and Recommendations
print_status $BLUE "📈 Phase 3: Analysis Summary"
echo ""

echo "Static Analysis Results:"
echo "  Conflicting patterns found: ${#conflicting_patterns[@]}"
echo "  Safe patterns found: ${#safe_patterns[@]}"

if [ ${#conflicting_patterns[@]} -gt 0 ]; then
    echo ""
    print_status $RED "❌ FILES WITH POTENTIAL EXECUTOR CONFLICTS:"
    for file in "${conflicting_patterns[@]}"; do
        echo "  - $file"
    done
fi

echo ""
echo "=== THREADING CONFLICT DETECTION SUMMARY ==="
echo ""
echo "Total Tests: $TOTAL_TESTS"
echo "Passed: $PASSED_TESTS"
echo "Failed: $FAILED_TESTS"
echo "Warnings: $WARNING_TESTS"

if [ $FAILED_TESTS -eq 0 ]; then
    if [ $WARNING_TESTS -eq 0 ]; then
        print_status $GREEN "✅ No threading conflicts detected!"
        echo ""
        print_status $GREEN "System is clear of executor conflicts and ready for production."
    else
        print_status $YELLOW "⚠️  No critical threading conflicts, but some warnings need review."
        echo ""
        print_status $YELLOW "Review warnings but system should be operational."
    fi
else
    print_status $RED "❌ Threading conflicts detected!"
    echo ""
    print_status $RED "CRITICAL: Fix executor conflicts before production deployment."
    echo ""
    echo "Recommended fixes:"
    echo "1. Remove internal executor management from nodes launched via ROS2 launch"
    echo "2. Use standard rclcpp::spin(node) pattern"
    echo "3. Test fixes using this script"
fi

echo ""
echo "Log files saved in /tmp/threading_test*.log for detailed analysis."

exit $FAILED_TESTS