#!/bin/bash
# GPIO Input Pins Test for Vehicle Control
# Tests all input pins: switches, buttons, sensors
# Must be run on Raspberry Pi with pigpiod daemon running

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

# GPIO Input Pins (from production.yaml)
declare -A INPUT_PINS=(
    ["direction_switch"]="21"      # Forward/Reverse switch
    ["stop_button"]="4"            # Vehicle stop/brake button
    ["auto_manual_switch"]="26"    # Auto/Manual mode switch
    ["arm_start"]="16"             # Manual arm start button
)

# Expected pull resistor configurations
declare -A PULL_CONFIG=(
    ["direction_switch"]="down"
    ["stop_button"]="down"
    ["auto_manual_switch"]="down"
    ["arm_start"]="down"
)

print_header() {
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  Vehicle Control - GPIO Input Pins Validation Test${NC}"
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

check_pigpiod() {
    print_test "Checking pigpiod daemon status..."
    if systemctl is-active --quiet pigpiod; then
        print_success "pigpiod daemon is running"
        return 0
    else
        print_failure "pigpiod daemon is not running"
        echo ""
        echo "Start pigpiod with: sudo systemctl start pigpiod"
        return 1
    fi
}

check_gpio_availability() {
    print_test "Checking GPIO device availability..."
    if [ -d "/sys/class/gpio" ]; then
        print_success "GPIO sysfs interface available"
        return 0
    else
        print_failure "GPIO sysfs interface not found"
        return 1
    fi
}

export_gpio_pin() {
    local pin=$1
    if [ ! -d "/sys/class/gpio/gpio${pin}" ]; then
        echo "${pin}" > /sys/class/gpio/export 2>/dev/null || true
        sleep 0.1
    fi
}

unexport_gpio_pin() {
    local pin=$1
    if [ -d "/sys/class/gpio/gpio${pin}" ]; then
        echo "${pin}" > /sys/class/gpio/unexport 2>/dev/null || true
    fi
}

test_gpio_input_read() {
    local name=$1
    local pin=$2
    
    print_test "Testing ${name} (GPIO ${pin}) - Input Reading"
    
    # Export and configure pin as input
    export_gpio_pin ${pin}
    
    if [ ! -d "/sys/class/gpio/gpio${pin}" ]; then
        print_failure "${name}: Cannot access GPIO ${pin}"
        return 1
    fi
    
    # Set direction to input
    echo "in" > /sys/class/gpio/gpio${pin}/direction 2>/dev/null || true
    
    # Read current value
    if [ -r "/sys/class/gpio/gpio${pin}/value" ]; then
        local value=$(cat /sys/class/gpio/gpio${pin}/value)
        print_success "${name}: Readable, current value = ${value}"
        echo "   📌 Pin ${pin} is ${value} (0=LOW/GND, 1=HIGH/3.3V)"
        return 0
    else
        print_failure "${name}: Cannot read GPIO ${pin} value"
        return 1
    fi
}

test_interactive_input() {
    local name=$1
    local pin=$2
    
    print_test "Interactive test for ${name} (GPIO ${pin})"
    print_info "Please activate the ${name} now..."
    echo ""
    echo "   Instructions:"
    case "${name}" in
        "direction_switch")
            echo "   - Toggle the direction switch (Forward/Reverse)"
            ;;
        "stop_button")
            echo "   - Press the STOP button"
            ;;
        "auto_manual_switch")
            echo "   - Toggle the Auto/Manual mode switch"
            ;;
        "arm_start")
            echo "   - Press the ARM START button"
            ;;
    esac
    echo ""
    
    # Export pin
    export_gpio_pin ${pin}
    
    # Read initial state
    local initial_state=$(cat /sys/class/gpio/gpio${pin}/value 2>/dev/null || echo "X")
    echo "   Initial state: ${initial_state}"
    
    # Monitor for changes (10 second timeout)
    print_info "Monitoring for state changes (10 seconds)..."
    local changed=0
    local start_time=$(date +%s)
    
    while [ $(($(date +%s) - start_time)) -lt 10 ]; do
        local current_state=$(cat /sys/class/gpio/gpio${pin}/value 2>/dev/null || echo "X")
        
        if [ "${current_state}" != "${initial_state}" ] && [ "${current_state}" != "X" ]; then
            print_success "${name}: State changed from ${initial_state} to ${current_state}"
            changed=1
            break
        fi
        sleep 0.2
    done
    
    if [ ${changed} -eq 0 ]; then
        print_failure "${name}: No state change detected in 10 seconds"
        echo "   ⚠️  Check wiring and switch operation"
        return 1
    fi
    
    return 0
}

test_all_inputs_basic() {
    echo ""
    print_header
    echo "Phase 1: Basic Input Pin Tests"
    echo "───────────────────────────────────────────────────────────"
    echo ""
    
    for name in "${!INPUT_PINS[@]}"; do
        local pin=${INPUT_PINS[$name]}
        test_gpio_input_read "${name}" "${pin}"
        echo ""
    done
}

test_all_inputs_interactive() {
    echo ""
    echo "Phase 2: Interactive Input Tests"
    echo "───────────────────────────────────────────────────────────"
    echo ""
    print_info "This phase requires manual interaction with hardware"
    echo ""
    
    read -p "Press Enter to start interactive tests (or Ctrl+C to skip)... "
    echo ""
    
    for name in "${!INPUT_PINS[@]}"; do
        local pin=${INPUT_PINS[$name]}
        test_interactive_input "${name}" "${pin}"
        echo ""
    done
}

cleanup_gpio() {
    print_info "Cleaning up GPIO pins..."
    for name in "${!INPUT_PINS[@]}"; do
        local pin=${INPUT_PINS[$name]}
        unexport_gpio_pin ${pin}
    done
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
        echo -e "${GREEN}✓ All GPIO input tests PASSED${NC}"
        echo ""
        echo "Next steps:"
        echo "  1. Test GPIO outputs: ./test_vehicle_gpio_outputs.sh"
        echo "  2. Test full GPIO integration: ./test_vehicle_gpio_full.sh"
        return 0
    else
        echo -e "${RED}✗ Some GPIO input tests FAILED${NC}"
        echo ""
        echo "Troubleshooting:"
        echo "  1. Check wiring connections"
        echo "  2. Verify pin assignments in production.yaml"
        echo "  3. Ensure switches/buttons are working"
        echo "  4. Check for short circuits or loose connections"
        return 1
    fi
}

# Main execution
main() {
    # Check if running on Raspberry Pi
    if [ ! -f /proc/device-tree/model ]; then
        echo -e "${RED}Error: This test must be run on a Raspberry Pi${NC}"
        exit 1
    fi
    
    # Check prerequisites
    check_pigpiod || exit 1
    check_gpio_availability || exit 1
    
    # Run tests
    test_all_inputs_basic
    
    # Ask for interactive tests
    echo ""
    read -p "Run interactive tests? (y/n): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        test_all_inputs_interactive
    else
        print_info "Skipping interactive tests"
    fi
    
    # Cleanup and summary
    cleanup_gpio
    print_summary
}

# Run main function
main "$@"
