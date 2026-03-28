#!/bin/bash
# ARCHIVED: This script used 6 MHz oscillator which is WRONG.
# The canonical oscillator value is 8 MHz per design decision D10.
# Use fix_can_oscillator.sh instead (correctly sets 8 MHz).
# Archived as part of task 7.2 — CAN oscillator script consolidation.
#
# Original description:
# Fix MG6010 Motor Communication
# Corrects oscillator configuration and tests properly

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}=========================================="
echo "MG6010 Motor Communication Fix"
echo -e "==========================================${NC}"
echo ""

# Step 1: Fix oscillator in config.txt
echo -e "${CYAN}Step 1: Fixing MCP2515 oscillator configuration${NC}"
echo ""
echo "Current configuration:"
grep -i mcp2515 /boot/firmware/config.txt || echo "No mcp2515 line found"
echo ""

echo "The MCP2515 on your system has a 6 MHz oscillator, not 12 MHz."
echo "This needs to be corrected in /boot/firmware/config.txt"
echo ""

echo -e "${YELLOW}Would you like to fix this now? (requires reboot)${NC}"
echo "1) Yes, fix it and reboot"
echo "2) No, just test with correct settings (temporary)"
echo "3) Cancel"
read -p "Choice [1-3]: " choice

case $choice in
    1)
        echo ""
        echo "Backing up current config.txt..."
        sudo cp /boot/firmware/config.txt /boot/firmware/config.txt.bak.$(date +%Y%m%d_%H%M%S)

        echo "Updating oscillator to 6 MHz..."
        sudo sed -i 's/dtoverlay=mcp2515-can0,oscillator=12000000/dtoverlay=mcp2515-can0,oscillator=6000000/' /boot/firmware/config.txt

        echo ""
        echo "New configuration:"
        grep -i mcp2515 /boot/firmware/config.txt

        echo ""
        echo -e "${GREEN}Configuration updated!${NC}"
        echo ""
        echo "System will reboot in 5 seconds..."
        echo "After reboot, run: bash ~/test_motor_fixed.sh"
        sleep 5
        sudo reboot
        ;;

    2)
        echo ""
        echo "Testing with correct settings (will not persist after reboot)..."
        ;;

    3)
        echo "Cancelled."
        exit 0
        ;;

    *)
        echo "Invalid choice. Exiting."
        exit 1
        ;;
esac

# Step 2: Configure CAN properly
echo ""
echo -e "${CYAN}Step 2: Configuring CAN at 500 kbps (normal mode)${NC}"
echo ""

# Bring down
sudo ip link set can0 down 2>/dev/null || true

# Note: We can't change the oscillator without reboot, but we can configure
# for the correct bitrate that should work with 6 MHz
# At 6 MHz, for 500 kbps we need different bit timing

if [ "$choice" == "2" ]; then
    echo "Note: Bit timing may be incorrect until oscillator is fixed in config.txt"
    echo "      Continuing anyway for testing..."
fi

# Configure for 500 kbps (this should auto-calculate timing)
sudo ip link set can0 type can bitrate 500000 restart-ms 100

# Bring up
sudo ip link set can0 up

echo ""
ip -details link show can0 | grep -E "state|bitrate|loopback"

# Step 3: Test motor communication
echo ""
echo -e "${CYAN}Step 3: Testing motor communication${NC}"
echo ""

# Start monitoring
echo "Starting candump..."
sudo timeout 10s candump -td can0 > /tmp/motor_fix_test.log 2>&1 &
CANDUMP_PID=$!
sleep 1

# Send initialization sequence
echo "Sending commands to motor..."
echo "  1. Motor OFF (0x80)"
sudo cansend can0 141#80
sleep 0.1

echo "  2. Clear Errors (0x9B)"
sudo cansend can0 141#9B
sleep 0.1

echo "  3. Motor ON (0x88)"
sudo cansend can0 141#88
sleep 0.15

echo "  4. Read Status (0x9A)"
sudo cansend can0 141#9A
sleep 0.3

echo ""
echo "Waiting for motor response (5 seconds)..."
sleep 5

# Stop candump
kill $CANDUMP_PID 2>/dev/null || true
wait $CANDUMP_PID 2>/dev/null || true

echo ""
echo -e "${CYAN}Results:${NC}"
echo ""

if [ -s /tmp/motor_fix_test.log ]; then
    echo "CAN traffic captured:"
    cat /tmp/motor_fix_test.log
    echo ""

    # Count unique message IDs (excluding echoes)
    UNIQUE_COUNT=$(cat /tmp/motor_fix_test.log | awk '{print $3}' | sort -u | wc -l)
    TOTAL_COUNT=$(cat /tmp/motor_fix_test.log | wc -l)

    echo "Messages: $TOTAL_COUNT (unique IDs: $UNIQUE_COUNT)"

    # Check if we're seeing echoes (loopback enabled)
    if [ $TOTAL_COUNT -gt $((UNIQUE_COUNT * 2 - 2)) ]; then
        echo -e "${YELLOW}⚠ WARNING: Loopback appears to be enabled${NC}"
        echo "Each message appears twice (sent + echo)"
        echo "This means we're seeing our own messages, not motor responses!"
        echo ""
        echo "To fix: Ensure CAN is configured without loopback:"
        echo "  sudo ip link set can0 down"
        echo "  sudo ip link set can0 type can bitrate 500000 restart-ms 100"
        echo "  sudo ip link set can0 up"
    else
        echo -e "${GREEN}✓ Motor appears to be responding!${NC}"
    fi
else
    echo -e "${RED}✗ No CAN traffic detected${NC}"
    echo "Motor is not responding or CAN interface issue."
fi

echo ""
echo "CAN statistics:"
ip -s link show can0

echo ""
echo -e "${CYAN}==========================================${NC}"
echo "Next steps:"
echo ""

if [ "$choice" == "2" ]; then
    echo "1. Fix the oscillator in /boot/firmware/config.txt:"
    echo "   Change: dtoverlay=mcp2515-can0,oscillator=12000000,interrupt=25"
    echo "   To:     dtoverlay=mcp2515-can0,oscillator=6000000,interrupt=25"
    echo ""
    echo "2. Reboot the system"
    echo ""
    echo "3. After reboot, test again with: bash ~/pragati_ws/scripts/validation/motor/quick_motor_test.sh"
fi

echo ""
echo "If motor is responding but ROS2 node still fails:"
echo "  - Modify test node to send Motor ON (0x88) before status reads"
echo "  - Increase timeout in mg6010_protocol.cpp from 10ms to 30ms"
echo ""
