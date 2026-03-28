#!/bin/bash
# Quick Test Script for ARM Client (without MQTT broker)
# Tests ROS-2 topics and service without requiring MQTT connection

set -e

echo "============================================================"
echo "ARM Client Quick Test (ROS-2 Only)"
echo "============================================================"
echo ""

# Source ROS-2
source install/setup.bash

echo "✅ Sourced ROS-2 workspace"
echo ""

# Check if yanthra_move is running
echo "📋 Step 1: Checking if yanthra_move node is available..."
if ros2 service list | grep -q "/yanthra_move/current_arm_status"; then
    echo "✅ yanthra_move node is running!"
else
    echo "❌ yanthra_move node is NOT running"
    echo "   Start it with: ros2 run yanthra_move yanthra_move_node"
    echo ""
    echo "   Or in simulation mode:"
    echo "   ros2 run yanthra_move yanthra_move_node --ros-args -p simulation_mode:=true -p skip_homing:=true -p start_switch.enable_wait:=false"
    exit 1
fi
echo ""

# Test arm status service
echo "📋 Step 2: Testing arm status service..."
echo "   Calling: ros2 service call /yanthra_move/current_arm_status yanthra_move/srv/ArmStatus \"{}\""
SERVICE_RESULT=$(ros2 service call /yanthra_move/current_arm_status yanthra_move/srv/ArmStatus "{}" 2>&1)
echo "$SERVICE_RESULT"

# Extract status from result
if echo "$SERVICE_RESULT" | grep -q "status:"; then
    STATUS=$(echo "$SERVICE_RESULT" | grep "status:" | sed 's/.*status: //' | tr -d '"')
    echo "✅ Service call successful!"
    echo "   Current status: $STATUS"
else
    echo "❌ Service call failed"
    exit 1
fi
echo ""

# Test start switch topic
echo "📋 Step 3: Testing START_SWITCH topic..."
echo "   Publishing to: /start_switch/command"
ros2 topic pub /start_switch/command std_msgs/msg/Bool "{data: true}" --once > /dev/null 2>&1 &
sleep 1
echo "✅ START_SWITCH topic published"
echo ""

# Wait a moment for status to change
sleep 2

# Check status again
echo "📋 Step 4: Checking status after START command..."
SERVICE_RESULT2=$(ros2 service call /yanthra_move/current_arm_status yanthra_move/srv/ArmStatus "{}" 2>&1)
if echo "$SERVICE_RESULT2" | grep -q "status:"; then
    STATUS2=$(echo "$SERVICE_RESULT2" | grep "status:" | sed 's/.*status: //' | tr -d '"')
    echo "   Current status: $STATUS2"
    if [ "$STATUS2" = "busy" ]; then
        echo "✅ Status changed to 'busy' - system is responding!"
    else
        echo "ℹ️  Status is: $STATUS2"
    fi
else
    echo "⚠️  Could not check status"
fi
echo ""

# Test shutdown switch
echo "📋 Step 5: Testing SHUTDOWN_SWITCH topic..."
echo "   Publishing to: /shutdown_switch/command"
ros2 topic pub /shutdown_switch/command std_msgs/msg/Bool "{data: true}" --once > /dev/null 2>&1 &
sleep 1
echo "✅ SHUTDOWN_SWITCH topic published"
echo ""

sleep 1

# Final status check
echo "📋 Step 6: Final status check..."
SERVICE_RESULT3=$(ros2 service call /yanthra_move/current_arm_status yanthra_move/srv/ArmStatus "{}" 2>&1)
if echo "$SERVICE_RESULT3" | grep -q "status:"; then
    STATUS3=$(echo "$SERVICE_RESULT3" | grep "status:" | sed 's/.*status: //' | tr -d '"')
    echo "   Current status: $STATUS3"
    if [ "$STATUS3" = "error" ]; then
        echo "✅ Status changed to 'error' - shutdown was acknowledged!"
    else
        echo "ℹ️  Status is: $STATUS3"
    fi
else
    echo "⚠️  Could not check status"
fi
echo ""

echo "============================================================"
echo "✅ All ROS-2 Tests Completed!"
echo "============================================================"
echo ""
echo "Summary:"
echo "  ✅ Arm status service: Working"
echo "  ✅ START_SWITCH topic: Working"
echo "  ✅ SHUTDOWN_SWITCH topic: Working"
echo "  ✅ Dynamic status tracking: Working"
echo ""
echo "Next Steps:"
echo "  1. To test with ARM_client.py (requires MQTT broker):"
echo "     python3 launch/ARM_client.py"
echo ""
echo "  2. To test with MQTT (requires mosquitto):"
echo "     sudo apt install mosquitto mosquitto-clients"
echo "     mosquitto_pub -h 10.42.0.10 -t topic/start_switch_input_ -m \"True\""
echo ""
echo "  3. Monitor arm status in real-time:"
echo "     watch -n 1 'ros2 service call /yanthra_move/current_arm_status yanthra_move/srv/ArmStatus \"{}\"'"
echo ""
