#!/bin/bash
# Complete RPi CAN Setup and Motor Test Script
# Run this directly on the Raspberry Pi

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}RPi CAN Setup & Motor Test${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# Step 1: Check current CAN interface
echo -e "${CYAN}Step 1: Checking current CAN interface...${NC}"
if ip link show can0 &>/dev/null; then
    echo -e "${GREEN}✓ can0 interface exists${NC}"
    echo ""
    echo "Current configuration:"
    sudo ip -details link show can0
    echo ""
    
    # Extract clock frequency
    CLOCK=$(sudo ip -details link show can0 | grep -oP 'clock \K[0-9]+')
    echo -e "Current clock: ${YELLOW}${CLOCK} Hz${NC}"
    
    if [ "$CLOCK" != "8000000" ]; then
        echo -e "${YELLOW}⚠ Clock is not 8 MHz! Need to fix boot config.${NC}"
        NEED_REBOOT=1
    else
        echo -e "${GREEN}✓ Clock is correctly set to 8 MHz${NC}"
        NEED_REBOOT=0
    fi
else
    echo -e "${RED}✗ can0 interface not found${NC}"
    exit 1
fi

echo ""

# Step 2: Check boot config
echo -e "${CYAN}Step 2: Checking boot configuration...${NC}"

CONFIG_FILE=""
if [ -f "/boot/firmware/config.txt" ]; then
    CONFIG_FILE="/boot/firmware/config.txt"
elif [ -f "/boot/config.txt" ]; then
    CONFIG_FILE="/boot/config.txt"
else
    echo -e "${RED}✗ Cannot find boot config file${NC}"
    exit 1
fi

echo "Config file: $CONFIG_FILE"
echo ""

if sudo grep -q "mcp2515" "$CONFIG_FILE"; then
    echo "Current mcp2515 configuration:"
    sudo grep "mcp2515" "$CONFIG_FILE"
    echo ""
    
    # Check if it has 6000000
    if sudo grep -q "oscillator=6000000" "$CONFIG_FILE"; then
        echo -e "${YELLOW}Found 6 MHz oscillator - updating to 8 MHz...${NC}"
        sudo sed -i 's/oscillator=6000000/oscillator=8000000/' "$CONFIG_FILE"
        echo -e "${GREEN}✓ Updated to 8 MHz${NC}"
        NEED_REBOOT=1
    elif sudo grep -q "oscillator=8000000" "$CONFIG_FILE"; then
        echo -e "${GREEN}✓ Already configured for 8 MHz${NC}"
    else
        echo -e "${YELLOW}⚠ Oscillator value found but not 6 or 8 MHz${NC}"
        sudo grep "mcp2515" "$CONFIG_FILE"
    fi
else
    echo -e "${YELLOW}⚠ No mcp2515 configuration found${NC}"
    echo "This might be a USB-CAN adapter or native CAN interface"
fi

echo ""

# Step 3: Reboot if needed
if [ "${NEED_REBOOT:-0}" -eq 1 ]; then
    echo -e "${YELLOW}========================================${NC}"
    echo -e "${YELLOW}REBOOT REQUIRED${NC}"
    echo -e "${YELLOW}========================================${NC}"
    echo ""
    echo "Boot configuration has been updated."
    echo "You need to reboot for changes to take effect."
    echo ""
    echo "After reboot, run this script again to continue testing."
    echo ""
    read -p "Reboot now? (y/n): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Rebooting in 3 seconds..."
        sleep 3
        sudo reboot
    else
        echo "Please reboot manually: sudo reboot"
        exit 0
    fi
fi

# Step 4: Bring up CAN interface
echo -e "${CYAN}Step 3: Bringing up CAN interface...${NC}"
sudo ip link set can0 down 2>/dev/null || true
sudo ip link set can0 type can bitrate 500000
sudo ip link set can0 up

echo -e "${GREEN}✓ CAN interface configured${NC}"
echo ""
echo "Interface status:"
ip -details link show can0 | grep -E "state|bitrate|clock"
echo ""

# Step 5: Check for can-utils
echo -e "${CYAN}Step 4: Checking for can-utils...${NC}"
if ! command -v candump &>/dev/null; then
    echo -e "${YELLOW}Installing can-utils...${NC}"
    sudo apt-get update -qq
    sudo apt-get install -y can-utils
fi
echo -e "${GREEN}✓ can-utils available${NC}"
echo ""

# Step 6: Quick CAN bus check
echo -e "${CYAN}Step 5: Checking for CAN traffic...${NC}"
echo "Listening for 3 seconds..."
timeout 3 candump can0 2>/dev/null || echo "No traffic detected (this is normal if motors are off)"
echo ""

# Step 7: Check ROS2 environment
echo -e "${CYAN}Step 6: Checking ROS2 environment...${NC}"
if [ -f "/opt/ros/jazzy/setup.bash" ]; then
    source /opt/ros/jazzy/setup.bash
    echo -e "${GREEN}✓ ROS2 Jazzy found${NC}"
elif [ -f "/opt/ros/humble/setup.bash" ]; then
    source /opt/ros/humble/setup.bash
    echo -e "${GREEN}✓ ROS2 Humble found${NC}"
else
    echo -e "${RED}✗ ROS2 not found${NC}"
    exit 1
fi

# Source workspace if it exists
if [ -f "$HOME/pragati_ros2/install/setup.bash" ]; then
    source "$HOME/pragati_ros2/install/setup.bash"
    echo -e "${GREEN}✓ Workspace sourced${NC}"
fi

echo ""

# Step 8: Run motor tests
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}Ready to test motors!${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""
echo "Motor Configuration:"
echo "  - Joint 3: CAN ID 141 (0x8D), Node ID 1"
echo "  - Joint 4: CAN ID 142 (0x8E), Node ID 2"
echo ""
echo -e "${YELLOW}WARNING: Motors will move! Ensure area is clear.${NC}"
echo ""
read -p "Proceed with motor tests? (y/n): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    cd ~/pragati_ros2
    echo ""
    echo -e "${CYAN}Starting motor tests...${NC}"
    echo ""
    bash test_motors_rpi.sh
else
    echo "Motor tests skipped."
    echo ""
    echo "To run tests manually:"
    echo "  cd ~/pragati_ros2"
    echo "  bash test_motors_rpi.sh"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
