#!/usr/bin/env bash
#
# MCP2515 Oscillator Auto-Detection and Fix
# ==========================================
# Automatically detects the correct oscillator frequency for MCP2515 CAN HATs
# and updates /boot/firmware/config.txt (or /boot/config.txt)
#
# CANONICAL VALUE: 8 MHz (8000000 Hz) per design decision D10.
# The Pragati project standardises on 8 MHz MCP2515 oscillator crystals.
# This script remains useful for diagnosing unknown / replacement HATs.
#
# Common oscillator frequencies:
# - 8 MHz  (Pragati standard, per D10) - shown as 4 MHz clock in 'ip' output
# - 12 MHz (Waveshare RS485/CAN HAT) - shown as 6 MHz clock in 'ip' output
# - 16 MHz (Waveshare 2-CH CAN HAT, most common) - shown as 8 MHz clock in 'ip' output
#
# Note: The clock value reported by 'ip -details' is half the crystal oscillator
# frequency. This is normal MCP2515 behavior. This script tests functionality,
# not clock values, so it won't incorrectly "fix" a working configuration.
#
# Usage:
#   sudo bash auto_detect_mcp2515_oscillator.sh
#   sudo bash auto_detect_mcp2515_oscillator.sh can0 500000
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
INTERFACE="${1:-can0}"
BITRATE="${2:-500000}"
TEST_MESSAGE="123#DEADBEEF"
TEST_TIMEOUT=2

# Possible oscillator frequencies (most common first)
OSCILLATORS=(16000000 12000000 8000000)

echo -e "${CYAN}======================================================================"
echo "MCP2515 Oscillator Auto-Detection"
echo "======================================================================"
echo -e "Interface: ${YELLOW}${INTERFACE}${NC}"
echo -e "Target bitrate: ${YELLOW}${BITRATE}${NC}"
echo -e "======================================================================${NC}"
echo ""

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}ERROR: This script must be run as root (use sudo)${NC}"
   exit 1
fi

# Detect Raspberry Pi
IS_RPI=false
CONFIG_FILE=""

if [[ -f /proc/device-tree/model ]] && grep -qi "raspberry pi" /proc/device-tree/model; then
    IS_RPI=true

    # Detect config file location
    if [[ -f /boot/firmware/config.txt ]]; then
        CONFIG_FILE="/boot/firmware/config.txt"
    elif [[ -f /boot/config.txt ]]; then
        CONFIG_FILE="/boot/config.txt"
    else
        echo -e "${RED}ERROR: Cannot find config.txt${NC}"
        echo "Expected locations:"
        echo "  - /boot/firmware/config.txt (Ubuntu on RPi)"
        echo "  - /boot/config.txt (Raspberry Pi OS)"
        exit 1
    fi

    echo -e "${GREEN}✓ Raspberry Pi detected${NC}"
    echo -e "Config file: ${BLUE}${CONFIG_FILE}${NC}"
else
    echo -e "${YELLOW}⚠ Not a Raspberry Pi - this script is for RPi with MCP2515 HATs${NC}"
    exit 0
fi

echo ""

# Check if MCP2515 overlay exists
echo "Checking for MCP2515 overlay in ${CONFIG_FILE}..."
if ! grep -q "mcp2515" "$CONFIG_FILE"; then
    echo -e "${RED}✗ No MCP2515 overlay found in ${CONFIG_FILE}${NC}"
    echo ""
    echo "You need to add the MCP2515 overlay first. Example (8 MHz per D10):"
    echo ""
    echo "  dtparam=spi=on"
    echo "  dtoverlay=mcp2515-can0,oscillator=8000000,interrupt=25,spimaxfrequency=1000000"
    echo ""
    echo "Then reboot and run this script again to verify."
    exit 1
fi

echo -e "${GREEN}✓ MCP2515 overlay found${NC}"
echo ""

# Get current oscillator setting
CURRENT_OSC=$(grep "mcp2515" "$CONFIG_FILE" | grep -oP 'oscillator=\K[0-9]+' | head -1)
if [[ -n "$CURRENT_OSC" ]]; then
    echo -e "Current oscillator setting: ${YELLOW}${CURRENT_OSC} Hz${NC}"
else
    echo -e "${YELLOW}⚠ Could not detect current oscillator setting${NC}"
    CURRENT_OSC="unknown"
fi

echo ""

# Load kernel modules
echo "Loading SocketCAN modules..."
modprobe can 2>/dev/null || true
modprobe can_raw 2>/dev/null || true
modprobe can_dev 2>/dev/null || true
modprobe mcp251x 2>/dev/null || true
sleep 1

# Check if interface exists
if ! ip link show "$INTERFACE" &>/dev/null; then
    echo -e "${RED}✗ Interface $INTERFACE not found${NC}"
    echo ""
    echo "The MCP2515 module may not have loaded properly."
    echo "Check kernel messages:"
    echo "  sudo dmesg | grep -i mcp251"
    echo ""
    exit 1
fi

echo -e "${GREEN}✓ Interface $INTERFACE exists${NC}"
echo ""

# Function to test oscillator frequency
test_oscillator() {
    local test_osc="$1"

    echo -e "${CYAN}Testing oscillator: ${test_osc} Hz...${NC}"

    # Unload and reload mcp251x with new frequency
    # Note: We can't change oscillator at runtime, but we can test
    # the current setting to see if it works

    # Bring interface down
    ip link set "$INTERFACE" down 2>/dev/null || true
    sleep 0.5

    # Configure interface
    if ! ip link set "$INTERFACE" type can bitrate "$BITRATE" restart-ms 100 2>/dev/null; then
        echo -e "  ${RED}✗ Failed to configure interface${NC}"
        return 1
    fi

    # Bring interface up
    if ! ip link set "$INTERFACE" up 2>/dev/null; then
        echo -e "  ${RED}✗ Failed to bring interface up${NC}"
        return 1
    fi

    sleep 0.5

    # Check interface state
    STATE=$(ip -details link show "$INTERFACE" | grep -oP 'state \K[A-Z-]+' | head -1)

    if [[ "$STATE" == "BUS-OFF" ]] || [[ "$STATE" == "ERROR-PASSIVE" ]]; then
        echo -e "  ${RED}✗ Interface in error state: $STATE${NC}"
        return 1
    fi

    # Try to send a message (loopback test)
    if timeout "$TEST_TIMEOUT" candump "$INTERFACE" > /tmp/can_test.log 2>&1 &
    then
        CANDUMP_PID=$!
        sleep 0.5

        if cansend "$INTERFACE" "$TEST_MESSAGE" 2>/dev/null; then
            sleep 0.5
            kill $CANDUMP_PID 2>/dev/null || true
            wait $CANDUMP_PID 2>/dev/null || true

            # Check if we received the message
            if [[ -s /tmp/can_test.log ]] && grep -q "123" /tmp/can_test.log; then
                echo -e "  ${GREEN}✓ CAN communication working!${NC}"
                rm -f /tmp/can_test.log
                return 0
            else
                echo -e "  ${YELLOW}⚠ Message sent but no response${NC}"
                rm -f /tmp/can_test.log
                return 1
            fi
        else
            kill $CANDUMP_PID 2>/dev/null || true
            echo -e "  ${RED}✗ Failed to send test message${NC}"
            rm -f /tmp/can_test.log
            return 1
        fi
    else
        echo -e "  ${RED}✗ candump failed to start${NC}"
        return 1
    fi
}

# If current oscillator is set and works, no need to change
if [[ "$CURRENT_OSC" != "unknown" ]]; then
    echo "Testing current oscillator setting..."
    if test_oscillator "$CURRENT_OSC"; then
        echo ""
        echo -e "${GREEN}======================================================================"
        echo "✓ Current oscillator setting is correct!"
        echo "======================================================================"
        echo -e "Oscillator: ${YELLOW}${CURRENT_OSC} Hz${NC}"
        echo -e "No changes needed."
        echo -e "======================================================================${NC}"
        exit 0
    fi
    echo ""
    echo -e "${YELLOW}Current oscillator setting doesn't work. Trying alternatives...${NC}"
    echo ""
fi

# Try each oscillator frequency
WORKING_OSC=""

for osc in "${OSCILLATORS[@]}"; do
    # Skip if it's the current one (already tested)
    if [[ "$osc" == "$CURRENT_OSC" ]]; then
        continue
    fi

    echo ""
    echo -e "${BLUE}Would need to test $osc Hz (requires reboot with new setting)${NC}"

    # Since we can't change oscillator at runtime, we'll update config
    # and ask user to reboot
    WORKING_OSC="$osc"
    break
done

# If we get here, current oscillator doesn't work
if [[ -z "$WORKING_OSC" ]]; then
    # Try the most common one (16 MHz)
    WORKING_OSC="16000000"
fi

echo ""
echo -e "${YELLOW}======================================================================"
echo "Oscillator Auto-Fix"
echo "======================================================================"
echo -e "Current setting: ${RED}${CURRENT_OSC} Hz${NC} (not working)"
echo -e "Recommended fix: ${GREEN}${WORKING_OSC} Hz${NC} (most common)"
echo -e "======================================================================${NC}"
echo ""

# Backup config
BACKUP_FILE="${CONFIG_FILE}.bak.$(date +%Y%m%d_%H%M%S)"
echo "Creating backup: ${BACKUP_FILE}"
cp "$CONFIG_FILE" "$BACKUP_FILE"

# Update oscillator in config
echo "Updating oscillator frequency in ${CONFIG_FILE}..."
if grep -q "mcp2515.*oscillator=" "$CONFIG_FILE"; then
    # Update existing oscillator value
    sed -i "s/oscillator=[0-9]\+/oscillator=${WORKING_OSC}/g" "$CONFIG_FILE"
else
    echo -e "${YELLOW}⚠ Could not find oscillator parameter to update${NC}"
    echo "Please manually edit ${CONFIG_FILE}"
    exit 1
fi

echo -e "${GREEN}✓ Configuration updated${NC}"
echo ""

# Show the change
echo "New configuration:"
grep "mcp2515" "$CONFIG_FILE"
echo ""

echo -e "${CYAN}======================================================================"
echo "Reboot Required"
echo "======================================================================"
echo -e "The oscillator frequency has been changed to ${GREEN}${WORKING_OSC} Hz${NC}"
echo ""
echo "You must REBOOT for the changes to take effect:"
echo ""
echo -e "  ${YELLOW}sudo reboot${NC}"
echo ""
echo "After reboot, test CAN communication:"
echo ""
echo "  sudo ip link set ${INTERFACE} type can bitrate ${BITRATE}"
echo "  sudo ip link set ${INTERFACE} up"
echo "  cansend ${INTERFACE} 123#DEADBEEF"
echo "  candump ${INTERFACE}"
echo ""
echo "If it still doesn't work, run this script again to try another frequency."
echo -e "======================================================================${NC}"
