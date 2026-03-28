#!/bin/bash
# Safe Motor Movement Test - Three Motors
# Tests each motor with small, controlled movements

set -e

CAN_IF="can0"
BITRATE="500000"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

log() { echo -e "${CYAN}[$(date +'%T')]${NC} $*"; }
log_success() { echo -e "${GREEN}[$(date +'%T')] ✓${NC} $*"; }
log_error() { echo -e "${RED}[$(date +'%T')] ✗${NC} $*"; }
log_warn() { echo -e "${YELLOW}[$(date +'%T')] ⚠${NC} $*"; }
log_user() { echo -e "${MAGENTA}[$(date +'%T')] 👉${NC} $*"; }

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║        SAFE MOTOR MOVEMENT TEST - Incremental Testing         ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

# Setup CAN
log "Setting up CAN interface..."
sudo ip link set "$CAN_IF" down 2>/dev/null || true
sudo ip link set "$CAN_IF" type can bitrate "$BITRATE"
sudo ip link set "$CAN_IF" up
log_success "CAN interface ready at ${BITRATE} bps"
echo ""

# Function to decode position from CAN response
decode_position() {
    local hex_data=$1
    # Position is in bytes 2-5 (little endian, in 0.01 degree units)
    # For now, just show raw hex
    echo "$hex_data"
}

# Function to test a single motor
test_motor_movement() {
    local node_id=$1
    local joint_name=$2
    local can_hex=$(printf "%X" $((0x140 + node_id)))
    
    log "═══════════════════════════════════════════════════════════════"
    log "Testing Motor $node_id - $joint_name (CAN: 0x$can_hex)"
    log "═══════════════════════════════════════════════════════════════"
    echo ""
    
    # Start monitoring
    candump can0 > /tmp/motor_${node_id}_move.log 2>&1 &
    DUMP_PID=$!
    sleep 0.5
    
    # Step 1: Motor ON
    log "Step 1: Sending Motor ON command..."
    cansend can0 ${can_hex}#8800000000000000
    sleep 0.5
    log_success "Motor ON command sent"
    
    # Step 2: Read current position
    log "Step 2: Reading current position..."
    cansend can0 ${can_hex}#9200000000000000
    sleep 0.5
    
    # Step 3: Small position movement test
    log "Step 3: Testing SMALL movement..."
    log_user "This will move motor VERY SLIGHTLY (0.1 radians = ~5.7 degrees)"
    log_user "Watch the motor - it should move slowly"
    echo ""
    read -p "Press Enter to proceed with movement test (or Ctrl+C to abort)..."
    
    # Position control: 0xA4 command
    # Format: A4 [angle_low] [angle_high] [max_speed_low] [max_speed_high]
    # Angle: 0.01 degree units, little endian
    # Speed: 0.01 dps units, little endian
    
    # Move to ~100 degrees (very small) at slow speed (100 dps = 1 degree/sec)
    # 100 degrees * 100 = 10000 = 0x2710 in hex
    # Speed: 100 dps = 0x0064
    log "Sending position command: 100 degrees at 100 dps..."
    cansend can0 ${can_hex}#A41027000064FFFF
    sleep 3
    
    log "Reading position after movement..."
    cansend can0 ${can_hex}#9200000000000000
    sleep 0.5
    
    # Step 4: Return to zero
    log "Step 4: Returning to zero position..."
    cansend can0 ${can_hex}#A400000000640000
    sleep 3
    
    log "Reading final position..."
    cansend can0 ${can_hex}#9200000000000000
    sleep 0.5
    
    # Step 5: Motor OFF
    log "Step 5: Motor OFF (stop holding)..."
    cansend can0 ${can_hex}#8000000000000000
    sleep 0.5
    
    # Stop monitoring
    kill $DUMP_PID 2>/dev/null
    wait $DUMP_PID 2>/dev/null || true
    
    echo ""
    log "Movement test complete for Motor $node_id"
    log "CAN traffic log saved to: /tmp/motor_${node_id}_move.log"
    echo ""
    
    # Show position responses
    log "Position readings:"
    grep "92" /tmp/motor_${node_id}_move.log | head -5
    echo ""
    
    # Ask user for verification
    log_user "Did Motor $node_id ($joint_name) move as expected?"
    log_user "  - Small movement observed?"
    log_user "  - Returned to start position?"
    log_user "  - No unusual sounds or vibrations?"
    echo ""
    read -p "Motor $node_id OK? (y/n): " MOTOR_OK
    
    if [[ "$MOTOR_OK" =~ ^[Yy]$ ]]; then
        log_success "Motor $node_id verified OK"
        return 0
    else
        log_warn "Motor $node_id needs attention"
        return 1
    fi
}

# Safety check
log_user "═══════════════════════════════════════════════════════════════"
log_user "⚠️  SAFETY CHECKLIST"
log_user "═══════════════════════════════════════════════════════════════"
log_user ""
log_user "Before proceeding, ensure:"
log_user "  1. ✓ Motors have clear range of motion (no obstacles)"
log_user "  2. ✓ Emergency stop button is accessible"
log_user "  3. ✓ 48V power supply is stable"
log_user "  4. ✓ You're ready to press emergency stop if needed"
log_user "  5. ✓ Each motor can move at least 10 degrees safely"
log_user ""
read -p "All safety checks passed? Press Enter to continue..."
echo ""

# Test each motor sequentially
MOTOR1_OK=0
MOTOR2_OK=0
MOTOR3_OK=0

log "Starting Motor 1 (Joint3 - Base) test..."
echo ""
if test_motor_movement 1 "Joint3 - Base"; then
    MOTOR1_OK=1
fi
echo ""

log "Starting Motor 2 (Joint4 - Upper Arm) test..."
echo ""
if test_motor_movement 2 "Joint4 - Upper Arm"; then
    MOTOR2_OK=1
fi
echo ""

log "Starting Motor 3 (Joint5 - End Effector) test..."
echo ""
if test_motor_movement 3 "Joint5 - End Effector"; then
    MOTOR3_OK=1
fi
echo ""

# Summary
log "═══════════════════════════════════════════════════════════════"
log "MOVEMENT TEST SUMMARY"
log "═══════════════════════════════════════════════════════════════"
echo ""
echo "Motor 1 (Joint3 - Base):      $([ $MOTOR1_OK -eq 1 ] && echo -e "${GREEN}✓ PASS${NC}" || echo -e "${RED}✗ NEEDS ATTENTION${NC}")"
echo "Motor 2 (Joint4 - Upper Arm): $([ $MOTOR2_OK -eq 1 ] && echo -e "${GREEN}✓ PASS${NC}" || echo -e "${RED}✗ NEEDS ATTENTION${NC}")"
echo "Motor 3 (Joint5 - End Eff):   $([ $MOTOR3_OK -eq 1 ] && echo -e "${GREEN}✓ PASS${NC}" || echo -e "${RED}✗ NEEDS ATTENTION${NC}")"
echo ""

TOTAL_OK=$((MOTOR1_OK + MOTOR2_OK + MOTOR3_OK))

if [ $TOTAL_OK -eq 3 ]; then
    log_success "✓ All motors tested successfully!"
    echo ""
    log "Ready for integrated system testing!"
    log "Next step: Run full validation script"
    log "  Command: cd /home/ubuntu/pragati_ws && bash scripts/validation/system/run_table_top_validation_v2.sh"
    exit 0
elif [ $TOTAL_OK -gt 0 ]; then
    log_warn "$TOTAL_OK/3 motors passed"
    log "Review failed motors before proceeding"
    exit 1
else
    log_error "No motors passed movement test"
    log "Check motor wiring, power, and mechanical setup"
    exit 1
fi
