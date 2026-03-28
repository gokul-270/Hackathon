#!/bin/bash
# All-in-One Thermal Test Runner
# Runs detection node, thermal monitor, and auto-trigger together

set -e

# Colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${CYAN}======================================================================${NC}"
echo -e "${CYAN}  🌡️  Comprehensive Thermal Test - OAK-D Lite${NC}"
echo -e "${CYAN}======================================================================${NC}"
echo ""

# Parse arguments
FPS=${1:-30}
DURATION=${2:-20}  # minutes
TRIGGER_INTERVAL=${3:-30}  # seconds

echo -e "${GREEN}Test Configuration:${NC}"
echo "  FPS: $FPS"
echo "  Duration: $DURATION minutes"
echo "  Trigger Interval: $TRIGGER_INTERVAL seconds"
echo ""

# Calculate trigger count
TRIGGER_COUNT=$((DURATION * 60 / TRIGGER_INTERVAL))

# Generate output filename
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="thermal_test_${FPS}fps_${TIMESTAMP}.csv"

echo -e "${CYAN}Output:${NC}"
echo "  📝 Thermal log: $LOG_FILE"
echo ""

echo -e "${YELLOW}Starting in 5 seconds... Press Ctrl+C to cancel${NC}"
sleep 5

echo ""
echo -e "${CYAN}======================================================================${NC}"
echo -e "${CYAN}  Starting Test Components${NC}"
echo -e "${CYAN}======================================================================${NC}"
echo ""

# Kill any existing processes that might lock the camera
echo -e "${YELLOW}🧹 Cleaning up any existing processes...${NC}"
if pgrep -f "cotton_detection_node" > /dev/null; then
    echo "   Stopping cotton_detection_node..."
    pkill -f "cotton_detection_node"
fi
if pgrep -f "monitor_camera_thermal" > /dev/null; then
    echo "   Stopping thermal monitor..."
    pkill -f "monitor_camera_thermal"
fi
if pgrep -f "auto_trigger_detections" > /dev/null; then
    echo "   Stopping auto-trigger..."
    pkill -f "auto_trigger_detections"
fi
sleep 3
echo -e "${GREEN}   ✅ Cleanup complete${NC}"
echo ""

# Terminal 1: Start thermal monitor FIRST (needs camera access)
echo -e "${GREEN}1️⃣  Starting Thermal Monitor...${NC}"
./monitor_camera_thermal_v2.py -i 10 -o "$LOG_FILE" > thermal_monitor_${TIMESTAMP}.log 2>&1 &
MONITOR_PID=$!
echo "   PID: $MONITOR_PID"
echo "   Waiting for camera connection..."
sleep 5

# Check if monitor connected successfully
if grep -q "Failed to connect" thermal_monitor_${TIMESTAMP}.log; then
    echo -e "${YELLOW}❌ Thermal monitor failed to connect to camera${NC}"
    echo ""
    echo "Error details:"
    cat thermal_monitor_${TIMESTAMP}.log | grep -A3 "Failed to connect"
    echo ""
    echo -e "${YELLOW}Possible causes:${NC}"
    echo "  - Camera not connected via USB"
    echo "  - Another process using the camera"
    echo "  - USB cable/port issue"
    echo ""
    kill $MONITOR_PID 2>/dev/null || true
    exit 1
elif grep -q "Connected to" thermal_monitor_${TIMESTAMP}.log; then
    DEVICE_ID=$(grep "Connected to:" thermal_monitor_${TIMESTAMP}.log | awk '{print $4}')
    echo -e "${GREEN}   ✅ Camera connected: $DEVICE_ID${NC}"
else
    echo -e "${YELLOW}⚠️  Monitor status unclear, checking...${NC}"
    tail -5 thermal_monitor_${TIMESTAMP}.log
    echo -e "${YELLOW}Proceeding anyway...${NC}"
fi
echo ""

# Terminal 2: Launch ROS2 node (thermal monitor already has camera access)
echo -e "${GREEN}2️⃣  Launching Cotton Detection Node...${NC}"
echo -e "   ${YELLOW}Note: ROS2 node will share camera with monitor${NC}"
source install/setup.bash
source /opt/ros/jazzy/setup.bash && source install/setup.bash && ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py > ros2_node_.log 2>&1 &
ROS2_PID=$!
echo "   PID: $ROS2_PID"
sleep 10  # Wait for node to initialize

# Check if node started successfully
if ! ps -p $ROS2_PID > /dev/null; then
    echo -e "${YELLOW}❌ Failed to start ROS2 node. Check ros2_node_${TIMESTAMP}.log${NC}"
    tail -20 ros2_node_${TIMESTAMP}.log
    kill $MONITOR_PID 2>/dev/null || true
    exit 1
fi
echo -e "${GREEN}   ✅ Node started${NC}"
echo ""

# Terminal 3: Start auto-trigger
echo -e "${GREEN}3️⃣  Starting Auto-Trigger (${TRIGGER_COUNT} triggers)...${NC}"
source /opt/ros/jazzy/setup.bash && TIMEOUT=$((TRIGGER_INTERVAL > 10 ? TRIGGER_INTERVAL - 5 : TRIGGER_INTERVAL - 2)); ./auto_trigger_detections.py -i $TRIGGER_INTERVAL -c $TRIGGER_COUNT -t $TIMEOUT &
TRIGGER_PID=$!
echo "   PID: $TRIGGER_PID"
echo -e "${GREEN}   ✅ Auto-trigger started${NC}"
echo ""

# Cleanup function
cleanup() {
    echo ""
    echo -e "${CYAN}======================================================================${NC}"
    echo -e "${CYAN}  🛑 Stopping Test${NC}"
    echo -e "${CYAN}======================================================================${NC}"
    echo ""
    
    echo "Stopping auto-trigger..."
    kill $TRIGGER_PID 2>/dev/null || true
    
    echo "Stopping thermal monitor..."
    kill $MONITOR_PID 2>/dev/null || true
    
    echo "Stopping ROS2 node..."
    kill $ROS2_PID 2>/dev/null || true
    
    sleep 2
    
    echo ""
    echo -e "${GREEN}📊 Test Complete!${NC}"
    echo ""
    echo "Results saved:"
    echo "  📝 Thermal data: $LOG_FILE"
    echo "  📋 ROS2 log: ros2_node_${TIMESTAMP}.log"
    echo "  📋 Monitor log: thermal_monitor_${TIMESTAMP}.log"
    echo ""
    echo "To analyze:"
    echo "  scp ubuntu@192.168.137.253:/home/ubuntu/pragati_ros2/$LOG_FILE ~/Downloads/"
    echo "  Open in Excel/LibreOffice and create a line chart"
    echo ""
}

trap cleanup EXIT INT TERM

# Display status and wait
echo -e "${CYAN}======================================================================${NC}"
echo -e "${CYAN}  ⏳ Test Running${NC}"
echo -e "${CYAN}======================================================================${NC}"
echo ""
echo "Test will run for $DURATION minutes"
echo "You can:"
echo "  - Watch thermal_monitor_${TIMESTAMP}.log for temperature"
echo "  - Watch ros2_node_${TIMESTAMP}.log for detections"
echo "  - Press Ctrl+C to stop early"
echo ""
echo "Monitoring..."
sleep 8
echo ""
echo -e "${CYAN}📊 Initial Temperature:${NC}"
tail -1 $LOG_FILE 2>/dev/null | awk -F"," '{if (NR>0) print "   🌡️  Avg: " $3 " | CSS: " $4 " | MSS: " $5 " | Status: " $8}'
echo ""

# Follow thermal log in foreground
tail -f thermal_monitor_${TIMESTAMP}.log
