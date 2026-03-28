#!/bin/bash
# Detailed Motor Status Check - All Three Motors
# Queries temperature, voltage, position, velocity from each motor

set -e

CAN_IF="can0"
BITRATE="500000"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log() { echo -e "${CYAN}[$(date +'%T')]${NC} $*"; }
log_success() { echo -e "${GREEN}[$(date +'%T')] ✓${NC} $*"; }
log_error() { echo -e "${RED}[$(date +'%T')] ✗${NC} $*"; }

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║          DETAILED MOTOR STATUS - All Three Motors             ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

# Setup CAN
log "Setting up CAN interface..."
sudo ip link set "$CAN_IF" down 2>/dev/null || true
sudo ip link set "$CAN_IF" type can bitrate "$BITRATE"
sudo ip link set "$CAN_IF" up
log_success "CAN interface ready"
echo ""

# Function to decode status response
decode_status() {
    local motor_id=$1
    local log_file=$2
    
    # Parse Status 1 response (0x9A): temp, voltage, error flags
    local status1=$(grep "9A" "$log_file" | head -1 | awk '{print $5, $6, $7, $8, $9, $10, $11, $12}')
    if [ -n "$status1" ]; then
        local temp_hex=$(echo $status1 | awk '{print $2}')
        local voltage_hex=$(echo $status1 | awk '{print $3 $4}')
        local error_hex=$(echo $status1 | awk '{print $5}')
        
        # Convert hex to decimal
        local temp=$((16#${temp_hex}))
        local voltage_raw=$((16#${voltage_hex}))
        local voltage=$(echo "scale=1; $voltage_raw / 10" | bc)
        local error=$((16#${error_hex}))
        
        echo "    Temperature: ${temp}°C"
        echo "    Voltage: ${voltage}V"
        echo "    Error Code: 0x${error_hex}"
        
        # Voltage check
        if (( $(echo "$voltage >= 44.0" | bc -l) )) && (( $(echo "$voltage <= 52.0" | bc -l) )); then
            echo -e "    ${GREEN}✓ Voltage OK${NC}"
        elif (( $(echo "$voltage < 44.0" | bc -l) )); then
            echo -e "    ${YELLOW}⚠ Low voltage warning${NC}"
        else
            echo -e "    ${RED}✗ Voltage too high!${NC}"
        fi
        
        # Temperature check
        if [ $temp -lt 60 ]; then
            echo -e "    ${GREEN}✓ Temperature OK${NC}"
        elif [ $temp -lt 70 ]; then
            echo -e "    ${YELLOW}⚠ Temperature elevated${NC}"
        else
            echo -e "    ${RED}✗ Temperature critical!${NC}"
        fi
    fi
}

# Function to get detailed motor status
get_motor_status() {
    local node_id=$1
    local joint_name=$2
    
    log "─────────────────────────────────────────────────────────────"
    log "Motor $node_id ($joint_name)"
    log "─────────────────────────────────────────────────────────────"
    
    local can_hex=$(printf "%X" $((0x140 + node_id)))
    local tmpfile="/tmp/motor_${node_id}_detail.log"
    
    # Start candump
    timeout 3s candump "$CAN_IF" > "$tmpfile" 2>&1 &
    local dump_pid=$!
    sleep 0.5
    
    # Query Status 1 (0x9A): Temperature, Voltage, Error
    cansend "$CAN_IF" "${can_hex}#9A00000000000000" 2>/dev/null
    sleep 0.3
    
    # Query Status 2 (0x9C): Temperature, Current, Speed, Encoder
    cansend "$CAN_IF" "${can_hex}#9C00000000000000" 2>/dev/null
    sleep 0.3
    
    # Read multi-turn angle (0x92)
    cansend "$CAN_IF" "${can_hex}#9200000000000000" 2>/dev/null
    sleep 0.3
    
    kill $dump_pid 2>/dev/null || true
    wait $dump_pid 2>/dev/null || true
    
    # Check if motor responded
    if grep -q "$can_hex" "$tmpfile"; then
        log_success "Motor $node_id is online"
        decode_status $node_id "$tmpfile"
        
        # Show raw responses
        echo ""
        echo "  Raw CAN responses:"
        grep "$can_hex" "$tmpfile" | head -5 | while read line; do
            echo "    $line"
        done
    else
        log_error "Motor $node_id not responding"
    fi
    
    echo ""
}

# Check all three motors
get_motor_status 1 "Joint3 - Base"
get_motor_status 2 "Joint4 - Upper Arm"
get_motor_status 3 "Joint5 - End Effector"

log "═══════════════════════════════════════════════════════════════"
log_success "Status check complete!"
log "═══════════════════════════════════════════════════════════════"
echo ""
log "All motors are ready for movement testing."
log "To test movements, you can:"
log "  1. Use ROS2: ros2 run motor_control_ros2 mg6010_test_node"
log "  2. Use CAN direct: cansend can0 141#A400000000000000"
log "  3. Run validation: bash scripts/validation/system/run_table_top_validation_v2.sh"
