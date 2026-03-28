#!/bin/bash

# Robust ROS2 Launch Script - Anti-Hang Version
# Addresses hangs by:
# 1. Proper DDS configuration
# 2. Timeouts on all operations
# 3. Progressive node startup
# 4. Health monitoring

set -e

echo "🚀 ROS2 Robust Launch System"
echo "============================"

# Configuration
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_DOMAIN_ID=0
# CycloneDDS config: disables iceoryx shared memory, forces loopback UDP
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
if [ -f "$REPO_ROOT/config/cyclonedds.xml" ]; then
    export CYCLONEDDS_URI="file://$REPO_ROOT/config/cyclonedds.xml"
else
    echo "⚠️  CycloneDDS config not found at $REPO_ROOT/config/cyclonedds.xml"
fi

cd "$REPO_ROOT"
source /opt/ros/jazzy/setup.bash
source install/setup.bash

# Function to start a node with monitoring
start_node_monitored() {
    local package="$1"
    local executable="$2"
    local node_name="$3"
    local extra_args="$4"

    echo "🔄 Starting $node_name..."

    # Start node in background with timeout monitoring
    timeout 30s ros2 run "$package" "$executable" --ros-args -r __node:="$node_name" $extra_args &
    local pid=$!

    # Wait for node to appear in node list
    local attempts=0
    while [ $attempts -lt 10 ]; do
        if timeout 2s ros2 node list | grep -q "$node_name" 2>/dev/null; then
            echo "✅ $node_name started successfully (PID: $pid)"
            echo $pid >> /tmp/robust_ros_pids.txt
            return 0
        fi
        sleep 1
        attempts=$((attempts + 1))
    done

    echo "❌ $node_name failed to start properly"
    kill $pid 2>/dev/null || true
    return 1
}

# Function to verify node health
verify_node_health() {
    local node_name="$1"
    echo "🔍 Verifying $node_name health..."

    if timeout 3s ros2 node list | grep -q "$node_name" 2>/dev/null; then
        echo "   ✅ $node_name is responsive"
        return 0
    else
        echo "   ❌ $node_name is not responsive"
        return 1
    fi
}

# Cleanup function
cleanup() {
    echo ""
    echo "🧹 Cleaning up processes..."
    if [ -f /tmp/robust_ros_pids.txt ]; then
        while read pid; do
            if [ ! -z "$pid" ] && kill -0 $pid 2>/dev/null; then
                echo "  🔌 Stopping process $pid"
                kill $pid 2>/dev/null || true
            fi
        done < /tmp/robust_ros_pids.txt
        rm -f /tmp/robust_ros_pids.txt
    fi

    # Force cleanup any remaining processes
    pkill -f "robot_state_publisher" || true
    pkill -f "joint_state_publisher" || true
    pkill -f "yanthra_move_node" || true

    echo "✅ Cleanup complete"
}

# Set up cleanup on exit
trap cleanup EXIT

# Main execution
main() {
    echo "📋 Pre-launch checks..."

    # Clean up any existing processes
    rm -f /tmp/robust_ros_pids.txt
    pkill -f "robot_state_publisher" || true
    pkill -f "joint_state_publisher" || true
    pkill -f "yanthra_move_node" || true
    pkill -f "ros2-daemon" || true

    sleep 2

    # Test basic ROS2 functionality
    echo "🔧 Testing ROS2 basic functionality..."
    if ! timeout 5s ros2 --help > /dev/null 2>&1; then
        echo "❌ ROS2 basic functionality test failed"
        exit 1
    fi
    echo "✅ ROS2 basic functionality OK"

    echo ""
    echo "🚀 Starting nodes progressively..."
    echo "=================================="

    # Start robot_state_publisher first (provides robot description)
    if start_node_monitored "robot_state_publisher" "robot_state_publisher" "robot_state_publisher" \
        "--param robot_description:=\"$(cat $REPO_ROOT/pragati_robot_description.urdf | tr -d '\n')\""; then
        sleep 2
        verify_node_health "/robot_state_publisher"
    else
        echo "❌ Failed to start robot_state_publisher - aborting"
        exit 1
    fi

    # Start joint_state_publisher
    if start_node_monitored "joint_state_publisher" "joint_state_publisher" "joint_state_publisher" ""; then
        sleep 2
        verify_node_health "/joint_state_publisher"
    else
        echo "⚠️  joint_state_publisher failed - continuing without it"
    fi

    # Start yanthra_move_node with proper parameter
    if start_node_monitored "yanthra_move" "yanthra_move_node" "yanthra_move_node" \
        "--param continous_operation:=false"; then
        sleep 2
        verify_node_health "/yanthra_move_node"
    else
        echo "⚠️  yanthra_move_node failed - continuing without it"
    fi

    echo ""
    echo "📊 System Status Check:"
    echo "======================"

    # Show final status
    echo "Active nodes:"
    timeout 3s ros2 node list 2>/dev/null | while read node; do
        echo "  ✅ $node"
    done

    echo ""
    echo "🎉 System launched successfully!"
    echo "================================"
    echo "💡 The system is now running with robust anti-hang protection"
    echo ""
    echo "🔧 Manual commands you can run:"
    echo "  ros2 node list"
    echo "  ros2 topic list"
    echo ""
    echo "Press Ctrl+C to stop the system"

    # Keep system running
    while true; do
        # Periodically check system health
        if ! timeout 3s ros2 node list > /dev/null 2>&1; then
            echo "⚠️  System health check failed - nodes may be hanging"
        fi
        sleep 10
    done
}

# Execute main function
main "$@"
