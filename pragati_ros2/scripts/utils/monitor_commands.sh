#!/bin/bash
# Monitor cotton detection and motor commands in real-time

cd ~/pragati_ros2
source /opt/ros/jazzy/setup.bash
source install/setup.bash

echo "=========================================="
echo "Starting System and Monitoring Commands"
echo "=========================================="

# Setup CAN
sudo ip link set can0 down 2>/dev/null || true
sudo ip link set can0 type can bitrate 500000
sudo ip link set can0 up

# Start system in background
echo "Starting system..."
ros2 launch yanthra_move pragati_complete.launch.py simulation_mode:=true > /tmp/system_monitor.log 2>&1 &
SYSTEM_PID=$!

sleep 20

echo "✅ System started (PID: $SYSTEM_PID)"
echo ""

# Send START
echo "Sending START signal..."
ros2 topic pub --once /start_switch/command std_msgs/Bool "data: true"
sleep 2

echo ""
echo "=========================================="
echo "Monitoring Topics"
echo "=========================================="
echo ""

# Monitor in parallel
echo "Opening monitors..."
echo ""

# Terminal 1: Monitor cotton detection
echo "1. Monitoring /cotton_detection/results"
gnome-terminal -- bash -c "source /opt/ros/jazzy/setup.bash && source ~/pragati_ros2/install/setup.bash && ros2 topic echo /cotton_detection/results" 2>/dev/null &

# Terminal 2: Monitor joint3 commands
echo "2. Monitoring /joint3_position_controller/command"
gnome-terminal -- bash -c "source /opt/ros/jazzy/setup.bash && source ~/pragati_ros2/install/setup.bash && ros2 topic echo /joint3_position_controller/command" 2>/dev/null &

# Terminal 3: Monitor joint5 commands  
echo "3. Monitoring /joint5_position_controller/command"
gnome-terminal -- bash -c "source /opt/ros/jazzy/setup.bash && source ~/pragati_ros2/install/setup.bash && ros2 topic echo /joint5_position_controller/command" 2>/dev/null &

# Terminal 4: Monitor joint_states
echo "4. Monitoring /joint_states"
gnome-terminal -- bash -c "source /opt/ros/jazzy/setup.bash && source ~/pragati_ros2/install/setup.bash && ros2 topic echo /joint_states --field position" 2>/dev/null &

sleep 3

echo ""
echo "=========================================="
echo "Sending Test Cotton Detection"
echo "=========================================="
echo ""

# Send cotton detection
echo "Sending cotton detection: (0.3, 0.1, 0.5) meters"
./scripts/testing/test_cotton_detection_publisher.py --single --count 2

echo ""
echo "Watch the terminal windows for:"
echo "  - Cotton detection message"
echo "  - Joint commands being sent"
echo "  - Joint states updating"
echo ""
echo "Press Enter to stop monitoring and shutdown system..."
read

# Cleanup
kill $SYSTEM_PID 2>/dev/null
pkill -f "ros2 topic echo"

echo "✅ Monitoring stopped"
