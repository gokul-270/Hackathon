#!/bin/bash

# Full ROS2 System Launch Script with LazyROS
# This script starts the complete ODrive ROS2 system and launches LazyROS for exploration

set -e

echo "🚀 Starting Full ROS2 ODrive System"
echo "=================================="

# Source ROS2 and workspace
source /opt/ros/jazzy/setup.bash
source /home/uday/Downloads/pragati_ros2/install/setup.bash
export PATH="$HOME/.local/bin:$PATH"

echo "📋 ROS_DISTRO: $ROS_DISTRO"
echo "📁 Workspace: $(pwd)"
echo ""

# Function to start a node in background and track its PID
start_node() {
    local node_cmd="$1"
    local node_name="$2"
    echo "🔄 Starting $node_name..."
    $node_cmd &
    local pid=$!
    echo "✅ $node_name started (PID: $pid)"
    echo $pid >> /tmp/ros2_pids.txt
    sleep 2  # Give each node time to initialize
}

# Clean up any existing PID tracking and processes
rm -f /tmp/ros2_pids.txt
echo "🧹 Ensuring clean startup..."
pkill -f "ros2 run" || true
pkill -f "robot_state_publisher" || true
pkill -f "joint_state_publisher" || true
pkill -f "odrive_service_node" || true
pkill -f "yanthra_move_node" || true
pkill -f "ros2 launch" || true
sleep 2

echo "🏃 Launching ROS2 System with Launch File..."
echo "==========================================="

# Launch all nodes using the ROS2 launch file
echo "🔄 Starting Complete ROS2 System..."
ros2 launch /home/uday/Downloads/pragati_ros2/launch_system.py &
launch_pid=$!
echo "✅ ROS2 System launched (PID: $launch_pid)"
echo $launch_pid >> /tmp/ros2_pids.txt

echo ""
echo "⏰ Waiting for nodes to fully initialize..."
sleep 5

echo ""
echo "🔍 System Status Check:"
echo "======================"

# Check if nodes are running
echo "📊 Active Nodes:"
ros2 node list | while read node; do
    echo "  ✅ $node"
done

echo ""
echo "📡 Active Topics:"
ros2 topic list | grep -E "(joint|state|description)" | while read topic; do
    echo "  📤 $topic"
done

echo ""
echo "🔧 Available Services:"
ros2 service list | grep -E "(joint|motor|calibr)" | head -10 | while read service; do
    echo "  🛠️  $service"
done

echo ""
echo "🎯 Individual Joint State Topics:"
ros2 topic list | grep "/joint.*state" | while read topic; do
    echo "  📊 $topic"
done

echo ""
echo "════════════════════════════════════════"
echo "🖥️  LAUNCHING LAZYROS FOR EXPLORATION"
echo "════════════════════════════════════════"
echo ""
echo "🎮 LazyROS Controls:"
echo "  • Use Arrow Keys to navigate"
echo "  • Tab to switch between panels"
echo "  • Enter to select/drill down"
echo "  • 'q' to quit LazyROS"
echo "  • 'r' to refresh"
echo ""
echo "💡 What to explore in LazyROS:"
echo "  1. Nodes tab - See all running nodes"
echo "  2. Topics tab - Check /jointN/state publishers"
echo "  3. Services tab - Explore ODrive services"
echo "  4. Parameters tab - View node configurations"
echo ""
echo "⚠️  Note: LazyROS may have some compatibility issues with ROS2 Jazzy"
echo "    If it crashes, the ROS2 system will continue running in background"
echo ""

# Function to cleanup background processes
cleanup() {
    echo ""
    echo "🧹 Cleaning up background processes..."
    if [ -f /tmp/ros2_pids.txt ]; then
        while read pid; do
            if kill -0 $pid 2>/dev/null; then
                echo "  🔌 Stopping process $pid"
                kill $pid 2>/dev/null || true
            fi
        done < /tmp/ros2_pids.txt
        rm -f /tmp/ros2_pids.txt
    fi
    
    # Also kill any remaining ROS2 processes
    pkill -f "ros2 run" || true
    pkill -f "robot_state_publisher" || true
    pkill -f "joint_state_publisher" || true
    pkill -f "odrive_service_node" || true
    
    echo "✅ Cleanup complete"
}

# Set up cleanup trap
trap cleanup EXIT

echo "🔄 Starting LazyROS..."
echo ""

# Try to start LazyROS with error handling
if command -v lazyros &> /dev/null; then
    lazyros || {
        echo ""
        echo "⚠️  LazyROS encountered an issue (likely ROS2 Jazzy compatibility)"
        echo "🔍 The ROS2 system is still running. You can explore manually:"
        echo ""
        echo "📋 Manual Commands to try:"
        echo "  ros2 node list"
        echo "  ros2 topic list"
        echo "  ros2 topic echo /joint2/state"
        echo "  ros2 service list"
        echo "  ros2 service call /joint_status odrive_control_ros2/srv/JointStatus '{joint_id: -1}'"
        echo ""
        echo "Press Ctrl+C to stop the system"
        
        # Keep system running for manual exploration
        while true; do
            sleep 1
        done
    }
else
    echo "❌ LazyROS not found in PATH"
    echo "🔧 Try: pipx install lazyros"
    echo ""
    echo "📋 Manual exploration commands:"
    echo "  ros2 node list"
    echo "  ros2 topic list"  
    echo "  ros2 topic echo /joint2/state"
    echo ""
    echo "Press Ctrl+C to stop the system"
    
    # Keep system running
    while true; do
        sleep 1
    done
fi