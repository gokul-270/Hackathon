#!/bin/bash
# RPi Pre-Test Setup - Enable C++ DepthAI Integration
# 
# This script must be run on the Raspberry Pi BEFORE hardware testing
# to enable direct camera acquisition with C++ DepthAI API.
#
# Date: 2025-10-29
# Issue Fix: Detection was taking 7-8s due to Python wrapper overhead
# Target: Reduce to 100-150ms with C++ direct acquisition

set -e  # Exit on error

echo "==========================================================="
echo "RPi Setup: Enable C++ DepthAI Integration"
echo "==========================================================="
echo ""
echo "This will:"
echo "  1. Install DepthAI C++ libraries"
echo "  2. Rebuild cotton_detection_ros2 with DepthAI support"
echo "  3. Verify the installation"
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

echo ""
echo "Step 1: Installing DepthAI packages..."
echo "---------------------------------------"
sudo apt update
sudo apt install -y ros-jazzy-depthai ros-jazzy-depthai-bridge

if [ $? -ne 0 ]; then
    echo "❌ Failed to install DepthAI packages"
    exit 1
fi

echo "✅ DepthAI packages installed"
echo ""

echo "Step 2: Verifying DepthAI installation..."
echo "-----------------------------------------"
dpkg -l | grep depthai
echo ""

echo "Step 3: Rebuilding cotton_detection_ros2..."
echo "--------------------------------------------"
cd ~/pragati_ros2

# Clean build artifacts
rm -rf build/cotton_detection_ros2 install/cotton_detection_ros2

# Build with DepthAI enabled
colcon build \
    --packages-select cotton_detection_ros2 \
    --cmake-args -DHAS_DEPTHAI=ON \
    --allow-overriding cotton_detection_ros2

if [ $? -ne 0 ]; then
    echo "❌ Build failed!"
    exit 1
fi

echo "✅ Build successful"
echo ""

echo "Step 4: Sourcing workspace..."
echo "------------------------------"
source install/setup.bash
echo "✅ Workspace sourced"
echo ""

echo "Step 5: Verifying DepthAI manager library..."
echo "---------------------------------------------"
if [ -f "install/cotton_detection_ros2/lib/libdepthai_manager.so" ]; then
    echo "✅ DepthAI manager library found"
else
    echo "❌ DepthAI manager library NOT found!"
    echo "   Build may have failed or HAS_DEPTHAI was not enabled"
    exit 1
fi
echo ""

echo "Step 6: Testing DepthAI hardware detection..."
echo "----------------------------------------------"
echo "Running: ros2 run cotton_detection_ros2 depthai_manager_hardware_test"
echo ""

timeout 10s ros2 run cotton_detection_ros2 depthai_manager_hardware_test || {
    echo ""
    echo "⚠️  DepthAI hardware test timed out or failed"
    echo "   This is normal if camera is not connected yet"
    echo "   Connect the OAK-D camera and run test manually:"
    echo "   ros2 run cotton_detection_ros2 depthai_manager_hardware_test"
}

echo ""
echo "=========================================================="
echo "✅ Setup Complete!"
echo "=========================================================="
echo ""
echo "Performance expectations:"
echo "  Before: 7-8 seconds per detection (Python wrapper)"
echo "  After:  100-150ms per detection (C++ direct)"
echo "  Speedup: 50-80x faster!"
echo ""
echo "Next steps:"
echo "  1. Connect OAK-D Lite camera"
echo "  2. Verify camera detection:"
echo "     lsusb | grep 03e7"
echo "     ros2 run cotton_detection_ros2 depthai_manager_hardware_test"
echo ""
echo "  3. Launch cotton detection:"
echo "     ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py"
echo ""
echo "  4. Run hardware tests:"
echo "     Follow HARDWARE_TEST_PLAN_2025-10-28.md"
echo ""
