#!/bin/bash
# Test script to validate motor availability and diagnostics

cd ~/pragati_ros2
source install/setup.bash

echo "Starting vehicle system..."
ros2 launch vehicle_control vehicle_complete.launch.py > /tmp/launch.log 2>&1 &
LAUNCH_PID=$!

echo "Waiting 12 seconds for initialization..."
sleep 12

echo ""
echo "=========================================="
echo "TESTING MOTOR AVAILABILITY SERVICE"
echo "=========================================="
ros2 service call /vehicle/vehicle_motor_control/get_motor_availability std_srvs/srv/Trigger

echo ""
echo "=========================================="
echo "TESTING VEHICLE DIAGNOSTICS"
echo "=========================================="
ros2 service call /vehicle/vehicle_control_node/diagnostics std_srvs/srv/Trigger

echo ""
echo "=========================================="
echo "CHECKING JOINT STATES"
echo "=========================================="
timeout 2 ros2 topic echo /vehicle/joint_states --once

echo ""
echo "Cleaning up..."
kill $LAUNCH_PID 2>/dev/null
sleep 2
pkill -9 -f "ros2 launch"
pkill -9 -f mg6010_controller_node
pkill -9 -f vehicle_control_node

echo "Test complete!"
