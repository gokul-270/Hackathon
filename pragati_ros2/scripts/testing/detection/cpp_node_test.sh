#!/bin/bash
# Test C++ detection node with fixed ImageManip pipeline

PI_IP="192.168.137.253"
PI_USER="ubuntu"

echo "================================"
echo "C++ Detection Node Test"
echo "================================"
echo ""

# Kill any existing nodes
echo "Stopping any running nodes..."
ssh ${PI_USER}@${PI_IP} "pkill -f cotton_detection" || true
sleep 2

# Start C++ node
echo "Starting C++ detection node..."
ssh ${PI_USER}@${PI_IP} "cd ~/pragati_ros2 && source install/setup.bash && ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py > /tmp/cpp_node.log 2>&1 &"

echo "Waiting for initialization (30s)..."
sleep 30

# Test detection
echo ""
echo "Running detection test..."
ssh ${PI_USER}@${PI_IP} "cd ~/pragati_ros2 && source install/setup.bash && ros2 service call /cotton_detection/detect cotton_detection_msgs/srv/CottonDetection '{detect_command: 1}'"

# Check logs
echo ""
echo "================================"
echo "Node logs (last 50 lines):"
echo "================================"
ssh ${PI_USER}@${PI_IP} "tail -50 /tmp/cpp_node.log"

# Cleanup
echo ""
echo "Stopping node..."
ssh ${PI_USER}@${PI_IP} "pkill -f cotton_detection"

echo ""
echo "✅ Test complete!"
