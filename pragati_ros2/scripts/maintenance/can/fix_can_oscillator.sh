#!/bin/bash
# Fix MCP2515 CAN HAT oscillator configuration
# HAT has 8 MHz crystal but config shows 12 MHz - this causes timing errors

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}=========================================="
echo "MCP2515 Oscillator Configuration Fix"
echo -e "==========================================${NC}"
echo ""

CONFIG_FILE="/boot/firmware/config.txt"

# Check if config file exists
if [ ! -f "$CONFIG_FILE" ]; then
    CONFIG_FILE="/boot/config.txt"
    if [ ! -f "$CONFIG_FILE" ]; then
        echo -e "${RED}ERROR: Cannot find boot config file${NC}"
        exit 1
    fi
fi

echo "Config file: $CONFIG_FILE"
echo ""

# Show current configuration
echo -e "${CYAN}Current MCP2515 configuration:${NC}"
grep "mcp2515" "$CONFIG_FILE" || echo "No mcp2515 overlay found"
echo ""

# Create backup
BACKUP_FILE="${CONFIG_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
echo -e "${YELLOW}Creating backup...${NC}"
sudo cp "$CONFIG_FILE" "$BACKUP_FILE"
echo -e "${GREEN}✓ Backup created: $BACKUP_FILE${NC}"
echo ""

# Update the oscillator value from 12000000 to 8000000
echo -e "${CYAN}Updating oscillator from 12 MHz to 8 MHz...${NC}"
sudo sed -i 's/dtoverlay=mcp2515-can0,oscillator=12000000/dtoverlay=mcp2515-can0,oscillator=8000000/' "$CONFIG_FILE"

# Verify the change
echo ""
echo -e "${CYAN}New MCP2515 configuration:${NC}"
grep "mcp2515" "$CONFIG_FILE"
echo ""

# Check if change was successful
if grep -q "oscillator=8000000" "$CONFIG_FILE"; then
    echo -e "${GREEN}✓ Configuration updated successfully!${NC}"
    echo ""
    echo -e "${YELLOW}IMPORTANT: You must REBOOT for changes to take effect${NC}"
    echo ""
    echo "After reboot, verify with:"
    echo "  ip -details link show can0 | grep clock"
    echo "  # Should show: clock 8000000"
    echo ""
    echo "Then test CAN communication:"
    echo "  bash ~/definitive_motor_test.sh"
    echo ""
    echo -e "${CYAN}Reboot now? (y/n)${NC}"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        echo "Rebooting in 3 seconds..."
        sleep 3
        sudo reboot
    else
        echo "Remember to reboot manually: sudo reboot"
    fi
else
    echo -e "${RED}✗ Configuration update failed${NC}"
    echo "Restoring backup..."
    sudo cp "$BACKUP_FILE" "$CONFIG_FILE"
    echo "Backup restored. Please check manually."
    exit 1
fi
