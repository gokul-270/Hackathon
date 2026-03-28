#!/bin/bash

# ROS2 System Cleanup Script
# Ensures a clean state before running tests

echo "🧹 Cleaning up ROS2 processes..."

# Kill all ROS2 related processes
pkill -f "ros2" 2>/dev/null || true
pkill -f "ARM_client" 2>/dev/null || true
pkill -f "yanthra_move" 2>/dev/null || true
pkill -f "odrive_service" 2>/dev/null || true
pkill -f "joint_state_publisher" 2>/dev/null || true
pkill -f "robot_state_publisher" 2>/dev/null || true
pkill -f "CottonDetect" 2>/dev/null || true

# Wait for processes to terminate
sleep 3

# Restart ROS2 daemon to clear stale node references
echo "🔄 Restarting ROS2 daemon..."
ros2 daemon stop 2>/dev/null || true
sleep 2
ros2 daemon start 2>/dev/null || true
sleep 3

# Verify cleanup
node_count=$(ros2 node list 2>/dev/null | wc -l)
if [ "$node_count" -eq 0 ]; then
    echo "✅ System is clean - no nodes running"
else
    echo "⚠️  Warning: $node_count nodes still running:"
    ros2 node list 2>/dev/null || true
fi

echo "🧹 Cleanup complete!"
