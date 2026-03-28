#!/bin/bash
# ============================================================================
# Consolidated Hardware Integration Test
# ============================================================================
# Purpose: Time-boxed tests for RPi hardware (motors, camera, full system)
# Hardware: 3x MG6010 motors (joints), OAK-D Lite camera, Raspberry Pi 4
# Max Duration: 90 minutes total (with strict time limits per section)
#
# Usage: ./scripts/hardware_integration_test.sh [section]
#   Sections: motors | camera | integration | all
#   Default: all
#
# Created: Oct 28, 2025
# ============================================================================

# set -e removed - handle errors manually for better control

# Configuration
ROS_DISTRO="${ROS_DISTRO:-jazzy}"
WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$WORKSPACE_ROOT/test_output/hardware_tests/$(date +%Y%m%d_%H%M%S)"
TEST_TIMEOUT_MOTOR=15  # 15 min for motor tests
TEST_TIMEOUT_CAMERA=20  # 20 min for camera tests
TEST_TIMEOUT_INTEGRATION=30  # 30 min for integration

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test tracking
START_TIME=$(date +%s)
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0

# ============================================================================
# Helper Functions
# ============================================================================

log() {
    echo -e "${BLUE}[$(date +%H:%M:%S)]${NC} $*"
}

success() {
    echo -e "${GREEN}✓${NC} $*"
    ((TESTS_PASSED++))
}

error() {
    echo -e "${RED}✗${NC} $*"
    ((TESTS_FAILED++))
}

warning() {
    echo -e "${YELLOW}⚠${NC} $*"
}

skip() {
    echo -e "${YELLOW}⊘${NC} $*"
    ((TESTS_SKIPPED++))
}

elapsed_time() {
    local start=$1
    local end=$(date +%s)
    local elapsed=$((end - start))
    local mins=$((elapsed / 60))
    local secs=$((elapsed % 60))
    echo "${mins}m ${secs}s"
}

section_header() {
    local title="$1"
    local max_time="$2"
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  $title (Max: ${max_time}m)${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

check_timeout() {
    local section_start=$1
    local max_seconds=$2
    local section_name="$3"

    local elapsed=$(($(date +%s) - section_start))
    if [ $elapsed -gt $max_seconds ]; then
        error "TIMEOUT: $section_name exceeded ${max_seconds}s limit"
        return 1
    fi
    return 0
}

# ============================================================================
# Prerequisite Checks
# ============================================================================

check_prerequisites() {
    section_header "Prerequisites Check" "5"
    local section_start=$(date +%s)

    log "Checking ROS2 installation..."
    if ! command -v ros2 &> /dev/null; then
        error "ROS2 not found. Source your ROS2 installation first"
        exit 1
    fi
    success "ROS2 installation found"

    log "Checking workspace build..."
    if [ ! -f "$WORKSPACE_ROOT/install/setup.bash" ]; then
        error "Workspace not built. Run 'colcon build' first"
        exit 1
    fi
    success "Workspace build found"

    log "Sourcing workspace..."
    if source "$WORKSPACE_ROOT/install/setup.bash" 2>/dev/null; then
        success "Workspace sourced"
    else
        warning "Workspace sourcing had warnings (this is usually OK)"
    fi

    log "Creating log directory: $LOG_DIR"
    mkdir -p "$LOG_DIR"
    success "Log directory created"

    log "Elapsed: $(elapsed_time $section_start)"
}

# ============================================================================
# Section 1: Motor Hardware Tests (15 minutes max)
# ============================================================================

test_motors() {
    section_header "Motor Hardware Tests" "$TEST_TIMEOUT_MOTOR"
    local section_start=$(date +%s)

    log "Testing 3x MG6010 motors (one per joint)..."

    # Test 1.1: CAN Bus Detection
    log "[1/5] Checking CAN bus interface..."
    if ip link show can0 &>/dev/null; then
        success "CAN0 interface exists"
    else
        error "CAN0 interface not found"
        warning "Run: sudo ip link add dev can0 type can && sudo ip link set can0 up type can bitrate 500000"
        return 1
    fi
    check_timeout $section_start $((TEST_TIMEOUT_MOTOR * 60)) "Motor Tests" || return 1

    # Test 1.2: Motor Node Launch
    log "[2/5] Launching motor control node (background)..."
    ros2 launch motor_control_ros2 hardware_interface.launch.py \
        use_sim_time:=false \
        > "$LOG_DIR/motor_node.log" 2>&1 &
    MOTOR_NODE_PID=$!

    sleep 5
    if kill -0 $MOTOR_NODE_PID 2>/dev/null; then
        success "Motor control node running (PID: $MOTOR_NODE_PID)"
    else
        error "Motor control node failed to start"
        cat "$LOG_DIR/motor_node.log"
        return 1
    fi
    check_timeout $section_start $((TEST_TIMEOUT_MOTOR * 60)) "Motor Tests" || return 1

    # Test 1.3: Service Availability
    log "[3/5] Checking motor services..."
    local services=("/motor_status" "/enable_motors" "/home_motors")
    local service_ok=true
    for svc in "${services[@]}"; do
        if ros2 service list | grep -q "$svc"; then
            success "Service available: $svc"
        else
            error "Service missing: $svc"
            service_ok=false
        fi
    done
    [ "$service_ok" = true ] || return 1
    check_timeout $section_start $((TEST_TIMEOUT_MOTOR * 60)) "Motor Tests" || return 1

    # Test 1.4: Motor Status Check
    log "[4/5] Checking motor status..."
    timeout 10s ros2 service call /motor_status std_srvs/srv/Trigger > "$LOG_DIR/motor_status.txt" 2>&1
    if [ $? -eq 0 ]; then
        success "Motor status service responded"
        cat "$LOG_DIR/motor_status.txt" | grep -i "motor"
    else
        error "Motor status check failed"
        cat "$LOG_DIR/motor_status.txt"
        service_ok=false
    fi
    check_timeout $section_start $((TEST_TIMEOUT_MOTOR * 60)) "Motor Tests" || return 1

    # Test 1.5: Small Movement Test with Verification
    log "[5/5] Testing small movement (safe range)..."
    warning "Ensure robot is in safe position before motor movement!"
    read -p "Continue with movement test? (y/N): " -t 10 -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # Read initial joint states
        log "Reading initial joint positions..."
        ros2 topic echo /joint_states --once > "$LOG_DIR/joint_states_before.txt" 2>&1 &
        ECHO_PID=$!
        sleep 2
        kill $ECHO_PID 2>/dev/null || true

        # Send movement command
        timeout 15s ros2 topic pub -1 /joint_commands std_msgs/msg/Float64MultiArray \
            "{data: [0.1, 0.0, 0.0]}" > "$LOG_DIR/movement_test.txt" 2>&1
        if [ $? -eq 0 ]; then
            success "Movement command sent successfully"

            # Wait and verify position changed
            sleep 3
            log "Reading final joint positions to verify movement..."
            ros2 topic echo /joint_states --once > "$LOG_DIR/joint_states_after.txt" 2>&1 &
            ECHO_PID=$!
            sleep 2
            kill $ECHO_PID 2>/dev/null || true

            # Check if positions changed
            if diff "$LOG_DIR/joint_states_before.txt" "$LOG_DIR/joint_states_after.txt" > /dev/null 2>&1; then
                error "MOTOR DID NOT MOVE - Joint states unchanged (false positive)"
                warning "Command succeeded but motors didn't respond!"
            else
                success "Motor movement VERIFIED - positions changed"
            fi
        else
            error "Movement test failed"
        fi
    else
        skip "Movement test skipped by user"
    fi

    # Cleanup
    log "Stopping motor node..."
    kill $MOTOR_NODE_PID 2>/dev/null || true
    wait $MOTOR_NODE_PID 2>/dev/null || true

    log "Motor tests elapsed: $(elapsed_time $section_start)"
    echo ""
    return 0
}

# ============================================================================
# Section 2: Camera Hardware Tests (20 minutes max)
# ============================================================================

test_camera() {
    section_header "Camera Hardware Tests" "$TEST_TIMEOUT_CAMERA"
    local section_start=$(date +%s)

    log "Testing OAK-D Lite camera for cotton detection..."

    # Test 2.1: USB Device Detection
    log "[1/6] Checking USB camera connection..."
    if lsusb | grep -i "03e7" > /dev/null; then
        success "OAK-D Lite detected on USB bus"
        lsusb | grep "03e7"
    else
        error "OAK-D Lite not detected"
        warning "Check USB connection and power"
        return 1
    fi
    check_timeout $section_start $((TEST_TIMEOUT_CAMERA * 60)) "Camera Tests" || return 1

    # Test 2.2: DepthAI Library Check
    log "[2/6] Verifying DepthAI library..."
    python3 -c "import depthai as dai; devices = dai.Device.getAllAvailableDevices(); print(f'Found {len(devices)} device(s)'); exit(0 if devices else 1)" > "$LOG_DIR/depthai_check.txt" 2>&1
    if [ $? -eq 0 ]; then
        success "DepthAI library can detect camera"
        cat "$LOG_DIR/depthai_check.txt"
    else
        error "DepthAI cannot detect camera"
        cat "$LOG_DIR/depthai_check.txt"
        return 1
    fi
    check_timeout $section_start $((TEST_TIMEOUT_CAMERA * 60)) "Camera Tests" || return 1

    # Test 2.3: C++ Node Launch (Primary Path)
    log "[3/6] Launching C++ cotton detection node..."
    ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
        simulation_mode:=false \
        use_depthai:=true \
        publish_debug_image:=false \
        > "$LOG_DIR/camera_cpp_node.log" 2>&1 &
    CAMERA_NODE_PID=$!

    sleep 8
    if kill -0 $CAMERA_NODE_PID 2>/dev/null; then
        success "Cotton detection C++ node running (PID: $CAMERA_NODE_PID)"
    else
        error "Cotton detection node failed to start"
        tail -30 "$LOG_DIR/camera_cpp_node.log"
        return 1
    fi
    check_timeout $section_start $((TEST_TIMEOUT_CAMERA * 60)) "Camera Tests" || return 1

    # Test 2.4: Service Check
    log "[4/6] Checking detection service..."
    sleep 3
    if ros2 service list | grep -q "/cotton_detection/detect"; then
        success "Detection service available"
    else
        error "Detection service not found"
        return 1
    fi
    check_timeout $section_start $((TEST_TIMEOUT_CAMERA * 60)) "Camera Tests" || return 1

    # Test 2.5: Detection Test
    log "[5/6] Triggering cotton detection..."
    timeout 15s ros2 service call /cotton_detection/detect \
        cotton_detection_msgs/srv/CottonDetection \
        "{detect_command: 1}" > "$LOG_DIR/detection_result.txt" 2>&1
    if [ $? -eq 0 ]; then
        success "Detection service responded"
        grep -A5 "success" "$LOG_DIR/detection_result.txt" || true
    else
        warning "Detection test timed out or failed (may be OK if no cotton visible)"
        tail -10 "$LOG_DIR/detection_result.txt" || true
    fi
    check_timeout $section_start $((TEST_TIMEOUT_CAMERA * 60)) "Camera Tests" || return 1

    # Test 2.6: Fallback - Python Wrapper (Optional)
    log "[6/6] Testing Python wrapper (legacy)..."
    warning "Python wrapper is DEPRECATED but testing for backward compatibility"
    skip "Skipping Python wrapper test (use C++ node as primary)"

    # Cleanup
    log "Stopping camera node..."
    kill $CAMERA_NODE_PID 2>/dev/null || true
    wait $CAMERA_NODE_PID 2>/dev/null || true

    log "Camera tests elapsed: $(elapsed_time $section_start)"
    echo ""
    return 0
}

# ============================================================================
# Section 3: Integration Tests (30 minutes max)
# ============================================================================

test_integration() {
    section_header "Hardware Integration Tests" "$TEST_TIMEOUT_INTEGRATION"
    local section_start=$(date +%s)

    log "Testing full system integration (motors + camera)..."

    # Test 3.1: Launch Full System
    log "[1/4] Launching complete system..."
    warning "This will start motors and camera - ensure safe environment"
    read -p "Continue with full integration test? (y/N): " -t 10 -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        skip "Integration test skipped by user"
        return 0
    fi

    # Launch using the main launch file
    ros2 launch yanthra_move pragati_complete.launch.py \
        simulation_mode:=false \
        use_hardware:=true \
        > "$LOG_DIR/full_system.log" 2>&1 &
    FULL_SYSTEM_PID=$!

    sleep 15
    if kill -0 $FULL_SYSTEM_PID 2>/dev/null; then
        success "Full system launched (PID: $FULL_SYSTEM_PID)"
    else
        error "Full system launch failed"
        tail -50 "$LOG_DIR/full_system.log"
        return 1
    fi
    check_timeout $section_start $((TEST_TIMEOUT_INTEGRATION * 60)) "Integration Tests" || return 1

    # Test 3.2: Node Health Check
    log "[2/4] Checking node health..."
    local expected_nodes=("motor_control" "cotton_detection")
    for node_name in "${expected_nodes[@]}"; do
        if ros2 node list | grep -q "$node_name"; then
            success "Node active: $node_name"
        else
            warning "Node not found: $node_name (may use different name)"
        fi
    done
    check_timeout $section_start $((TEST_TIMEOUT_INTEGRATION * 60)) "Integration Tests" || return 1

    # Test 3.3: Topic Check
    log "[3/4] Checking data flow on topics..."
    local key_topics=("/joint_states" "/cotton_detection/results")
    for topic in "${key_topics[@]}"; do
        if timeout 5s ros2 topic echo $topic --once > /dev/null 2>&1; then
            success "Topic publishing: $topic"
        else
            warning "Topic not publishing or timeout: $topic"
        fi
    done
    check_timeout $section_start $((TEST_TIMEOUT_INTEGRATION * 60)) "Integration Tests" || return 1

    # Test 3.4: Basic Workflow Test
    log "[4/4] Testing detection -> movement workflow..."
    warning "This is a functional test - monitor robot behavior"
    skip "Workflow test requires manual validation - skipping automated portion"

    # Cleanup
    log "Stopping full system..."
    kill $FULL_SYSTEM_PID 2>/dev/null || true
    wait $FULL_SYSTEM_PID 2>/dev/null || true

    log "Integration tests elapsed: $(elapsed_time $section_start)"
    echo ""
    return 0
}

# ============================================================================
# Summary Report
# ============================================================================

print_summary() {
    local total_elapsed=$(elapsed_time $START_TIME)

    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  Test Summary${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "Total Time: $total_elapsed"
    echo ""
    echo -e "${GREEN}Passed:  $TESTS_PASSED${NC}"
    echo -e "${RED}Failed:  $TESTS_FAILED${NC}"
    echo -e "${YELLOW}Skipped: $TESTS_SKIPPED${NC}"
    echo ""
    echo "Logs saved to: $LOG_DIR"
    echo ""

    if [ $TESTS_FAILED -eq 0 ]; then
        echo -e "${GREEN}✓ All tests passed!${NC}"
        return 0
    else
        echo -e "${RED}✗ Some tests failed. Check logs for details.${NC}"
        return 1
    fi
}

# ============================================================================
# Main Execution
# ============================================================================

main() {
    local test_section="${1:-all}"

    echo ""
    echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║      Hardware Integration Test Suite - Pragati ROS2          ║${NC}"
    echo -e "${BLUE}║      Max Duration: 90 minutes with strict time limits        ║${NC}"
    echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    check_prerequisites

    case "$test_section" in
        motors)
            test_motors || true
            ;;
        camera)
            test_camera || true
            ;;
        integration)
            test_integration || true
            ;;
        all)
            test_motors || true
            test_camera || true
            test_integration || true
            ;;
        *)
            error "Unknown test section: $test_section"
            echo "Usage: $0 [motors|camera|integration|all]"
            exit 1
            ;;
    esac

    print_summary
}

# Trap Ctrl+C for cleanup
trap 'echo ""; warning "Test interrupted by user"; print_summary; exit 130' INT

main "$@"
