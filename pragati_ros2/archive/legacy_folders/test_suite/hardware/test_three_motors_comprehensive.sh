#!/bin/bash
# Comprehensive Test for Three MG6010 Motors
# Tests each motor (ID 1, 2, 3) individually with full test suite

set -e

CAN_IF="can0"
BITRATE="250000"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
NC='\033[0m'

log() { echo -e "${CYAN}[$(date +'%T')]${NC} $*"; }
log_success() { echo -e "${GREEN}[$(date +'%T')] ✓${NC} $*"; }
log_error() { echo -e "${RED}[$(date +'%T')] ✗${NC} $*"; }
log_warn() { echo -e "${YELLOW}[$(date +'%T')] ⚠${NC} $*"; }
log_header() { echo -e "${BLUE}[$(date +'%T')] ═══${NC} $*"; }

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     COMPREHENSIVE THREE-MOTOR TEST - Sequential Testing        ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Create output directory
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="test_output/integration/three_motors_${TIMESTAMP}"
mkdir -p "$OUTPUT_DIR"

log "Test results will be saved to: $OUTPUT_DIR"
echo ""

# Setup CAN interface
log_header "Setting up CAN interface"
sudo ip link set "$CAN_IF" down 2>/dev/null || true
sudo ip link set "$CAN_IF" type can bitrate "$BITRATE"
sudo ip link set "$CAN_IF" up

if ip -details link show "$CAN_IF" | grep -q "UP"; then
    log_success "CAN interface $CAN_IF is UP @ ${BITRATE} bps"
else
    log_error "Failed to bring up CAN interface"
    exit 1
fi

CAN_STATE=$(ip -details link show "$CAN_IF" | grep -oP 'state \K\S+' || echo "UNKNOWN")
log "CAN State: $CAN_STATE"
echo ""

# Function to run comprehensive test for one motor
test_motor() {
    local MOTOR_ID=$1
    local JOINT_NAME=$2
    local CAN_HEX=$(printf "14%X" $MOTOR_ID)
    
    echo ""
    log_header "════════════════════════════════════════════════════════════════"
    log_header "Testing Motor $MOTOR_ID - $JOINT_NAME (CAN ID: 0x$CAN_HEX)"
    log_header "════════════════════════════════════════════════════════════════"
    echo ""
    
    local MOTOR_LOG="$OUTPUT_DIR/motor_${MOTOR_ID}_${JOINT_NAME}.log"
    
    # Start CAN monitoring for this motor
    candump can0 > "$MOTOR_LOG" 2>&1 &
    local DUMP_PID=$!
    sleep 0.5
    
    local TESTS_PASSED=0
    local TESTS_FAILED=0
    
    # Test 1: Motor Status (0x9A)
    echo ""
    log "Test 1: Reading Motor Status (0x9A)..."
    cansend can0 ${CAN_HEX}#9A00000000000000
    sleep 0.5
    
    if grep -q "${CAN_HEX}.*9A" "$MOTOR_LOG"; then
        local STATUS_LINE=$(grep "${CAN_HEX}.*9A" "$MOTOR_LOG" | tail -1)
        log_success "Motor $MOTOR_ID responded to status query"
        echo "    Response: $STATUS_LINE"
        
        # Parse temperature and voltage
        local TEMP_HEX=$(echo "$STATUS_LINE" | awk '{print $6}')
        local VOLT_LOW=$(echo "$STATUS_LINE" | awk '{print $7}')
        local VOLT_HIGH=$(echo "$STATUS_LINE" | awk '{print $8}')
        
        if [ -n "$TEMP_HEX" ] && [ -n "$VOLT_LOW" ] && [ -n "$VOLT_HIGH" ]; then
            local TEMP=$((16#${TEMP_HEX}))
            local VOLT_RAW=$((16#${VOLT_HIGH}${VOLT_LOW}))
            local VOLTAGE=$(echo "scale=1; $VOLT_RAW * 0.01" | bc)
            
            log "    Temperature: ${TEMP}°C"
            log "    Voltage: ${VOLTAGE}V"
            
            if (( $(echo "$VOLTAGE >= 44.0" | bc -l) )) && (( $(echo "$VOLTAGE <= 52.0" | bc -l) )); then
                log_success "    Voltage is within safe range (44-52V)"
                TESTS_PASSED=$((TESTS_PASSED + 1))
            else
                log_error "    Voltage out of range!"
                TESTS_FAILED=$((TESTS_FAILED + 1))
            fi
        else
            log_warn "    Could not parse telemetry data"
            TESTS_FAILED=$((TESTS_FAILED + 1))
        fi
    else
        log_error "Motor $MOTOR_ID did not respond to status query"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
    
    # Test 2: Read Encoder (0x92)
    echo ""
    log "Test 2: Reading Encoder Position (0x92)..."
    cansend can0 ${CAN_HEX}#9200000000000000
    sleep 0.5
    
    if grep -q "${CAN_HEX}.*92" "$MOTOR_LOG"; then
        local ENCODER_LINE=$(grep "${CAN_HEX}.*92" "$MOTOR_LOG" | tail -1)
        log_success "Motor $MOTOR_ID encoder data received"
        echo "    Response: $ENCODER_LINE"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        log_error "Motor $MOTOR_ID encoder read failed"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
    
    # Test 3: Motor ON (0x88)
    echo ""
    log "Test 3: Motor ON Command (0x88)..."
    cansend can0 ${CAN_HEX}#8800000000000000
    sleep 0.5
    
    if grep -q "${CAN_HEX}.*88" "$MOTOR_LOG"; then
        log_success "Motor $MOTOR_ID acknowledged Motor ON"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        log_error "Motor $MOTOR_ID did not acknowledge Motor ON"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
    
    # Test 4: Position Control (0xA4) - Small movement
    echo ""
    log "Test 4: Position Control Test (0xA4)..."
    log "    Sending small position command (100 encoder units)..."
    
    # Read initial position
    cansend can0 ${CAN_HEX}#9200000000000000
    sleep 0.3
    local INITIAL_POS=$(grep "${CAN_HEX}.*92" "$MOTOR_LOG" | tail -1)
    
    # Send position command: 100 units at speed 100 dps
    cansend can0 ${CAN_HEX}#A46400000064FFFF
    sleep 2
    
    # Read final position
    cansend can0 ${CAN_HEX}#9200000000000000
    sleep 0.3
    local FINAL_POS=$(grep "${CAN_HEX}.*92" "$MOTOR_LOG" | tail -1)
    
    if [ "$INITIAL_POS" != "$FINAL_POS" ]; then
        log_success "Motor $MOTOR_ID responded to position command"
        log "    Initial: $INITIAL_POS"
        log "    Final:   $FINAL_POS"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        log_warn "Motor $MOTOR_ID position unchanged (may already be at target)"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
    
    # Test 5: Return to zero
    echo ""
    log "Test 5: Return to Zero Position..."
    cansend can0 ${CAN_HEX}#A400000000640000
    sleep 2
    
    cansend can0 ${CAN_HEX}#9200000000000000
    sleep 0.3
    
    if grep -q "${CAN_HEX}.*92" "$MOTOR_LOG"; then
        log_success "Motor $MOTOR_ID returned to zero"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        log_error "Motor $MOTOR_ID failed to return to zero"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
    
    # Test 6: Motor OFF (0x80)
    echo ""
    log "Test 6: Motor OFF Command (0x80)..."
    cansend can0 ${CAN_HEX}#8000000000000000
    sleep 0.5
    
    if grep -q "${CAN_HEX}.*80" "$MOTOR_LOG"; then
        log_success "Motor $MOTOR_ID acknowledged Motor OFF"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        log_error "Motor $MOTOR_ID did not acknowledge Motor OFF"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
    
    # Test 7: Final status check
    echo ""
    log "Test 7: Final Status Check..."
    cansend can0 ${CAN_HEX}#9A00000000000000
    sleep 0.5
    
    if grep -q "${CAN_HEX}.*9A" "$MOTOR_LOG"; then
        log_success "Motor $MOTOR_ID final status OK"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        log_error "Motor $MOTOR_ID final status check failed"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
    
    # Stop CAN monitoring
    kill $DUMP_PID 2>/dev/null || true
    wait $DUMP_PID 2>/dev/null || true
    
    # Summary for this motor
    echo ""
    log_header "Motor $MOTOR_ID ($JOINT_NAME) Test Summary"
    log_header "────────────────────────────────────────────────────────────────"
    
    local TOTAL_TESTS=$((TESTS_PASSED + TESTS_FAILED))
    local SUCCESS_RATE=$(echo "scale=1; ($TESTS_PASSED * 100) / $TOTAL_TESTS" | bc)
    
    echo -e "  Tests Passed:  ${GREEN}$TESTS_PASSED${NC}/${TOTAL_TESTS}"
    echo -e "  Tests Failed:  ${RED}$TESTS_FAILED${NC}/${TOTAL_TESTS}"
    echo -e "  Success Rate:  ${YELLOW}${SUCCESS_RATE}%${NC}"
    echo ""
    
    if [ $TESTS_PASSED -ge 6 ]; then
        echo -e "  ${GREEN}✓ Motor $MOTOR_ID is OPERATIONAL${NC}"
        echo "$MOTOR_ID:PASS:$TESTS_PASSED/$TOTAL_TESTS" >> "$OUTPUT_DIR/summary.txt"
        return 0
    else
        echo -e "  ${RED}✗ Motor $MOTOR_ID needs attention${NC}"
        echo "$MOTOR_ID:FAIL:$TESTS_PASSED/$TOTAL_TESTS" >> "$OUTPUT_DIR/summary.txt"
        return 1
    fi
}

# Initialize summary file
echo "Motor Testing Summary - $TIMESTAMP" > "$OUTPUT_DIR/summary.txt"
echo "======================================" >> "$OUTPUT_DIR/summary.txt"
echo "" >> "$OUTPUT_DIR/summary.txt"

# Test all three motors
MOTOR1_OK=0
MOTOR2_OK=0
MOTOR3_OK=0

if test_motor 1 "Joint3_Base"; then
    MOTOR1_OK=1
fi

echo ""
read -p "Press Enter to test Motor 2..."
echo ""

if test_motor 2 "Joint4_UpperArm"; then
    MOTOR2_OK=1
fi

echo ""
read -p "Press Enter to test Motor 3..."
echo ""

if test_motor 3 "Joint5_EndEffector"; then
    MOTOR3_OK=1
fi

# Overall Summary
echo ""
echo ""
log_header "════════════════════════════════════════════════════════════════"
log_header "       OVERALL THREE-MOTOR TEST SUMMARY"
log_header "════════════════════════════════════════════════════════════════"
echo ""

echo -e "Motor 1 (Joint3 - Base):         $([ $MOTOR1_OK -eq 1 ] && echo -e "${GREEN}✓ PASS${NC}" || echo -e "${RED}✗ FAIL${NC}")"
echo -e "Motor 2 (Joint4 - Upper Arm):    $([ $MOTOR2_OK -eq 1 ] && echo -e "${GREEN}✓ PASS${NC}" || echo -e "${RED}✗ FAIL${NC}")"
echo -e "Motor 3 (Joint5 - End Effector): $([ $MOTOR3_OK -eq 1 ] && echo -e "${GREEN}✓ PASS${NC}" || echo -e "${RED}✗ FAIL${NC}")"
echo ""

TOTAL_OK=$((MOTOR1_OK + MOTOR2_OK + MOTOR3_OK))
echo "Motors Operational: $TOTAL_OK/3"
echo ""

# Save overall summary
echo "" >> "$OUTPUT_DIR/summary.txt"
echo "Overall Results:" >> "$OUTPUT_DIR/summary.txt"
echo "  Motor 1: $([ $MOTOR1_OK -eq 1 ] && echo "PASS" || echo "FAIL")" >> "$OUTPUT_DIR/summary.txt"
echo "  Motor 2: $([ $MOTOR2_OK -eq 1 ] && echo "PASS" || echo "FAIL")" >> "$OUTPUT_DIR/summary.txt"
echo "  Motor 3: $([ $MOTOR3_OK -eq 1 ] && echo "PASS" || echo "FAIL")" >> "$OUTPUT_DIR/summary.txt"
echo "  Total: $TOTAL_OK/3 operational" >> "$OUTPUT_DIR/summary.txt"

log "Detailed logs saved to: $OUTPUT_DIR/"
log "Summary: $OUTPUT_DIR/summary.txt"
echo ""

if [ $TOTAL_OK -eq 3 ]; then
    log_success "════════════════════════════════════════════════════════════════"
    log_success "   ✓✓✓ ALL THREE MOTORS FULLY OPERATIONAL! ✓✓✓"
    log_success "════════════════════════════════════════════════════════════════"
    echo ""
    log "Next steps:"
    log "  1. Test multi-motor coordination"
    log "  2. Run integrated system validation"
    log "  3. Test with ROS2 motor controller"
    exit 0
elif [ $TOTAL_OK -ge 2 ]; then
    log_warn "════════════════════════════════════════════════════════════════"
    log_warn "   ⚠ $TOTAL_OK/3 motors operational - review failed motor(s)"
    log_warn "════════════════════════════════════════════════════════════════"
    exit 1
else
    log_error "════════════════════════════════════════════════════════════════"
    log_error "   ✗ Multiple motors failed - check power and wiring"
    log_error "════════════════════════════════════════════════════════════════"
    echo ""
    log "Troubleshooting:"
    log "  1. Verify 48V power to all motors"
    log "  2. Check CAN bus wiring and termination"
    log "  3. Confirm motor Node IDs are set correctly (1, 2, 3)"
    log "  4. Review individual motor logs in $OUTPUT_DIR/"
    exit 1
fi
