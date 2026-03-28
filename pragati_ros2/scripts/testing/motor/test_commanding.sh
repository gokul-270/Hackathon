#!/bin/bash
# Test Motor Commanding with Cotton Detection Integration
set -e

echo "=========================================="
echo "MOTOR COMMANDING TEST"
echo "=========================================="

# Source ROS2
source /opt/ros/jazzy/setup.bash
source ~/pragati_ros2/install/setup.bash

# Setup CAN interface
echo "Setting up CAN interface..."
sudo ip link set can0 type can bitrate 500000
sudo ip link set up can0
sleep 1

# Kill any existing processes
echo "Cleaning up existing processes..."
pkill -9 -f "ros2 launch" || true
pkill -9 -f "yanthra_move" || true
pkill -9 -f "cotton_detection" || true
pkill -9 -f "mg6010" || true
sleep 2

# Launch the complete system with simulation disabled
echo "Launching complete system..."
ros2 launch yanthra_move pragati_complete.launch.py \
    use_simulation:=false \
    continuous_operation:=false \
    enable_arm_client:=false > /tmp/motor_commanding_test.log 2>&1 &
SYSTEM_PID=$!

echo "Waiting 30 seconds for system initialization..."
sleep 30

# Check if motor controller is running
echo "Checking motor controller status..."
ros2 node list | grep mg6010 || echo "WARNING: Motor controller not found!"

# Send a test cotton detection
echo ""
echo "Sending test cotton detection at position (0.3, 0.2, 0.1)..."
ros2 topic pub --once /cotton_detection/results cotton_detection_msgs/msg/DetectionResult \
"{
  header: {stamp: {sec: 0, nanosec: 0}, frame_id: 'camera_link'},
  total_count: 1,
  pickable_count: 1,
  positions: [
    {
      position: {x: 0.3, y: 0.2, z: 0.1},
      confidence: 0.95
    }
  ]
}"

sleep 2

# Send start signal
echo "Sending START signal..."
ros2 topic pub --once /start_switch/command std_msgs/Bool "data: true"

echo ""
echo "System running... Monitor logs in separate terminal:"
echo "  tail -f /tmp/motor_commanding_test.log"
echo ""
echo "Watch joint commands:"
echo "  ros2 topic echo /joint3_position_controller/command"
echo "  ros2 topic echo /joint5_position_controller/command"
echo ""
echo "Press Ctrl+C to stop..."

# Wait for user interrupt
wait $SYSTEM_PID || true

echo ""
echo "Test completed. Check logs at /tmp/motor_commanding_test.log"
