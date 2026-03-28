#!/bin/bash
###############################################################################
# MG6010 Motor Testing Script - Phase 5
# Run this AFTER scripts/validation/motor/setup/setup_mg6010_test.sh completes successfully
# This will power on the motor and run communication tests
###############################################################################

set -e  # Exit on error

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}MG6010 Motor Testing - Phase 5${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Load environment
if [ -f ~/mg6010_test_env.sh ]; then
    source ~/mg6010_test_env.sh
else
    echo -e "${RED}Error: Environment file not found. Run scripts/validation/motor/setup/setup_mg6010_test.sh first${NC}"
    exit 1
fi

echo -e "${YELLOW}⚠️  SAFETY CHECK${NC}"
echo ""
echo "Before proceeding:"
echo "  1. Ensure motor is FREE TO MOVE"
echo "  2. Ensure area is CLEAR OF OBSTRUCTIONS"
echo "  3. Be ready to cut power in case of issues"
echo ""
read -p "Is it safe to power on and test the motor? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo -e "${YELLOW}Cancelled. Run this script when ready.${NC}"
    exit 0
fi

echo ""
echo -e "${BLUE}Phase 5.1: Switching CAN to normal mode...${NC}"

# Switch CAN to normal operation
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 500000 listen-only off restart-ms 100
sudo ip link set can0 up

# Verify status
echo -e "${YELLOW}CAN Interface Status:${NC}"
ip -details link show can0 | grep -E "can0|state|bitrate"

if ip link show can0 | grep -q "state UP"; then
    echo -e "${GREEN}✓ CAN is in normal mode at 500 kbps${NC}"
else
    echo -e "${RED}✗ CAN failed to switch to normal mode${NC}"
    exit 1
fi

echo ""
echo -e "${RED}===========================================${NC}"
echo -e "${RED}POWER ON THE MOTOR NOW${NC}"
echo -e "${RED}===========================================${NC}"
echo ""
read -p "Press ENTER after motor is powered on..."

echo ""
echo -e "${BLUE}Checking for immediate CAN errors...${NC}"
sleep 2
dmesg | egrep -i "can0|bus-off|error" | tail -10 || echo "No immediate errors"

# Check if CAN is still UP
if ! ip link show can0 | grep -q "state UP"; then
    echo -e "${RED}✗ CAN interface went down! Check wiring and termination${NC}"
    exit 1
fi

echo -e "${GREEN}✓ CAN interface remains UP${NC}"
echo ""

###############################################################################
# Run Tests
###############################################################################

echo -e "${BLUE}Phase 5.2: Running status test...${NC}"
echo ""

ros2 run motor_control_ros2 mg6010_test_node --ros-args \
  -p interface_name:=$CAN_IFACE \
  -p baud_rate:=$CAN_BITRATE \
  -p node_id:=$MG6010_NODE_ID \
  -p mode:=status \
  2>&1 | tee ~/pragati_ws/mg6010_status_test.log

STATUS_RESULT=$?

if [ $STATUS_RESULT -eq 0 ]; then
    echo -e "${GREEN}✓ Status test completed${NC}"
else
    echo -e "${RED}✗ Status test failed${NC}"
    echo "Check ~/pragati_ws/mg6010_status_test.log for details"
    exit 1
fi

echo ""
echo -e "${YELLOW}CAN messages captured:${NC}"
tmux capture-pane -pt canmon | tail -20

echo ""
read -p "Continue with angle test? (yes/no): " CONTINUE
if [ "$CONTINUE" != "yes" ]; then
    echo -e "${YELLOW}Tests stopped. Motor remains powered.${NC}"
    exit 0
fi

echo ""
echo -e "${BLUE}Phase 5.3: Running angle test...${NC}"
echo ""

ros2 run motor_control_ros2 mg6010_test_node --ros-args \
  -p interface_name:=$CAN_IFACE \
  -p baud_rate:=$CAN_BITRATE \
  -p node_id:=$MG6010_NODE_ID \
  -p mode:=angle \
  2>&1 | tee ~/pragati_ws/mg6010_angle_test.log

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Angle test completed${NC}"
else
    echo -e "${RED}✗ Angle test failed${NC}"
fi

echo ""
read -p "Continue with motor on/off test? (motor will activate!) (yes/no): " CONTINUE
if [ "$CONTINUE" != "yes" ]; then
    echo -e "${YELLOW}Tests stopped. Motor remains powered.${NC}"
    exit 0
fi

echo ""
echo -e "${BLUE}Phase 5.4: Running motor on/off test...${NC}"
echo -e "${YELLOW}⚠️  Motor will briefly activate${NC}"
echo ""

ros2 run motor_control_ros2 mg6010_test_node --ros-args \
  -p interface_name:=$CAN_IFACE \
  -p baud_rate:=$CAN_BITRATE \
  -p node_id:=$MG6010_NODE_ID \
  -p mode:=on_off \
  2>&1 | tee ~/pragati_ws/mg6010_on_off_test.log

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Motor on/off test completed${NC}"
else
    echo -e "${RED}✗ Motor on/off test failed${NC}"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Basic Tests Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Test logs saved to:"
echo "  ~/pragati_ws/mg6010_status_test.log"
echo "  ~/pragati_ws/mg6010_angle_test.log"
echo "  ~/pragati_ws/mg6010_on_off_test.log"
echo ""
echo "CAN messages captured:"
echo "  View with: tmux attach -t canmon"
echo "  Or: tmux capture-pane -pt canmon | less"
echo ""
echo -e "${YELLOW}Additional tests available:${NC}"
echo "  - position test (specify target angle)"
echo "  - velocity test (specify target speed)"
echo "  - acceleration test"
echo ""
echo "Run individual tests with:"
echo "  ros2 run motor_control_ros2 mg6010_test_node --ros-args \\"
echo "    -p interface_name:=can0 \\"
echo "    -p baud_rate:=500000 \\"
echo "    -p node_id:=1 \\"
echo "    -p mode:=<test_mode>"
echo ""
