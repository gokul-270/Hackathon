#!/bin/bash
# Set timezone to Asia/Kolkata and enable NTP for clock accuracy
# Required for consistent log timestamps across dev machine and RPi

set -e

echo "=========================================="
echo "Timezone & NTP Configuration"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run with sudo: sudo bash $0"
    exit 1
fi

TARGET_TZ="Asia/Kolkata"

# Get current timezone
current_tz=$(timedatectl show --property=Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null || echo "unknown")
echo "Current timezone: ${current_tz}"

# Set timezone
if [ "$current_tz" = "$TARGET_TZ" ]; then
    echo "Timezone already set to ${TARGET_TZ} -- no change needed"
else
    timedatectl set-timezone "$TARGET_TZ"
    echo "Timezone changed: ${current_tz} -> ${TARGET_TZ}"
fi

# Enable NTP
ntp_status=$(timedatectl show --property=NTP --value 2>/dev/null || echo "unknown")
if [ "$ntp_status" = "yes" ]; then
    echo "NTP already enabled"
else
    timedatectl set-ntp true
    systemctl restart systemd-timesyncd 2>/dev/null || true
    echo "NTP enabled and timesyncd restarted"
fi

echo ""
echo "Current time settings:"
timedatectl status 2>/dev/null | head -5
echo ""
echo "Done!"
echo ""
