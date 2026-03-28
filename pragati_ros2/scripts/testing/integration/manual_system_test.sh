#!/bin/bash
# Integrated Camera + Motor Test
# This script runs a full system test with OAK-D Lite camera detection and MG6010 motor control

set -e

echo "=========================================="
echo "  Integrated Camera + Motor Test"
echo "=========================================="
echo ""

# Source ROS2 environment
source /opt/ros/jazzy/setup.bash
source install/setup.bash

echo "Step 1: Initialize CAN interface for motors"
sudo ip link set can0 down 2>/dev/null || true
sudo ip link set can0 type can bitrate 500000
sudo ip link set can0 up
echo "✅ CAN interface ready"
echo ""

echo "Step 2: Launch motor controller (Terminal 1)"
echo "Run in separate terminal:"
echo "  ros2 run motor_control_ros2 mg6010_controller_node \\"
echo "    --ros-args --params-file src/motor_control_ros2/config/mg6010_three_motors.yaml"
echo ""
read -p "Press Enter when motor controller is running..."

echo "Step 3: Launch cotton detection with camera (Terminal 2)"
echo "Run in separate terminal:"
echo "  ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \\"
echo "    simulation_mode:=false use_depthai:=true"
echo ""
read -p "Press Enter when cotton detection is running..."

echo "Step 4: Launch yanthra_move (main control)"
echo "Run in separate terminal:"
echo "  ros2 launch yanthra_move yanthra_move_launch.py simulation_mode:=true"
echo ""
read -p "Press Enter when yanthra_move is running..."

echo "Step 5: Send START signal"
echo "Publishing START command..."
ros2 topic pub --once /start_switch/command std_msgs/Bool "data: true"
echo "✅ START signal sent"
echo ""

echo "=========================================="
echo "  System is now running!"
echo "=========================================="
echo ""
echo "Monitor detections:"
echo "  ros2 topic echo /cotton_detection/results"
echo ""
echo "Monitor motor positions:"
echo "  ros2 topic echo /joint_states"
echo ""
echo "Trigger manual detection:"
echo "  ros2 service call /cotton_detection/detect cotton_detection_msgs/srv/CottonDetection '{detect_command: 1}'"
echo ""
echo "Stop everything with Ctrl+C in each terminal"
echo ""
