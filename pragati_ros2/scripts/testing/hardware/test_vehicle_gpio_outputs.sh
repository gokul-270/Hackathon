#!/bin/bash
# GPIO Output Pins Test for Vehicle Control
# Tests all output pins: LEDs, fan control
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

# GPIO Output Pins (from GPIO_PINS constants)
declare -A OUTPUT_PINS=(
    ["green_led"]="17"       # Status OK LED
    ["yellow_led"]="27"      # Warning LED
    ["red_led"]="22"         # Error LED
    ["fan"]="23"             # Cooling fan control
    ["error_led"]="24"       # Critical error LED
)

print_header() {
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  Vehicle Control - GPIO Output Pins Validation Test${NC}"
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

test_gpio_output_control() {
    local name=$1
    local pin=$2
    
    print_test "Testing ${name} (GPIO ${pin})"
    
    # Export and configure pin as output
    export_gpio_pin ${pin}
    
    if [ ! -d "/sys/class/gpio/gpio${pin}" ]; then
        print_failure "${name}: Cannot access GPIO ${pin}"
        return 1
    fi
    
    # Set direction to output
    echo "out" > /sys/class/gpio/gpio${pin}/direction 2>/dev/null || true
    
    # Test turning ON
    echo "1" > /sys/class/gpio/gpio${pin}/value 2>/dev/null
    local value_on=$(cat /sys/class/gpio/gpio${pin}/value 2>/dev/null || echo "X")
    
    if [ "${value_on}" != "1" ]; then
        print_failure "${name}: Failed to set HIGH"
        return 1
    fi
    
    sleep 0.5
    
    # Test turning OFF
    echo "0" > /sys/class/gpio/gpio${pin}/value 2>/dev/null
    local value_off=$(cat /sys/class/gpio/gpio${pin}/value 2>/dev/null || echo "X")
    
    if [ "${value_off}" != "0" ]; then
        print_failure "${name}: Failed to set LOW"
        return 1
    fi
    
    print_success "${name}: Control verified (HIGH/LOW)"
    return 0
}

test_visual_output() {
    local name=$1
    local pin=$2
    
    print_test "Visual test for ${name} (GPIO ${pin})"
    
    # Export pin
    export_gpio_pin ${pin}
    echo "out" > /sys/class/gpio/gpio${pin}/direction 2>/dev/null || true
    
    echo ""
    print_info "Blinking ${name} 3 times..."
    
    for i in {1..3}; do
        echo "   Blink ${i}/3: ON"
        echo "1" > /sys/class/gpio/gpio${pin}/value
        sleep 0.5
        echo "   Blink ${i}/3: OFF"
        echo "0" > /sys/class/gpio/gpio${pin}/value
        sleep 0.5
    done
    
    echo ""
    read -p "Did you see the ${name} blinking? (y/n): " -n 1 -r
    echo ""
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_success "${name}: Visual confirmation OK"
        return 0
    else
        print_failure "${name}: Visual confirmation FAILED"
        echo "   ⚠️  Check LED/device connection and orientation"
        return 1
    fi
}

test_all_outputs_basic() {
    echo ""
    print_header
    echo "Phase 1: Basic Output Pin Control Tests"
    echo "───────────────────────────────────────────────────────────"
    echo ""
    
    for name in "${!OUTPUT_PINS[@]}"; do
        local pin=${OUTPUT_PINS[$name]}
        test_gpio_output_control "${name}" "${pin}"
        echo ""
    done
}

test_all_outputs_visual() {
    echo ""
    echo "Phase 2: Visual Output Tests"
    echo "───────────────────────────────────────────────────────────"
    echo ""
    print_info "This phase requires visual confirmation of LEDs/devices"
    echo ""
    
    read -p "Press Enter to start visual tests (or Ctrl+C to skip)... "
    echo ""
    
    for name in "${!OUTPUT_PINS[@]}"; do
        local pin=${OUTPUT_PINS[$name]}
        test_visual_output "${name}" "${pin}"
        echo ""
    done
}

test_led_sequence() {
    echo ""
    echo "Phase 3: LED Sequence Test"
    echo "───────────────────────────────────────────────────────────"
    echo ""
    print_test "Running LED sequence (all LEDs in order)"
    
    local led_pins=("${OUTPUT_PINS[green_led]}" "${OUTPUT_PINS[yellow_led]}" 
                    "${OUTPUT_PINS[red_led]}" "${OUTPUT_PINS[error_led]}")
    local led_names=("GREEN" "YELLOW" "RED" "ERROR")
    
    # Export all LED pins
    for pin in "${led_pins[@]}"; do
        export_gpio_pin ${pin}
        echo "out" > /sys/class/gpio/gpio${pin}/direction
        echo "0" > /sys/class/gpio/gpio${pin}/value
    done
    
    echo ""
    print_info "Watch the LED sequence..."
    echo ""
    
    # Run sequence 2 times
    for round in {1..2}; do
        echo "   Round ${round}/2:"
        for i in "${!led_pins[@]}"; do
            local pin=${led_pins[$i]}
            local name=${led_names[$i]}
            echo "     - ${name} LED ON"
            echo "1" > /sys/class/gpio/gpio${pin}/value
            sleep 0.5
            echo "0" > /sys/class/gpio/gpio${pin}/value
            sleep 0.2
        done
    done
    
    echo ""
    read -p "Did you see all LEDs light up in sequence? (y/n): " -n 1 -r
    echo ""
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_success "LED sequence test PASSED"
    else
        print_failure "LED sequence test FAILED"
    fi
    echo ""
}

test_fan_control() {
    echo ""
    echo "Phase 4: Fan Control Test"
    echo "───────────────────────────────────────────────────────────"
    echo ""
    print_test "Testing cooling fan control"
    
    local fan_pin=${OUTPUT_PINS[fan]}
    
    export_gpio_pin ${fan_pin}
    echo "out" > /sys/class/gpio/gpio${fan_pin}/direction
    
    echo ""
    print_info "Starting fan for 3 seconds..."
    echo "1" > /sys/class/gpio/gpio${fan_pin}/value
    sleep 3
    
    print_info "Stopping fan..."
    echo "0" > /sys/class/gpio/gpio${fan_pin}/value
    
    echo ""
    read -p "Did you hear/feel the fan running? (y/n): " -n 1 -r
    echo ""
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_success "Fan control test PASSED"
    else
        print_failure "Fan control test FAILED"
        echo "   ⚠️  Check fan connection and power"
    fi
    echo ""
}

cleanup_gpio() {
    print_info "Cleaning up GPIO pins (all OFF)..."
    for name in "${!OUTPUT_PINS[@]}"; do
        local pin=${OUTPUT_PINS[$name]}
        if [ -d "/sys/class/gpio/gpio${pin}" ]; then
            echo "0" > /sys/class/gpio/gpio${pin}/value 2>/dev/null || true
            unexport_gpio_pin ${pin}
        fi
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
        echo -e "${GREEN}✓ All GPIO output tests PASSED${NC}"
        echo ""
        echo "Next steps:"
        echo "  1. Test full GPIO integration: ./test_vehicle_gpio_full.sh"
        echo "  2. Enable GPIO in production.yaml: enable_gpio: true"
        return 0
    else
        echo -e "${RED}✗ Some GPIO output tests FAILED${NC}"
        echo ""
        echo "Troubleshooting:"
        echo "  1. Check LED polarity (anode/cathode orientation)"
        echo "  2. Verify resistor values (typically 220-330Ω for LEDs)"
        echo "  3. Check power supply voltage (3.3V for GPIO)"
        echo "  4. Test with multimeter for continuity"
        echo "  5. Check for short circuits or damaged components"
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
    
    # Run tests
    test_all_outputs_basic
    
    # Ask for visual tests
    echo ""
    read -p "Run visual confirmation tests? (y/n): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        test_all_outputs_visual
        test_led_sequence
        test_fan_control
    else
        print_info "Skipping visual tests"
    fi
    
    # Cleanup and summary
    cleanup_gpio
    print_summary
}

# Run main function
main "$@"
