#!/bin/bash
# Quick test to validate health score fix

cd ~/pragati_ros2
source install/setup.bash

echo "Cleaning up old processes..."
pkill -9 -f "ros2|mg6010|vehicle_control" 2>/dev/null
sleep 2

echo "Launching vehicle system..."
ros2 launch vehicle_control vehicle_complete.launch.py > /tmp/test_launch.log 2>&1 &
LAUNCH_PID=$!

echo "Waiting 15 seconds for initialization..."
sleep 15

echo ""
echo "===================="
echo "HEALTH SCORE TEST"
echo "===================="
ros2 service call /vehicle/vehicle_control/diagnostics std_srvs/srv/Trigger | grep -E "(health_score|ok_count|Motors:)"

echo ""
echo "Cleaning up..."
kill $LAUNCH_PID 2>/dev/null
sleep 1
pkill -9 -f "ros2|mg6010|vehicle_control" 2>/dev/null

echo "Done!"
