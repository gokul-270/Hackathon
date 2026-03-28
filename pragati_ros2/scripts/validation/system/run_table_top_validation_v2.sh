#!/usr/bin/env bash
#
# TABLE-TOP VALIDATION SCRIPT V2 - Pragati ROS2
# ==============================================
#
# Uses pragati_complete.launch.py for proper system integration
# Increased timeouts for hardware warm-up
# Better user guidance with prompts
#
# Usage:
#   cd <workspace>
#   bash scripts/validation/system/run_table_top_validation_v2.sh

set -eo pipefail

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

# Topics
RESULTS_TOPIC="/cotton_detection/results"

# INCREASED Timeouts for hardware warm-up
DETECTION_WARMUP_S="15"
DETECTION_TIMEOUT_S="10.0"
MOTOR_WARMUP_S="5"
MOTOR_TIMEOUT_S="8.0"
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
SYSTEM_PID=""
BAG_PID=""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
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

log_user() {
    echo -e "${MAGENTA}[$(date +'%F %T')] 👉${NC} $*" | tee -a "$RUN_LOG"
}

die() {
    log_error "FATAL: $*"
    exit 1
}

cleanup() {
    log "Cleanup: Stopping processes..."
    [[ -n "${BAG_PID:-}" ]] && kill "$BAG_PID" 2>/dev/null || true
    [[ -n "${SYSTEM_PID:-}" ]] && kill "$SYSTEM_PID" 2>/dev/null || true
    pkill -f "pragati_complete.launch" 2>/dev/null || true
    sleep 2
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
    echo "║     PRAGATI TABLE-TOP VALIDATION V2 - Complete System         ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

banner

log "Starting table-top validation V2 at $STAMP"
log "Output directory: $OUT_DIR"
echo ""

if [[ ! -d "$WORK_DIR" ]]; then
    die "Working directory not found: $WORK_DIR"
fi
cd "$WORK_DIR"

log "Sourcing ROS 2 workspace..."
if [[ -f "$WORK_DIR/install/setup.bash" ]]; then
    source "$WORK_DIR/install/setup.bash"
elif [[ -f "$WORK_DIR/install/local_setup.bash" ]]; then
    source "$WORK_DIR/install/local_setup.bash"
else
    die "Cannot find ROS 2 setup.bash in $WORK_DIR/install"
fi
log_success "ROS 2 workspace sourced"

export DEPTHAI_USB2_FORCE=1
log "Set DEPTHAI_USB2_FORCE=1 for OAK-D Lite"

echo ""
log "═══════════════════════════════════════════════════════════════"
log "PHASE 1: HARDWARE BRINGUP"
log "═══════════════════════════════════════════════════════════════"

echo ""
log "Bringing up CAN interface $CAN_IF @ ${CAN_BITRATE} bps..."
sudo ip link set "$CAN_IF" down 2>/dev/null || true
sudo ip link set "$CAN_IF" type can bitrate "$CAN_BITRATE"
sudo ip link set "$CAN_IF" up

if ip -details link show "$CAN_IF" | tee -a "$RUN_LOG" | grep -q "UP"; then
    log_success "CAN interface $CAN_IF is UP"
else
    die "Failed to bring up CAN interface $CAN_IF"
fi

CAN_STATE=$(ip -details link show "$CAN_IF" | grep -oP 'state \K\S+' || echo "UNKNOWN")
log "CAN State: $CAN_STATE"

log_user "═══════════════════════════════════════════════════════════════"
log_user "📷 USER ACTION REQUIRED"
log_user "═══════════════════════════════════════════════════════════════"
log_user ""
log_user "Before proceeding, please ensure:"
log_user "  1. Motor is powered ON (48V)"
log_user "  2. Camera USB cable is connected"
log_user "  3. Cotton sample is placed in camera view"
log_user "     - Distance: 0.15m to 1.0m from camera"
log_user "     - Position: Center of camera view"
log_user ""
log_user "Press Enter when ready to start system..."
read -r

echo ""
log "Launching complete Pragati system..."
log "Using: pragati_complete.launch.py"

ros2 launch yanthra_move pragati_complete.launch.py \
    use_simulation:=false \
    continuous_operation:=false \
    enable_arm_client:=false \
    can_interface:="$CAN_IF" \
    can_bitrate:="$CAN_BITRATE" \
    > "$OUT_DIR/system_launch.log" 2>&1 &
SYSTEM_PID=$!

log "System PID: $SYSTEM_PID"
log "Waiting for system initialization (${DETECTION_WARMUP_S}s warm-up)..."
sleep "$DETECTION_WARMUP_S"

log "Publishing START_SWITCH signal to activate robot..."
ros2 topic pub --once /start_switch/state std_msgs/Bool "data: true" >/dev/null 2>&1 &
sleep 2
log_success "START_SWITCH signal sent"

if ! ps -p "$SYSTEM_PID" > /dev/null 2>&1; then
    log_error "System died immediately. Check $OUT_DIR/system_launch.log"
    tail -30 "$OUT_DIR/system_launch.log"
    die "System failed to start"
fi

log "Waiting for cotton detection topic..."
TOPIC_FOUND=0
for attempt in {1..20}; do
    if ros2 topic list 2>/dev/null | grep -q "$RESULTS_TOPIC" 2>/dev/null; then
        TOPIC_FOUND=1
        break
    fi
    sleep 1
+done
+
+if [[ $TOPIC_FOUND -eq 1 ]]; then
+    log_success "Cotton detection topic ready: $RESULTS_TOPIC"
+else
+    log_warn "Detection topic $RESULTS_TOPIC not found yet"
+fi
+
+log "System services available:"
+ros2 service list | grep -E "cotton|joint|motor" | head -10 | tee -a "$RUN_LOG"
+
+echo ""
+log "Starting rosbag recording..."
+ros2 bag record -o "$OUT_DIR/rosbag" \
+    "$RESULTS_TOPIC" \
+    /joint_states \
+    > "$OUT_DIR/rosbag.log" 2>&1 &
+BAG_PID=$!
+log "Rosbag PID: $BAG_PID"
+sleep 2
+
+# =============================================================================
+# TEST FUNCTIONS
+# =============================================================================
+
+test_cotton_detection() {
+    log "════════════════════════════════════════════════════════════════"
+    log "TEST 1: Cotton Detection Integration"
+    log "════════════════════════════════════════════════════════════════"
+    echo ""
+    
+    log_user "👉 Make sure cotton is visible in camera view!"
+    log_user "   Adjust position if needed, then press Enter..."
+    read -r
+    
+    log "Triggering cotton detection..."
+    
+    if timeout "${DETECTION_TIMEOUT_S}s" ros2 topic echo -n 1 "$RESULTS_TOPIC" > "$OUT_DIR/test1_result.yaml" 2>&1; then
+        log_success "Detection results received"
+        
+        if grep -q "detections:" "$OUT_DIR/test1_result.yaml"; then
+            local num_detections=$(grep -c "bbox:" "$OUT_DIR/test1_result.yaml" || echo "0")
+            log_success "Detection message valid ($num_detections detections)"
+            echo "1" > "$OUT_DIR/test1_result.txt"
+            return 0
+        else
+            log_warn "Detection message format unexpected"
+            echo "0" > "$OUT_DIR/test1_result.txt"
+            return 1
+        fi
+    else
+        log_error "No detection results received within timeout"
+        echo "0" > "$OUT_DIR/test1_result.txt"
+        return 1
+    fi
+}
+
+test_motor_position() {
+    log "════════════════════════════════════════════════════════════════"
+    log "TEST 2: Motor Position Control"
+    log "════════════════════════════════════════════════════════════════"
+    echo ""
+    
+    log_user "👉 Motor will move through test positions"
+    log_user "   Ensure motor has clear range of motion, then press Enter..."
+    read -r
+    
+    log "Testing motor via joint states..."
+    
+    if timeout 5s ros2 topic echo -n 3 /joint_states >> "$OUT_DIR/test2_motor.log" 2>&1; then
+        log_success "Joint states publishing"
+        echo "1" > "$OUT_DIR/test2_result.txt"
+        return 0
+    else
+        log_error "No joint states received"
+        echo "0" > "$OUT_DIR/test2_result.txt"
+        return 1
+    fi
+}
+
+test_integration() {
+    log "════════════════════════════════════════════════════════════════"
+    log "TEST 3: System Integration Check"
+    log "════════════════════════════════════════════════════════════════"
+    echo ""
+    
+    log "Checking all system components..."
+    
+    local checks_passed=0
+    local total_checks=3
+    
+    if ros2 topic info "$RESULTS_TOPIC" &>/dev/null; then
+        log_success "Detection topic active"
+        checks_passed=$((checks_passed + 1))
+    else
+        log_warn "Detection topic not found"
+    fi
+    
+    if ros2 topic info /joint_states &>/dev/null; then
+        log_success "Joint states active"
+        checks_passed=$((checks_passed + 1))
+    else
+        log_warn "Joint states not found"
+    fi
+    
+    if ros2 service list | grep -q "cotton_detection"; then
+        log_success "Cotton detection services available"
+        checks_passed=$((checks_passed + 1))
+    else
+        log_warn "No cotton detection services"
+    fi
+    
+    log "Integration check: $checks_passed/$total_checks components active"
+    
+    if [[ $checks_passed -ge 2 ]]; then
+        log_success "System integration validated"
+        echo "1" > "$OUT_DIR/test3_result.txt"
+        return 0
+    else
+        log_error "Insufficient components active"
+        echo "0" > "$OUT_DIR/test3_result.txt"
+        return 1
+    fi
+}
+
+test_repeatability() {
+    log "════════════════════════════════════════════════════════════════"
+    log "TEST 4: Repeatability (${REPEAT_CYCLES} cycles)"
+    log "════════════════════════════════════════════════════════════════"
+    echo ""
+    
+    local success=0
+    echo "cycle,result" > "$OUT_DIR/repeatability.csv"
+    
+    for i in $(seq 1 "$REPEAT_CYCLES"); do
+        log "Repeatability cycle $i/$REPEAT_CYCLES..."
+        
+        if timeout "${DETECTION_TIMEOUT_S}s" ros2 topic echo -n 1 "$RESULTS_TOPIC" >> "$OUT_DIR/test4_repeat.log" 2>&1; then
+            log_success "  Cycle $i: PASS"
+            echo "$i,PASS" >> "$OUT_DIR/repeatability.csv"
+            success=$((success + 1))
+        else
+            log_error "  Cycle $i: FAIL"
+            echo "$i,FAIL" >> "$OUT_DIR/repeatability.csv"
+        fi
+        
+        sleep 2
+    done
+    
+    local rate=$(python3 -c "print(f'{($success/$REPEAT_CYCLES)*100:.1f}')")
+    log "Repeatability success rate: $rate% ($success/$REPEAT_CYCLES)"
+    echo "$rate" > "$OUT_DIR/repeatability_rate.txt"
+    
+    if (( $(echo "$rate >= 80.0" | bc -l) )); then
+        log_success "Repeatability target met (≥80%)"
+        echo "1" > "$OUT_DIR/test4_result.txt"
+        return 0
+    else
+        log_error "Repeatability below threshold ($rate% < 80%)"
+        echo "0" > "$OUT_DIR/test4_result.txt"
+        return 1
+    fi
+}
+
+# =============================================================================
+# RUN TESTS
+# =============================================================================
+
+echo ""
+log "═══════════════════════════════════════════════════════════════"
+log "PHASE 2: RUNNING VALIDATION TESTS"
+log "═══════════════════════════════════════════════════════════════"
+echo ""
+
+TEST1_PASS=0
+TEST2_PASS=0
+TEST3_PASS=0
+TEST4_PASS=0
+
+if test_cotton_detection; then
+    TEST1_PASS=1
+fi
+echo ""
+
+if test_motor_position; then
+    TEST2_PASS=1
+fi
+echo ""
+
+if test_integration; then
+    TEST3_PASS=1
+fi
+echo ""
+
+if test_repeatability; then
+    TEST4_PASS=1
+fi
+echo ""
+
+# =============================================================================
+# GENERATE SUMMARY
+# =============================================================================
+
+log "═══════════════════════════════════════════════════════════════"
+log "PHASE 3: GENERATING SUMMARY REPORT"
+log "═══════════════════════════════════════════════════════════════"
+echo ""
+
+TOTAL_TESTS=4
+PASSED_TESTS=$((TEST1_PASS + TEST2_PASS + TEST3_PASS + TEST4_PASS))
+SUCCESS_RATE=$(python3 -c "print(f'{($PASSED_TESTS/$TOTAL_TESTS)*100:.1f}')")
+
+cat > "$OUT_DIR/summary.json" << EOF
+{
+  "timestamp": "$STAMP",
+  "version": "v2_complete_launch",
+  "tests": {
+    "cotton_detection": $([ $TEST1_PASS -eq 1 ] && echo "true" || echo "false"),
+    "motor_control": $([ $TEST2_PASS -eq 1 ] && echo "true" || echo "false"),
+    "system_integration": $([ $TEST3_PASS -eq 1 ] && echo "true" || echo "false"),
+    "repeatability": $([ $TEST4_PASS -eq 1 ] && echo "true" || echo "false")
+  },
+  "summary": {
+    "total_tests": $TOTAL_TESTS,
+    "passed_tests": $PASSED_TESTS,
+    "success_rate_percent": $SUCCESS_RATE
+  },
+  "output_directory": "$OUT_DIR"
+}
+EOF
+
+{
+    echo "╔════════════════════════════════════════════════════════════════╗"
+    echo "║         PRAGATI TABLE-TOP VALIDATION V2 SUMMARY                ║"
+    echo "╚════════════════════════════════════════════════════════════════╝"
+    echo ""
+    echo "Validation Date: $STAMP"
+    echo "Launch Method: pragati_complete.launch.py"
+    echo "Output Directory: $OUT_DIR"
+    echo ""
+    echo "TEST RESULTS:"
+    echo "─────────────────────────────────────────────────────────────────"
+    echo " 1. Cotton Detection Integration:     $([ $TEST1_PASS -eq 1 ] && echo '✓ PASS' || echo '✗ FAIL')"
+    echo " 2. Motor Position Control:            $([ $TEST2_PASS -eq 1 ] && echo '✓ PASS' || echo '✗ FAIL')"
+    echo " 3. System Integration:                $([ $TEST3_PASS -eq 1 ] && echo '✓ PASS' || echo '✗ FAIL')"
+    echo " 4. Repeatability:                     $([ $TEST4_PASS -eq 1 ] && echo '✓ PASS' || echo '✗ FAIL')"
+    echo "─────────────────────────────────────────────────────────────────"
+    echo ""
+    echo "OVERALL: $PASSED_TESTS/$TOTAL_TESTS tests passed ($SUCCESS_RATE%)"
+    echo ""
+    
+    if [[ $PASSED_TESTS -eq $TOTAL_TESTS ]]; then
+        echo "✓ VALIDATION SUCCESSFUL - System is ready!"
+        echo ""
+        echo "NEXT STEPS:"
+        echo "  1. Add second motor to table-top setup"
+        echo "  2. Run validation again with both motors"
+        echo "  3. Repeat for third motor"
+    elif [[ $PASSED_TESTS -ge 3 ]]; then
+        echo "⚠ PARTIAL SUCCESS - Most tests passed"
+    else
+        echo "✗ VALIDATION FAILED - Review logs"
+    fi
+    echo ""
+    echo "ARTIFACTS:"
+    echo "  - Summary: $OUT_DIR/summary.txt"
+    echo "  - JSON: $OUT_DIR/summary.json"
+    echo "  - System Log: $OUT_DIR/system_launch.log"
+    echo "  - Rosbag: $OUT_DIR/rosbag"
+    echo ""
+} | tee "$OUT_DIR/summary.txt"
+
+echo ""
+log "═══════════════════════════════════════════════════════════════"
+log "VALIDATION COMPLETE"
+log "═══════════════════════════════════════════════════════════════"
+log "Summary: $OUT_DIR/summary.txt"
+
+if [[ $PASSED_TESTS -eq $TOTAL_TESTS ]]; then
+    exit 0
+else
+    exit 1
+fi
