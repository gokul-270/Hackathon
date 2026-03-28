#!/bin/bash
################################################################################
# Pragati ROS2 - pigpiod Service Installation Script
# 
# This script installs the pigpiod systemd service for GPIO daemon auto-start.
# 
# Usage: sudo ./install_pigpiod_service.sh
################################################################################

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${1}${2}${NC}"
}

print_status $BLUE "════════════════════════════════════════════════"
print_status $BLUE "  Pragati ROS2 - pigpiod Service Installer"
print_status $BLUE "════════════════════════════════════════════════"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    print_status $RED "❌ This script must be run with sudo"
    echo "   Usage: sudo ./install_pigpiod_service.sh"
    exit 1
fi

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SERVICE_FILE="$SCRIPT_DIR/pigpiod.service"

# Check if pigpiod is installed
if ! command -v pigpiod &> /dev/null; then
    print_status $YELLOW "⚠️  pigpiod not found. Installing..."
    apt-get update
    apt-get install -y pigpio
    print_status $GREEN "✅ pigpiod installed"
else
    print_status $GREEN "✅ pigpiod already installed"
fi

# Check if service file exists
if [ ! -f "$SERVICE_FILE" ]; then
    print_status $RED "❌ Service file not found: $SERVICE_FILE"
    exit 1
fi

print_status $BLUE "📋 Installing pigpiod.service..."

# Copy service file
cp "$SERVICE_FILE" /etc/systemd/system/
print_status $GREEN "✅ Service file copied to /etc/systemd/system/"

# Reload systemd
systemctl daemon-reload
print_status $GREEN "✅ Systemd reloaded"

# Enable service
systemctl enable pigpiod.service
print_status $GREEN "✅ Service enabled (will start on boot)"

# Start service
systemctl start pigpiod.service
print_status $GREEN "✅ Service started"

# Wait a moment for service to fully start
sleep 2

# Check status
echo ""
print_status $BLUE "📊 Service Status:"
print_status $BLUE "═══════════════════"
systemctl status pigpiod.service --no-pager || true

echo ""
print_status $BLUE "🔍 Verification:"
print_status $BLUE "═══════════════════"

# Check if pigpiod process is running
if pgrep -x pigpiod > /dev/null; then
    print_status $GREEN "✅ pigpiod daemon is running"
    print_status $GREEN "   Process: $(ps aux | grep -v grep | grep pigpiod)"
else
    print_status $RED "❌ pigpiod daemon is NOT running"
    echo ""
    print_status $YELLOW "Check logs with:"
    echo "   sudo journalctl -u pigpiod.service -n 50"
    exit 1
fi

echo ""
print_status $GREEN "════════════════════════════════════════════════"
print_status $GREEN "  ✅ Installation Complete!"
print_status $GREEN "════════════════════════════════════════════════"
echo ""
print_status $BLUE "📝 Next Steps:"
echo ""
echo "1. Test GPIO access from regular user (non-root):"
echo "   python3 -c \"import pigpio; pi=pigpio.pi(); print('Connected:', pi.connected)\""
echo ""
echo "2. View service logs:"
echo "   sudo journalctl -u pigpiod.service -f"
echo ""
echo "3. Reboot and verify auto-start:"
echo "   sudo reboot"
echo "   sudo systemctl status pigpiod.service"
echo ""
print_status $BLUE "📖 For more information, see: systemd/README.md"
echo ""
