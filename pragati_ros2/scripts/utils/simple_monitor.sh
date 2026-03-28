#!/bin/bash
# Simple monitoring - shows joint commands and cotton detection

cd ~/pragati_ros2
source /opt/ros/jazzy/setup.bash
source install/setup.bash

echo "=========================================="
echo "Simple Command Monitor"
echo "=========================================="

# Setup CAN
echo "Setting up CAN..."
sudo ip link set can0 down 2>/dev/null || true
sudo ip link set can0 type can bitrate 500000
sudo ip link set can0 up

# Start system  
echo "Starting system (this takes ~20 seconds)..."
ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=false > /tmp/monitor.log 2>&1 &
SYSTEM_PID=$!

sleep 20

if ! kill -0 $SYSTEM_PID 2>/dev/null; then
    echo "❌ System failed to start"
    cat /tmp/monitor.log | tail -20
    exit 1
fi

echo "✅ System running"
echo ""

echo "=========================================="
echo "Current Joint Positions (before cotton)"
echo "=========================================="
timeout 2 ros2 topic echo /joint_states --once 2>/dev/null | grep -A 5 "name:"

echo ""
echo "=========================================="
echo "Sending Cotton Detection FIRST"
echo "=========================================="
echo "Position: (0.4, 0.0, 0.6) meters"
echo "(This must be sent BEFORE START signal)"
echo ""

chmod +x test_cotton_detection_publisher.py
./test_cotton_detection_publisher.py --custom 0.4 0.0 0.6 2>&1 | grep -v "not initialized"

sleep 2

# Send START AFTER cotton detection
echo ""
echo "=========================================="
echo "Now sending START signal"
echo "=========================================="
ros2 topic pub --once /start_switch/command std_msgs/Bool "data: true" >/dev/null 2>&1

echo "Waiting for motion to complete..."
sleep 5

echo ""
echo "=========================================="
echo "Checking Joint Commands Sent"
echo "=========================================="
echo ""

# Check if any commands were received by motor controller
echo "Motor controller log (last 20 lines with 'Received'):"
grep "Received position command" /tmp/monitor.log | tail -10

if [ $? -ne 0 ]; then
    echo "⚠️  NO MOTOR COMMANDS FOUND!"
    echo ""
    echo "Checking yanthra_move log for cotton detection:"
    grep -i "cotton" /tmp/monitor.log | tail -10
fi

echo ""
echo "=========================================="
echo "Final Joint Positions (after cotton)"
echo "=========================================="
timeout 2 ros2 topic echo /joint_states --once 2>/dev/null | grep -A 5 "name:"

echo ""
echo "=========================================="
echo "Analysis"
echo "=========================================="
echo ""
echo "If you see 'Received position command' above:"
echo "  ✅ Commands ARE being sent to motors"
echo "  → Check if values are too small (need multiplication)"
echo ""
echo "If you DON'T see 'Received position command':"
echo "  ❌ Commands NOT being sent"
echo "  → Check yanthra_move cotton detection processing"
echo ""

# Cleanup
kill $SYSTEM_PID 2>/dev/null
sleep 2

echo "✅ Monitoring complete"
