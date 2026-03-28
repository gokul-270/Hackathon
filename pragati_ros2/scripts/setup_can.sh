#!/usr/bin/env bash
# CAN Interface Setup Script for MG6010 Motors
# Usage: sudo ./setup_can.sh [interface] [bitrate] [restart_ms]
# Example: sudo ./setup_can.sh can0 500000 100

set -e

# Default values
INTERFACE="${1:-can0}"
BITRATE="${2:-500000}"
RESTART_MS="${3:-100}"

echo "======================================"
echo "CAN Interface Setup for MG6010 Motors"
echo "======================================"
echo "Interface:   $INTERFACE"
echo "Bitrate:     $BITRATE bps"
echo "Restart-ms:  $RESTART_MS"
echo "Berr-report: on"
echo "======================================"

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "❌ ERROR: This script must be run as root (use sudo)"
    exit 1
fi

# Check if interface exists
if ! ip link show "$INTERFACE" &> /dev/null; then
    echo "⚠️  WARNING: CAN interface $INTERFACE not found"
    echo ""
    echo "Possible reasons:"
    echo "  1. CAN hardware not connected"
    echo "  2. CAN kernel modules not loaded"
    echo "  3. Wrong interface name"
    echo ""
    echo "To load CAN modules:"
    echo "  sudo modprobe can"
    echo "  sudo modprobe can_raw"
    echo "  sudo modprobe vcan  # For virtual CAN (testing)"
    echo ""
    echo "To create virtual CAN (testing only):"
    echo "  sudo ip link add dev vcan0 type vcan"
    echo "  sudo ip link set up vcan0"
    exit 1
fi

# Bring down interface if already up
echo "📉 Bringing down $INTERFACE..."
ip link set "$INTERFACE" down 2>/dev/null || true

# Configure CAN bitrate + auto-restart
# Note:
# - restart-ms enables automatic recovery from BUS-OFF
# - berr-reporting improves visibility into bus errors

echo "⚙️  Configuring CAN: bitrate=$BITRATE restart-ms=$RESTART_MS berr-reporting=on ..."
if ! ip link set "$INTERFACE" type can bitrate "$BITRATE" restart-ms "$RESTART_MS" berr-reporting on; then
    echo "⚠️  WARNING: Failed to set restart-ms/berr-reporting (iproute2 too old?)"
    echo "    Falling back to bitrate-only configuration..."
    if ! ip link set "$INTERFACE" type can bitrate "$BITRATE"; then
        echo "❌ ERROR: Failed to configure CAN bitrate"
        echo "Make sure the interface supports CAN and the bitrate is valid"
        exit 1
    fi
fi

# Bring up interface
echo "📈 Bringing up $INTERFACE..."
if ! ip link set "$INTERFACE" up; then
    echo "❌ ERROR: Failed to bring up CAN interface"
    exit 1
fi

# Verify status
echo ""
echo "✅ CAN Interface Status:"
echo "======================================"
ip -details -statistics link show "$INTERFACE"
echo "======================================"

# Check for CAN utilities
if command -v candump &> /dev/null; then
    echo ""
    echo "✅ can-utils installed"
    echo "To monitor CAN traffic:"
    echo "  candump $INTERFACE"
else
    echo ""
    echo "⚠️  can-utils not installed"
    echo "To install:"
    echo "  sudo apt-get install can-utils"
fi

echo ""
echo "✅ CAN setup complete!"
echo ""
echo "📝 To make this persistent across reboots:"
echo "   - Preferred: install CAN watchdog (auto recovery + reconfigure at boot)"
echo "       sudo bash scripts/maintenance/can/install_can_watchdog.sh $INTERFACE"
echo "   - Or configure CAN in your network config (bitrate only)"

exit 0
