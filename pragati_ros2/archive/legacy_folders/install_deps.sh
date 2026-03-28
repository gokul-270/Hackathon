#!/bin/bash

################################################################################
# Pragati ROS2 - Dependency Installation Script
#
# This script installs all required dependencies for the Pragati cotton
# picking robot ROS2 system.
################################################################################

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_status() {
    echo -e "${1}${2}${NC}"
}

print_status $BLUE "🔧 Installing Pragati ROS2 Dependencies..."
print_status $BLUE "=========================================="
echo ""

# Check if ROS2 is installed
if ! command -v ros2 &> /dev/null; then
    print_status $RED "❌ ROS2 not found. Please install ROS2 Jazzy first:"
    echo "   https://docs.ros.org/en/jazzy/Installation.html"
    exit 1
fi

print_status $GREEN "✅ ROS2 installation found"

# Update system
print_status $YELLOW "📦 Updating system packages..."
sudo apt update

# Install ROS2 dependencies
print_status $YELLOW "📦 Installing ROS2 build tools..."
sudo apt install -y \
    python3-colcon-common-extensions \
    python3-rosdep \
    python3-vcstool \
    python3-pip

# Install build optimization tools (HIGHLY RECOMMENDED)
print_status $YELLOW "📦 Installing build optimization tools..."
sudo apt install -y \
    ccache \
    ninja-build \
    mold

if command -v ccache &> /dev/null; then
    ccache --set-config=max_size=5G
    print_status $GREEN "✅ ccache installed (5GB cache, ~98% faster rebuilds)"
fi

if command -v ninja &> /dev/null; then
    print_status $GREEN "✅ Ninja build system installed (~10-15% faster builds)"
fi

# Install hardware dependencies
print_status $YELLOW "📦 Installing hardware dependencies..."
sudo apt install -y \
    can-utils \
    python3-cantools \
    python3-serial \
    python3-opencv-contrib-python \
    pigpio \
    python3-pigpio

# Install Python dependencies
print_status $YELLOW "📦 Installing Python dependencies..."
pip3 install --user \
    cantools \
    python-can \
    opencv-python \
    numpy \
    paho-mqtt

# Install rosdep dependencies
print_status $YELLOW "📦 Installing ROS dependencies..."
cd "$(dirname "$0")"
rosdep update
rosdep install --from-paths src --ignore-src -r -y

# Setup CAN interface (optional)
print_status $YELLOW "🔧 Setting up CAN interface..."
if lsmod | grep -q "can"; then
    print_status $GREEN "✅ CAN kernel modules loaded"
else
    print_status $YELLOW "⚠️  CAN modules not loaded. Enable with:"
    echo "   sudo modprobe can"
    echo "   sudo modprobe can-raw"
    echo "   sudo modprobe can-bcm"
fi

print_status $GREEN "✅ DEPENDENCIES INSTALLED SUCCESSFULLY!"
echo ""
print_status $GREEN "Build Optimizations:"
if command -v ccache &> /dev/null && command -v ninja &> /dev/null; then
    print_status $GREEN "   ccache: faster incremental builds"
    print_status $GREEN "   Ninja: faster build graph evaluation"
    if command -v mold &> /dev/null; then
        print_status $GREEN "   mold: faster linking (2-5x vs GNU ld)"
    fi
else
    print_status $YELLOW "   Install ccache + ninja + mold for dramatic speedup:"
    print_status $YELLOW "      sudo apt install ccache ninja-build mold"
fi
echo ""
print_status $BLUE "📋 Next Steps:"
print_status $BLUE "   1. Build the workspace: ./build.sh fast  (RECOMMENDED)"
print_status $BLUE "   2. Or standard build: ./build.sh"
print_status $BLUE "   3. Launch the system: ros2 launch yanthra_move pragati_complete.launch.py"
print_status $BLUE "   4. Run audit: ./build.sh audit"
echo ""
print_status $BLUE "📖 Build Guide: docs/BUILD_OPTIMIZATION_GUIDE.md"
print_status $BLUE "📖 For Raspberry Pi deployment, see RASPBERRY_PI_DEPLOYMENT.md"
