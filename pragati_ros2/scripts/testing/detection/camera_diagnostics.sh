#!/bin/bash
# Test script for Camera Diagnostics Enhancements
# Run this when OAK-D Lite camera is connected

set -e

echo "================================================"
echo "Camera Diagnostics Enhancement Test"
echo "================================================"
echo ""
echo "This script will:"
echo "  1. Launch cotton detection with DepthAI enabled"
echo "  2. Wait for initialization (shows camera specs)"
echo "  3. Trigger a detection (shows temperature & stats)"
echo ""
echo "Make sure your OAK-D Lite camera is connected!"
echo ""
read -p "Press Enter to continue or Ctrl+C to cancel..."

# Source workspace
cd /home/uday/Downloads/pragati_ros2
source install/setup.bash

echo ""
echo "================================================"
echo "Step 1: Launching Cotton Detection Node"
echo "================================================"
echo ""
echo "Watch for these sections in the output:"
echo "  📋 Camera Specifications"
echo "  📡 Available Sensors"
echo ""

# Launch in background
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py &
LAUNCH_PID=$!

# Wait for node to initialize
echo ""
echo "Waiting for node initialization (20 seconds)..."
sleep 20

if ! ps -p $LAUNCH_PID > /dev/null; then
    echo ""
    echo "❌ Launch failed! Camera may not be connected."
    echo ""
    exit 1
fi

echo ""
echo "================================================"
echo "Step 2: Triggering Detection"
echo "================================================"
echo ""
echo "This will show:"
echo "  📸 Pre-Capture Camera Status"
echo "  🌡️  Temperature"
echo "  📊 FPS"
echo "  And more stats..."
echo ""

# Trigger detection
ros2 service call /cotton_detection/detect cotton_detection_msgs/srv/CottonDetection "{detect_command: 1}"

echo ""
echo "================================================"
echo "Test Complete!"
echo "================================================"
echo ""
echo "Press Ctrl+C to stop the node, or let it run..."
echo ""

# Wait for user interrupt
wait $LAUNCH_PID
