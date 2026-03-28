#!/usr/bin/env bash
#
# CAN Watchdog Installer
# ======================
# Installs CAN auto-recovery watchdog as a system service
# User-independent: works on any Linux system (PC, Raspberry Pi)
#
# Usage:
#   sudo bash install_can_watchdog.sh [interface]
#   sudo bash install_can_watchdog.sh can0
#   sudo bash install_can_watchdog.sh can1
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
INTERFACE="${1:-can0}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

echo -e "${CYAN}======================================================================"
echo "CAN Bus Auto-Recovery Watchdog Installer"
echo "======================================================================"
echo -e "Interface: ${YELLOW}${INTERFACE}${NC}"
echo -e "Project root: ${BLUE}${PROJECT_ROOT}${NC}"
echo -e "======================================================================${NC}"
echo ""

# =============================================================================
# PRE-FLIGHT CHECKS
# =============================================================================

echo -e "${CYAN}[1/8] Pre-flight checks...${NC}"

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}ERROR: This script must be run as root (use sudo)${NC}"
   exit 1
fi

# Check if watchdog script exists
WATCHDOG_SCRIPT="$PROJECT_ROOT/scripts/maintenance/can/can_watchdog.sh"
if [[ ! -f "$WATCHDOG_SCRIPT" ]]; then
    echo -e "${RED}ERROR: Watchdog script not found at: $WATCHDOG_SCRIPT${NC}"
    exit 1
fi

# Check if systemd service file exists
SERVICE_FILE="$PROJECT_ROOT/systemd/can-watchdog@.service"
if [[ ! -f "$SERVICE_FILE" ]]; then
    echo -e "${RED}ERROR: Systemd service file not found at: $SERVICE_FILE${NC}"
    exit 1
fi

echo -e "${GREEN}✓ All required files found${NC}"
echo ""

# =============================================================================
# INSTALL WATCHDOG SCRIPT
# =============================================================================

echo -e "${CYAN}[2/8] Installing watchdog script to system path...${NC}"

# Copy to system-wide location (user-independent)
cp "$WATCHDOG_SCRIPT" /usr/local/sbin/can_watchdog.sh
chmod +x /usr/local/sbin/can_watchdog.sh

echo -e "${GREEN}✓ Installed: /usr/local/sbin/can_watchdog.sh${NC}"
echo ""

# =============================================================================
# INSTALL SYSTEMD SERVICE
# =============================================================================

echo -e "${CYAN}[3/8] Installing systemd service...${NC}"

# Copy service file
cp "$SERVICE_FILE" "/etc/systemd/system/can-watchdog@.service"

echo -e "${GREEN}✓ Installed: /etc/systemd/system/can-watchdog@.service${NC}"
echo ""

# =============================================================================
# CREATE DEFAULT CONFIGURATION
# =============================================================================

echo -e "${CYAN}[4/8] Creating default configuration...${NC}"

# Create global config if doesn't exist
if [[ ! -f /etc/default/can-watchdog ]]; then
    cat > /etc/default/can-watchdog <<'EOF'
# CAN Watchdog Global Configuration
# ==================================
# This file is sourced by all watchdog instances

# Check interval (seconds) - configurable per your needs
# - 0.5 = Very fast recovery, ~0.015% CPU
# - 1.0 = Fast recovery, ~0.012% CPU
# - 1.5 = Balanced (default), ~0.01% CPU
# - 3.0 = Slower but minimal CPU, ~0.005% CPU
CHECK_INTERVAL_SEC=1.5

# Log directory
LOG_DIR=/tmp

# Recovery settings
COOLDOWN_MIN_MS=500
MAX_RECOVERIES_PER_HOUR=20
EXP_BACKOFF_MAX_SEC=60

# Error state handling
RECOVER_ON_ERROR_PASSIVE=yes
CHRONIC_THRESHOLD=5
CHRONIC_WINDOW_SEC=300

# WARNING state monitoring (optional - disabled by default)
# Enable this to log when error counters exceed threshold
# This does NOT trigger recovery, just logs warnings for monitoring
MONITOR_WARNING_STATE=no
WARNING_ERROR_THRESHOLD=100
WARNING_LOG_INTERVAL_SEC=300

# Module and script integration
AUTO_MODPROBE=yes
USE_SETUP_CAN_SH=auto
ON_RECOVERY_HOOK=

# Per-interface defaults (override in can-watchdog-INTERFACE files)
# NOTE: Default bitrate aligned with production configs (500 kbps). Override if your bus is different.
BITRATE_can0=500000
RESTART_MS_can0=100

BITRATE_can1=500000
RESTART_MS_can1=100
EOF
    echo -e "${GREEN}✓ Created: /etc/default/can-watchdog${NC}"
else
    echo -e "${YELLOW}⚠ Config exists: /etc/default/can-watchdog (not overwriting)${NC}"
fi

# Create per-interface config if doesn't exist
INTERFACE_CONFIG="/etc/default/can-watchdog-${INTERFACE}"
if [[ ! -f "$INTERFACE_CONFIG" ]]; then
    cat > "$INTERFACE_CONFIG" <<EOF
# CAN Watchdog Configuration for ${INTERFACE}
# ============================================

# Interface-specific bitrate
BITRATE_${INTERFACE}=500000
RESTART_MS_${INTERFACE}=100

# You can override any global setting here
# CHECK_INTERVAL_SEC=1.0
# RECOVER_ON_ERROR_PASSIVE=no
EOF
    echo -e "${GREEN}✓ Created: $INTERFACE_CONFIG${NC}"
else
    echo -e "${YELLOW}⚠ Config exists: $INTERFACE_CONFIG (not overwriting)${NC}"
fi

echo ""

# =============================================================================
# RELOAD SYSTEMD
# =============================================================================

echo -e "${CYAN}[5/8] Reloading systemd daemon...${NC}"

systemctl daemon-reload

echo -e "${GREEN}✓ Systemd reloaded${NC}"
echo ""

# =============================================================================
# CHECK CAN INTERFACE
# =============================================================================

echo -e "${CYAN}[6/8] Checking CAN interface...${NC}"

if ip link show "$INTERFACE" &>/dev/null; then
    echo -e "${GREEN}✓ Interface $INTERFACE exists${NC}"
    ip -details link show "$INTERFACE" | head -3
else
    echo -e "${YELLOW}⚠ Interface $INTERFACE not found${NC}"
    echo ""
    echo "Possible reasons:"
    echo "  - CAN hardware not connected"
    echo "  - Kernel modules not loaded"
    echo "  - Wrong interface name"
    echo ""

    # Detect Raspberry Pi
    if [[ -f /proc/device-tree/model ]] && grep -qi "raspberry pi" /proc/device-tree/model; then
        echo -e "${BLUE}Raspberry Pi detected!${NC}"
        echo ""
        echo "For MCP2515 CAN HAT, add to /boot/firmware/config.txt (or /boot/config.txt):"
        echo ""
        echo "  dtparam=spi=on"
        echo "  dtoverlay=mcp2515-can0,oscillator=8000000,interrupt=25,spimaxfrequency=1000000"
        echo ""
        echo "  NOTE: 8 MHz is the canonical oscillator value (design decision D10)."
        echo ""
        echo "Then reboot and run this installer again."
        echo ""
    fi

    echo "To load modules manually:"
    echo "  sudo modprobe can"
    echo "  sudo modprobe can_raw"
    echo "  sudo modprobe can_dev"
    echo "  sudo modprobe mcp251x"
    echo ""
fi

echo ""

# =============================================================================
# ENABLE AND START SERVICE
# =============================================================================

echo -e "${CYAN}[7/8] Enabling and starting service...${NC}"

# Enable service
systemctl enable "can-watchdog@${INTERFACE}.service"
echo -e "${GREEN}✓ Service enabled (will start on boot)${NC}"

# Start service
if ip link show "$INTERFACE" &>/dev/null; then
    echo "Starting service..."
    systemctl start "can-watchdog@${INTERFACE}.service"
    sleep 2

    # Check status
    if systemctl is-active --quiet "can-watchdog@${INTERFACE}.service"; then
        echo -e "${GREEN}✓ Service running${NC}"
    else
        echo -e "${YELLOW}⚠ Service failed to start${NC}"
        echo "Check status with: sudo systemctl status can-watchdog@${INTERFACE}.service"
    fi
else
    echo -e "${YELLOW}⚠ Skipping start (interface not available)${NC}"
    echo "Service will start automatically when interface becomes available"
fi

echo ""

# =============================================================================
# SUMMARY
# =============================================================================

echo -e "${CYAN}[8/8] Installation complete!${NC}"
echo ""
echo -e "${GREEN}======================================================================"
echo "CAN Watchdog Installed Successfully"
echo "======================================================================${NC}"
echo ""
echo -e "${YELLOW}Service:${NC}       can-watchdog@${INTERFACE}.service"
echo -e "${YELLOW}Interface:${NC}     $INTERFACE"
echo -e "${YELLOW}Config:${NC}        /etc/default/can-watchdog"
echo -e "${YELLOW}              /etc/default/can-watchdog-${INTERFACE}${NC}"
echo -e "${YELLOW}Log:${NC}           /tmp/can_watchdog_${INTERFACE}.log"
echo -e "${YELLOW}Journald:${NC}      journalctl -u can-watchdog@${INTERFACE}.service -f"
echo ""
echo -e "${BLUE}Management Commands:${NC}"
echo "  sudo systemctl status can-watchdog@${INTERFACE}.service   # Check status"
echo "  sudo systemctl start can-watchdog@${INTERFACE}.service    # Start"
echo "  sudo systemctl stop can-watchdog@${INTERFACE}.service     # Stop"
echo "  sudo systemctl restart can-watchdog@${INTERFACE}.service  # Restart"
echo "  sudo journalctl -u can-watchdog@${INTERFACE}.service -f   # View logs"
echo ""
echo -e "${BLUE}Configuration:${NC}"
echo "  sudo nano /etc/default/can-watchdog-${INTERFACE}  # Edit config"
echo "  sudo systemctl restart can-watchdog@${INTERFACE}.service  # Apply changes"
echo ""
echo -e "${BLUE}Adjust Polling Interval (CPU usage):${NC}"
echo "  Edit /etc/default/can-watchdog-${INTERFACE}"
echo "  Set: CHECK_INTERVAL_SEC=1.0   (faster, ~0.012% CPU)"
echo "       CHECK_INTERVAL_SEC=1.5   (default, ~0.01% CPU)"
echo "       CHECK_INTERVAL_SEC=3.0   (slower, ~0.005% CPU)"
echo ""
echo -e "${GREEN}✓ User-independent: Works for any user on any machine${NC}"
echo -e "${GREEN}✓ Minimal impact: ~0.01% CPU, ~2-5 MB memory${NC}"
echo -e "${GREEN}✓ Auto-recovery: BUS-OFF, ERROR-PASSIVE, DOWN states${NC}"
echo -e "${GREEN}✓ Safety: Rate limiting, backoff, chronic failure detection${NC}"
echo ""
echo -e "${CYAN}======================================================================${NC}"
