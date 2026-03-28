#!/bin/bash
# Test script to measure true detection service latency
# Run this on the Raspberry Pi when the detection node is running

set -e

cd ~/pragati_ros2
source install/setup.bash

echo "🔍 Testing Detection Service Latency..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "This test uses a persistent ROS2 client (not CLI) to measure"
echo "true production latency without node instantiation overhead."
echo ""

# Check if detection service is available
echo "📡 Checking if detection service is available..."
if ! ros2 service list | grep -q "/cotton_detection/detect"; then
    echo "❌ Detection service not found!"
    echo "   Please start the detection node first:"
    echo "   ros2 run cotton_detection_ros2 cotton_detection_node"
    exit 1
fi

echo "✅ Detection service found"
echo ""

# Run the persistent client test
echo "🚀 Running latency test (5 calls)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
timeout 60 ros2 run cotton_detection_ros2 test_persistent_client

echo ""
echo "✅ Test completed!"
