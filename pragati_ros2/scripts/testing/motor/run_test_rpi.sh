#!/bin/bash
# Sequential Motor Test Script for RPi
# This script tests both motors one at a time

cd ~/pragati_ros2
source /opt/ros/jazzy/setup.bash
source install/setup.bash

echo "=========================================="
echo "Setting up CAN interface"
echo "=========================================="
sudo ip link set can0 down 2>/dev/null || true
sudo ip link set can0 type can bitrate 500000
sudo ip link set can0 up

if ip link show can0 | grep -q "state UP"; then
    echo "✅ CAN interface is UP"
else
    echo "❌ CAN interface failed"
    exit 1
fi
echo ""

echo "=========================================="
echo "Starting Motor Controller Node"
echo "=========================================="

# Start motor controller in background
# The config file uses 'mg6010_controller' but node is 'mg6010_controller_node'
# We remap the node name to match the config
ros2 run motor_control_ros2 mg6010_controller_node \
  --ros-args -r __node:=mg6010_controller \
  --params-file ~/pragati_ros2/src/motor_control_ros2/config/mg6010_three_motors.yaml &
CONTROLLER_PID=$!

echo "Controller PID: $CONTROLLER_PID"
echo "Waiting for initialization..."
sleep 5

# Check if controller is still running
if ! kill -0 $CONTROLLER_PID 2>/dev/null; then
    echo "❌ Motor controller failed to start"
    exit 1
fi

echo "✅ Motor controller started"
echo ""

# Check joint_states topic
echo "Checking /joint_states topic..."
timeout 3 ros2 topic echo /joint_states --once > /tmp/joint_states_check.txt 2>&1
if [ $? -eq 0 ]; then
    echo "✅ /joint_states is publishing"
    echo ""
    echo "Current joint states:"
    cat /tmp/joint_states_check.txt | grep -A 10 "name:"
else
    echo "⚠️  /joint_states not publishing yet"
fi

echo ""
echo "=========================================="
echo "Testing Motor 1 (Joint 3)"
echo "=========================================="
echo "Sending command: joint3 = 1.0 rad"
echo ""

# Send joint3 command
ros2 topic pub --rate 2 --times 6 /joint3_position_controller/command std_msgs/msg/Float64 "{data: 1.0}" &
CMD_PID=$!

sleep 4

# Check joint states after command
echo ""
echo "Joint states after joint3 command:"
timeout 2 ros2 topic echo /joint_states --once | grep -A 10 "position:"

echo ""
echo "🔍 Did Motor 1 (joint3) move physically? Watch the robot!"
echo "Waiting 5 seconds..."
sleep 5

echo ""
echo "Returning joint3 to 0.0..."
ros2 topic pub --rate 2 --times 6 /joint3_position_controller/command std_msgs/msg/Float64 "{data: 0.0}" &
sleep 4

echo ""
echo "=========================================="
echo "Testing Motor 2 (Joint 5)"
echo "=========================================="
echo "Sending command: joint5 = 0.5 rad"
echo ""

# Send joint5 command
ros2 topic pub --rate 2 --times 6 /joint5_position_controller/command std_msgs/msg/Float64 "{data: 0.5}" &
CMD_PID=$!

sleep 4

# Check joint states after command
echo ""
echo "Joint states after joint5 command:"
timeout 2 ros2 topic echo /joint_states --once | grep -A 10 "position:"

echo ""
echo "🔍 Did Motor 2 (joint5) move physically? Watch the robot!"
echo "Waiting 5 seconds..."
sleep 5

echo ""
echo "Returning joint5 to 0.0..."
ros2 topic pub --rate 2 --times 6 /joint5_position_controller/command std_msgs/msg/Float64 "{data: 0.0}" &
sleep 4

echo ""
echo "=========================================="
echo "Final Joint States"
echo "=========================================="
timeout 2 ros2 topic echo /joint_states --once

echo ""
echo "=========================================="
echo "Stopping Motor Controller"
echo "=========================================="
kill $CONTROLLER_PID 2>/dev/null
wait $CONTROLLER_PID 2>/dev/null

echo ""
echo "=========================================="
echo "Test Complete!"
echo "=========================================="
echo ""
echo "Please report:"
echo "1. Did Motor 1 (joint3) move? YES/NO"
echo "2. Did Motor 2 (joint5) move? YES/NO"
echo "3. Did you see any errors?"
echo ""
