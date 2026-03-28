#!/bin/bash
# Quick Test Script for Three MG6010 Motors
# Tests each motor individually to verify CAN communication and basic functionality

set -e

CAN_IF="can0"
BITRATE="500000"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log() { echo -e "${CYAN}[$(date +'%T')]${NC} $*"; }
log_success() { echo -e "${GREEN}[$(date +'%T')] ✓${NC} $*"; }
log_error() { echo -e "${RED}[$(date +'%T')] ✗${NC} $*"; }
log_warn() { echo -e "${YELLOW}[$(date +'%T')] ⚠${NC} $*"; }

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║      THREE MG6010 MOTOR TEST - Individual Motor Verification  ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

# Setup CAN interface
log "Setting up CAN interface $CAN_IF @ ${BITRATE} bps..."
sudo ip link set "$CAN_IF" down 2>/dev/null || true
sudo ip link set "$CAN_IF" type can bitrate "$BITRATE"
sudo ip link set "$CAN_IF" up

if ip -details link show "$CAN_IF" | grep -q "UP"; then
    log_success "CAN interface $CAN_IF is UP"
else
    log_error "Failed to bring up CAN interface"
    exit 1
fi

echo ""
log "═══════════════════════════════════════════════════════════════"
log "Motor Configuration:"
log "  Motor 1 (Joint3 - Base):      Node ID 1, CAN 0x141"
log "  Motor 2 (Joint4 - Upper Arm): Node ID 2, CAN 0x142"
log "  Motor 3 (Joint5 - End Eff):   Node ID 3, CAN 0x143"
log "═══════════════════════════════════════════════════════════════"
echo ""

# Function to test a motor
test_motor() {
    local node_id=$1
    local can_id=$2
    local joint_name=$3
    
    log "─────────────────────────────────────────────────────────────"
    log "Testing Motor $node_id ($joint_name) - CAN ID: $can_id"
    log "─────────────────────────────────────────────────────────────"
    
    # Send status query command (0x9A)
    local cmd_hex=$(printf "%X" $((0x140 + node_id)))
    log "Sending status query: cansend $CAN_IF ${cmd_hex}#9A00000000000000"
    
    # Start candump in background
    timeout 2s candump "$CAN_IF" > /tmp/motor_${node_id}_test.log 2>&1 &
    local dump_pid=$!
    sleep 0.5
    
    # Send command
    cansend "$CAN_IF" "${cmd_hex}#9A00000000000000" 2>/dev/null || {
        log_error "Failed to send CAN command"
        return 1
    }
    
    sleep 1
    kill $dump_pid 2>/dev/null || true
    
    # Check for response
    if grep -q "$cmd_hex" /tmp/motor_${node_id}_test.log; then
        log_success "Motor $node_id responded!"
        
        # Show response data
        log "Response:"
        grep "$cmd_hex" /tmp/motor_${node_id}_test.log | head -3 | while read line; do
            echo "    $line"
        done
        echo ""
        return 0
    else
        log_error "Motor $node_id did NOT respond"
        log_warn "Check:"
        log_warn "  - Motor powered on (48V)"
        log_warn "  - Node ID set correctly to $node_id"
        log_warn "  - CAN wiring connected"
        echo ""
        return 1
    fi
}

# Test all three motors
MOTOR1_OK=0
MOTOR2_OK=0
MOTOR3_OK=0

if test_motor 1 0x141 "Joint3"; then
    MOTOR1_OK=1
fi

if test_motor 2 0x142 "Joint4"; then
    MOTOR2_OK=1
fi

if test_motor 3 0x143 "Joint5"; then
    MOTOR3_OK=1
fi

# Summary
echo ""
log "═══════════════════════════════════════════════════════════════"
log "TEST SUMMARY"
log "═══════════════════════════════════════════════════════════════"

TOTAL_OK=$((MOTOR1_OK + MOTOR2_OK + MOTOR3_OK))

echo "Motor 1 (Joint3 - Base):      $([ $MOTOR1_OK -eq 1 ] && echo -e "${GREEN}✓ PASS${NC}" || echo -e "${RED}✗ FAIL${NC}")"
echo "Motor 2 (Joint4 - Upper Arm): $([ $MOTOR2_OK -eq 1 ] && echo -e "${GREEN}✓ PASS${NC}" || echo -e "${RED}✗ FAIL${NC}")"
echo "Motor 3 (Joint5 - End Eff):   $([ $MOTOR3_OK -eq 1 ] && echo -e "${GREEN}✓ PASS${NC}" || echo -e "${RED}✗ FAIL${NC}")"
echo ""

if [ $TOTAL_OK -eq 3 ]; then
    log_success "All motors responding! ✓"
    log "Next steps:"
    log "  1. Test individual motor movements"
    log "  2. Run integrated system test"
    log "  3. Execute validation script"
    exit 0
elif [ $TOTAL_OK -gt 0 ]; then
    log_warn "$TOTAL_OK/3 motors responding"
    log "Fix non-responding motors before proceeding"
    exit 1
else
    log_error "No motors responding!"
    log "Troubleshooting:"
    log "  1. Check 48V power to all motors"
    log "  2. Verify CAN bus wiring and termination"
    log "  3. Confirm motor node IDs are set (1, 2, 3)"
    log "  4. Run: candump can0 to monitor bus activity"
    exit 1
fi
