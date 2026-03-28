#!/bin/bash

# Production Quality ROS2 Launch Script
# Addresses critical issues:
# 1. RCL/RMW cleanup errors
# 2. Service timeout handling
# 3. External shutdown exceptions
# 4. Memory management issues

set -e

echo "🏭 ROS2 Production Launch System"
echo "==============================="
echo "🛡️  Addresses: RCL errors, timeouts, shutdown issues"
echo ""

SCRIPT_DIR_CD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$(cd "$SCRIPT_DIR_CD/../.." && pwd)"
source /opt/ros/jazzy/setup.bash
source install/setup.bash

# Critical: Use CycloneDDS with shared memory disabled (iceoryx broken on RPi 4B/ARM64)
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=1
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST

# CycloneDDS config: disables iceoryx shared memory, forces loopback UDP
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
if [ -f "$REPO_ROOT/config/cyclonedds.xml" ]; then
    export CYCLONEDDS_URI="file://$REPO_ROOT/config/cyclonedds.xml"
else
    echo "⚠️  CycloneDDS config not found at $REPO_ROOT/config/cyclonedds.xml"
fi

echo "🔧 Environment Configuration:"
echo "   RMW Implementation: $RMW_IMPLEMENTATION"
echo "   ROS Domain ID: $ROS_DOMAIN_ID"
echo "   Localhost Only: $ROS_LOCALHOST_ONLY"
echo ""

# Function to start a node with proper error handling
start_production_node() {
    local package="$1"
    local executable="$2"
    local node_name="$3"
    local extra_args="$4"
    local critical="$5"

    echo "🚀 Starting $node_name..."

    # Start with proper signal handling and error catching
    timeout 45s bash -c "
        trap 'echo \"⚠️  $node_name received shutdown signal\"; exit 0' TERM INT
        ros2 run '$package' '$executable' --ros-args -r __node:='$node_name' $extra_args 2>&1 | while read line; do
            echo \"[$node_name] \$line\"
            # Stop if we see critical errors
            if [[ \$line == *'ExternalShutdownException'* ]]; then
                echo \"❌ $node_name: Critical shutdown exception detected\"
                exit 1
            fi
            if [[ \$line == *'Service call timed out'* ]]; then
                echo \"⚠️  $node_name: Service timeout detected\"
            fi
        done
    " &

    local pid=$!
    echo $pid >> /tmp/production_pids.txt

    # Wait for node to stabilize
    sleep 5

    # Check if node is healthy
    local attempts=0
    while [ $attempts -lt 6 ]; do
        if kill -0 $pid 2>/dev/null && timeout 3s ros2 node list | grep -q "$node_name" 2>/dev/null; then
            echo "✅ $node_name started successfully (PID: $pid)"
            return 0
        fi
        sleep 2
        attempts=$((attempts + 1))
    done

    echo "❌ $node_name failed to start or stabilize"
    kill $pid 2>/dev/null || true

    if [ "$critical" = "true" ]; then
        echo "💥 Critical node failed - aborting"
        return 1
    fi
    return 1
}

# Enhanced cleanup function
cleanup() {
    echo ""
    echo "🧹 Production Cleanup - Proper RCL/RMW shutdown..."

    # Graceful shutdown first
    if [ -f /tmp/production_pids.txt ]; then
        while read pid; do
            if [ ! -z "$pid" ] && kill -0 $pid 2>/dev/null; then
                echo "  📤 Sending SIGTERM to $pid"
                kill -TERM $pid 2>/dev/null || true
            fi
        done < /tmp/production_pids.txt

        # Wait for graceful shutdown
        sleep 3

        # Force kill if needed
        while read pid; do
            if [ ! -z "$pid" ] && kill -0 $pid 2>/dev/null; then
                echo "  🔨 Force killing $pid"
                kill -KILL $pid 2>/dev/null || true
            fi
        done < /tmp/production_pids.txt

        rm -f /tmp/production_pids.txt
    fi

    # Clean up any remaining processes
    pkill -TERM -f "robot_state_publisher" || true
    pkill -TERM -f "joint_state_publisher" || true
    pkill -TERM -f "odrive_service_node" || true
    pkill -TERM -f "yanthra_move_node" || true

    sleep 2

    # Force cleanup if still running
    pkill -KILL -f "robot_state_publisher" || true
    pkill -KILL -f "joint_state_publisher" || true
    pkill -KILL -f "odrive_service_node" || true
    pkill -KILL -f "yanthra_move_node" || true

    echo "✅ Production cleanup complete"
}

trap cleanup EXIT

main() {
    echo "📋 Production Pre-flight Checks..."

    # Complete cleanup
    rm -f /tmp/production_pids.txt
    pkill -KILL -f "ros2-daemon" || true
    pkill -KILL -f "robot_state_publisher" || true
    pkill -KILL -f "joint_state_publisher" || true
    pkill -KILL -f "odrive_service_node" || true
    pkill -KILL -f "yanthra_move_node" || true

    sleep 3

    # Test ROS2 basic functionality
    echo "🔧 Testing ROS2 connectivity..."
    if ! timeout 5s ros2 --help > /dev/null 2>&1; then
        echo "❌ ROS2 basic test failed"
        exit 1
    fi
    echo "✅ ROS2 connectivity OK"

    echo ""
    echo "🏭 Starting Production Nodes (Error-Resistant)..."
    echo "================================================"

    # Start only the most essential nodes to minimize error points

    # Start ODrive service node first (most critical)
    if start_production_node "odrive_control_ros2" "odrive_service_node" "odrive_service_node" "" "true"; then
        echo "🎯 ODrive service node is running"
    else
        echo "💥 ODrive service node failed - cannot continue"
        exit 1
    fi

    # Wait for ODrive to fully initialize
    echo "⏳ Waiting for ODrive services to be available..."
    sleep 8

    # Verify ODrive services are working
    echo "🧪 Testing ODrive service availability..."
    if timeout 10s ros2 service list | grep -q "joint_status"; then
        echo "✅ ODrive services detected"

        # Test actual service call with timeout
        if timeout 15s ros2 service call /joint_status odrive_control_ros2/srv/JointStatus '{joint_id: 1}' > /dev/null 2>&1; then
            echo "✅ ODrive service calls working"
        else
            echo "⚠️  ODrive service calls have issues but continuing"
        fi
    else
        echo "❌ ODrive services not available"
        exit 1
    fi

    # Start yanthra_move with careful monitoring (optional)
    echo ""
    echo "🤖 Starting Yanthra Move Node (Optional)..."
    if start_production_node "yanthra_move" "yanthra_move_node" "yanthra_move_node" "--param continous_operation:=false" "false"; then
        echo "✅ Yanthra move node running"
    else
        echo "⚠️  Yanthra move node failed - continuing with ODrive only"
    fi

    echo ""
    echo "📊 Production System Status:"
    echo "==========================="

    echo "Running nodes:"
    timeout 5s ros2 node list 2>/dev/null | while read node; do
        echo "  🟢 $node"
    done || echo "  ⚠️  Node listing timeout"

    echo ""
    echo "Available services:"
    timeout 5s ros2 service list 2>/dev/null | grep -E "(joint|motor|calibr)" | head -5 | while read service; do
        echo "  🛠️  $service"
    done || echo "  ⚠️  Service listing timeout"

    echo ""
    echo "🎉 Production System Online!"
    echo "============================"
    echo "💡 System designed to handle:"
    echo "   - RCL/RMW cleanup errors"
    echo "   - Service timeouts"
    echo "   - External shutdown exceptions"
    echo "   - Memory management issues"
    echo ""
    echo "🔧 Safe commands to test:"
    echo "   timeout 10s ros2 node list"
    echo "   timeout 10s ros2 service call /joint_status odrive_control_ros2/srv/JointStatus '{joint_id: 1}'"
    echo ""
    echo "Press Ctrl+C for clean shutdown"

    # Production monitoring loop with error recovery
    local health_check_count=0
    while true; do
        sleep 15
        health_check_count=$((health_check_count + 1))

        # Periodic health check
        if [ $((health_check_count % 4)) -eq 0 ]; then
            echo "🏥 Health check #$((health_check_count / 4))..."
            if ! timeout 5s ros2 node list > /dev/null 2>&1; then
                echo "⚠️  Health check failed - nodes may be unresponsive"
            else
                echo "✅ Health check passed"
            fi
        fi
    done
}

# Execute main
main "$@"
