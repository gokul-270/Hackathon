#!/usr/bin/env bash
#
# RPi Setup Verification Script
# ==============================
#
# Run this on the Raspberry Pi after deployment to verify
# all dependencies and configurations are correct.
#
# Usage:
#   ./rpi_verify_setup.sh
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

ERRORS=0
WARNINGS=0

check_pass() {
    echo -e "  ${GREEN}✓${NC} $1"
}

check_fail() {
    echo -e "  ${RED}✗${NC} $1"
    ERRORS=$((ERRORS + 1))
}

check_warn() {
    echo -e "  ${YELLOW}⚠${NC} $1"
    WARNINGS=$((WARNINGS + 1))
}

echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║      Raspberry Pi Setup Verification                          ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check 1: ROS2 Installation
echo -e "${BLUE}[1] ROS2 Installation${NC}"
if [ -d "/opt/ros/jazzy" ]; then
    check_pass "ROS2 Jazzy installed"
    
    # Check if sourced
    if [ -n "$ROS_DISTRO" ] && [ "$ROS_DISTRO" = "jazzy" ]; then
        check_pass "ROS2 environment sourced"
    else
        check_warn "ROS2 not sourced - run: source /opt/ros/jazzy/setup.bash"
    fi
else
    check_fail "ROS2 Jazzy not found"
fi
echo ""

# Check 2: Workspace Structure
echo -e "${BLUE}[2] Workspace Structure${NC}"
WORKSPACE_DIR="${HOME}/pragati_ros2"

if [ -d "$WORKSPACE_DIR" ]; then
    check_pass "Workspace directory exists"
else
    check_fail "Workspace directory not found: $WORKSPACE_DIR"
fi

if [ -d "$WORKSPACE_DIR/src" ]; then
    check_pass "Source directory exists"
    
    # Count packages
    PKG_COUNT=$(find "$WORKSPACE_DIR/src" -name "package.xml" | wc -l)
    if [ "$PKG_COUNT" -ge 5 ]; then
        check_pass "Found $PKG_COUNT packages"
    else
        check_warn "Only found $PKG_COUNT packages (expected 7)"
    fi
else
    check_fail "Source directory not found"
fi

if [ -d "$WORKSPACE_DIR/config" ]; then
    check_pass "Config directory exists"
else
    check_warn "Config directory not found"
fi

if [ -f "$WORKSPACE_DIR/build.sh" ]; then
    check_pass "Build script exists"
else
    check_fail "build.sh not found"
fi
echo ""

# Check 3: Build Status
echo -e "${BLUE}[3] Build Status${NC}"
if [ -d "$WORKSPACE_DIR/install" ]; then
    check_pass "Install directory exists"
    
    # Check for built packages
    if [ -f "$WORKSPACE_DIR/install/setup.bash" ]; then
        check_pass "Setup script exists"
    else
        check_warn "install/setup.bash not found"
    fi
else
    check_warn "Install directory not found - need to build"
    echo -e "     ${YELLOW}Run: cd $WORKSPACE_DIR && ./build.sh vehicle${NC}"
fi
echo ""

# Check 4: System Dependencies
echo -e "${BLUE}[4] System Dependencies${NC}"

# Colcon
if command -v colcon &> /dev/null; then
    check_pass "colcon build tool installed"
else
    check_fail "colcon not found"
fi

# CAN utilities
if command -v cansend &> /dev/null; then
    check_pass "CAN utilities installed"
else
    check_warn "CAN utilities not found (install: sudo apt install can-utils)"
fi

# Python packages
if python3 -c "import cv2" 2>/dev/null; then
    check_pass "OpenCV (cv2) installed"
else
    check_warn "OpenCV not found (install: sudo apt install python3-opencv)"
fi

# GPIO
if [ -d "/sys/class/gpio" ]; then
    check_pass "GPIO interface available"
else
    check_warn "GPIO interface not found"
fi
echo ""

# Check 5: Hardware Interfaces
echo -e "${BLUE}[5] Hardware Interfaces${NC}"

# CAN interface
if ip link show can0 &> /dev/null; then
    check_pass "CAN interface (can0) exists"
    
    # Check if up
    if ip link show can0 | grep -q "UP"; then
        check_pass "CAN interface is UP"
    else
        check_warn "CAN interface is DOWN (run: sudo ip link set can0 up type can bitrate 500000)"
    fi
else
    check_warn "CAN interface (can0) not found - check /boot/firmware/config.txt"
fi

# SPI (required for MCP2515 CAN controller)
if ls /dev/spi* &> /dev/null; then
    check_pass "SPI interface available"
else
    check_warn "SPI not found - enable in raspi-config"
fi
echo ""

# Check 6: Network
echo -e "${BLUE}[6] Network Configuration${NC}"

# Check localhost
if ping -c 1 -W 1 localhost &> /dev/null; then
    check_pass "Localhost reachable"
else
    check_warn "Localhost not reachable"
fi

# Check ROS_DOMAIN_ID
if [ -n "$ROS_DOMAIN_ID" ]; then
    check_pass "ROS_DOMAIN_ID set to $ROS_DOMAIN_ID"
else
    check_warn "ROS_DOMAIN_ID not set (nodes will use default domain 0)"
fi
echo ""

# Check 7: Permissions
echo -e "${BLUE}[7] User Permissions${NC}"

# GPIO group
if groups | grep -q gpio; then
    check_pass "User in 'gpio' group"
else
    check_warn "User not in 'gpio' group (run: sudo usermod -a -G gpio $USER)"
fi

# Dialout group (for serial/CAN)
if groups | grep -q dialout; then
    check_pass "User in 'dialout' group"
else
    check_warn "User not in 'dialout' group (run: sudo usermod -a -G dialout $USER)"
fi
echo ""

# Check 8: System Resources
echo -e "${BLUE}[8] System Resources${NC}"

# Memory
TOTAL_MEM=$(free -m | awk 'NR==2{print $2}')
AVAIL_MEM=$(free -m | awk 'NR==2{print $7}')

if [ "$TOTAL_MEM" -ge 3500 ]; then
    check_pass "Total RAM: ${TOTAL_MEM}MB"
else
    check_warn "Low RAM: ${TOTAL_MEM}MB (recommended: 4GB+)"
fi

if [ "$AVAIL_MEM" -ge 1000 ]; then
    check_pass "Available RAM: ${AVAIL_MEM}MB"
else
    check_warn "Low available RAM: ${AVAIL_MEM}MB"
fi

# Disk space
DISK_AVAIL=$(df -h . | awk 'NR==2{print $4}')
check_pass "Available disk: $DISK_AVAIL"

# Temperature
if command -v vcgencmd &> /dev/null; then
    TEMP=$(vcgencmd measure_temp | cut -d= -f2)
    check_pass "CPU Temperature: $TEMP"
fi
echo ""

# Summary
echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                    Verification Summary                        ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✓ All checks passed!${NC}"
    echo ""
    echo -e "${BLUE}Ready to build and run:${NC}"
    echo "  1. cd ~/pragati_ros2"
    echo "  2. source /opt/ros/jazzy/setup.bash"
    echo "  3. ./build.sh vehicle"
    echo "  4. source install/setup.bash"
    echo "  5. ros2 launch vehicle_control vehicle_complete.launch.py"
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}⚠ Verification completed with $WARNINGS warning(s)${NC}"
    echo ""
    echo "System should work but some features may not be available."
    echo "Review warnings above and fix if needed."
else
    echo -e "${RED}✗ Verification failed with $ERRORS error(s) and $WARNINGS warning(s)${NC}"
    echo ""
    echo "Please fix errors above before proceeding."
    exit 1
fi
echo ""
