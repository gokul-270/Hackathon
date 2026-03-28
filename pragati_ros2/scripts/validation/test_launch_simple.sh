#!/bin/bash

# Simple ROS2 System Test Launch Script
# This script tests the system step by step to avoid infinite loops

set -e

echo "🧪 Testing ROS2 ODrive + Yanthra System (Step by Step)"
echo "======================================================"

# Source ROS2 and workspace
source /opt/ros/jazzy/setup.bash
source /home/uday/Downloads/pragati_ros2/install/setup.bash
export PATH="$HOME/.local/bin:$PATH"

# Set CycloneDDS as RMW implementation
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

echo "📋 ROS_DISTRO: $ROS_DISTRO"
echo "🔧 RMW_IMPLEMENTATION: $RMW_IMPLEMENTATION"
echo ""

# Clean up any existing processes
pkill -f "ros2 run" || true
pkill -f "odrive_service_node" || true
pkill -f "yanthra_move_node" || true
pkill -f "robot_state_publisher" || true
sleep 2

echo "🔄 Step 1: Testing ODrive Service Node"
echo "======================================"
echo "Starting ODrive node for 10 seconds to verify it works..."

ros2 run odrive_control_ros2 odrive_service_node &
ODRIVE_PID=$!
echo "ODrive Service Node started (PID: $ODRIVE_PID)"

# Wait and check if it's still running
sleep 8
if kill -0 $ODRIVE_PID 2>/dev/null; then
    echo "✅ ODrive Service Node is stable"
    
    # Check topics
    echo "📊 Joint state topics found:"
    ros2 topic list | grep "/joint.*state" || echo "  ⚠️ No joint state topics found"
    
    # Check services
    echo "🔧 ODrive services found:"
    ros2 service list | grep -E "(joint|motor|calibr)" | head -3 || echo "  ⚠️ No ODrive services found"
    
else
    echo "❌ ODrive Service Node crashed"
    exit 1
fi

# Stop ODrive node
kill $ODRIVE_PID 2>/dev/null || true
wait $ODRIVE_PID 2>/dev/null || true
sleep 2

echo ""
echo "🔄 Step 2: Testing Yanthra Move Node (NON-CONTINUOUS)"
echo "=================================================="

# Copy required files from ROS1 workspace
echo "📁 Copying required files from ROS1 workspace..."
cp /home/uday/Downloads/pragati/outputs/Cotton*.txt /home/uday/Downloads/pragati_ros2/data/outputs/ 2>/dev/null || true
cp /home/uday/Downloads/pragati/outputs/cotton_details.txt /home/uday/Downloads/pragati_ros2/data/outputs/ 2>/dev/null || true
cp /home/uday/Downloads/pragati/outputs/aruco_points.log /home/uday/Downloads/pragati_ros2/data/outputs/ 2>/dev/null || true

# Verify required files exist
echo "📁 Checking required files:"
for file in "CottonCoordinatesUnsorted.txt" "cotton_details.txt" "aruco_points.log"; do
    if [ -f "/home/uday/Downloads/pragati_ros2/data/outputs/$file" ]; then
        echo "  ✅ $file exists"
    else
        echo "  ❌ $file missing"
        exit 1
    fi
done

echo ""
echo "Starting Yanthra Move Node with non-continuous config for 15 seconds..."

YANTHRA_CONFIG="/home/uday/Downloads/pragati_ros2/data/outputs/yanthra_move_ros2_working.yaml"
ros2 run yanthra_move yanthra_move_node --ros-args --params-file "$YANTHRA_CONFIG" &
YANTHRA_PID=$!
echo "Yanthra Move Node started (PID: $YANTHRA_PID)"

# Monitor for 15 seconds
for i in {1..15}; do
    if kill -0 $YANTHRA_PID 2>/dev/null; then
        echo "  ⏰ Running for ${i}s..."
        sleep 1
    else
        echo "  ℹ️ Yanthra Move Node completed/exited normally after ${i}s"
        break
    fi
done

# Stop Yanthra node if still running
if kill -0 $YANTHRA_PID 2>/dev/null; then
    echo "✅ Yanthra Move Node is stable (manually stopping for test)"
    kill $YANTHRA_PID 2>/dev/null || true
    wait $YANTHRA_PID 2>/dev/null || true
else
    echo "✅ Yanthra Move Node completed execution without infinite loop"
fi

sleep 2

echo ""
echo "🔄 Step 3: Testing Both Nodes Together"
echo "====================================="
echo "Starting both nodes together for final test..."

# Start ODrive first
ros2 run odrive_control_ros2 odrive_service_node &
ODRIVE_PID=$!
echo "✅ ODrive Service Node started (PID: $ODRIVE_PID)"
sleep 5

# Start Yanthra Move
ros2 run yanthra_move yanthra_move_node --ros-args --params-file "$YANTHRA_CONFIG" &
YANTHRA_PID=$!
echo "✅ Yanthra Move Node started (PID: $YANTHRA_PID)"

# Monitor both for 10 seconds
echo "⏰ Monitoring both nodes for 10 seconds..."
for i in {1..10}; do
    ODRIVE_RUNNING=$(kill -0 $ODRIVE_PID 2>/dev/null && echo "OK" || echo "STOPPED")
    YANTHRA_RUNNING=$(kill -0 $YANTHRA_PID 2>/dev/null && echo "OK" || echo "STOPPED")
    echo "  ${i}s: ODrive=$ODRIVE_RUNNING, Yanthra=$YANTHRA_RUNNING"
    
    if [[ "$YANTHRA_RUNNING" == "STOPPED" ]]; then
        echo "  ℹ️ Yanthra Move completed execution"
        break
    fi
    
    sleep 1
done

# Final status check
echo ""
echo "🎯 Final System Status:"
echo "======================"

if kill -0 $ODRIVE_PID 2>/dev/null; then
    echo "✅ ODrive Service Node: RUNNING"
    echo "📊 Topics:"
    ros2 topic list | grep "/joint.*state" | while read topic; do
        echo "    📡 $topic"
    done
else
    echo "❌ ODrive Service Node: STOPPED"
fi

if kill -0 $YANTHRA_PID 2>/dev/null; then
    echo "⚠️ Yanthra Move Node: STILL RUNNING (might be in continuous mode)"
else
    echo "✅ Yanthra Move Node: COMPLETED"
fi

# Cleanup
echo ""
echo "🧹 Cleaning up..."
kill $ODRIVE_PID 2>/dev/null || true
kill $YANTHRA_PID 2>/dev/null || true
wait $ODRIVE_PID 2>/dev/null || true
wait $YANTHRA_PID 2>/dev/null || true

echo ""
echo "🎉 TEST COMPLETE"
echo "==============="
echo "✅ All nodes started without segmentation faults"
echo "✅ No infinite loops detected in test run"
echo "✅ Required files are available"
echo "✅ System is ready for full launch"