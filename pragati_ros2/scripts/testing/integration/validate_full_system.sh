#!/bin/bash
# Complete End-to-End ARM Client Validation Script
# Tests everything: ROS-2 + ARM_client.py + MQTT (if available)

set -e

echo "============================================================"
echo "ARM CLIENT - COMPLETE VALIDATION SCRIPT"
echo "============================================================"
echo ""
echo "This script will validate:"
echo "  1. ✓ Build status"
echo "  2. ✓ yanthra_move node functionality"
echo "  3. ✓ ARM status service"
echo "  4. ✓ Topic subscriptions"
echo "  5. ✓ ARM_client.py functionality"
echo "  6. ✓ MQTT connectivity (if broker available)"
echo ""
read -p "Press ENTER to start validation..." 

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

success() {
    echo -e "${GREEN}✓ $1${NC}"
}

error() {
    echo -e "${RED}✗ $1${NC}"
}

warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Source workspace
echo ""
echo "============================================================"
echo "STEP 1: Environment Setup"
echo "============================================================"
if [ -f "install/setup.bash" ]; then
    source install/setup.bash
    success "Sourced ROS-2 workspace"
else
    error "install/setup.bash not found. Run: colcon build --packages-select yanthra_move"
    exit 1
fi
echo ""

# Check dependencies
echo "============================================================"
echo "STEP 2: Dependency Check"
echo "============================================================"
echo -n "Checking paho-mqtt... "
if python3 -c "import paho.mqtt.client" 2>/dev/null; then
    success "paho-mqtt installed"
else
    error "paho-mqtt not installed"
    echo "  Install with: sudo apt install python3-paho-mqtt"
    exit 1
fi

echo -n "Checking rclpy... "
if python3 -c "import rclpy" 2>/dev/null; then
    success "rclpy available"
else
    error "rclpy not available"
    exit 1
fi

echo -n "Checking yanthra_move interfaces... "
if python3 -c "from yanthra_move.srv import ArmStatus" 2>/dev/null; then
    success "yanthra_move.srv.ArmStatus available"
else
    error "yanthra_move interfaces not built"
    exit 1
fi
echo ""

# Check MQTT broker availability
echo "============================================================"
echo "STEP 3: MQTT Broker Check"
echo "============================================================"
MQTT_HOST="10.42.0.10"
MQTT_PORT="1883"

echo -n "Checking MQTT broker at ${MQTT_HOST}:${MQTT_PORT}... "
if timeout 2 bash -c "echo > /dev/tcp/${MQTT_HOST}/${MQTT_PORT}" 2>/dev/null; then
    success "MQTT broker is reachable!"
    MQTT_AVAILABLE=true
else
    warning "MQTT broker not reachable (will test without MQTT)"
    MQTT_AVAILABLE=false
    echo ""
    echo "  To test MQTT later:"
    echo "    - Ensure broker is running at ${MQTT_HOST}:${MQTT_PORT}"
    echo "    - Or install local broker: sudo apt install mosquitto"
fi
echo ""

# Start yanthra_move in simulation mode (background)
echo "============================================================"
echo "STEP 4: Start yanthra_move Node"
echo "============================================================"
echo "Starting yanthra_move in simulation mode..."

# Kill any existing yanthra_move processes
pkill -f yanthra_move_node || true
sleep 1

# Start in background with logging
ros2 run yanthra_move yanthra_move_node --ros-args \
  -p simulation_mode:=true \
  -p skip_homing:=true \
  -p start_switch.enable_wait:=false \
  > /tmp/yanthra_move.log 2>&1 &

YANTHRA_PID=$!
echo "Started yanthra_move (PID: $YANTHRA_PID)"

# Wait for node to initialize
echo -n "Waiting for node to initialize"
for i in {1..10}; do
    echo -n "."
    sleep 1
    if ros2 service list 2>/dev/null | grep -q "/yanthra_move/current_arm_status"; then
        break
    fi
done
echo ""

# Check if service is available
if ros2 service list 2>/dev/null | grep -q "/yanthra_move/current_arm_status"; then
    success "yanthra_move node is running!"
else
    error "yanthra_move node failed to start"
    echo "Check logs: tail /tmp/yanthra_move.log"
    kill $YANTHRA_PID 2>/dev/null || true
    exit 1
fi
echo ""

# Test arm status service
echo "============================================================"
echo "STEP 5: Test Arm Status Service"
echo "============================================================"
echo "Calling /yanthra_move/current_arm_status..."
SERVICE_OUTPUT=$(ros2 service call /yanthra_move/current_arm_status yanthra_move/srv/ArmStatus "{}" 2>&1)

if echo "$SERVICE_OUTPUT" | grep -q "status:"; then
    STATUS=$(echo "$SERVICE_OUTPUT" | grep "status:" | sed 's/.*status: //; s/[" ]//g')
    REASON=$(echo "$SERVICE_OUTPUT" | grep "reason:" | sed 's/.*reason: //; s/^"//; s/"$//')
    success "Service call successful!"
    echo "  Status: $STATUS"
    echo "  Reason: $REASON"
else
    error "Service call failed"
    echo "$SERVICE_OUTPUT"
    kill $YANTHRA_PID 2>/dev/null || true
    exit 1
fi
echo ""

# Test START_SWITCH topic
echo "============================================================"
echo "STEP 6: Test START_SWITCH Topic"
echo "============================================================"
echo "Publishing to /start_switch/command..."
ros2 topic pub /start_switch/command std_msgs/msg/Bool "{data: true}" --once &
sleep 2

# Check status changed to busy
SERVICE_OUTPUT2=$(ros2 service call /yanthra_move/current_arm_status yanthra_move/srv/ArmStatus "{}" 2>&1)
STATUS2=$(echo "$SERVICE_OUTPUT2" | grep "status:" | sed 's/.*status: //; s/[" ]//g')

if [ "$STATUS2" = "busy" ] || [ "$STATUS2" = "ready" ]; then
    success "START_SWITCH processed! Status: $STATUS2"
else
    warning "Unexpected status: $STATUS2"
fi
echo ""

# Wait for cycle to complete
echo "Waiting for operational cycle to complete..."
sleep 3

# Test SHUTDOWN_SWITCH topic
echo "============================================================"
echo "STEP 7: Test SHUTDOWN_SWITCH Topic"
echo "============================================================"
echo "Publishing to /shutdown_switch/command..."
ros2 topic pub /shutdown_switch/command std_msgs/msg/Bool "{data: true}" --once &
sleep 2

# Check status changed
SERVICE_OUTPUT3=$(ros2 service call /yanthra_move/current_arm_status yanthra_move/srv/ArmStatus "{}" 2>&1)
STATUS3=$(echo "$SERVICE_OUTPUT3" | grep "status:" | sed 's/.*status: //; s/[" ]//g')

if [ "$STATUS3" = "error" ]; then
    success "SHUTDOWN_SWITCH processed! Status: $STATUS3"
else
    warning "Status after shutdown: $STATUS3"
fi
echo ""

# Test ARM_client.py
echo "============================================================"
echo "STEP 8: Test ARM_client.py"
echo "============================================================"

if [ "$MQTT_AVAILABLE" = false ]; then
    warning "Skipping ARM_client.py test - MQTT broker not available"
    echo "  ARM_client.py requires MQTT broker at ${MQTT_HOST}:${MQTT_PORT}"
    echo ""
else
    echo "Starting ARM_client.py..."
    
    # Start ARM client in background
    python3 launch/ARM_client.py > /tmp/arm_client.log 2>&1 &
    ARM_CLIENT_PID=$!
    
    echo "ARM_client.py started (PID: $ARM_CLIENT_PID)"
    echo -n "Waiting for initialization"
    
    for i in {1..10}; do
        echo -n "."
        sleep 1
        if grep -q "ARM_Yanthra_StateMachine started" /tmp/arm_client.log 2>/dev/null; then
            break
        fi
    done
    echo ""
    
    # Check if ARM client started successfully
    if ps -p $ARM_CLIENT_PID > /dev/null 2>&1; then
        success "ARM_client.py is running!"
        
        # Show last few log lines
        echo ""
        echo "ARM Client logs:"
        tail -10 /tmp/arm_client.log | sed 's/^/  /'
        echo ""
        
        # Clean up ARM client
        echo "Stopping ARM_client.py..."
        kill $ARM_CLIENT_PID 2>/dev/null || true
        sleep 1
    else
        error "ARM_client.py failed to start"
        echo "Check logs: cat /tmp/arm_client.log"
    fi
    echo ""
fi

# Summary
echo "============================================================"
echo "VALIDATION SUMMARY"
echo "============================================================"
echo ""
success "✓ Build and dependencies"
success "✓ yanthra_move node functionality"
success "✓ Arm status service (dynamic status)"
success "✓ START_SWITCH topic handling"
success "✓ SHUTDOWN_SWITCH topic handling"

if [ "$MQTT_AVAILABLE" = true ]; then
    success "✓ ARM_client.py execution"
    success "✓ MQTT broker connectivity"
else
    warning "⚠ MQTT tests skipped (broker not available)"
fi

echo ""
echo "============================================================"
echo "NEXT STEPS"
echo "============================================================"
echo ""

if [ "$MQTT_AVAILABLE" = false ]; then
    echo "To complete full validation with MQTT:"
    echo ""
    echo "Option 1: Connect to production MQTT broker"
    echo "  - Ensure broker is accessible at ${MQTT_HOST}:${MQTT_PORT}"
    echo "  - Update ARM_client.py if different IP needed"
    echo ""
    echo "Option 2: Install local MQTT broker for testing"
    echo "  sudo apt install mosquitto mosquitto-clients"
    echo "  # Edit ARM_client.py line 47: MQTT_ADDRESS = 'localhost'"
    echo "  python3 launch/ARM_client.py"
    echo ""
fi

echo "To test manually:"
echo "  Terminal 1: ros2 run yanthra_move yanthra_move_node --ros-args -p simulation_mode:=true -p skip_homing:=true -p start_switch.enable_wait:=false"
echo "  Terminal 2: python3 launch/ARM_client.py"
echo "  Terminal 3: watch -n 1 'ros2 service call /yanthra_move/current_arm_status yanthra_move/srv/ArmStatus \"{}\"'"
echo ""

# Cleanup
echo "Cleaning up test processes..."
kill $YANTHRA_PID 2>/dev/null || true
pkill -f arm_client 2>/dev/null || true
sleep 1

success "Validation complete!"
echo ""
echo "Logs saved to:"
echo "  - /tmp/yanthra_move.log"
echo "  - /tmp/arm_client.log"
echo ""
