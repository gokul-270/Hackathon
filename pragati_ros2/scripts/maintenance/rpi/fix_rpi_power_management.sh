#!/bin/bash
# Fix Raspberry Pi Power Management Issues
# This script disables WiFi, USB, and NetworkManager power saving
# to prevent frequent disconnections

set -e

echo "=========================================="
echo "Raspberry Pi Power Management Fix"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run with sudo: sudo bash $0${NC}"
    exit 1
fi

echo -e "${YELLOW}[1/5] Fixing NetworkManager WiFi Power Save...${NC}"
# Check if WiFi power save is already off
CURRENT_PS=$(iw dev wlan0 get power_save 2>/dev/null | grep -o 'on\|off' || echo "unknown")
NM_CONFIG="/etc/NetworkManager/conf.d/wifi-powersave.conf"
DESIRED_NM_CONTENT="[connection]
wifi.powersave = 2"

nm_needs_change=false
if [ "$CURRENT_PS" = "off" ] && [ -f "$NM_CONFIG" ] && \
   echo "$DESIRED_NM_CONTENT" | cmp -s "$NM_CONFIG" -; then
    echo -e "${GREEN}  ✓ NetworkManager WiFi power save already configured (skipped)${NC}"
else
    nm_needs_change=true
    mkdir -p /etc/NetworkManager/conf.d
    # Only backup if source content differs
    if [ -f "$NM_CONFIG" ] && ! echo "$DESIRED_NM_CONTENT" | cmp -s "$NM_CONFIG" -; then
        cp -a /etc/NetworkManager/conf.d /etc/NetworkManager/conf.d.bak.$(date +%F-%H%M%S) 2>/dev/null || true
    elif [ ! -f "$NM_CONFIG" ]; then
        cp -a /etc/NetworkManager/conf.d /etc/NetworkManager/conf.d.bak.$(date +%F-%H%M%S) 2>/dev/null || true
    fi

    # Find and fix wifi.powersave settings
    files=$(grep -RIl "wifi\.powersave" /etc/NetworkManager/conf.d 2>/dev/null || true)
    if [ -n "$files" ]; then
        echo "  Found existing config files, updating them..."
        for file in $files; do
            sed -i 's/wifi\.powersave *= *.*/wifi.powersave = 2/g' "$file"
            echo "  Updated: $file"
        done
    else
        echo "  Creating new config file..."
        printf "[connection]\nwifi.powersave = 2\n" > "$NM_CONFIG"
        echo "  Created: $NM_CONFIG"
    fi

    # Restart NetworkManager only if config changed
    echo "  Restarting NetworkManager..."
    systemctl restart NetworkManager
    sleep 3
    echo -e "${GREEN}  ✓ NetworkManager configured${NC}"
fi

# Verify WiFi power save is off
POWER_SAVE=$(iw dev wlan0 get power_save 2>/dev/null | grep -o 'on\|off' || echo "unknown")
echo "  Current WiFi power save: $POWER_SAVE"

echo ""
echo -e "${YELLOW}[2/5] Disabling USB Autosuspend (runtime)...${NC}"
# Check current USB autosuspend value before writing
CURRENT_AUTOSUSPEND=$(cat /sys/module/usbcore/parameters/autosuspend 2>/dev/null || echo "unknown")
if [ "$CURRENT_AUTOSUSPEND" = "-1" ]; then
    echo "  USB autosuspend already set to: $CURRENT_AUTOSUSPEND"
    echo -e "${GREEN}  ✓ USB autosuspend already disabled (skipped)${NC}"
else
    echo -1 > /sys/module/usbcore/parameters/autosuspend
    AUTOSUSPEND=$(cat /sys/module/usbcore/parameters/autosuspend)
    echo "  USB autosuspend set to: $AUTOSUSPEND"
    echo -e "${GREEN}  ✓ USB autosuspend disabled (runtime)${NC}"
fi

echo ""
echo -e "${YELLOW}[3/5] Making USB Autosuspend persistent (kernel parameter)...${NC}"
if [ -f /boot/firmware/cmdline.txt ]; then
    if grep -q 'usbcore\.autosuspend=-1' /boot/firmware/cmdline.txt; then
        echo "  usbcore.autosuspend=-1 already in cmdline.txt"
        echo -e "${GREEN}  ✓ Kernel parameter already configured (skipped)${NC}"
    else
        # Backup only when we're about to change
        cp /boot/firmware/cmdline.txt /boot/firmware/cmdline.txt.bak.$(date +%F-%H%M%S)
        echo "  Backed up: /boot/firmware/cmdline.txt"

        if ! grep -q 'usbcore.autosuspend' /boot/firmware/cmdline.txt; then
            sed -i '1 s/$/ usbcore.autosuspend=-1/' /boot/firmware/cmdline.txt
            echo "  Added: usbcore.autosuspend=-1"
        else
            sed -i 's/usbcore\.autosuspend=[^ ]*/usbcore.autosuspend=-1/' /boot/firmware/cmdline.txt
            echo "  Updated: usbcore.autosuspend=-1"
        fi
        echo -e "${GREEN}  ✓ Kernel parameter configured (will apply after reboot)${NC}"
    fi
else
    echo -e "${RED}  ✗ /boot/firmware/cmdline.txt not found!${NC}"
fi

echo ""
echo -e "${YELLOW}[4/5] Forcing all USB devices to stay on (runtime)...${NC}"
# Force all USB devices to "on" state
count=0
for control_file in /sys/bus/usb/devices/*/power/control; do
    if [ -w "$control_file" ]; then
        echo on > "$control_file" 2>/dev/null || true
        count=$((count + 1))
    fi
done
echo "  Set $count USB devices to 'on' state"
echo -e "${GREEN}  ✓ USB devices configured${NC}"

echo ""
echo -e "${YELLOW}[5/5] Updating /etc/rc.local for persistence...${NC}"
# Desired rc.local content
DESIRED_RC_LOCAL='#!/bin/sh -e
# Disable WiFi power management
iw dev wlan0 set power_save off 2>/dev/null || true

# Keep all USB devices awake
for i in /sys/bus/usb/devices/*/power/control; do
    [ -w "$i" ] && echo on > "$i" 2>/dev/null || true
done

exit 0'

if [ -f /etc/rc.local ] && echo "$DESIRED_RC_LOCAL" | cmp -s /etc/rc.local -; then
    echo -e "${GREEN}  ✓ /etc/rc.local already configured (skipped)${NC}"
else
    # Backup only if file exists and content differs
    if [ -f /etc/rc.local ]; then
        cp /etc/rc.local /etc/rc.local.bak.$(date +%F-%H%M%S)
        echo "  Backed up: /etc/rc.local"
    fi

    echo "$DESIRED_RC_LOCAL" > /etc/rc.local
    chmod +x /etc/rc.local

    # Enable rc-local service if it exists
    if systemctl list-unit-files | grep -q rc-local.service; then
        systemctl enable rc-local.service 2>/dev/null || true
        echo "  Enabled rc-local.service"
    fi

    echo -e "${GREEN}  ✓ /etc/rc.local configured${NC}"
fi

echo ""
echo "=========================================="
echo -e "${GREEN}Power Management Fix Complete!${NC}"
echo "=========================================="
echo ""
echo "Current Status:"
echo "  WiFi Power Save: $(iw dev wlan0 get power_save 2>/dev/null || echo 'unknown')"
echo "  USB Autosuspend: $(cat /sys/module/usbcore/parameters/autosuspend)"
echo "  NetworkManager Config: $(grep -r 'wifi.powersave' /etc/NetworkManager/conf.d/ 2>/dev/null | head -1 || echo 'not found')"
echo ""
echo -e "${YELLOW}IMPORTANT: Reboot required for all changes to take effect!${NC}"
echo ""
echo "After reboot, verify with:"
echo "  iw dev wlan0 get power_save"
echo "  cat /sys/module/usbcore/parameters/autosuspend"
echo "  for i in /sys/bus/usb/devices/*/power/control; do echo \"\$i: \$(cat \$i)\"; done"
echo ""
