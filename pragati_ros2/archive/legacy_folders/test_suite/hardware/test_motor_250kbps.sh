#!/bin/bash
# Test MG6010 Motor Communication at 250kbps
# Run on Raspberry Pi: sudo bash test_motor_250kbps.sh

set -e

echo "=========================================="
echo "MG6010 Motor Test at 250kbps (Node ID 1)"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run with sudo: sudo bash $0"
    exit 1
fi

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}[1/4] Testing CAN Hardware (Loopback Mode)...${NC}"
echo ""

# Configure loopback mode
ip link set can0 down 2>/dev/null || true
ip link set can0 type can bitrate 250000 loopback on
ip link set can0 up

echo "Sending test message in loopback mode..."
timeout 2 candump can0 > /tmp/loopback_test.log 2>&1 &
CANDUMP_PID=$!
sleep 0.5
cansend can0 123#DEADBEEF
sleep 1.5

if grep -q "123" /tmp/loopback_test.log; then
    echo -e "${GREEN}✓ CAN hardware working! (received own message)${NC}"
    cat /tmp/loopback_test.log
    HARDWARE_OK=1
else
    echo -e "${RED}✗ CAN hardware not working properly${NC}"
    HARDWARE_OK=0
fi

rm -f /tmp/loopback_test.log

echo ""
echo -e "${BLUE}[2/4] Reconfiguring for Normal Mode (250kbps)...${NC}"

# Disable loopback, configure for normal operation
ip link set can0 down
ip link set can0 type can bitrate 250000
ip link set can0 up

sleep 1

echo -e "${GREEN}✓ CAN interface UP at 250kbps${NC}"
ip -details link show can0 | grep -E "state|bitrate"

echo ""
echo -e "${BLUE}[3/4] Testing Motor Communication (Node ID 1)...${NC}"
echo ""
echo "Motor configuration:"
echo "  - Baud rate: 250kbps"
echo "  - Node ID: 1"
echo "  - CAN Arbitration ID: 0x141"
echo ""

echo "IMPORTANT: Make sure:"
echo "  1. Motor is POWERED ON"
echo "  2. CAN wiring: CAN-H, CAN-L, GND connected"
echo "  3. 120Ω termination resistors at BOTH ends"
echo ""
echo "Press Enter to continue or Ctrl+C to abort..."
read

echo "Starting CAN monitor in background..."
timeout 10 candump can0 > /tmp/motor_test.log 2>&1 &
CANDUMP_PID=$!
sleep 1

echo "Sending commands to Motor ID 1 (0x141)..."
echo ""

# Send multiple commands to increase chances of response
echo "  1. Motor Status Request (0x9A)..."
cansend can0 141#9A
sleep 0.3

echo "  2. Read Multi-Turn Angle (0x92)..."
cansend can0 141#92
sleep 0.3

echo "  3. Read Single-Turn Angle (0x94)..."
cansend can0 141#94
sleep 0.3

echo "  4. Read PID Parameters (0x30)..."
cansend can0 141#30
sleep 0.3

echo "  5. Read Encoder (0x90)..."
cansend can0 141#90
sleep 0.3

echo ""
echo "Waiting for responses (5 seconds)..."
sleep 5

# Kill candump
kill $CANDUMP_PID 2>/dev/null || true
wait $CANDUMP_PID 2>/dev/null || true

echo ""
echo -e "${BLUE}[4/4] Results...${NC}"
echo ""

if [ -s /tmp/motor_test.log ]; then
    echo -e "${GREEN}✓✓✓ MOTOR RESPONDED! ✓✓✓${NC}"
    echo ""
    echo "CAN Messages Received:"
    cat /tmp/motor_test.log
    echo ""
    
    # Parse motor ID
    RESPONSE_IDS=$(cat /tmp/motor_test.log | awk '{print $2}' | sort -u)
    echo "Detected CAN IDs: $RESPONSE_IDS"
    
    if echo "$RESPONSE_IDS" | grep -q "141"; then
        echo -e "${GREEN}✓ Confirmed: Motor ID 1 (0x141) is responding${NC}"
    fi
else
    echo -e "${RED}✗ No response from motor${NC}"
    echo ""
    echo "Troubleshooting steps:"
    echo ""
    echo "1. Check Motor Power:"
    echo "   - Is motor powered on?"
    echo "   - Check power LED (if present)"
    echo "   - Verify voltage (12V/24V/48V as needed)"
    echo ""
    echo "2. Check CAN Wiring:"
    echo "   - CAN-H to CAN-H"
    echo "   - CAN-L to CAN-L"
    echo "   - GND connected (CRITICAL!)"
    echo ""
    echo "3. Check Termination:"
    echo "   - Need 120Ω resistor at RPi end"
    echo "   - Need 120Ω resistor at Motor end"
    echo "   - Measure resistance between CAN-H and CAN-L:"
    echo "     Should be ~60Ω (two 120Ω in parallel)"
    echo ""
    echo "4. Verify Motor Settings:"
    echo "   - Confirm baud rate is 250kbps"
    echo "   - Confirm Node ID is 1"
    echo "   - Some motors need to be 'enabled' first"
    echo ""
    echo "5. Check CAN Bus Errors:"
    ip -statistics link show can0
    echo ""
fi

rm -f /tmp/motor_test.log

echo ""
echo "=========================================="
echo "Test Complete"
echo "=========================================="
echo ""

if [ "$HARDWARE_OK" -eq 1 ]; then
    echo -e "CAN Hardware: ${GREEN}✓ Working${NC}"
else
    echo -e "CAN Hardware: ${RED}✗ Issue detected${NC}"
fi

echo "CAN Interface: $(ip link show can0 | grep -o 'state [A-Z]*' | awk '{print $2}')"
echo "Bitrate: 250kbps"
echo "Motor ID: 1 (0x141)"
echo ""

echo "To monitor CAN traffic continuously:"
echo "  candump can0"
echo ""
echo "To send manual test:"
echo "  cansend can0 141#9A"
echo ""
