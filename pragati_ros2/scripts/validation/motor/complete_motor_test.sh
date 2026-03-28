#!/bin/bash
# Complete MG6010 Motor Test with CAN Traffic Analysis (Legacy helper)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="${PRAGATI_WORKSPACE:-$(cd "$SCRIPT_DIR/../../.." && pwd)}"
SETUP_FILE="${WORKSPACE_ROOT}/install/setup.bash"

if [[ ! -f "$SETUP_FILE" ]]; then
    echo "✗ ROS2 workspace not built. Expected setup file at: $SETUP_FILE"
    exit 1
fi

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

printf "${CYAN}==========================================\n"
printf "Complete MG6010 Motor Test\n"
printf "Node ID: 1, Baud: 500 kbps\n"
printf "==========================================${NC}\n\n"

printf "${CYAN}Step 1: Configuring CAN interface${NC}\n"
sudo ip link set can0 down 2>/dev/null || true
sudo ip link set can0 type can bitrate 500000 restart-ms 100
sudo ip link set can0 up

CAN_STATE=$(ip -details link show can0 | grep -oP "state \K\S+")
printf "  CAN State: %s\n" "$CAN_STATE"

if [[ "$CAN_STATE" == "ERROR-ACTIVE" ]]; then
    printf "  ${GREEN}✓ CAN interface healthy${NC}\n"
else
    printf "  ${YELLOW}⚠ CAN in %s state${NC}\n" "$CAN_STATE"
fi

printf "\n${CYAN}Step 2: Testing with raw CAN commands${NC}\n\n"

LOG_FILE="/tmp/motor_candump_complete.log"
timeout 2s candump can0 > "$LOG_FILE" 2>&1 &
CANDUMP_PID=$!
sleep 0.5

echo "Sending commands:"
echo "  - Motor OFF (0x80)"
cansend can0 141#80
sleep 0.1

echo "  - Motor ON (0x88)"
cansend can0 141#88
sleep 0.15

echo "  - Read Status (0x9A)"
cansend can0 141#9A
sleep 0.5

echo "  - Read Status (0x9A) again"
cansend can0 141#9A
sleep 0.5

kill $CANDUMP_PID 2>/dev/null || true
wait $CANDUMP_PID 2>/dev/null || true

printf "\nCAN Traffic Captured:\n"
cat "$LOG_FILE"
printf "\nTotal messages: %s\n" "$(wc -l < "$LOG_FILE")"

printf "\n${CYAN}Step 3: CAN Statistics${NC}\n"
ip -s link show can0 | grep -A 2 "RX:\|TX:"

TX_DROPPED=$(ip -s link show can0 | grep "TX:" -A 1 | tail -1 | awk '{print $5}')
printf "TX Dropped packets: %s\n" "$TX_DROPPED"

if [[ "$TX_DROPPED" -gt 0 ]]; then
    printf "${YELLOW}\nEXPLANATION OF DROPPED PACKETS:\n"
    printf "================================${NC}\n\n"
    cat <<'EOF'
Dropped TX packets occur when:
1. The CAN TX buffer is full (messages sent faster than the bus can handle)
2. The motor doesn't ACK the message (motor not ready/powered/responding)
3. Bus errors occur during transmission

In this case this is expected during initial testing as the motor powers on.
EOF
fi

printf "\n${CYAN}Step 4: Testing with ROS2 node${NC}\n\n"

source "$SETUP_FILE"

LOG_FILE_ROS="/tmp/motor_ros2_test.log"
timeout 2s candump can0 > "$LOG_FILE_ROS" 2>&1 &
CANDUMP_PID=$!
sleep 0.5

ros2 run motor_control_ros2 mg6010_test_node --ros-args \
  -p interface_name:=can0 \
  -p baud_rate:=500000 \
  -p node_id:=1 \
  -p mode:=status

kill $CANDUMP_PID 2>/dev/null || true
wait $CANDUMP_PID 2>/dev/null || true

printf "\nCAN Traffic during ROS2 test:\n"
cat "$LOG_FILE_ROS"

printf "\n${CYAN}Step 5: Final CAN Statistics${NC}\n"
ip -s link show can0 | grep -A 2 "RX:\|TX:"

printf "\n${CYAN}==========================================\n"
printf "Test Complete\n"
printf "==========================================${NC}\n"
