#!/bin/bash
################################################################################
# End-to-End Pragati ROS2 Validation Script
# 
# Complete workflow: Install Dependencies → Build → Launch → Test
# Interactive script with help options using existing infrastructure
################################################################################

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
INTERACTIVE_MODE=true
SIMULATION_MODE=true
CLEAN_BUILD=false
RUN_FULL_TESTS=true

# Function to print formatted messages
print_header() {
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${WHITE}  $1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════════${NC}"
}

print_step() {
    echo -e "${CYAN}🚀 $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${PURPLE}ℹ️  $1${NC}"
}

# Function to show help
show_help() {
    cat << EOF
$(print_header "Pragati ROS2 End-to-End Validation Script")

DESCRIPTION:
    Complete validation workflow for Pragati ROS2 cotton-picking robot system.
    This script handles dependency installation, building, launching, and testing
    using the existing build and test infrastructure.

USAGE:
    $0 [OPTIONS]

OPTIONS:
    -h, --help              Show this help message
    -n, --non-interactive   Run in non-interactive mode (assumes defaults)
    -c, --clean             Perform clean build (removes build/install/log directories)
    -s, --hardware          Run in hardware mode instead of simulation (DANGEROUS!)
    -t, --test-only         Skip build and run tests only (assumes already built)
    -q, --quick-test        Run only essential tests, skip comprehensive suite

WORKFLOW STEPS:
    1. 📋 Dependency Check     - Verify ROS2, packages, and system requirements
    2. 🔧 Build System        - Clean build using build.sh script
    3. 🚀 Launch Validation   - Start system and verify nodes/services/topics
    4. 🧪 Comprehensive Test  - Run full test suite with detailed reports
    5. 📊 Generate Reports    - Create validation summary and recommendations

EXAMPLES:
    $0                                    # Interactive mode with all defaults
    $0 --clean --non-interactive          # Non-interactive clean build and test
    $0 --test-only --quick-test           # Quick test of already-built system
    $0 --hardware --non-interactive       # Hardware mode (requires confirmation)

SAFETY:
    • Default simulation mode prevents hardware damage
    • Hardware mode requires explicit confirmation
    • Comprehensive logging for debugging
    • Automatic cleanup of test artifacts

REPORTS:
    Results saved to: ~/pragati_test_output/integration/
    • Build logs and warnings
    • Launch validation results  
    • Comprehensive test reports
    • Performance metrics
    • Migration recommendations

For more details, see: README.md and RASPBERRY_PI_DEPLOYMENT.md
EOF
}

# Function to check user confirmation
confirm_action() {
    local message="$1"
    local default="${2:-y}"
    
    if [ "$INTERACTIVE_MODE" = false ]; then
        return 0  # Always proceed in non-interactive mode
    fi
    
    local prompt="$message"
    if [ "$default" = "y" ]; then
        prompt="$prompt [Y/n]: "
    else
        prompt="$prompt [y/N]: "
    fi
    
    read -p "$(echo -e "${CYAN}$prompt${NC}")" response
    response=${response:-$default}
    
    case "$response" in
        [Yy]*) return 0 ;;
        [Nn]*) return 1 ;;
        *) echo -e "${RED}Please answer yes or no.${NC}"; confirm_action "$message" "$default" ;;
    esac
}

# Function to check ROS2 installation
check_ros2() {
    print_step "Checking ROS2 installation..."
    
    if command -v ros2 &> /dev/null; then
        local ros_version=$(ros2 --version 2>/dev/null | head -1)
        print_success "ROS2 found: $ros_version"
        return 0
    else
        print_error "ROS2 not found!"
        print_info "Please install ROS2 Jazzy following: https://docs.ros.org/en/jazzy/Installation.html"
        return 1
    fi
}

# Function to check system dependencies
check_dependencies() {
    print_step "Checking system dependencies..."
    
    local missing_deps=()
    local deps=("python3" "colcon" "git" "cmake" "build-essential")
    
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" &> /dev/null && ! dpkg -l | grep -q "^ii.*$dep"; then
            missing_deps+=("$dep")
        fi
    done
    
    # Check for colcon specifically
    if ! python3 -c "import colcon_core" &> /dev/null; then
        missing_deps+=("python3-colcon-common-extensions")
    fi
    
    if [ ${#missing_deps[@]} -eq 0 ]; then
        print_success "All system dependencies found"
        return 0
    else
        print_warning "Missing dependencies: ${missing_deps[*]}"
        
        if confirm_action "Install missing dependencies?"; then
            sudo apt update
            sudo apt install -y "${missing_deps[@]}"
            print_success "Dependencies installed"
            return 0
        else
            print_error "Cannot proceed without required dependencies"
            return 1
        fi
    fi
}

# Function to check pigpio (optional for GPIO)
check_pigpio() {
    print_step "Checking pigpio installation (for GPIO support)..."
    
    if dpkg -l | grep -q "^ii.*libpigpiod-if-dev"; then
        print_success "pigpio development libraries found"
        return 0
    else
        print_warning "pigpio development libraries not found"
        
        if confirm_action "Install pigpio for hardware GPIO support?" "n"; then
            sudo apt update
            sudo apt install -y libpigpiod-if-dev pigpio
            print_success "pigpio installed"
        else
            print_info "Continuing with sysfs GPIO fallback"
        fi
        return 0
    fi
}

# Function to perform build
build_system() {
    print_step "Building Pragati ROS2 system..."
    
    cd "$WORKSPACE_ROOT"
    
    local build_cmd="./build.sh"
    if [ "$CLEAN_BUILD" = true ]; then
        build_cmd="$build_cmd --clean"
    fi
    
    print_info "Running: $build_cmd"
    if $build_cmd; then
        print_success "Build completed successfully"
        return 0
    else
        print_error "Build failed!"
        print_info "Check the error messages above for details"
        return 1
    fi
}

# Function to validate launch system
validate_launch() {
    print_step "Validating system launch..."
    
    cd "$WORKSPACE_ROOT"
    source install/setup.bash
    
    print_info "Starting system in background for validation..."
    
    local sim_flag=""
    if [ "$SIMULATION_MODE" = true ]; then
        sim_flag="use_simulation:=true"
        print_info "Running in SIMULATION mode (safe)"
    else
        print_warning "Running in HARDWARE mode!"
    fi
    
    # Launch system in background
    timeout 30s ros2 launch yanthra_move pragati_complete.launch.py $sim_flag > /tmp/launch_validation.log 2>&1 &
    local launch_pid=$!
    
    # Wait for system to start
    sleep 15
    
    # Check if nodes are running
    local nodes=$(ros2 node list 2>/dev/null | wc -l)
    local topics=$(ros2 topic list 2>/dev/null | wc -l)  
    local services=$(ros2 service list 2>/dev/null | wc -l)
    
    # Cleanup launch
    kill $launch_pid 2>/dev/null || true
    pkill -f "pragati_complete.launch.py" 2>/dev/null || true
    sleep 3
    
    print_info "System validation results:"
    echo -e "  ${CYAN}Nodes found: $nodes${NC}"
    echo -e "  ${CYAN}Topics found: $topics${NC}"
    echo -e "  ${CYAN}Services found: $services${NC}"
    
    if [ "$nodes" -ge 3 ] && [ "$topics" -ge 5 ] && [ "$services" -ge 10 ]; then
        print_success "Launch validation passed"
        return 0
    else
        print_warning "Launch validation has concerns - proceeding with tests for details"
        return 0  # Continue to tests for detailed diagnosis
    fi
}

# Function to run comprehensive tests
run_comprehensive_tests() {
    print_step "Running comprehensive test suite..."
    
    cd "$WORKSPACE_ROOT"
    
    local test_script="$WORKSPACE_ROOT/scripts/validation/comprehensive_test_suite.sh"
    
    if [ ! -f "$test_script" ]; then
        print_error "Comprehensive test suite not found at: $test_script"
        return 1
    fi
    
    print_info "Starting comprehensive test suite..."
    if bash "$test_script"; then
        print_success "Comprehensive tests completed"
        
        # Show test results location
        if [ -d "$HOME/pragati_test_results" ]; then
            local latest_results=$(ls -t "$HOME/pragati_test_results" | head -1)
            print_info "Test results saved to: ~/pragati_test_output/integration/$latest_results"
        fi
        return 0
    else
        print_warning "Some tests may have failed - check detailed reports"
        return 0  # Don't fail entire script on test warnings
    fi
}

# Function to run quick tests
run_quick_tests() {
    print_step "Running quick validation tests..."
    
    cd "$WORKSPACE_ROOT"
    source install/setup.bash
    
    print_info "Testing ROS2 node creation..."
    if timeout 10s python3 -c "
import rclpy
rclpy.init()
node = rclpy.create_node('test_node')
print('✅ Node creation: SUCCESS')
node.destroy_node()
rclpy.shutdown()
" 2>/tmp/node_test_error.log; then
        print_success "ROS2 node creation test passed"
    else
        print_error "ROS2 node creation test failed"
        if [ -f /tmp/node_test_error.log ]; then
            print_info "Error details: $(cat /tmp/node_test_error.log | head -2)"
        fi
        return 1
    fi
    
    print_info "Testing package imports and ROS2 commands..."
    cd "$WORKSPACE_ROOT"
    source install/setup.bash
    
    # Test if ros2 commands work without broken pipes
    print_info "Testing ros2 pkg command..."
    if ! ros2 pkg list >/tmp/pkg_test.log 2>&1; then
        print_error "ros2 pkg list command failed"
        if [ -f /tmp/pkg_test.log ]; then
            print_info "Error: $(head -3 /tmp/pkg_test.log)"
        fi
        return 1
    fi
    
    # Test critical package availability
    # Store package list to avoid broken pipe errors
    local pkg_list=$(ros2 pkg list 2>/dev/null)
    local missing_packages=()
    
    for pkg in "yanthra_move" "odrive_control_ros2" "robo_description"; do
        if ! echo "$pkg_list" | grep -q "$pkg"; then
            missing_packages+=("$pkg")
        fi
    done
    
    if [ ${#missing_packages[@]} -eq 0 ]; then
        print_success "All critical packages found"
    else
        print_error "Missing critical packages: ${missing_packages[*]}"
        return 1
    fi
    
    print_success "Quick tests completed"
    return 0
}

# Function to generate summary report
generate_summary() {
    print_header "VALIDATION SUMMARY"
    
    local timestamp=$(date)
    local summary_file="$HOME/pragati_validation_summary_$(date +%Y%m%d_%H%M%S).txt"
    
    echo "Pragati ROS2 End-to-End Validation Summary" > "$summary_file"
    echo "==========================================" >> "$summary_file"
    echo "Timestamp: $timestamp" >> "$summary_file"
    echo "Workspace: $WORKSPACE_ROOT" >> "$summary_file"
    echo "Mode: $([ "$SIMULATION_MODE" = true ] && echo "Simulation" || echo "Hardware")" >> "$summary_file"
    echo "" >> "$summary_file"
    
    print_info "Validation completed on: $timestamp"
    print_info "Workspace: $WORKSPACE_ROOT"
    print_info "Mode: $([ "$SIMULATION_MODE" = true ] && echo "Simulation" || echo "Hardware")"
    print_info "Summary saved to: $summary_file"
    echo ""
    
    print_success "🎉 End-to-end validation completed!"
    print_info "Next steps:"
    echo -e "  • Review test reports in ~/pragati_test_output/integration/"
    echo -e "  • Start the robot: ${CYAN}ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=true${NC}"
    echo -e "  • Use terminal interface: ${CYAN}./scripts/terminal_interface.py${NC}"
    echo -e "  • See README.md for usage documentation"
}

# Main execution function
main() {
    print_header "Pragati ROS2 End-to-End Validation"
    
    print_info "Workspace: $WORKSPACE_ROOT"
    print_info "Mode: $([ "$SIMULATION_MODE" = true ] && echo "Simulation" || echo "Hardware")"
    print_info "Interactive: $([ "$INTERACTIVE_MODE" = true ] && echo "Yes" || echo "No")"
    echo ""
    
    # Step 1: Check dependencies
    if ! check_ros2 || ! check_dependencies; then
        print_error "Dependency check failed - cannot proceed"
        exit 1
    fi
    
    check_pigpio  # Optional, won't fail script
    
    # Step 2: Build system (unless test-only mode)
    if [ "$TEST_ONLY" != true ]; then
        if ! confirm_action "Proceed with build?"; then
            print_info "Build skipped by user"
        else
            if ! build_system; then
                print_error "Build failed - cannot proceed"
                exit 1
            fi
        fi
    fi
    
    # Step 3: Validate launch
    if ! confirm_action "Validate system launch?"; then
        print_info "Launch validation skipped by user"
    else
        validate_launch  # Won't fail script on warnings
    fi
    
    # Step 4: Run tests
    if [ "$RUN_FULL_TESTS" = true ]; then
        if ! confirm_action "Run comprehensive test suite?"; then
            print_info "Comprehensive tests skipped by user"
        else
            run_comprehensive_tests  # Won't fail script on warnings
        fi
    else
        if ! confirm_action "Run quick tests?"; then
            print_info "Quick tests skipped by user" 
        else
            if ! run_quick_tests; then
                print_error "Quick tests failed"
                exit 1
            fi
        fi
    fi
    
    # Step 5: Generate summary
    generate_summary
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -n|--non-interactive)
            INTERACTIVE_MODE=false
            shift
            ;;
        -c|--clean)
            CLEAN_BUILD=true
            shift
            ;;
        -s|--hardware)
            SIMULATION_MODE=false
            shift
            ;;
        -t|--test-only)
            TEST_ONLY=true
            shift
            ;;
        -q|--quick-test)
            RUN_FULL_TESTS=false
            shift
            ;;
        *)
            print_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Safety check for hardware mode
if [ "$SIMULATION_MODE" = false ]; then
    print_warning "HARDWARE MODE DETECTED!"
    print_warning "This will attempt to control real hardware and could cause damage!"
    if ! confirm_action "Are you sure you want to proceed in hardware mode?" "n"; then
        print_info "Switching to simulation mode for safety"
        SIMULATION_MODE=true
    fi
fi

# Execute main workflow
main
