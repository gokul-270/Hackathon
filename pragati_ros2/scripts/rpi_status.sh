#!/bin/bash
################################################################################
# File: rpi_status.sh
# Purpose: Quick health check for RPi connectivity and status
# Part of: Pragati Cotton Picker - Generic Ubuntu Development Setup
#
# Created: 2025-02-03
# Version: 1.0.0
#
# Usage:
#   ./scripts/rpi_status.sh [hostname_or_ip]
#   ./scripts/rpi_status.sh rpi
#   ./scripts/rpi_status.sh 192.168.137.238
#
# Exit Codes:
#   0 - RPi is reachable and healthy
#   1 - RPi is unreachable or has issues
################################################################################

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${1:-rpi}"
TIMEOUT=5

# Source RPi bridge if in WSL
if [ -f "${SCRIPT_DIR}/rpi-wsl-bridge.sh" ]; then
    source "${SCRIPT_DIR}/rpi-wsl-bridge.sh" 2>/dev/null || true
    create_rpi_ssh_wrappers 2>/dev/null || true
fi

################################################################################
# Status Checks
################################################################################

echo "========================================"
echo " RPi Status Check"
echo "========================================"
echo "Target: $TARGET"
echo "Timeout: ${TIMEOUT}s"
echo ""

# Check 1: Network connectivity
echo -n "Network (ping)....... "
if ping -c 1 -W "$TIMEOUT" "$TARGET" &>/dev/null; then
    echo -e "${GREEN}✅ OK${NC}"
    NETWORK_OK=true
else
    echo -e "${RED}❌ FAIL${NC}"
    NETWORK_OK=false
fi

if [ "$NETWORK_OK" = false ]; then
    echo ""
    echo -e "${RED}Cannot reach RPi at $TARGET${NC}"
    echo "Check:"
    echo "  1. RPi is powered on"
    echo "  2. Network connection (WiFi/Ethernet)"
    echo "  3. IP address is correct"
    exit 1
fi

# Check 2: SSH connectivity
echo -n "SSH access........... "
if ssh -o ConnectTimeout="$TIMEOUT" -o BatchMode=yes -o StrictHostKeyChecking=no "$TARGET" "echo OK" &>/dev/null; then
    echo -e "${GREEN}✅ OK${NC}"
    SSH_OK=true
else
    echo -e "${RED}❌ FAIL${NC}"
    SSH_OK=false
fi

if [ "$SSH_OK" = false ]; then
    echo ""
    echo -e "${YELLOW}SSH connection failed${NC}"
    echo "Try:"
    echo "  ssh-copy-id $TARGET"
    exit 1
fi

# Check 3: Hostname & IP
echo -n "Hostname/IP.......... "
HOSTNAME=$(ssh -o ConnectTimeout="$TIMEOUT" "$TARGET" "hostname" 2>/dev/null || echo "Unknown")
IP=$(ssh -o ConnectTimeout="$TIMEOUT" "$TARGET" "hostname -I | awk '{print \$1}'" 2>/dev/null || echo "Unknown")
echo -e "${GREEN}$HOSTNAME${NC} / ${BLUE}$IP${NC}"

# Check 4: System load
echo -n "System load.......... "
LOAD=$(ssh -o ConnectTimeout="$TIMEOUT" "$TARGET" "uptime | awk -F'load average:' '{print \$2}'" 2>/dev/null || echo "Unknown")
echo -e "${BLUE}$LOAD${NC}"

# Check 5: Memory
echo -n "Memory (available)... "
MEM=$(ssh -o ConnectTimeout="$TIMEOUT" "$TARGET" "free -h | grep Mem | awk '{print \$7}'" 2>/dev/null || echo "Unknown")
echo -e "${BLUE}$MEM${NC}"

# Check 6: Disk space
echo -n "Disk space (/)....... "
DISK=$(ssh -o ConnectTimeout="$TIMEOUT" "$TARGET" "df -h / | tail -1 | awk '{print \$4 \" (\" \$5 \" used)\"}'" 2>/dev/null || echo "Unknown")
if [[ "$DISK" == *9[0-9]%* ]] || [[ "$DISK" == *100%* ]]; then
    echo -e "${RED}$DISK ⚠️${NC}"
else
    echo -e "${GREEN}$DISK${NC}"
fi

# Check 7: ROS2
echo -n "ROS2................. "
ROS2_VER=$(ssh -o ConnectTimeout="$TIMEOUT" "$TARGET" "ros2 --version 2>/dev/null" || echo "")
if [ -n "$ROS2_VER" ]; then
    echo -e "${GREEN}✅ $ROS2_VER${NC}"
else
    echo -e "${YELLOW}❌ Not installed${NC}"
fi

# Check 8: Python
echo -n "Python............... "
PYTHON_VER=$(ssh -o ConnectTimeout="$TIMEOUT" "$TARGET" "python3 --version 2>/dev/null" || echo "Unknown")
echo -e "${BLUE}$PYTHON_VER${NC}"

# Check 9: Critical services
echo -n "pigpiod service...... "
PIGPIO=$(ssh -o ConnectTimeout="$TIMEOUT" "$TARGET" "systemctl is-active pigpiod 2>/dev/null" || echo "unknown")
if [ "$PIGPIO" = "active" ]; then
    echo -e "${GREEN}✅ Active${NC}"
elif [ "$PIGPIO" = "inactive" ]; then
    echo -e "${YELLOW}⚠️  Inactive${NC}"
else
    echo -e "${YELLOW}❌ $PIGPIO${NC}"
fi

# Check 10: Project directory
echo -n "Project directory.... "
if ssh -o ConnectTimeout="$TIMEOUT" "$TARGET" "[ -d ~/pragati_ros2 ]" 2>/dev/null; then
    PROJ_SIZE=$(ssh "$TARGET" "du -sh ~/pragati_ros2 2>/dev/null | awk '{print \$1}'" || echo "Unknown")
    echo -e "${GREEN}✅ Exists${NC} (${BLUE}$PROJ_SIZE${NC})"
else
    echo -e "${YELLOW}❌ Not found${NC}"
fi

# Check 11: Git status
echo -n "Git status........... "
GIT_BRANCH=$(ssh -o ConnectTimeout="$TIMEOUT" "$TARGET" "cd ~/pragati_ros2 2>/dev/null && git rev-parse --abbrev-ref HEAD 2>/dev/null" || echo "")
if [ -n "$GIT_BRANCH" ]; then
    GIT_COMMIT=$(ssh "$TARGET" "cd ~/pragati_ros2 && git rev-parse --short HEAD 2>/dev/null" || echo "unknown")
    echo -e "${BLUE}$GIT_BRANCH${NC} @ ${BLUE}$GIT_COMMIT${NC}"
else
    echo -e "${YELLOW}Not a git repo${NC}"
fi

echo ""
echo "========================================"
echo -e " ${GREEN}✅ RPi Health Check Complete${NC}"
echo "========================================"
echo ""
echo "Quick commands:"
echo "  ssh $TARGET                    # Connect to RPi"
echo "  ./scripts/rpi_config_snapshot.sh $TARGET  # Full snapshot"
echo "  ./sync.sh --ip $IP --status    # Project sync status"

exit 0
