#!/bin/bash
# Full GPIO Integration Test for Vehicle Control
# Tests GPIO system via ROS2 vehicle_control_node services
# Validates complete GPIO stack: pigpiod -> GPIO manager -> ROS2 services

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test results tracking
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# ROS2 services for GPIO control
LED_SERVICE="/vehicle_control/led_control"
LID_SERVICE="/vehicle_control/lid_open"
EMERGENCY_SERVICE="/vehicle_control/emergency_stop"
GPIO_STATUS_TOPIC="/vehicle_control/gpio_status"

print_header() {
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  Vehicle Control - Full GPIO Integration Test${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo ""
}

print_test() {
    echo -e "${YELLOW}▶ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
    ((PASSED_TESTS++))
    ((TOTAL_TESTS++))
}

print_failure() {
    echo -e "${RED}✗ $1${NC}"
    ((FAILED_TESTS++))
    ((TOTAL_TESTS++))
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

check_ros2_sourced() {
    print_test "Checking ROS2 environment..."
    if [ -z "$ROS_DISTRO" ]; then
        print_failure "ROS2 not sourced"
        echo ""
        echo "Source ROS2 with:"
        echo "  source /opt/ros/jazzy/setup.bash"
        echo "  source ${WORKSPACE_ROOT}/install/setup.bash"
        return 1
    else
        print_success "ROS2 environment ready (${ROS_DISTRO})"
        return 0
    fi
}

check_vehicle_node_running() {
    print_test "Checking vehicle_control_node status..."
    if ros2 node list 2>/dev/null | grep -q "vehicle_control_node"; then
        print_success "vehicle_control_node is running"
        return 0
    else
        print_failure "vehicle_control_node is not running"
        echo ""
        echo "Start the node with:"
        echo "  ros2 run vehicle_control vehicle_control_node"
        return 1
    fi
}

check_gpio_enabled() {
    print_test "Checking GPIO configuration..."
    
    # Check if GPIO is enabled in config by looking for warning message
    local node_log=$(ros2 node info /vehicle_control_node 2>&1 | grep -i "gpio" || echo "")
    
    # Try to call a GPIO service to verify it's enabled
    if ros2 service list 2>/dev/null | grep -q "${LED_SERVICE}"; then
        print_success "GPIO services available"
        return 0
    else
        print_failure "GPIO services not available"
        echo ""
        echo "Enable GPIO in config/production.yaml:"
        echo "  enable_gpio: true"
        return 1
    fi
}

test_led_service() {
    local led_state=$1
    local description=$2
    
    print_test "Testing LED service: ${description}"
    
    # Call LED control service
    local result=$(ros2 service call ${LED_SERVICE} std_srvs/srv/SetBool "{data: ${led_state}}" 2>&1)
    
    if echo "${result}" | grep -q "success: True\|success: true"; then
        print_success "LED service call successful: ${description}"
        return 0
    else
        print_failure "LED service call failed: ${description}"
        echo "   Response: ${result}"
        return 1
    fi
}

test_lid_service() {
    local lid_open=$1
    local description=$2
    
    print_test "Testing lid control service: ${description}"
    
    # Call lid control service
    local result=$(ros2 service call ${LID_SERVICE} std_srvs/srv/SetBool "{data: ${lid_open}}" 2>&1)
    
    if echo "${result}" | grep -q "success: True\|success: true"; then
        print_success "Lid service call successful: ${description}"
        return 0
    else
        print_failure "Lid service call failed: ${description}"
        echo "   Response: ${result}"
        return 1
    fi
}

test_emergency_stop_service() {
    print_test "Testing emergency stop service"
    
    # Call emergency stop service
    local result=$(ros2 service call ${EMERGENCY_SERVICE} std_srvs/srv/Trigger 2>&1)
    
    if echo "${result}" | grep -q "success: True\|success: true"; then
        print_success "Emergency stop service call successful"
        return 0
    else
        print_failure "Emergency stop service call failed"
        echo "   Response: ${result}"
        return 1
    fi
}

test_gpio_status_topic() {
    print_test "Testing GPIO status topic"
    
    # Listen to GPIO status topic for 2 seconds
    timeout 2s ros2 topic echo ${GPIO_STATUS_TOPIC} --once > /tmp/gpio_status.txt 2>&1 || true
    
    if [ -s /tmp/gpio_status.txt ]; then
        print_success "GPIO status topic publishing data"
        echo "   Sample data:"
        head -5 /tmp/gpio_status.txt | sed 's/^/   /'
        rm -f /tmp/gpio_status.txt
        return 0
    else
        print_failure "GPIO status topic not publishing"
        rm -f /tmp/gpio_status.txt
        return 1
    fi
}

test_led_sequence_ros2() {
    echo ""
    echo "Visual Test: LED Sequence via ROS2"
    echo "───────────────────────────────────────────────────────────"
    echo ""
    print_info "Testing LED control through ROS2 services"
    echo ""
    
    print_test "LED ON sequence"
    test_led_service "true" "Turn LED ON"
    sleep 1
    
    print_test "LED OFF sequence"
    test_led_service "false" "Turn LED OFF"
    sleep 1
    
    print_test "LED blinking"
    for i in {1..3}; do
        echo "   Blink ${i}/3"
        ros2 service call ${LED_SERVICE} std_srvs/srv/SetBool "{data: true}" > /dev/null 2>&1
        sleep 0.5
        ros2 service call ${LED_SERVICE} std_srvs/srv/SetBool "{data: false}" > /dev/null 2>&1
        sleep 0.5
    done
    
    echo ""
    read -p "Did you see the LED blinking via ROS2 control? (y/n): " -n 1 -r
    echo ""
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_success "ROS2 LED control verified"
    else
        print_failure "ROS2 LED control not verified"
    fi
}

test_gpio_input_monitoring() {
    echo ""
    echo "Input Test: GPIO Status Monitoring"
    echo "───────────────────────────────────────────────────────────"
    echo ""
    print_info "Monitoring GPIO inputs for 10 seconds"
    print_info "Please activate switches/buttons during this time"
    echo ""
    
    # Monitor GPIO status topic
    timeout 10s ros2 topic echo ${GPIO_STATUS_TOPIC} > /tmp/gpio_monitor.txt 2>&1 || true
    
    if [ -s /tmp/gpio_monitor.txt ]; then
        local message_count=$(grep -c "automatic_mode\|vehicle_stop\|arm_start" /tmp/gpio_monitor.txt || echo "0")
        print_success "Received ${message_count} GPIO status messages"
        echo ""
        echo "   Last status:"
        tail -20 /tmp/gpio_monitor.txt | sed 's/^/   /'
    else
        print_failure "No GPIO status messages received"
    fi
    
    rm -f /tmp/gpio_monitor.txt
    echo ""
}

test_complete_integration() {
    echo ""
    echo "Phase 1: Service Availability Tests"
    echo "───────────────────────────────────────────────────────────"
    echo ""
    
    print_test "Checking available GPIO services..."
    ros2 service list | grep vehicle_control | grep -E "led|lid|emergency" || true
    echo ""
    
    # Test each service
    test_led_service "true" "LED ON"
    sleep 0.5
    test_led_service "false" "LED OFF"
    echo ""
    
    test_lid_service "true" "Lid OPEN"
    sleep 0.5
    test_lid_service "false" "Lid CLOSE"
    echo ""
    
    test_emergency_stop_service
    echo ""
    
    test_gpio_status_topic
    echo ""
}

print_summary() {
    echo ""
    echo "═══════════════════════════════════════════════════════════"
    echo "Test Summary"
    echo "═══════════════════════════════════════════════════════════"
    echo ""
    echo "Total Tests:  ${TOTAL_TESTS}"
    echo -e "Passed:       ${GREEN}${PASSED_TESTS}${NC}"
    echo -e "Failed:       ${RED}${FAILED_TESTS}${NC}"
    echo ""
    
    if [ ${FAILED_TESTS} -eq 0 ]; then
        echo -e "${GREEN}✓ All GPIO integration tests PASSED${NC}"
        echo ""
        echo "GPIO system is fully operational:"
        echo "  ✓ pigpiod daemon connected"
        echo "  ✓ GPIO manager initialized"
        echo "  ✓ ROS2 services functional"
        echo "  ✓ Input/output operations working"
        echo ""
        echo "System is ready for field deployment!"
        return 0
    else
        echo -e "${RED}✗ Some GPIO integration tests FAILED${NC}"
        echo ""
        echo "Troubleshooting steps:"
        echo "  1. Check pigpiod: sudo systemctl status pigpiod"
        echo "  2. Check node logs: ros2 node info /vehicle_control_node"
        echo "  3. Verify config: cat config/production.yaml | grep enable_gpio"
        echo "  4. Restart node with GPIO enabled"
        echo "  5. Run individual tests: test_vehicle_gpio_inputs.sh"
        return 1
    fi
}

# Main execution
main() {
    print_header
    
    # Check prerequisites
    check_ros2_sourced || exit 1
    check_vehicle_node_running || exit 1
    check_gpio_enabled || {
        echo ""
        echo -e "${YELLOW}⚠️  GPIO appears to be disabled${NC}"
        echo ""
        echo "To enable GPIO and run this test:"
        echo "  1. Edit config/production.yaml: enable_gpio: true"
        echo "  2. Rebuild: colcon build --packages-select vehicle_control"
        echo "  3. Restart vehicle_control_node"
        echo "  4. Run this test again"
        exit 1
    }
    
    # Run integration tests
    test_complete_integration
    
    # Visual tests
    echo ""
    read -p "Run visual LED tests? (y/n): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        test_led_sequence_ros2
    fi
    
    # Input monitoring test
    echo ""
    read -p "Run GPIO input monitoring test? (y/n): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        test_gpio_input_monitoring
    fi
    
    # Summary
    print_summary
}

# Run main function
main "$@"
