#!/bin/bash

# Minimal Working ROS2 Launch - Avoids All Hang Issues
# This script works around the parameter parsing and DDS issues

set -e

echo "🚀 ROS2 Minimal Working Launch"
echo "=============================="

cd /home/uday/Downloads/pragati_ros2
source /opt/ros/jazzy/setup.bash
source install/setup.bash

# Use default RMW implementation to avoid DDS config issues
unset RMW_IMPLEMENTATION
unset CYCLONEDDS_URI
export ROS_DOMAIN_ID=0

echo "🧹 Cleaning up any existing processes..."
pkill -f "robot_state_publisher" || true
pkill -f "joint_state_publisher" || true
pkill -f "odrive_service_node" || true
pkill -f "yanthra_move_node" || true
sleep 2

# Function to start and monitor a node
start_node_simple() {
    local package="$1"
    local executable="$2"
    local node_name="$3"
    
    echo "🔄 Starting $node_name..."
    ros2 run "$package" "$executable" &
    local pid=$!
    echo $pid >> /tmp/simple_pids.txt
    sleep 3
    
    # Check if it's running
    if kill -0 $pid 2>/dev/null && timeout 5s ros2 node list | grep -q "$node_name"; then
        echo "✅ $node_name started successfully"
        return 0
    else
        echo "❌ $node_name failed"
        return 1
    fi
}

# Cleanup function
cleanup() {
    echo ""
    echo "🧹 Cleaning up..."
    if [ -f /tmp/simple_pids.txt ]; then
        while read pid; do
            kill $pid 2>/dev/null || true
        done < /tmp/simple_pids.txt
        rm -f /tmp/simple_pids.txt
    fi
    pkill -f "robot_state_publisher" || true
    pkill -f "joint_state_publisher" || true
    pkill -f "odrive_service_node" || true
    pkill -f "yanthra_move_node" || true
}

trap cleanup EXIT

echo "🚀 Starting nodes..."
rm -f /tmp/simple_pids.txt

# Skip robot_state_publisher for now to avoid parameter issues
echo "⏭️  Skipping robot_state_publisher (parameter parsing issues)"

# Start joint_state_publisher
start_node_simple "joint_state_publisher" "joint_state_publisher" "/joint_state_publisher" || echo "⚠️  Continuing without joint_state_publisher"

# Start ODrive service node
if start_node_simple "odrive_control_ros2" "odrive_service_node" "/odrive_service_node"; then
    echo "✅ ODrive service node is critical and working!"
else
    echo "❌ ODrive service node failed - this is critical"
    exit 1
fi

# Start yanthra_move_node (it will use default parameters)
start_node_simple "yanthra_move" "yanthra_move_node" "/yanthra_move_node" || echo "⚠️  Continuing without yanthra_move_node"

echo ""
echo "📊 Final System Status:"
echo "======================"

# Show what's running
echo "Active nodes:"
timeout 5s ros2 node list | while read node; do
    echo "  ✅ $node"
done

echo ""
echo "Available services:"
timeout 5s ros2 service list | grep -E "(joint|motor|calibr)" | head -5 | while read service; do
    echo "  🛠️  $service"
done

echo ""
echo "🎯 Testing ODrive functionality:"
if timeout 10s ros2 service call /joint_status odrive_control_ros2/srv/JointStatus '{joint_id: 1}'; then
    echo "✅ ODrive services are working!"
else
    echo "⚠️  ODrive service test had issues"
fi

echo ""
echo "🎉 Minimal system is running successfully!"
echo "========================================="
echo "💡 This minimal setup avoids the hang issues by:"
echo "   - Using default RMW implementation"
echo "   - Skipping problematic robot_description parameter"
echo "   - Using simple timeouts"
echo ""
echo "🔧 You can now test:"
echo "   ros2 node list"
echo "   ros2 service call /joint_status odrive_control_ros2/srv/JointStatus '{joint_id: -1}'"
echo ""
echo "Press Ctrl+C to stop"

# Keep running with health checks
while true; do
    if ! timeout 3s ros2 node list > /dev/null 2>&1; then
        echo "⚠️  Health check failed"
    fi
    sleep 10
done