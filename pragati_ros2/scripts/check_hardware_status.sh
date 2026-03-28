#!/bin/bash
# Quick Hardware Status Check
# Run on RPi to verify hardware connections

echo "=========================================="
echo "Hardware Status Check - Pragati ROS2"
echo "=========================================="
echo ""

# 1. CAN Interface
echo "1. CAN Interface (for motors):"
if ip link show can0 &>/dev/null; then
    echo "   ✓ CAN0 interface exists"
    ip link show can0 | grep -o "state [A-Z]*" || echo "   State: Unknown"
else
    echo "   ✗ CAN0 not configured"
    echo "   Fix: sudo ip link add dev can0 type can"
    echo "        sudo ip link set can0 up type can bitrate 500000"
fi
echo ""

# 2. USB Camera
echo "2. OAK-D Lite Camera:"
if lsusb | grep -q "03e7"; then
    echo "   ✓ Camera detected on USB"
    lsusb | grep "03e7"
else
    echo "   ✗ Camera not detected"
    echo "   Fix: Check USB connection and power"
fi
echo ""

# 3. Python DepthAI
echo "3. DepthAI Library:"
python3 -c "import depthai as dai; print(f'   ✓ Version: {dai.__version__}')" 2>/dev/null || echo "   ✗ Not installed"
echo ""

# 4. ROS2
echo "4. ROS2 Installation:"
if command -v ros2 &>/dev/null; then
    echo "   ✓ ROS2 available"
    ros2 --version 2>/dev/null || echo "   Version unknown"
else
    echo "   ✗ ROS2 not sourced"
    echo "   Fix: source /opt/ros/jazzy/setup.bash"
fi
echo ""

# 5. Workspace
echo "5. Workspace Status:"
if [ -f "$HOME/pragati_ws/install/setup.bash" ]; then
    echo "   ✓ Workspace built at $HOME/pragati_ws"
    echo "   Built: $(stat -c %y $HOME/pragati_ws/install/setup.bash | cut -d' ' -f1)"
else
    echo "   ✗ Workspace not built"
fi
echo ""

# 6. Cotton Detection Scripts
echo "6. Cotton Detection Scripts:"
WORKING_SCRIPT="$HOME/pragati_ws/src/cotton_detection_ros2/scripts/OakDTools/CottonDetect_WorkingCode_6Apr2023.py"
if [ -f "$WORKING_SCRIPT" ]; then
    echo "   ✓ Working code found: CottonDetect_WorkingCode_6Apr2023.py"
else
    echo "   ✗ Working code not found"
fi
echo ""

# Summary
echo "=========================================="
echo "Quick Action Items:"
echo "=========================================="
echo ""
echo "Next steps based on what's connected:"
echo ""
echo "For MOTORS:"
echo "  - CAN interface is UP"
echo "  - Need to rebuild workspace: cd ~/pragati_ws && colcon build"
echo "  - Then test motors with existing scripts"
echo ""
echo "For CAMERA:"
echo "  - USB detected but DepthAI access needs verification"
echo "  - Try running working Python script directly"
echo "  - Or rebuild workspace with latest code"
echo ""
echo "RECOMMENDATION:"
echo "  Focus on getting ONE subsystem working first (motors OR camera)"
echo "  Don't waste time on both simultaneously"
echo ""
