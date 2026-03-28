#!/bin/bash
# MG6010 Motor Communication Diagnostic and Fix Script
# Run this on the Raspberry Pi to diagnose and fix motor communication issues

set -e

echo "=========================================="
echo "MG6010 Motor Communication Diagnostic"
echo "=========================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if running with sudo
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Please run with sudo: sudo bash $0${NC}"
    exit 1
fi

echo -e "${BLUE}[1/7] Checking CAN Hardware...${NC}"
echo "System: $(uname -srm)"
echo ""

# Check for CAN interface
if ip link show can0 &> /dev/null; then
    echo -e "${GREEN}✓ CAN interface 'can0' exists${NC}"
else
    echo -e "${RED}✗ CAN interface 'can0' not found${NC}"
    echo "  Check /boot/firmware/config.txt for mcp2515 overlay"
    exit 1
fi

echo ""
echo -e "${BLUE}[2/7] Checking CAN Modules...${NC}"
# Check kernel modules
if lsmod | grep -q "mcp251x"; then
    echo -e "${GREEN}✓ MCP2515 CAN module loaded${NC}"
    OSCILLATOR=$(dmesg | grep mcp251x | grep -o "clock [0-9]*" | awk '{print $2}' | head -1)
    if [ -n "$OSCILLATOR" ]; then
        echo "  Oscillator: ${OSCILLATOR} Hz ($(($OSCILLATOR / 1000000)) MHz)"
    fi
else
    echo -e "${YELLOW}⚠ MCP2515 module not loaded (might load automatically)${NC}"
fi

if lsmod | grep -q "can_dev"; then
    echo -e "${GREEN}✓ CAN device module loaded${NC}"
else
    echo -e "${RED}✗ CAN device module not loaded${NC}"
    modprobe can_dev
fi

echo ""
echo -e "${BLUE}[3/7] Checking SPI Interface...${NC}"
if [ -e /dev/spidev0.0 ] || [ -e /dev/spidev0.1 ]; then
    echo -e "${GREEN}✓ SPI device available: $(ls /dev/spidev*  | tr '\n' ' ')${NC}"
else
    echo -e "${RED}✗ No SPI devices found${NC}"
    echo "  Enable SPI in /boot/firmware/config.txt"
fi

echo ""
echo -e "${BLUE}[4/7] Current CAN Interface Status...${NC}"
CAN_STATE=$(ip -details link show can0 | grep "state" | awk '{print $9}')
echo "  Current state: $CAN_STATE"

if [ "$CAN_STATE" = "DOWN" ] || [ "$CAN_STATE" = "STOPPED" ]; then
    echo -e "${YELLOW}  Interface is DOWN${NC}"
else
    echo -e "${GREEN}  Interface is UP${NC}"
fi

echo ""
echo -e "${BLUE}[5/7] Configuring CAN Interface...${NC}"

# Bring down if already up
ip link set can0 down 2>/dev/null || true

# Configure for Pragati MG6010 motors
echo "  Setting bitrate to 500000 bps (500 kbps - Pragati configuration)..."
if ip link set can0 type can bitrate 500000 restart-ms 100 berr-reporting on; then
    echo -e "${GREEN}  ✓ Bitrate configured${NC}"
else
    echo -e "${RED}  ✗ Failed to set bitrate to 500 kbps${NC}"
    exit 1
fi

# Bring interface up
echo "  Bringing interface UP..."
if ip link set can0 up; then
    echo -e "${GREEN}  ✓ Interface UP${NC}"
else
    echo -e "${RED}  ✗ Failed to bring interface UP${NC}"
    dmesg | tail -20
    exit 1
fi

sleep 1

echo ""
echo -e "${BLUE}[6/7] Verifying CAN Interface...${NC}"
ip -details link show can0

# Show statistics
echo ""
echo "Statistics:"
ip -statistics link show can0 | grep -A 5 "RX:\|TX:"

echo ""
echo -e "${BLUE}[7/7] Testing CAN Communication...${NC}"

# Check if motor is present
echo "  Scanning for MG6010 motors (Node IDs 1-5)..."
echo "  Sending ping commands..."

# Function to test motor ID
test_motor_id() {
    local motor_id=$1
    local arb_id=$((0x140 + motor_id))
    
    # Send READ_STATUS_1 command (0x9A) to check if motor responds
    # Format: cansend can0 <ARB_ID>#<DATA>
    # 0x9A = Read motor status command
    timeout 0.5 cansend can0 $(printf "%03X" $arb_id)#9A 2>/dev/null || true
    sleep 0.1
}

# Test motor IDs 1-5
FOUND_MOTORS=""
for motor_id in {1..5}; do
    echo -n "  Testing Motor ID $motor_id (0x$(printf '%03X' $((0x140 + motor_id)))): "
    test_motor_id $motor_id
    echo "sent"
done

echo ""
echo "  Listening for responses (5 seconds)..."
echo "  Run this in another terminal: candump can0"
echo ""

# Start candump in background for 5 seconds
timeout 5 candump can0 > /tmp/candump_test.log 2>&1 &
CANDUMP_PID=$!
sleep 5

if [ -s /tmp/candump_test.log ]; then
    echo -e "${GREEN}✓ CAN messages detected!${NC}"
    echo ""
    echo "Messages received:"
    cat /tmp/candump_test.log
    
    # Try to identify motors
    echo ""
    MOTOR_IDS=$(cat /tmp/candump_test.log | awk '{print $2}' | sort -u)
    echo "Detected CAN IDs: $MOTOR_IDS"
else
    echo -e "${YELLOW}⚠ No CAN messages detected${NC}"
    echo ""
    echo "Possible reasons:"
    echo "  1. Motor not powered on"
    echo "  2. Motor not connected to CAN bus"
    echo "  3. Wrong baud rate"
    echo "  4. CAN wiring issues (check CAN-H, CAN-L, GND)"
    echo "  5. Missing 120Ω termination resistors"
    echo "  6. Motor configured with different Node ID"
fi

rm -f /tmp/candump_test.log

echo ""
echo "=========================================="
echo -e "${GREEN}CAN Interface Configuration Complete${NC}"
echo "=========================================="
echo ""
echo "Interface Status: $(ip link show can0 | grep -o 'state [A-Z]*' | awk '{print $2}')"
echo "Bitrate: $(ip -details link show can0 | grep -o 'bitrate [0-9]*' | awk '{print $2}') bps"
echo ""

echo "Next Steps:"
echo "  1. Check motor power supply"
echo "  2. Verify CAN wiring (CAN-H, CAN-L, GND)"
echo "  3. Ensure 120Ω termination at both ends"
echo "  4. Monitor CAN bus: candump can0"
echo "  5. Test with MG6010 test node (see instructions below)"
echo ""

echo "To monitor CAN traffic:"
echo "  candump can0"
echo ""

echo "To test with ROS2 (after building workspace):"
echo "  cd ~/pragati_ws"
echo "  source install/setup.bash"
echo "  ros2 run odrive_control_ros2 mg6010_test_node --ros-args \\"
echo "    -p interface_name:=can0 \\"
echo "    -p baud_rate:=500000 \\\"
echo "    -p node_id:=1 \\"
echo "    -p mode:=status"
echo ""

echo "To make CAN interface auto-start on boot:"
echo "  sudo tee /etc/network/interfaces.d/can0 << EOF"
echo "auto can0"
echo "iface can0 inet manual"
echo "    pre-up /sbin/ip link set can0 type can bitrate 500000 restart-ms 100 berr-reporting on"
echo "    up /sbin/ip link set can0 up"
echo "    down /sbin/ip link set can0 down"
echo "EOF"
echo ""
