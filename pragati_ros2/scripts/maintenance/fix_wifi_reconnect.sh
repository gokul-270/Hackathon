#!/bin/bash
################################################################################
# WiFi Auto-Reconnect Fix for Raspberry Pi
#
# Fixes the issue where RPi doesn't automatically reconnect to WiFi hotspot
# after the hotspot is restarted (e.g., when Windows PC reboots).
#
# Usage:
#   sudo ./fix_wifi_reconnect.sh
#
# What it does:
#   1. Disables WiFi power saving (prevents missing AP return)
#   2. Configures saved connections for infinite retry autoconnect
################################################################################

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_status() {
    echo -e "${1}${2}${NC}"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_status $RED "❌ Please run as root: sudo $0"
    exit 1
fi

echo ""
print_status $YELLOW "📶 WiFi Auto-Reconnect Fix for Raspberry Pi"
echo "=============================================="
echo ""

# 1. Disable WiFi power saving
print_status $YELLOW "Step 1: Disabling WiFi power saving..."
mkdir -p /etc/NetworkManager/conf.d
cat > /etc/NetworkManager/conf.d/wifi-powersave.conf <<'EOF'
# Disable WiFi power saving for reliable reconnection
# powersave values: 0=default, 1=ignore, 2=disable, 3=enable
[connection]
wifi.powersave = 2
EOF
print_status $GREEN "✅ WiFi power saving disabled"

# Also disable immediately (no reboot needed)
iw dev wlan0 set power_save off 2>/dev/null || true

# 2. Install WiFi reconnect dispatcher script
# NOTE: The dispatcher was causing reconnect loops, so we're removing it.
# The power-save disable + autoconnect settings should be sufficient.
print_status $YELLOW "Step 2: Removing problematic dispatcher (if exists)..."
rm -f /etc/NetworkManager/dispatcher.d/99-wifi-reconnect 2>/dev/null || true
print_status $GREEN "✅ Dispatcher removed (not needed with proper autoconnect settings)"

# 3. Configure existing WiFi connections
print_status $YELLOW "Step 3: Configuring saved WiFi connections..."
FOUND_CONNECTIONS=0
for conn in $(nmcli -t -f NAME,TYPE con show | grep wireless | cut -d: -f1); do
    if [ -n "$conn" ]; then
        nmcli connection modify "$conn" connection.autoconnect yes 2>/dev/null || true
        nmcli connection modify "$conn" connection.autoconnect-retries 0 2>/dev/null || true
        nmcli connection modify "$conn" connection.autoconnect-priority 100 2>/dev/null || true
        print_status $GREEN "  ✅ Configured: $conn"
        FOUND_CONNECTIONS=1
    fi
done

if [ "$FOUND_CONNECTIONS" -eq 0 ]; then
    print_status $YELLOW "  ⚠️  No saved WiFi connections found"
fi

# 4. Restart NetworkManager
print_status $YELLOW "Step 4: Restarting NetworkManager..."
systemctl restart NetworkManager
sleep 2
print_status $GREEN "✅ NetworkManager restarted"

# 5. Verify current connection
echo ""
print_status $YELLOW "Current WiFi status:"
nmcli -t -f DEVICE,STATE,CONNECTION dev status | grep wlan0 || echo "wlan0 not found"

echo ""
print_status $GREEN "=============================================="
print_status $GREEN "✅ WiFi auto-reconnect fix applied!"
print_status $GREEN "=============================================="
echo ""
echo "The RPi will now automatically reconnect when the hotspot restarts."
echo ""
echo "To test:"
echo "  1. Turn off your Windows hotspot"
echo "  2. Wait 5 seconds"
echo "  3. Turn hotspot back on"
echo "  4. RPi should reconnect within ~15-30 seconds"
echo ""
echo "To monitor reconnection:"
echo "  watch -n1 'nmcli -t -f DEVICE,STATE,CONNECTION dev status'"
echo ""
