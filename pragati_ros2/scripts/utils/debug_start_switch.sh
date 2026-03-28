#!/bin/bash
# Debug START_SWITCH issue

echo "=== START_SWITCH Debug ==="
echo ""

source /opt/ros/jazzy/setup.bash
source install/setup.bash

echo "1. Checking topic info..."
ros2 topic info /start_switch/command
echo ""

echo "2. Checking who's subscribed..."
ros2 topic list -v | grep start_switch
echo ""

echo "3. Publishing START command (watch yanthra_move terminal)..."
echo "   You should see: '🎯 START_SWITCH command received via topic!'"
ros2 topic pub --once /start_switch/command std_msgs/Bool "data: true"
echo ""

echo "4. Waiting 2 seconds..."
sleep 2

echo "5. Publishing again..."
ros2 topic pub --once /start_switch/command std_msgs/Bool "data: true"
echo ""

echo "Done! Check yanthra_move terminal for the message."
