#!/bin/bash
# Test complete automatic flow: detection → yanthra_move → motors

echo "=========================================="
echo "AUTOMATIC FLOW TEST"
echo "Detection → Yanthra Move → Motors"
echo "=========================================="
echo ""

# 1. Check if system is running
echo "Step 1: Checking system status..."
if ! ros2 node list | grep -q yanthra_move; then
    echo "❌ Yanthra Move not running. Please start system first."
    exit 1
fi
if ! ros2 node list | grep -q cotton_detection; then
    echo "❌ Cotton detection not running. Please start system first."
    exit 1
fi
echo "✅ All nodes running"
echo ""

# 2. Check topics
echo "Step 2: Verifying topics..."
ros2 topic info /cotton_detection/results | grep -q "Subscription count: 1" && echo "✅ Yanthra Move subscribed" || echo "❌ No subscription"
echo ""

# 3. Enable start switch
echo "Step 3: Enabling start switch..."
ros2 topic pub --once /start_switch/command std_msgs/msg/Bool '{data: true}'
sleep 2
echo "✅ Start switch enabled"
echo ""

# 4. Trigger detection
echo "Step 4: Triggering cotton detection..."
ros2 service call /cotton_detection/detect cotton_detection_msgs/srv/CottonDetection '{detect_command: 1}' &
DETECT_PID=$!
echo ""

# 5. Monitor for automatic processing
echo "Step 5: Monitoring automatic flow (10 seconds)..."
echo "  Watching /cotton_detection/results topic..."
timeout 10 ros2 topic echo /cotton_detection/results --once &

echo "  Watching motor command topics..."
timeout 10 candump can0 &

wait $DETECT_PID
sleep 10

echo ""
echo "=========================================="
echo "Check above for:"
echo "  1. Detection results published"
echo "  2. CAN messages showing motor commands"
echo "=========================================="
