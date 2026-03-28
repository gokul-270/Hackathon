#!/bin/bash
# MG6010 Motor Communication Failure Investigation Script
# For motor at Node ID 1, 500 kbps (Pragati configuration)
# 
# This script systematically investigates why the motor is not responding
# when physical hardware (power, cables, termination) is confirmed working.
#
# Run on Raspberry Pi: bash investigate_motor_failure.sh

set +e  # Don't exit on errors; we want to collect all diagnostics

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Output file
LOG_FILE="/tmp/motor_investigation_$(date +%Y%m%d_%H%M%S).log"
CANDUMP_LOG="/tmp/candump_investigation.log"

echo -e "${CYAN}=========================================="
echo "MG6010 Motor Communication Investigation"
echo "Node ID: 1 (0x141), Baud: 500 kbps"
echo "Time: $(date)"
echo -e "==========================================${NC}"
echo ""
echo "Log file: $LOG_FILE"
echo ""

# Function to log and display
log_section() {
    echo "" | tee -a "$LOG_FILE"
    echo -e "${BLUE}=== $1 ===${NC}" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
}

log_cmd() {
    echo -e "${CYAN}\$ $1${NC}" | tee -a "$LOG_FILE"
    eval "$1" 2>&1 | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
}

# ============================================================================
# STEP 1: Capture Baseline State
# ============================================================================

log_section "STEP 1: Current System State (Baseline)"

log_cmd "date"
log_cmd "uname -a"

echo "Kernel messages for MCP2515/CAN:" | tee -a "$LOG_FILE"
sudo dmesg -T | grep -i "mcp251\|can0" | tail -20 | tee -a "$LOG_FILE" || echo "No dmesg access or no messages" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

log_cmd "lsmod | grep -E 'mcp251x|can_raw|can_dev'"
log_cmd "ip -details -statistics link show can0"

echo -e "${YELLOW}Current CAN state analysis:${NC}" | tee -a "$LOG_FILE"
CAN_STATE=$(ip -details link show can0 2>/dev/null | grep -oP "state \K\S+")
echo "  CAN State: $CAN_STATE" | tee -a "$LOG_FILE"

if [ "$CAN_STATE" == "ERROR-PASSIVE" ]; then
    echo -e "  ${RED}⚠ ERROR-PASSIVE: CAN controller has seen errors${NC}" | tee -a "$LOG_FILE"
    echo -e "  ${YELLOW}This usually means messages sent but not acknowledged${NC}" | tee -a "$LOG_FILE"
elif [ "$CAN_STATE" == "ERROR-ACTIVE" ]; then
    echo -e "  ${GREEN}✓ ERROR-ACTIVE: Normal state${NC}" | tee -a "$LOG_FILE"
elif [ "$CAN_STATE" == "BUS-OFF" ]; then
    echo -e "  ${RED}✗ BUS-OFF: Controller disabled due to too many errors${NC}" | tee -a "$LOG_FILE"
else
    echo -e "  ${YELLOW}Unknown state: $CAN_STATE${NC}" | tee -a "$LOG_FILE"
fi

# ============================================================================
# STEP 2: Clean Up Active Processes
# ============================================================================

log_section "STEP 2: Stopping Interfering Processes"

echo "Killing any running CAN-related processes..." | tee -a "$LOG_FILE"
sudo pkill -f mg6010_test_node 2>/dev/null || true
sudo pkill -f candump 2>/dev/null || true
sleep 1

echo "Checking for remaining CAN sockets:" | tee -a "$LOG_FILE"
sudo ss -xp 2>/dev/null | grep -i can | tee -a "$LOG_FILE" || echo "No CAN sockets found (good)" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# ============================================================================
# STEP 3: Hard Reset CAN Controller
# ============================================================================

log_section "STEP 3: Hard Reset MCP2515 and Configure at 500 kbps"

echo "Bringing down CAN interface..." | tee -a "$LOG_FILE"
sudo ip link set can0 down 2>/dev/null || true

echo "Unloading MCP2515 driver..." | tee -a "$LOG_FILE"
sudo modprobe -r mcp251x 2>/dev/null || true
sleep 1

echo "Reloading MCP2515 driver..." | tee -a "$LOG_FILE"
sudo modprobe mcp251x
sleep 1

echo "Configuring CAN at 500 kbps with robust options..." | tee -a "$LOG_FILE"
sudo ip link set can0 type can bitrate 500000 restart-ms 100 berr-reporting on one-shot off
echo "Bringing CAN interface up..." | tee -a "$LOG_FILE"
sudo ip link set can0 up

echo "" | tee -a "$LOG_FILE"
log_cmd "ip -details link show can0"

# Verify configuration
BITRATE=$(ip -details link show can0 2>/dev/null | grep -oP "bitrate \K\d+")
RESTART_MS=$(ip -details link show can0 2>/dev/null | grep -oP "restart-ms \K\d+")
CAN_STATE=$(ip -details link show can0 2>/dev/null | grep -oP "state \K\S+")

echo -e "${YELLOW}Configuration verification:${NC}" | tee -a "$LOG_FILE"
echo "  Bitrate: $BITRATE bps (expected: 500000)" | tee -a "$LOG_FILE"
echo "  Restart-ms: $RESTART_MS (expected: 100)" | tee -a "$LOG_FILE"
echo "  State: $CAN_STATE" | tee -a "$LOG_FILE"

if [ "$BITRATE" != "500000" ]; then
    echo -e "  ${RED}✗ Bitrate mismatch!${NC}" | tee -a "$LOG_FILE"
else
    echo -e "  ${GREEN}✓ Bitrate correct${NC}" | tee -a "$LOG_FILE"
fi

# ============================================================================
# STEP 4: Manual Controller Restart to Clear Error Counters
# ============================================================================

log_section "STEP 4: Restart Controller to Clear Error Counters"

log_cmd "sudo ip link set can0 type can restart"
sleep 0.2
log_cmd "ip -statistics link show can0"

# ============================================================================
# STEP 5: Loopback Test (Isolate Pi Hardware)
# ============================================================================

log_section "STEP 5: Loopback Test (Isolate Raspberry Pi CAN Hardware)"

echo "Configuring loopback mode..." | tee -a "$LOG_FILE"
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 500000 loopback on
sudo ip link set can0 up

echo "Starting candump in background..." | tee -a "$LOG_FILE"
rm -f "$CANDUMP_LOG"
sudo timeout 3s candump -td can0 > "$CANDUMP_LOG" 2>&1 &
CANDUMP_PID=$!
sleep 0.5

echo "Sending test message in loopback..." | tee -a "$LOG_FILE"
sudo cansend can0 123#DEADBEEF 2>&1 | tee -a "$LOG_FILE"
sleep 0.5
sudo cansend can0 141#9A 2>&1 | tee -a "$LOG_FILE"
sleep 1.5

wait $CANDUMP_PID 2>/dev/null || true

echo "Loopback test results:" | tee -a "$LOG_FILE"
if [ -s "$CANDUMP_LOG" ]; then
    echo -e "${GREEN}✓ Loopback working! CAN hardware is functional.${NC}" | tee -a "$LOG_FILE"
    cat "$CANDUMP_LOG" | tee -a "$LOG_FILE"
    LOOPBACK_OK=1
else
    echo -e "${RED}✗ Loopback failed! CAN hardware issue detected.${NC}" | tee -a "$LOG_FILE"
    echo "This indicates a problem with the MCP2515 or its configuration." | tee -a "$LOG_FILE"
    LOOPBACK_OK=0
fi

echo "" | tee -a "$LOG_FILE"
echo "Reverting to normal mode (no loopback)..." | tee -a "$LOG_FILE"
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 500000 loopback off restart-ms 100 berr-reporting on
sudo ip link set can0 up
sleep 0.5

# ============================================================================
# STEP 6: Motor Communication Test with Initialization Sequence
# ============================================================================

log_section "STEP 6: Motor Communication Test (with Enable Sequence)"

echo -e "${YELLOW}Testing motor communication at Node ID 1 (0x141)${NC}" | tee -a "$LOG_FILE"
echo "Motor MUST be powered ON and CAN cables connected." | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

echo "Starting candump to monitor bus..." | tee -a "$LOG_FILE"
rm -f "$CANDUMP_LOG"
sudo timeout 15s candump -td can0 > "$CANDUMP_LOG" 2>&1 &
CANDUMP_PID=$!
sleep 1

echo "Sending initialization and status query sequence..." | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Send commands with proper spacing
echo "  1. Motor OFF (0x80) - Safe state" | tee -a "$LOG_FILE"
sudo cansend can0 141#80 2>&1 | tee -a "$LOG_FILE"
sleep 0.1

echo "  2. Clear Errors (0x9B)" | tee -a "$LOG_FILE"
sudo cansend can0 141#9B 2>&1 | tee -a "$LOG_FILE"
sleep 0.1

echo "  3. Motor ON (0x88) - Enable motor" | tee -a "$LOG_FILE"
sudo cansend can0 141#88 2>&1 | tee -a "$LOG_FILE"
sleep 0.15

echo "  4. Read Status (0x9A) - Multiple attempts" | tee -a "$LOG_FILE"
for i in 1 2 3; do
    sudo cansend can0 141#9A 2>&1 | tee -a "$LOG_FILE"
    sleep 0.1
done

echo "  5. Read Status 2 (0x9C)" | tee -a "$LOG_FILE"
for i in 1 2; do
    sudo cansend can0 141#9C 2>&1 | tee -a "$LOG_FILE"
    sleep 0.1
done

echo "  6. Read Encoder (0x90)" | tee -a "$LOG_FILE"
sudo cansend can0 141#90 2>&1 | tee -a "$LOG_FILE"
sleep 0.1

echo "  7. Read Multi-Turn Angle (0x92)" | tee -a "$LOG_FILE"
sudo cansend can0 141#92 2>&1 | tee -a "$LOG_FILE"
sleep 0.1

echo "  8. Read Single-Turn Angle (0x94)" | tee -a "$LOG_FILE"
sudo cansend can0 141#94 2>&1 | tee -a "$LOG_FILE"
sleep 0.5

echo "" | tee -a "$LOG_FILE"
echo "Waiting for responses (10 seconds)..." | tee -a "$LOG_FILE"
sleep 10

# Stop candump
kill $CANDUMP_PID 2>/dev/null || true
wait $CANDUMP_PID 2>/dev/null || true

echo "" | tee -a "$LOG_FILE"
echo "CAN bus activity log:" | tee -a "$LOG_FILE"
if [ -s "$CANDUMP_LOG" ]; then
    echo -e "${GREEN}✓✓✓ MOTOR RESPONDED! ✓✓✓${NC}" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
    cat "$CANDUMP_LOG" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
    
    # Analyze responses
    RESPONSE_IDS=$(cat "$CANDUMP_LOG" | awk '{print $3}' | cut -d'#' -f1 | sort -u)
    echo "Detected CAN IDs in responses: $RESPONSE_IDS" | tee -a "$LOG_FILE"
    
    if echo "$RESPONSE_IDS" | grep -qE "141|241"; then
        echo -e "${GREEN}✓ Motor ID 1 confirmed responding (0x141 or 0x241)${NC}" | tee -a "$LOG_FILE"
        MOTOR_RESPONDING=1
    else
        echo -e "${YELLOW}⚠ Responses detected but not from expected ID${NC}" | tee -a "$LOG_FILE"
        MOTOR_RESPONDING=0
    fi
else
    echo -e "${RED}✗ No CAN bus activity detected${NC}" | tee -a "$LOG_FILE"
    echo "Motor is not responding." | tee -a "$LOG_FILE"
    MOTOR_RESPONDING=0
fi

echo "" | tee -a "$LOG_FILE"
echo "CAN statistics after test:" | tee -a "$LOG_FILE"
ip -statistics link show can0 | tee -a "$LOG_FILE"

# ============================================================================
# STEP 7: Check Oscillator Configuration
# ============================================================================

log_section "STEP 7: Verify MCP2515 Oscillator Configuration"

echo "Checking dmesg for MCP2515 clock setting..." | tee -a "$LOG_FILE"
CLOCK_LINE=$(sudo dmesg -T 2>/dev/null | grep -i mcp251x | grep -i clock | tail -1)
echo "$CLOCK_LINE" | tee -a "$LOG_FILE"

if echo "$CLOCK_LINE" | grep -q "6000000"; then
    echo -e "${GREEN}✓ Clock is 6 MHz (correct for this setup)${NC}" | tee -a "$LOG_FILE"
    CLOCK_OK=1
elif echo "$CLOCK_LINE" | grep -q "clock"; then
    CLOCK_VALUE=$(echo "$CLOCK_LINE" | grep -oP "clock \K\d+")
    echo -e "${YELLOW}⚠ Clock is $CLOCK_VALUE Hz (expected 6000000)${NC}" | tee -a "$LOG_FILE"
    echo "This may cause bit timing issues!" | tee -a "$LOG_FILE"
    CLOCK_OK=0
else
    echo -e "${YELLOW}⚠ Could not determine clock frequency${NC}" | tee -a "$LOG_FILE"
    CLOCK_OK=0
fi

echo "" | tee -a "$LOG_FILE"
echo "Device tree overlay configuration:" | tee -a "$LOG_FILE"
if [ -f /boot/firmware/config.txt ]; then
    grep -i mcp251 /boot/firmware/config.txt | tee -a "$LOG_FILE" || echo "No mcp2515 overlay found in config.txt" | tee -a "$LOG_FILE"
elif [ -f /boot/config.txt ]; then
    grep -i mcp251 /boot/config.txt | tee -a "$LOG_FILE" || echo "No mcp2515 overlay found in config.txt" | tee -a "$LOG_FILE"
else
    echo "Could not find config.txt" | tee -a "$LOG_FILE"
fi

# ============================================================================
# STEP 8: Summary and Recommendations
# ============================================================================

log_section "STEP 8: Investigation Summary"

echo -e "${CYAN}Test Results:${NC}" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

if [ "$LOOPBACK_OK" -eq 1 ]; then
    echo -e "  ${GREEN}✓ CAN Hardware (Pi): Working${NC}" | tee -a "$LOG_FILE"
else
    echo -e "  ${RED}✗ CAN Hardware (Pi): FAILED${NC}" | tee -a "$LOG_FILE"
fi

if [ "$CLOCK_OK" -eq 1 ]; then
    echo -e "  ${GREEN}✓ MCP2515 Clock: Correct (6 MHz)${NC}" | tee -a "$LOG_FILE"
else
    echo -e "  ${YELLOW}⚠ MCP2515 Clock: Check configuration${NC}" | tee -a "$LOG_FILE"
fi

if [ "$MOTOR_RESPONDING" -eq 1 ]; then
    echo -e "  ${GREEN}✓ Motor Communication: SUCCESS${NC}" | tee -a "$LOG_FILE"
else
    echo -e "  ${RED}✗ Motor Communication: FAILED${NC}" | tee -a "$LOG_FILE"
fi

echo "" | tee -a "$LOG_FILE"
echo -e "${CYAN}Current CAN State:${NC}" | tee -a "$LOG_FILE"
ip -details link show can0 | grep "state" | tee -a "$LOG_FILE"

echo "" | tee -a "$LOG_FILE"
echo -e "${CYAN}Recommendations:${NC}" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

if [ "$MOTOR_RESPONDING" -eq 1 ]; then
    echo -e "${GREEN}SUCCESS! Motor is responding.${NC}" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
    echo "The issue was likely:" | tee -a "$LOG_FILE"
    echo "  1. CAN controller stuck in ERROR-PASSIVE state" | tee -a "$LOG_FILE"
    echo "  2. Motor needed enable command (0x88) before status queries" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
    echo "Next steps:" | tee -a "$LOG_FILE"
    echo "  - Run ROS2 test node again: bash ~/pragati_ws/scripts/validation/motor/quick_motor_test.sh" | tee -a "$LOG_FILE"
    echo "  - If it fails, ensure the node sends 0x88 (enable) before 0x9A (status)" | tee -a "$LOG_FILE"
    echo "  - Consider increasing timeout in mg6010_protocol.cpp (currently 10ms)" | tee -a "$LOG_FILE"
else
    echo -e "${RED}Motor still not responding.${NC}" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
    
    if [ "$LOOPBACK_OK" -eq 0 ]; then
        echo "Priority: Fix CAN hardware issue" | tee -a "$LOG_FILE"
        echo "  - Check /boot/firmware/config.txt for mcp2515 overlay" | tee -a "$LOG_FILE"
        echo "  - Verify SPI connection (spi0.0)" | tee -a "$LOG_FILE"
        echo "  - Check interrupt GPIO pin configuration" | tee -a "$LOG_FILE"
    else
        echo "CAN hardware is working, but motor not responding:" | tee -a "$LOG_FILE"
        echo "  1. Verify motor is actually powered ON (check LED if present)" | tee -a "$LOG_FILE"
        echo "  2. Check CAN-H, CAN-L physical connections at motor end" | tee -a "$LOG_FILE"
        echo "  3. Verify motor Node ID is actually 1 (might have been reconfigured)" | tee -a "$LOG_FILE"
        echo "  4. Try scanning Node IDs 1-5:" | tee -a "$LOG_FILE"
        echo "       for id in 141 142 143 144 145; do sudo cansend can0 \$id#9A; sleep 0.2; done" | tee -a "$LOG_FILE"
        echo "  5. Check if motor baud rate was reset (though you said it's fixed)" | tee -a "$LOG_FILE"
    fi
fi

echo "" | tee -a "$LOG_FILE"
echo -e "${CYAN}Full log saved to: $LOG_FILE${NC}"
echo ""

# Keep candump log if motor responded
if [ "$MOTOR_RESPONDING" -eq 1 ]; then
    echo "CAN dump saved to: $CANDUMP_LOG"
fi

echo ""
echo -e "${CYAN}=========================================="
echo "Investigation Complete"
echo -e "==========================================${NC}"
