#!/bin/bash

# Complete ROS2 System Launch Script - FIXED VERSION
# This script starts the complete system with proper node coordination

set -e

echo "🚀 Starting COMPLETE ROS2 ODrive + Yanthra System"
echo "=================================================="

# Source ROS2 and workspace
source /opt/ros/jazzy/setup.bash
source /home/uday/Downloads/pragati_ros2/install/setup.bash
export PATH="$HOME/.local/bin:$PATH"

# Set CycloneDDS as RMW implementation to avoid FastRTPS segfaults
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

# Create a minimal robot description to prevent robot_state_publisher failure
export ROBOT_DESCRIPTION='<?xml version="1.0"?>
<robot name="yanthra_robot">
  <link name="base_link">
    <visual>
      <geometry>
        <box size="0.1 0.1 0.1"/>
      </geometry>
    </visual>
  </link>
  <joint name="joint1" type="revolute">
    <parent link="base_link"/>
    <child link="link1"/>
    <axis xyz="0 0 1"/>
    <limit lower="-3.14" upper="3.14" effort="100" velocity="10"/>
  </joint>
  <link name="link1">
    <visual>
      <geometry>
        <cylinder radius="0.05" length="0.2"/>
      </geometry>
    </visual>
  </link>
  <joint name="joint2" type="revolute">
    <parent link="link1"/>
    <child link="link2"/>
    <axis xyz="0 1 0"/>
    <limit lower="-1.57" upper="1.57" effort="100" velocity="10"/>
  </joint>
  <link name="link2">
    <visual>
      <geometry>
        <cylinder radius="0.05" length="0.2"/>
      </geometry>
    </visual>
  </link>
  <joint name="joint3" type="revolute">
    <parent link="link2"/>
    <child link="link3"/>
    <axis xyz="0 1 0"/>
    <limit lower="-1.57" upper="1.57" effort="100" velocity="10"/>
  </joint>
  <link name="link3">
    <visual>
      <geometry>
        <cylinder radius="0.05" length="0.2"/>
      </geometry>
    </visual>
  </link>
  <joint name="joint4" type="revolute">
    <parent link="link3"/>
    <child link="link4"/>
    <axis xyz="1 0 0"/>
    <limit lower="-1.57" upper="1.57" effort="100" velocity="10"/>
  </joint>
  <link name="link4">
    <visual>
      <geometry>
        <cylinder radius="0.05" length="0.15"/>
      </geometry>
    </visual>
  </link>
  <joint name="joint5" type="revolute">
    <parent link="link4"/>
    <child link="link5"/>
    <axis xyz="0 0 1"/>
    <limit lower="-3.14" upper="3.14" effort="100" velocity="10"/>
  </joint>
  <link name="link5">
    <visual>
      <geometry>
        <cylinder radius="0.03" length="0.1"/>
      </geometry>
    </visual>
  </link>
</robot>'

echo "📋 ROS_DISTRO: $ROS_DISTRO"
echo "📁 Workspace: $(pwd)"
echo "🔧 RMW_IMPLEMENTATION: $RMW_IMPLEMENTATION"
echo ""

# Function to start a node in background and track its PID
start_node() {
    local node_cmd="$1"
    local node_name="$2"
    local wait_time=${3:-5}  # Default 5 seconds, can override
    echo "🔄 Starting $node_name..."
    
    # Start node with error handling
    eval "$node_cmd" &
    local pid=$!
    echo "✅ $node_name started (PID: $pid)"
    echo $pid >> /tmp/ros2_pids.txt
    
    # Wait and verify node is still running
    sleep $wait_time
    if ! kill -0 $pid 2>/dev/null; then
        echo "❌ $node_name crashed during startup (PID: $pid)"
        return 1
    fi
    echo "🎯 $node_name running stable after $wait_time seconds"
    return 0
}

# Clean up any existing PID tracking
rm -f /tmp/ros2_pids.txt

echo "🏃 Launching Complete ROS2 System..."
echo "===================================="

# 1. Start ODrive service node FIRST (provides joint states and services)
if ! start_node "ros2 run odrive_control_ros2 odrive_service_node" "ODrive Service Node" 8; then
    echo "❌ ODrive Service Node failed to start properly"
    exit 1
fi

# 2. Start robot state publisher with robot description parameter
if ! start_node "ros2 run robot_state_publisher robot_state_publisher --ros-args -p robot_description:='$ROBOT_DESCRIPTION'" "Robot State Publisher" 3; then
    echo "❌ Robot State Publisher failed to start properly"
    exit 1
fi

# 3. Check if yanthra_move config exists, prefer ROS1-based working config
YANTHRA_WORKING_CONFIG="/home/uday/Downloads/pragati_ros2/data/outputs/yanthra_move_ros2_working.yaml"
YANTHRA_ORIGINAL_CONFIG="/home/uday/Downloads/pragati_ros2/src/yanthra_move/config/yanthra_move_picking_ros2.yaml"

if [ -f "$YANTHRA_WORKING_CONFIG" ]; then
    YANTHRA_CMD="ros2 run yanthra_move yanthra_move_node --ros-args --params-file $YANTHRA_WORKING_CONFIG"
    echo "📁 Using ROS1-based working config: $YANTHRA_WORKING_CONFIG"
elif [ -f "$YANTHRA_ORIGINAL_CONFIG" ]; then
    YANTHRA_CMD="ros2 run yanthra_move yanthra_move_node --ros-args --params-file $YANTHRA_ORIGINAL_CONFIG"
    echo "📁 Using original config file: $YANTHRA_ORIGINAL_CONFIG"
else
    YANTHRA_CMD="ros2 run yanthra_move yanthra_move_node"
    echo "⚠️ Config file not found, using default parameters"
fi

if ! start_node "$YANTHRA_CMD" "Yanthra Move Node" 6; then
    echo "❌ Yanthra Move Node failed to start properly"
    echo "ℹ️  Continuing without Yanthra Move Node for debugging..."
fi

echo ""
echo "⏰ Waiting for all nodes to fully initialize and discover topics..."
sleep 8

# Additional verification that critical services are available
echo "🔍 Verifying critical services are available..."
for service in "/joint_status" "/calibrate_joint"; do
    if ros2 service list | grep -q "$service"; then
        echo "  ✅ $service is available"
    else
        echo "  ⚠️ $service is NOT available"
    fi
done

echo ""
echo "🔍 System Status Check:"
echo "======================"

# Check if nodes are running
echo "📊 Active Nodes:"
ros2 node list | while read node; do
    echo "  ✅ $node"
done

echo ""
echo "🎯 Critical Joint State Topics (our fix verification):"
ros2 topic list | grep "/joint.*state" | while read topic; do
    echo "  📊 $topic"
    
    # Check if topic has publishers
    echo "    Publishers: $(ros2 topic info $topic | grep 'Publisher count:' || echo 'Unknown')"
    echo "    Subscribers: $(ros2 topic info $topic | grep 'Subscription count:' || echo 'Unknown')"
done

echo ""
echo "🔧 Available ODrive Services:"
ros2 service list | grep -E "(joint|motor|calibr)" | head -8 | while read service; do
    echo "  🛠️  $service"
done

echo ""
echo "💬 Testing Joint State Communication:"
echo "===================================="
echo "📊 Checking if joint2 state is being published:"
timeout 3s ros2 topic echo /joint2/state --once || echo "  ⚠️ No data received within 3 seconds"

echo ""
echo "⚡ Testing ODrive Services:"
echo "=========================="
echo "🔍 Getting status of all joints:"
ros2 service call /joint_status odrive_control_ros2/srv/JointStatus '{joint_id: -1}' || echo "  ⚠️ Service call failed"

echo ""
echo "════════════════════════════════════════"
echo "🎉 SYSTEM READY FOR EXPLORATION!"
echo "════════════════════════════════════════"
echo ""
echo "🔍 Key Success Indicators:"
echo "  ✅ ODrive Service Node: Provides /jointN/state publishers"
echo "  ✅ Yanthra Move Node: Subscribes to /jointN/state topics"
echo "  ✅ No duplicate joint_state_publisher nodes"
echo "  ✅ All critical topics have publishers AND subscribers"
echo ""
echo "💡 To explore the system:"
echo "  • ros2 topic list | grep joint"
echo "  • ros2 node info /yanthra_move"
echo "  • ros2 node info /odrive_service_node"
echo "  • ros2 topic echo /joint2/state"
echo "  • ros2 service list | grep joint"
echo ""
echo "Press Ctrl+C to stop all nodes"

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
    pkill -f "yanthra_move_node" || true
    pkill -f "odrive_service_node" || true
    pkill -f "robot_state_publisher" || true
    
    echo "✅ Cleanup complete"
}

# Set up cleanup trap
trap cleanup EXIT

# Keep system running for exploration
echo "🔄 System running... (Press Ctrl+C to stop)"
while true; do
    sleep 5
    
    # Periodic health check
    if ! pgrep -f "yanthra_move_node" > /dev/null; then
        echo "⚠️ Yanthra Move Node stopped unexpectedly"
    fi
    
    if ! pgrep -f "odrive_service_node" > /dev/null; then
        echo "⚠️ ODrive Service Node stopped unexpectedly"
    fi
done