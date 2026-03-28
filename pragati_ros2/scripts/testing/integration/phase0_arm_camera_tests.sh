#!/bin/bash
# Phase 0 ARM and Camera Tests - December 9, 2025
# Tests that can run NOW with RPi + Camera (no motors needed)

cd ~/pragati_ros2
source install/setup.bash

echo "=================================="
echo "PHASE 0: ARM & CAMERA TESTS"
echo "=================================="
echo ""

# Kill any running processes
echo "Cleaning up old processes..."
pkill -9 -f cotton_detection 2>/dev/null
pkill -9 -f yanthra 2>/dev/null
sleep 2

# Test 0.12: Camera Launch
echo "=== Test 0.12: Camera Launch ==="
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py > /tmp/camera_test.log 2>&1 &
CAM_PID=$!
sleep 8

if ps -p $CAM_PID > /dev/null; then
    echo "✅ Camera node launched successfully"
else
    echo "❌ Camera node failed to launch"
    exit 1
fi

# Test 0.13: Detection Service (no cotton)
echo ""
echo "=== Test 0.13: Detection Service (no cotton) ==="
RESULT=$(ros2 service call /cotton_detection/detect cotton_detection_msgs/srv/CottonDetection "{detect_command: 1}" 2>&1)
if echo "$RESULT" | grep -q "success"; then
    echo "✅ Detection service responds (0 detections expected)"
    echo "$RESULT" | grep "detection_count"
else
    echo "❌ Detection service failed"
fi

# Test 0.15: No-cotton behavior
echo ""
echo "=== Test 0.15: No-cotton Behavior ==="
if ps -p $CAM_PID > /dev/null; then
    echo "✅ Node still running after empty detection - no crash"
else
    echo "❌ Node crashed on empty scene"
fi

# Check camera topics
echo ""
echo "=== Camera Topics ==="
ros2 topic list | grep cotton_detection

# Cleanup
echo ""
echo "Cleaning up..."
kill $CAM_PID 2>/dev/null
sleep 2
pkill -f cotton_detection 2>/dev/null

echo ""
echo "=================================="
echo "PHASE 0 CAMERA TESTS COMPLETE"
echo "=================================="
echo ""
echo "Note: Test 0.14 (Camera auto-reconnect) requires manual USB unplug/replug"
echo "Note: ARM tests (0.19-0.21) require motors or pure simulation mode (TBD)"
