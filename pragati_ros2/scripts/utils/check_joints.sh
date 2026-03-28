#!/bin/bash
# Check Joint States (Encoder Feedback) Script

cd ~/pragati_ros2
source /opt/ros/jazzy/setup.bash
source install/setup.bash

echo "=========================================="
echo "Starting Motor Controller"
echo "=========================================="

# Setup CAN
sudo ip link set can0 down 2>/dev/null || true
sudo ip link set can0 type can bitrate 500000
sudo ip link set can0 up

# Start controller in background
ros2 run motor_control_ros2 mg6010_controller_node \
  --ros-args -r __node:=mg6010_controller \
  --params-file ~/pragati_ros2/src/motor_control_ros2/config/mg6010_three_motors.yaml > /tmp/controller.log 2>&1 &
CONTROLLER_PID=$!

echo "Controller PID: $CONTROLLER_PID"
echo "Waiting for initialization..."
sleep 8

if ! kill -0 $CONTROLLER_PID 2>/dev/null; then
    echo "❌ Motor controller failed to start"
    cat /tmp/controller.log
    exit 1
fi

echo "✅ Motor controller started"
echo ""

echo "=========================================="
echo "Checking /joint_states Topic"
echo "=========================================="
echo ""

# Check if topic exists
if ros2 topic list | grep -q "/joint_states"; then
    echo "✅ /joint_states topic exists"
else
    echo "❌ /joint_states topic NOT found"
    ros2 topic list
    kill $CONTROLLER_PID
    exit 1
fi

echo ""
echo "Reading joint_states (3 samples)..."
echo ""

for i in 1 2 3; do
    echo "Sample $i:"
    timeout 2 ros2 topic echo /joint_states --once 2>&1
    echo ""
    sleep 1
done

echo ""
echo "=========================================="
echo "Sending Test Command to Joint3"
echo "=========================================="
echo "Command: joint3 = 0.5 rad"
echo ""

ros2 topic pub --rate 2 --times 6 /joint3_position_controller/command std_msgs/msg/Float64 "{data: 0.5}" > /dev/null 2>&1 &

sleep 4

echo "Joint states after command:"
timeout 2 ros2 topic echo /joint_states --once

echo ""
echo "=========================================="
echo "Sending Test Command to Joint5"
echo "=========================================="
echo "Command: joint5 = 0.1 rad"
echo ""

ros2 topic pub --rate 2 --times 6 /joint5_position_controller/command std_msgs/msg/Float64 "{data: 0.1}" > /dev/null 2>&1 &

sleep 4

echo "Joint states after command:"
timeout 2 ros2 topic echo /joint_states --once

echo ""
echo "=========================================="
echo "Continuous Joint States (5 seconds)"
echo "=========================================="
echo ""

timeout 5 ros2 topic echo /joint_states

echo ""
echo "=========================================="
echo "Stopping Controller"
echo "=========================================="

kill $CONTROLLER_PID 2>/dev/null
wait $CONTROLLER_PID 2>/dev/null

echo ""
echo "Test Complete!"
echo ""
echo "Summary:"
echo "- If you saw 'name: [joint3, joint5]' - encoder names are correct ✅"
echo "- If position values changed when motors moved - encoders working ✅"
echo "- If position values stayed at 0 - encoder feedback broken ❌"
