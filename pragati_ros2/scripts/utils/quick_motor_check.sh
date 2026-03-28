#!/bin/bash
# Quick Motor Check Script
# This helps coordinate the multi-terminal testing

echo "================================================"
echo "Quick Motor Test - Coordination Script"
echo "================================================"
echo ""
echo "This script will help you test both motors."
echo "You'll need to open 3 SSH sessions to the RPi."
echo ""
echo "RPi IP: 192.168.137.253"
echo "User: ubuntu"
echo ""
echo "================================================"
echo ""

read -p "Press ENTER when you have 3 terminals open to the RPi..."

echo ""
echo "TERMINAL 1 - Run Motor Controller:"
echo "-----------------------------------"
echo "cd ~/pragati_ros2"
echo "source /opt/ros/jazzy/setup.bash"
echo "source install/setup.bash"
echo "ros2 run motor_control_ros2 mg6010_controller_node --ros-args --params-file src/motor_control_ros2/config/mg6010_two_motors.yaml"
echo ""

read -p "Press ENTER after Terminal 1 shows 'All motors initialized successfully'..."

echo ""
echo "TERMINAL 2 - Monitor Joint States:"
echo "-----------------------------------"
echo "cd ~/pragati_ros2"
echo "source /opt/ros/jazzy/setup.bash"
echo "source install/setup.bash"
echo "ros2 topic echo /joint_states --field position"
echo ""

read -p "Press ENTER after Terminal 2 shows position values..."

echo ""
echo "TERMINAL 3 - Test Motor 1 (Joint 3):"
echo "-------------------------------------"
echo "cd ~/pragati_ros2"
echo "source /opt/ros/jazzy/setup.bash"
echo "source install/setup.bash"
echo "ros2 topic pub --rate 2 --times 6 /joint3_position_controller/command std_msgs/msg/Float64 \"{data: 1.0}\""
echo ""

read -p "Did Motor 1 (joint3) PHYSICALLY MOVE? (y/n): " motor1_moved

echo ""
echo "TERMINAL 3 - Test Motor 2 (Joint 5):"
echo "-------------------------------------"
echo "ros2 topic pub --rate 2 --times 6 /joint5_position_controller/command std_msgs/msg/Float64 \"{data: 0.5}\""
echo ""

read -p "Did Motor 2 (joint5) PHYSICALLY MOVE? (y/n): " motor2_moved

echo ""
echo "================================================"
echo "TEST RESULTS"
echo "================================================"
echo ""

if [ "$motor1_moved" = "y" ]; then
    echo "✅ Motor 1 (joint3, CAN 141): MOVED"
else
    echo "❌ Motor 1 (joint3, CAN 141): DID NOT MOVE"
fi

if [ "$motor2_moved" = "y" ]; then
    echo "✅ Motor 2 (joint5, CAN 143): MOVED"
else
    echo "❌ Motor 2 (joint5, CAN 143): DID NOT MOVE"
fi

echo ""

if [ "$motor2_moved" != "y" ]; then
    echo "⚠️  Motor 2 (joint5) not moving - investigating..."
    echo ""
    echo "Next diagnostic steps:"
    echo "1. Check Terminal 1 - did you see 'Received position command for joint5'?"
    echo "2. Check Terminal 2 - did position[1] value change?"
    echo "3. Run 'candump can0' to check CAN traffic for ID 143"
    echo ""
fi

echo "================================================"
