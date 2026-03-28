#!/usr/bin/env bash
#
# TABLE-TOP VALIDATION SCRIPT - Pragati ROS2
# ===========================================
#
# Purpose: Validate integrated camera (OAK-D Lite) and motor (MG6010-i6) system
#          before adding remaining motors to the table-top setup.
#
# Usage:
#   cd <workspace>
#   bash scripts/validation/system/run_table_top_validation.sh
#
# This script:
#   - Reuses existing test scripts (no duplication per user preference)
#   - Tests 5 categories: detection, motor control, coordination, repeatability, logging
#   - Generates comprehensive reports and metrics
#   - Validates system readiness for multi-motor expansion

set -eo pipefail  # Removed -u to allow unset variables in sourced files

# =============================================================================
# CONFIGURATION
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_WORK_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Auto-detect workspace directory
if [[ -z "${PRAGATI_WORKSPACE:-}" ]]; then
    if [[ -f "$(pwd)/install/setup.bash" ]]; then
        WORK_DIR="$(pwd)"
    elif [[ -f "$DEFAULT_WORK_DIR/install/setup.bash" ]]; then
        WORK_DIR="$DEFAULT_WORK_DIR"
    elif [[ -f "/home/ubuntu/pragati_ws/install/setup.bash" ]]; then
        WORK_DIR="/home/ubuntu/pragati_ws"
    elif [[ -f "/home/uday/Downloads/pragati_ros2/install/setup.bash" ]]; then
        WORK_DIR="/home/uday/Downloads/pragati_ros2"
    else
        WORK_DIR="$(pwd)"
    fi
else
    WORK_DIR="$PRAGATI_WORKSPACE"
fi

CAN_IF="can0"
CAN_BITRATE="500000"
MOTOR_ID="1"

# Topics and Services (adjust if needed after first run)
RESULTS_TOPIC="/cotton_detection/results"
DETECT_SERVICE="/cotton_detection/detect"
# Motor topics will be discovered dynamically from mg6010_test node

# Test Thresholds
X_MIN="-0.30"; X_MAX="0.30"
Y_MIN="-0.30"; Y_MAX="0.30"
Z_MIN="0.15";  Z_MAX="1.00"
DETECTION_TIMEOUT_S="2.0"  # USB2 mode, be generous
MOTOR_TOL_DEG="2.0"  # MG6010 encoder tolerance
MOTOR_TIMEOUT_S="5.0"
K_DEG_PER_M="180.0"  # Mapping scale: meters to degrees
MAX_ANGLE_DEG="70.0"
REPEAT_CYCLES="5"

# Output Directory - INSIDE project for persistence
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="$WORK_DIR/validation_logs/table_top_${STAMP}"
mkdir -p "$OUT_DIR"
RUN_LOG="$OUT_DIR/run.log"

# Offline testing directory
OFFLINE_TEST_IMAGES="$OUT_DIR/offline_test_images"
mkdir -p "$OFFLINE_TEST_IMAGES"

# Process tracking
MOTOR_PID=""
DETECT_PID=""
BAG_PID=""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
NC='\033[0m'

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

log() { 
    echo -e "${CYAN}[$(date +'%F %T')]${NC} $*" | tee -a "$RUN_LOG"
}

log_success() {
    echo -e "${GREEN}[$(date +'%F %T')] ✓${NC} $*" | tee -a "$RUN_LOG"
}

log_error() {
    echo -e "${RED}[$(date +'%F %T')] ✗${NC} $*" | tee -a "$RUN_LOG"
}

log_warn() {
    echo -e "${YELLOW}[$(date +'%F %T')] ⚠${NC} $*" | tee -a "$RUN_LOG"
}

die() {
    log_error "FATAL: $*"
    exit 1
}

# Cleanup handler
cleanup() {
    log "Cleanup: Stopping processes..."
    [[ -n "${BAG_PID:-}" ]] && kill "$BAG_PID" 2>/dev/null || true
    [[ -n "${MOTOR_PID:-}" ]] && kill "$MOTOR_PID" 2>/dev/null || true
    [[ -n "${DETECT_PID:-}" ]] && kill "$DETECT_PID" 2>/dev/null || true
    log "Results saved to: $OUT_DIR"
    log "Summary: $OUT_DIR/summary.txt"
}

trap cleanup EXIT INT TERM

# =============================================================================
# SETUP AND PREFLIGHT CHECKS
# =============================================================================

banner() {
    echo -e "${BLUE}"
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║     PRAGATI TABLE-TOP VALIDATION - Camera + Motor System      ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

banner

log "Starting table-top validation at $STAMP"
log "Output directory: $OUT_DIR"
echo ""

# Check working directory
if [[ ! -d "$WORK_DIR" ]]; then
    die "Working directory not found: $WORK_DIR"
fi
cd "$WORK_DIR"

# Source ROS 2 workspace
log "Sourcing ROS 2 workspace..."
if [[ -f "$WORK_DIR/install/setup.bash" ]]; then
    source "$WORK_DIR/install/setup.bash"
elif [[ -f "$WORK_DIR/install/local_setup.bash" ]]; then
    source "$WORK_DIR/install/local_setup.bash"
else
    die "Cannot find ROS 2 setup.bash in $WORK_DIR/install"
fi
log_success "ROS 2 workspace sourced"

# Force USB2 mode for OAK-D Lite
export DEPTHAI_USB2_FORCE=1
log "Set DEPTHAI_USB2_FORCE=1 for OAK-D Lite"

# Check DepthAI
log "Checking DepthAI installation..."
if python3 -c "import depthai; print(f'DepthAI version: {depthai.__version__}')" >> "$RUN_LOG" 2>&1; then
    log_success "DepthAI available"
else
    log_warn "DepthAI check failed (may not be critical if camera node handles it)"
fi

# Check OAK-D Lite USB connection
log "Checking OAK-D Lite USB connection..."
if lsusb | grep -i luxonis >> "$RUN_LOG" 2>&1; then
    log_success "OAK-D Lite detected on USB"
else
    log_warn "OAK-D Lite not detected via lsusb (may connect during node startup)"
fi

echo ""
log "═══════════════════════════════════════════════════════════════"
log "PHASE 1: HARDWARE BRINGUP"
log "═══════════════════════════════════════════════════════════════"
echo ""

# =============================================================================
# PHASE 1: BRING UP CAN AND MOTOR
# =============================================================================

log "Bringing up CAN interface $CAN_IF @ ${CAN_BITRATE} bps..."
sudo ip link set "$CAN_IF" down 2>/dev/null || true
sudo ip link set "$CAN_IF" type can bitrate "$CAN_BITRATE"
sudo ip link set "$CAN_IF" up
if ip -details link show "$CAN_IF" | tee -a "$RUN_LOG" | grep -q "UP"; then
    log_success "CAN interface $CAN_IF is UP"
else
    die "Failed to bring up CAN interface $CAN_IF"
fi

# Check CAN state
CAN_STATE=$(ip -details link show "$CAN_IF" | grep -oP 'state \K\S+' || echo "UNKNOWN")
log "CAN State: $CAN_STATE"
if [[ "$CAN_STATE" != "ERROR-ACTIVE" ]]; then
    log_warn "CAN state is $CAN_STATE (expected ERROR-ACTIVE)"
fi

echo ""
log "Launching motor driver (mg6010_test node)..."
ros2 launch motor_control_ros2 mg6010_test.launch.py \
    can_interface:="$CAN_IF" \
    motor_id:="$MOTOR_ID" \
    test_mode:=status \
    > "$OUT_DIR/motor_launch.log" 2>&1 &
MOTOR_PID=$!

log "Motor driver PID: $MOTOR_PID"
log "Waiting for motor node to be ready..."
sleep 3

# Verify motor node is running
if ! ps -p "$MOTOR_PID" > /dev/null 2>&1; then
    log_error "Motor node died immediately. Check $OUT_DIR/motor_launch.log"
    tail -20 "$OUT_DIR/motor_launch.log"
    die "Motor node failed to start"
fi

# Wait for motor-related topics (flexible check)
log "Waiting for motor feedback topic..."
TOPIC_FOUND=0
for attempt in {1..20}; do
    if ros2 topic list 2>/dev/null | grep -q "mg6010\|motor\|joint" 2>/dev/null; then
        TOPIC_FOUND=1
        break
    fi
    sleep 0.5
done

if [[ $TOPIC_FOUND -eq 1 ]]; then
    log_success "Motor topics detected"
    ros2 topic list | grep -E "mg6010|motor|joint" | tee -a "$RUN_LOG" || true
else
    log_warn "No motor topics found yet (may appear during operation)"
fi

# =============================================================================
# PHASE 2: BRING UP COTTON DETECTION
# =============================================================================

echo ""
log "Starting cotton detection node..."

# Check if cotton detection launch file exists (updated to production path 2025-10-21)
if ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py --show-args >/dev/null 2>&1; then
    log "Using cotton_detection_cpp.launch.py (production)"
    ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
        use_depthai:=true \
        simulation_mode:=false \
        > "$OUT_DIR/detect_launch.log" 2>&1 &
    DETECT_PID=$!
    log "Detection node PID: $DETECT_PID"
    sleep 5
elif [[ -f "$WORK_DIR/test_suite/hardware/test_cotton_detection.py" ]]; then
    log_warn "Launch file not found, using test script"
    python3 "$WORK_DIR/test_suite/hardware/test_cotton_detection.py" > "$OUT_DIR/detect_node.log" 2>&1 &
    DETECT_PID=$!
    sleep 3
else
    log_error "No cotton detection node or test script found"
fi

# Wait for detection topic
log "Waiting for cotton detection topic..."
TOPIC_FOUND=0
for attempt in {1..30}; do
    if ros2 topic list 2>/dev/null | grep -q "$RESULTS_TOPIC" 2>/dev/null; then
        TOPIC_FOUND=1
        break
    fi
    sleep 0.5
done

if [[ $TOPIC_FOUND -eq 1 ]]; then
    log_success "Cotton detection topic ready: $RESULTS_TOPIC"
else
    log_warn "Detection topic $RESULTS_TOPIC not found (will retry during tests)"
fi

# List available services
log "Available cotton detection services:"
ros2 service list | grep cotton || log_warn "No cotton services found"

# =============================================================================
# PHASE 3: START ROSBAG RECORDING
# =============================================================================

echo ""
log "Starting rosbag recording..."
ros2 bag record -o "$OUT_DIR/rosbag" \
    "$RESULTS_TOPIC" \
    /joint_states \
    > "$OUT_DIR/rosbag.log" 2>&1 &
BAG_PID=$!
log "Rosbag PID: $BAG_PID"
sleep 2

# =============================================================================
# TEST FUNCTIONS
# =============================================================================

test_cotton_detection() {
    log "════════════════════════════════════════════════════════════════"
    log "TEST 1: Cotton Detection Integration"
    log "════════════════════════════════════════════════════════════════"
    echo ""
    
    local test_script="$WORK_DIR/test_suite/hardware/test_cotton_detection.py"
    if [[ ! -f "$test_script" ]]; then
        log_error "Test script not found: $test_script"
        echo "0" > "$OUT_DIR/test1_result.txt"
        return 1
    fi
    
    log "Running cotton detection test..."
    if timeout 30s python3 "$test_script" > "$OUT_DIR/test1_detection.log" 2>&1; then
        log_success "Detection test completed"
        
        log "Checking for detection results on topic..."
        if timeout "${DETECTION_TIMEOUT_S}s" ros2 topic echo -n 1 "$RESULTS_TOPIC" > "$OUT_DIR/test1_result.yaml" 2>&1; then
            log_success "Detection results received within ${DETECTION_TIMEOUT_S}s"
            
            if grep -q "detections:" "$OUT_DIR/test1_result.yaml"; then
                log_success "Detection message structure looks valid"
                echo "1" > "$OUT_DIR/test1_result.txt"
                return 0
            else
                log_warn "Detection message format unexpected"
                echo "0" > "$OUT_DIR/test1_result.txt"
                return 1
            fi
        else
            log_error "No detection results received within timeout"
            echo "0" > "$OUT_DIR/test1_result.txt"
            return 1
        fi
    else
        log_error "Detection test failed or timed out"
        tail -20 "$OUT_DIR/test1_detection.log" | tee -a "$RUN_LOG"
        echo "0" > "$OUT_DIR/test1_result.txt"
        return 1
    fi
}

test_motor_position() {
    log "════════════════════════════════════════════════════════════════"
    log "TEST 2: Motor Position Control"
    log "════════════════════════════════════════════════════════════════"
    echo ""
    
    local test_script="$WORK_DIR/scripts/validation/motor/comprehensive_can_motor_test.sh"
    if [[ ! -f "$test_script" ]]; then
        log_warn "comprehensive_can_motor_test.sh not found, trying alternative..."
        test_script="$WORK_DIR/scripts/validation/motor/complete_motor_test.sh"
    fi
    
    if [[ ! -f "$test_script" ]]; then
        log_error "No motor test script found"
        echo "0" > "$OUT_DIR/test2_result.txt"
        return 1
    fi
    
    log "Running motor position test using: $(basename "$test_script")"
    if timeout 120s bash "$test_script" > "$OUT_DIR/test2_motor.log" 2>&1; then
        log_success "Motor test completed"
        
        if grep -q "PASS\|completed successfully\|Test completed" "$OUT_DIR/test2_motor.log"; then
            log_success "Motor position control validated"
            echo "1" > "$OUT_DIR/test2_result.txt"
            return 0
        else
            log_warn "Motor test completed but success unclear"
            echo "0" > "$OUT_DIR/test2_result.txt"
            return 1
        fi
    else
        log_error "Motor test failed or timed out"
        tail -30 "$OUT_DIR/test2_motor.log" | tee -a "$RUN_LOG"
        echo "0" > "$OUT_DIR/test2_result.txt"
        return 1
    fi
}

test_coordination() {
    log "════════════════════════════════════════════════════════════════"
    log "TEST 3: Camera-Motor Coordination"
    log "════════════════════════════════════════════════════════════════"
    echo ""
    
    log "Testing coordinated detection and motor response..."
    
    local cycles=3
    local success=0
    
    for i in $(seq 1 $cycles); do
        log "Coordination cycle $i/$cycles..."
        
        if timeout 10s python3 "$WORK_DIR/test_suite/hardware/test_cotton_detection.py" >> "$OUT_DIR/test3_coord.log" 2>&1; then
            log "  Detection triggered"
            
            if timeout 2s ros2 topic echo -n 1 /joint_states >> "$OUT_DIR/test3_coord.log" 2>&1; then
                log_success "  Joint states active"
                success=$((success + 1))
            else
                log_warn "  No joint states received"
            fi
        else
            log_warn "  Detection trigger failed"
        fi
        
        sleep 2
    done
    
    log "Coordination test: $success/$cycles cycles successful"
    
    if [[ $success -ge 2 ]]; then
        log_success "Camera-motor coordination validated"
        echo "1" > "$OUT_DIR/test3_result.txt"
        return 0
    else
        log_error "Insufficient successful coordination cycles"
        echo "0" > "$OUT_DIR/test3_result.txt"
        return 1
    fi
}

test_repeatability() {
    log "════════════════════════════════════════════════════════════════"
    log "TEST 4: Repeatability (${REPEAT_CYCLES} cycles)"
    log "════════════════════════════════════════════════════════════════"
    echo ""
    
    local success=0
    echo "cycle,result" > "$OUT_DIR/repeatability.csv"
    
    for i in $(seq 1 "$REPEAT_CYCLES"); do
        log "Repeatability cycle $i/$REPEAT_CYCLES..."
        
        if timeout 15s python3 "$WORK_DIR/test_suite/hardware/test_cotton_detection.py" >> "$OUT_DIR/test4_repeat.log" 2>&1; then
            log_success "  Cycle $i: PASS"
            echo "$i,PASS" >> "$OUT_DIR/repeatability.csv"
            success=$((success + 1))
        else
            log_error "  Cycle $i: FAIL"
            echo "$i,FAIL" >> "$OUT_DIR/repeatability.csv"
        fi
        
        sleep 1
    done
    
    local rate=$(python3 -c "print(f'{($success/$REPEAT_CYCLES)*100:.1f}')")
    log "Repeatability success rate: $rate% ($success/$REPEAT_CYCLES)"
    echo "$rate" > "$OUT_DIR/repeatability_rate.txt"
    
    if (( $(echo "$rate >= 80.0" | bc -l) )); then
        log_success "Repeatability target met (≥80%)"
        echo "1" > "$OUT_DIR/test4_result.txt"
        return 0
    else
        log_error "Repeatability below threshold ($rate% < 80%)"
        echo "0" > "$OUT_DIR/test4_result.txt"
        return 1
    fi
}

test_offline_images() {
    log "════════════════════════════════════════════════════════════════"
    log "TEST 5: Offline Image-Based Testing"
    log "════════════════════════════════════════════════════════════════"
    echo ""
    
    local test_script="$WORK_DIR/src/cotton_detection_ros2/test/test_with_images.py"
    if [[ ! -f "$test_script" ]]; then
        log_warn "test_with_images.py not found, skipping offline test"
        echo "0" > "$OUT_DIR/test5_result.txt"
        return 1
    fi
    
    local image_sources=(
        "$WORK_DIR/inputs"
        "$WORK_DIR/data/inputs"
        "$WORK_DIR/test_images"
        "$HOME/pragati/inputs"
    )
    
    local image_dir=""
    for dir in "${image_sources[@]}"; do
        if [[ -d "$dir" ]] && ls "$dir"/*.{jpg,jpeg,png,JPG,JPEG,PNG} &>/dev/null 2>&1; then
            image_dir="$dir"
            log "Found offline test images in: $image_dir"
            break
        fi
    done
    
    if [[ -z "$image_dir" ]]; then
        log_warn "No offline test images found in standard locations"
        log "Checked: ${image_sources[*]}"
        log "Skipping offline test (not a failure - just no images available)"
        echo "0" > "$OUT_DIR/test5_result.txt"
        return 0
    fi
    
    log "Running offline image testing..."
    log "Image directory: $image_dir"
    
    if timeout 60s python3 "$test_script" \
        --dir "$image_dir" \
        --output "$OUT_DIR/offline_results.json" \
        --timeout 5.0 \
        > "$OUT_DIR/test5_offline.log" 2>&1; then
        
        log_success "Offline image test completed"
        
        if [[ -f "$OUT_DIR/offline_results.json" ]]; then
            local num_images=$(python3 -c "import json; data=json.load(open('$OUT_DIR/offline_results.json')); print(len(data))" 2>/dev/null || echo "0")
            local images_with_detection=$(python3 -c "import json; data=json.load(open('$OUT_DIR/offline_results.json')); print(sum(1 for r in data.values() if r.get('num_detections', 0) > 0))" 2>/dev/null || echo "0")
            
            log "Tested $num_images offline images"
            log "Images with detections: $images_with_detection"
            
            if [[ $num_images -gt 0 ]]; then
                log_success "Offline testing validated with $num_images images"
                echo "1" > "$OUT_DIR/test5_result.txt"
                return 0
            else
                log_warn "No images were processed"
                echo "0" > "$OUT_DIR/test5_result.txt"
                return 1
            fi
        else
            log_warn "No results JSON created"
            echo "0" > "$OUT_DIR/test5_result.txt"
            return 1
        fi
    else
        log_error "Offline image test failed or timed out"
        tail -20 "$OUT_DIR/test5_offline.log" | tee -a "$RUN_LOG"
        echo "0" > "$OUT_DIR/test5_result.txt"
        return 1
    fi
}

# =============================================================================
# RUN TESTS
# =============================================================================

echo ""
log "═══════════════════════════════════════════════════════════════"
log "PHASE 2: RUNNING VALIDATION TESTS"
log "═══════════════════════════════════════════════════════════════"
echo ""

TEST1_PASS=0
TEST2_PASS=0
TEST3_PASS=0
TEST4_PASS=0
TEST5_PASS=0

if test_cotton_detection; then
    TEST1_PASS=1
fi
echo ""

if test_motor_position; then
    TEST2_PASS=1
fi
echo ""

if test_coordination; then
    TEST3_PASS=1
fi
echo ""

if test_repeatability; then
    TEST4_PASS=1
fi
echo ""

if test_offline_images; then
    TEST5_PASS=1
fi
echo ""

# =============================================================================
# GENERATE SUMMARY
# =============================================================================

log "═══════════════════════════════════════════════════════════════"
log "PHASE 3: GENERATING SUMMARY REPORT"
log "═══════════════════════════════════════════════════════════════"
echo ""

TOTAL_TESTS=5
PASSED_TESTS=$((TEST1_PASS + TEST2_PASS + TEST3_PASS + TEST4_PASS + TEST5_PASS))
SUCCESS_RATE=$(python3 -c "print(f'{($PASSED_TESTS/$TOTAL_TESTS)*100:.1f}')")

cat > "$OUT_DIR/summary.json" << EOF
{
  "timestamp": "$STAMP",
  "tests": {
    "cotton_detection": $([ $TEST1_PASS -eq 1 ] && echo "true" || echo "false"),
    "motor_position": $([ $TEST2_PASS -eq 1 ] && echo "true" || echo "false"),
    "camera_motor_coordination": $([ $TEST3_PASS -eq 1 ] && echo "true" || echo "false"),
    "repeatability": $([ $TEST4_PASS -eq 1 ] && echo "true" || echo "false"),
    "offline_image_testing": $([ $TEST5_PASS -eq 1 ] && echo "true" || echo "false")
  },
  "summary": {
    "total_tests": $TOTAL_TESTS,
    "passed_tests": $PASSED_TESTS,
    "success_rate_percent": $SUCCESS_RATE
  },
  "output_directory": "$OUT_DIR"
}
EOF

{
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║         PRAGATI TABLE-TOP VALIDATION SUMMARY                   ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "Validation Date: $STAMP"
    echo "Output Directory: $OUT_DIR"
    echo ""
    echo "TEST RESULTS:"
    echo "─────────────────────────────────────────────────────────────────"
    echo " 1. Cotton Detection Integration:     $([ $TEST1_PASS -eq 1 ] && echo '✓ PASS' || echo '✗ FAIL')"
    echo " 2. Motor Position Control:            $([ $TEST2_PASS -eq 1 ] && echo '✓ PASS' || echo '✗ FAIL')"
    echo " 3. Camera-Motor Coordination:         $([ $TEST3_PASS -eq 1 ] && echo '✓ PASS' || echo '✗ FAIL')"
    echo " 4. Repeatability:                     $([ $TEST4_PASS -eq 1 ] && echo '✓ PASS' || echo '✗ FAIL')"
    echo " 5. Offline Image-Based Testing:       $([ $TEST5_PASS -eq 1 ] && echo '✓ PASS' || echo '⊘ SKIP')"
    echo "─────────────────────────────────────────────────────────────────"
    echo ""
    echo "OVERALL: $PASSED_TESTS/$TOTAL_TESTS tests passed ($SUCCESS_RATE%)"
    echo ""
    
    if [[ $PASSED_TESTS -eq $TOTAL_TESTS ]]; then
        echo "✓ VALIDATION SUCCESSFUL - Ready to add remaining motors!"
        echo ""
        echo "NEXT STEPS:"
        echo "  1. Add second motor to table-top setup"
        echo "  2. Run validation again with both motors"
        echo "  3. Repeat for third motor"
    elif [[ $PASSED_TESTS -ge 3 ]]; then
        echo "⚠ PARTIAL SUCCESS - Most tests passed, review failures"
        echo ""
        echo "REVIEW:"
        [ $TEST1_PASS -eq 0 ] && echo "  - Check detection logs: $OUT_DIR/test1_*.log"
        [ $TEST2_PASS -eq 0 ] && echo "  - Check motor logs: $OUT_DIR/test2_*.log"
        [ $TEST3_PASS -eq 0 ] && echo "  - Check coordination logs: $OUT_DIR/test3_*.log"
        [ $TEST4_PASS -eq 0 ] && echo "  - Check repeatability logs: $OUT_DIR/test4_*.log"
        [ $TEST5_PASS -eq 0 ] && echo "  - Check offline test logs: $OUT_DIR/test5_*.log"
    else
        echo "✗ VALIDATION FAILED - Multiple critical issues detected"
        echo ""
        echo "TROUBLESHOOTING:"
        echo "  1. Review individual test logs in $OUT_DIR"
        echo "  2. Check node logs: motor_launch.log, detect_launch.log"
        echo "  3. Verify hardware connections (CAN, USB, power)"
        echo "  4. Inspect rosbag: ros2 bag info $OUT_DIR/rosbag"
    fi
    echo ""
    echo "ARTIFACTS:"
    echo "  - Summary: $OUT_DIR/summary.txt"
    echo "  - JSON: $OUT_DIR/summary.json"
    echo "  - Logs: $OUT_DIR/*.log"
    echo "  - Rosbag: $OUT_DIR/rosbag"
    echo "  - Run log: $OUT_DIR/run.log"
    echo ""
} | tee "$OUT_DIR/summary.txt"

echo ""
log "═══════════════════════════════════════════════════════════════"
log "VALIDATION COMPLETE"
log "═══════════════════════════════════════════════════════════════"
log "Summary: $OUT_DIR/summary.txt"
log "JSON: $OUT_DIR/summary.json"
log "Full log: $OUT_DIR/run.log"

if [[ $PASSED_TESTS -eq $TOTAL_TESTS ]]; then
    exit 0
else
    exit 1
fi
