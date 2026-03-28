#!/bin/bash
# Definitive MG6010 Motor Test
# Following EXACT manufacturer protocol from LK-TECH documentation
# Motor confirmed working on Windows, so this MUST work on RPi

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}=========================================="
echo "Definitive MG6010 Motor Test"
echo "Following LK-TECH Official Protocol"
echo "==========================================${NC}"
echo ""

echo "Motor Details:"
echo "  - Model: MG6010-i6-v3"
echo "  - Node ID: 1 (0x141)"
echo "  - Baud Rate: 500 kbps"
echo "  - Protocol: LK-TECH CAN V2.35"
echo ""

# Step 1: Reset CAN completely
echo -e "${CYAN}Step 1: Resetting CAN interface${NC}"
sudo ip link set can0 down 2>/dev/null || true
sudo modprobe -r mcp251x 2>/dev/null || true
sleep 1
sudo modprobe mcp251x
sleep 1

# Configure exactly as specified
sudo ip link set can0 type can bitrate 500000 restart-ms 100
sudo ip link set can0 up

CAN_STATE=$(ip -details link show can0 | grep -oP "can state \K\S+")
echo "  CAN State: $CAN_STATE"
if [ "$CAN_STATE" != "ERROR-ACTIVE" ]; then
    echo -e "  ${RED}✗ CAN not in ERROR-ACTIVE state!${NC}"
    exit 1
fi
echo -e "  ${GREEN}✓ CAN interface ready${NC}"

# Check statistics before test
echo ""
echo "Statistics BEFORE test:"
ip -s link show can0 | grep -A 2 "RX:\|TX:"

echo ""
echo -e "${CYAN}Step 2: Testing with EXACT manufacturer commands${NC}"
echo ""

# Create test file
TEST_LOG="/tmp/motor_definitive_test.log"
rm -f "$TEST_LOG"

# Start candump with detailed logging
sudo candump -td -x can0 > "$TEST_LOG" 2>&1 &
CANDUMP_PID=$!
sleep 0.5

echo "Sending commands in EXACT manufacturer format:"
echo ""

# Command 1: Motor OFF (ensure clean state)
echo "  1. Motor OFF"
echo "     ID: 0x141, DATA: 80 00 00 00 00 00 00 00"
sudo cansend can0 141#8000000000000000
sleep 0.2

# Command 2: Clear Errors
echo "  2. Clear Errors"
echo "     ID: 0x141, DATA: 9B 00 00 00 00 00 00 00"
sudo cansend can0 141#9B00000000000000
sleep 0.2

# Command 3: Motor ON
echo "  3. Motor ON"
echo "     ID: 0x141, DATA: 88 00 00 00 00 00 00 00"
sudo cansend can0 141#8800000000000000
sleep 0.3

# Command 4: Read State 1 (Status)
echo "  4. Read State 1"
echo "     ID: 0x141, DATA: 9A 00 00 00 00 00 00 00"
sudo cansend can0 141#9A00000000000000
sleep 0.2

# Command 5: Read State 2  
echo "  5. Read State 2"
echo "     ID: 0x141, DATA: 9C 00 00 00 00 00 00 00"
sudo cansend can0 141#9C00000000000000
sleep 0.2

# Command 6: Read Multi Angle
echo "  6. Read Multi Angle"
echo "     ID: 0x141, DATA: 92 00 00 00 00 00 00 00"
sudo cansend can0 141#9200000000000000
sleep 0.2

# Command 7: Read Single Angle
echo "  7. Read Single Angle"
echo "     ID: 0x141, DATA: 94 00 00 00 00 00 00 00"
sudo cansend can0 141#9400000000000000
sleep 0.5

# Stop candump
sudo kill $CANDUMP_PID 2>/dev/null || true
wait $CANDUMP_PID 2>/dev/null || true

echo ""
echo -e "${CYAN}Step 3: Analyzing Results${NC}"
echo ""

# Show captured traffic
if [ -s "$TEST_LOG" ]; then
    LINE_COUNT=$(wc -l < "$TEST_LOG")
    echo "CAN Traffic Captured ($LINE_COUNT messages):"
    echo "----------------------------------------"
    cat "$TEST_LOG"
    echo "----------------------------------------"
    echo ""
    
    if [ $LINE_COUNT -gt 0 ]; then
        echo -e "${GREEN}✓✓✓ MOTOR IS RESPONDING! ✓✓✓${NC}"
        echo ""
        
        # Analyze response IDs
        RESPONSE_IDS=$(cat "$TEST_LOG" | awk '{print $3}' | cut -d'#' -f1 | sort -u)
        echo "Detected CAN IDs: $RESPONSE_IDS"
        
        if echo "$RESPONSE_IDS" | grep -qE "141|241"; then
            echo -e "${GREEN}✓ Motor ID 1 (0x141) confirmed!${NC}"
        fi
    fi
else
    echo -e "${RED}✗ NO CAN traffic captured${NC}"
    echo ""
    echo "Candump log is empty. This means:"
    echo "  - Either motor is not responding, OR"
    echo "  - CAN interface issue"
fi

echo ""
echo "Statistics AFTER test:"
ip -s link show can0 | grep -A 2 "RX:\|TX:"

# Analyze statistics
RX_PACKETS=$(ip -s link show can0 | grep "RX:" -A 1 | tail -1 | awk '{print $2}')
TX_PACKETS=$(ip -s link show can0 | grep "TX:" -A 1 | tail -1 | awk '{print $2}')
TX_ERRORS=$(ip -s link show can0 | grep "TX:" -A 1 | tail -1 | awk '{print $3}')
TX_DROPPED=$(ip -s link show can0 | grep "TX:" -A 1 | tail -1 | awk '{print $4}')

echo ""
echo -e "${CYAN}Analysis:${NC}"
echo "  TX Packets: $TX_PACKETS (expected: 7 commands sent)"
echo "  RX Packets: $RX_PACKETS (motor responses)"
echo "  TX Errors: $TX_ERRORS"
echo "  TX Dropped: $TX_DROPPED"
echo ""

if [ "$RX_PACKETS" -gt "0" ]; then
    echo -e "${GREEN}SUCCESS: Motor responded with $RX_PACKETS packets!${NC}"
    echo ""
    echo "Next step: Test with ROS2 node"
    echo "  cd ~/pragati_ws && source install/setup.bash"
    echo "  ros2 run motor_control_ros2 mg6010_test_node --ros-args -p mode:=status"
else
    echo -e "${RED}FAILURE: Motor did not respond (0 RX packets)${NC}"
    echo ""
    echo "Troubleshooting:"
    echo ""
    echo "1. VERIFY MOTOR POWER:"
    echo "   - Check motor power LED"
    echo "   - Measure voltage at motor power terminals"
    echo ""
    echo "2. VERIFY CAN WIRING:"
    echo "   - CAN-H (usually Orange) connected?"
    echo "   - CAN-L (usually Green) connected?"
    echo "   - GND connected? (CRITICAL!)"
    echo ""
    echo "3. CHECK MOTOR CONFIGURATION:"
    echo "   - Is motor actually configured for Node ID 1?"
    echo "   - Is motor set to 500 kbps baud rate?"
    echo "   - Try Windows software again to confirm motor still works"
    echo ""
    echo "4. PHYSICAL CONNECTIONS:"
    echo "   - Are CAN wires properly terminated (120Ω at both ends)?"
    echo "   - Are cables damaged?"
    echo "   - Is RPi CAN hat properly connected to SPI?"
fi

echo ""
echo -e "${CYAN}=========================================="
echo "Test Complete"
echo -e "==========================================${NC}"

# Save detailed log
DETAIL_LOG="/tmp/motor_test_details_$(date +%Y%m%d_%H%M%S).txt"
{
    echo "MG6010 Motor Test - Detailed Log"
    echo "================================="
    echo "Date: $(date)"
    echo ""
    echo "CAN Configuration:"
    ip -details link show can0
    echo ""
    echo "Statistics:"
    ip -s link show can0
    echo ""
    echo "CAN Traffic:"
    cat "$TEST_LOG"
} > "$DETAIL_LOG"

echo "Detailed log saved to: $DETAIL_LOG"
