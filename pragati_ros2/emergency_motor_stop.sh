#!/bin/bash
# Emergency Motor Stop Script
# This script stops all motors after the main system is killed or shut down
# Place this outside src/ for standalone execution

set +e  # Don't exit on errors - we want to try all stop commands

echo "=========================================="
echo "Emergency Motor Stop Script"
echo "=========================================="
echo "$(date '+%Y-%m-%d %H:%M:%S') - Starting emergency motor shutdown..."
echo ""

# Source ROS2 environment
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$SCRIPT_DIR"
cd "$WORKSPACE_DIR" || exit 1

if [ -f "install/setup.bash" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Sourcing ROS2 workspace..."
    source install/setup.bash
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ⚠️  WARNING: ROS2 workspace not found at $WORKSPACE_DIR/install/setup.bash"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Attempting to use system ROS2 installation..."
    if [ -f "/opt/ros/jazzy/setup.bash" ]; then
        source /opt/ros/jazzy/setup.bash
    else
        echo "$(date '+%Y-%m-%d %H:%M:%S') - ❌ ERROR: No ROS2 installation found!"
        exit 1
    fi
fi

echo ""
echo "=========================================="
echo "Step 1: Stopping ROS2 Processes"
echo "=========================================="

# Kill all ROS2 launch processes
echo "$(date '+%Y-%m-%d %H:%M:%S') - Terminating ROS2 launch processes..."
pkill -INT -f "ros2 launch" && echo "$(date '+%Y-%m-%d %H:%M:%S') - ✅ Sent SIGINT to launch processes" || echo "$(date '+%Y-%m-%d %H:%M:%S') - ℹ️  No launch processes found"
sleep 2

# Kill specific nodes if still running
echo "$(date '+%Y-%m-%d %H:%M:%S') - Terminating yanthra_move_node..."
pkill -INT -f "yanthra_move_node" && echo "$(date '+%Y-%m-%d %H:%M:%S') - ✅ Sent SIGINT to yanthra_move" || echo "$(date '+%Y-%m-%d %H:%M:%S') - ℹ️  yanthra_move not running"
sleep 1

echo "$(date '+%Y-%m-%d %H:%M:%S') - Terminating mg6010_controller..."
pkill -INT -f "mg6010" && echo "$(date '+%Y-%m-%d %H:%M:%S') - ✅ Sent SIGINT to mg6010 controller" || echo "$(date '+%Y-%m-%d %H:%M:%S') - ℹ️  mg6010 controller not running"
sleep 1

echo "$(date '+%Y-%m-%d %H:%M:%S') - Terminating odrive_service_node..."
pkill -INT -f "odrive" && echo "$(date '+%Y-%m-%d %H:%M:%S') - ✅ Sent SIGINT to ODrive controller" || echo "$(date '+%Y-%m-%d %H:%M:%S') - ℹ️  ODrive controller not running"
sleep 1

echo ""
echo "=========================================="
echo "Step 2: Commanding Motors to IDLE State"
echo "=========================================="

# Wait a moment for ROS2 daemon to be ready
sleep 2

# Send idle commands to all joints via ROS2 service
echo "$(date '+%Y-%m-%d %H:%M:%S') - Sending IDLE command to all joints..."

# Check if joint_idle service exists
if ros2 service list 2>/dev/null | grep -q "/joint_idle"; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ✅ Found /joint_idle service, calling it..."

    # Call joint_idle service with all joint IDs
    # Based on the code, joints are 0,1,2,3 (joint3=0, joint4=1, joint5=2, joint2=3)
    for joint_id in 0 1 2 3; do
        echo "$(date '+%Y-%m-%d %H:%M:%S') - Idling joint $joint_id..."
        timeout 3 ros2 service call /joint_idle motor_control_ros2/srv/JointHoming "{joint_id: $joint_id}" 2>/dev/null && \
            echo "$(date '+%Y-%m-%d %H:%M:%S') - ✅ Joint $joint_id set to IDLE" || \
            echo "$(date '+%Y-%m-%d %H:%M:%S') - ⚠️  Failed to idle joint $joint_id"
        sleep 0.5
    done
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ⚠️  /joint_idle service not available"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - This is normal if motor controller is not running"
fi

echo ""
echo "=========================================="
echo "Step 3: Stopping MG6010 CAN Motors"
echo "=========================================="

# Try to send motor off command via topics if services aren't available
echo "$(date '+%Y-%m-%d %H:%M:%S') - Sending stop commands via joint position topics..."

for joint in 2 3 4 5; do
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Stopping joint${joint}..."
    timeout 2 ros2 topic pub --once /joint${joint}_position_controller/command std_msgs/msg/Float64 "{data: 0.0}" 2>/dev/null && \
        echo "$(date '+%Y-%m-%d %H:%M:%S') - ✅ Sent stop to joint${joint}" || \
        echo "$(date '+%Y-%m-%d %H:%M:%S') - ⚠️  Could not publish to joint${joint}"
done

echo ""
echo "=========================================="
echo "Step 4: Hardware-Level Motor Shutdown"
echo "=========================================="

# If CAN interface is available, send emergency stop via CAN
if command -v cansend &> /dev/null; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Checking CAN interface..."

    if ip link show can0 &>/dev/null; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') - ✅ CAN interface can0 found"
        echo "$(date '+%Y-%m-%d %H:%M:%S') - Sending emergency stop to MG6010 motors..."

        # Send motor off command to each motor (IDs 1-4)
        # MG6010 motor off command: CAN ID 0x141-0x144, command 0x80 (motor off)
        for motor_id in 1 2 3 4; do
            can_id=$((0x140 + motor_id))
            can_id_hex=$(printf "%03X" $can_id)
            echo "$(date '+%Y-%m-%d %H:%M:%S') - Sending OFF to motor $motor_id (CAN ID: 0x$can_id_hex)..."
            # Motor OFF command: 0x80 in byte 0, rest zeros
            cansend can0 ${can_id_hex}#8000000000000000 2>/dev/null && \
                echo "$(date '+%Y-%m-%d %H:%M:%S') - ✅ Motor $motor_id OFF command sent" || \
                echo "$(date '+%Y-%m-%d %H:%M:%S') - ⚠️  Failed to send CAN command to motor $motor_id"
            sleep 0.2
        done

        echo "$(date '+%Y-%m-%d %H:%M:%S') - Sending emergency stop to ODrive drive motors..."

        # Send estop command to each ODrive axis (node IDs 0, 1, 2)
        # ODrive CANSimple: arb_id = (node_id << 5) | cmd_id
        # Estop command = 0x02, empty payload
        for node_id in 0 1 2; do
            can_id=$(( (node_id << 5) | 0x02 ))
            can_id_hex=$(printf "%03X" $can_id)
            echo "$(date '+%Y-%m-%d %H:%M:%S') - Sending ESTOP to ODrive node $node_id (CAN ID: 0x$can_id_hex)..."
            cansend can0 ${can_id_hex}# 2>/dev/null && \
                echo "$(date '+%Y-%m-%d %H:%M:%S') - ✅ ODrive node $node_id ESTOP sent" || \
                echo "$(date '+%Y-%m-%d %H:%M:%S') - ⚠️  Failed to send ESTOP to ODrive node $node_id"
            sleep 0.2
        done
    else
        echo "$(date '+%Y-%m-%d %H:%M:%S') - ℹ️  CAN interface can0 not available"
    fi
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ℹ️  cansend command not available (install can-utils if needed)"
fi

echo ""
echo "=========================================="
echo "Step 4b: GPIO Cleanup (End Effector & Compressor OFF)"
echo "=========================================="

# Ensure end effector and compressor are OFF via GPIO
# These use BCM pin numbering (not physical pin numbers)
# EE M1: BCM 21 (enable), BCM 13 (direction)
# EE M2: BCM 12 (enable), BCM 20 (direction)
# Compressor: BCM 18

if [ -d /sys/class/gpio ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Setting GPIO pins LOW (EE + compressor OFF)..."
    for pin in 21 13 12 20 18; do
        # Export pin if not already exported
        if [ ! -d "/sys/class/gpio/gpio${pin}" ]; then
            echo "$pin" > /sys/class/gpio/export 2>/dev/null || true
            sleep 0.05
        fi
        # Set as output and drive LOW
        echo "out" > "/sys/class/gpio/gpio${pin}/direction" 2>/dev/null || true
        echo "0" > "/sys/class/gpio/gpio${pin}/value" 2>/dev/null && \
            echo "$(date '+%Y-%m-%d %H:%M:%S') -   BCM $pin → LOW" || \
            echo "$(date '+%Y-%m-%d %H:%M:%S') -   ⚠️  Failed to set BCM $pin"
    done
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ✅ GPIO cleanup complete"
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ℹ️  /sys/class/gpio not available (not running on RPi?)"
fi

echo ""
echo "=========================================="
echo "Step 5: Final Cleanup"
echo "=========================================="

# Force kill any remaining motor-related processes
echo "$(date '+%Y-%m-%d %H:%M:%S') - Force-stopping any remaining processes..."
sleep 2

pkill -9 -f "yanthra_move_node" 2>/dev/null && echo "$(date '+%Y-%m-%d %H:%M:%S') - Force-killed yanthra_move" || true
pkill -9 -f "mg6010" 2>/dev/null && echo "$(date '+%Y-%m-%d %H:%M:%S') - Force-killed mg6010 processes" || true
pkill -9 -f "odrive" 2>/dev/null && echo "$(date '+%Y-%m-%d %H:%M:%S') - Force-killed odrive processes" || true

# Stop ROS2 daemon
echo "$(date '+%Y-%m-%d %H:%M:%S') - Stopping ROS2 daemon..."
ros2 daemon stop 2>/dev/null && echo "$(date '+%Y-%m-%d %H:%M:%S') - ✅ ROS2 daemon stopped" || true

echo ""
echo "=========================================="
echo "Emergency Motor Stop Complete"
echo "=========================================="
echo "$(date '+%Y-%m-%d %H:%M:%S') - All shutdown procedures completed"
echo ""
echo "Summary:"
echo "  ✅ ROS2 processes terminated (MG6010 + ODrive)"
echo "  ✅ Motor IDLE commands sent (if service available)"
echo "  ✅ Joint position stop commands sent"
echo "  ✅ CAN emergency stop sent -- MG6010 OFF + ODrive ESTOP (if interface available)"
echo "  ✅ GPIO pins driven LOW (EE + compressor OFF)"
echo "  ✅ Remaining processes force-killed"
echo ""
echo "⚠️  IMPORTANT: Verify motors are actually stopped by:"
echo "  1. Visual inspection of motor movement"
echo "  2. Checking motor LED status indicators"
echo "  3. Verifying CAN bus traffic: candump can0"
echo ""
echo "If motors are still active, manually power off the motor controller"
echo "or disconnect the 24V/48V power supply to the MG6010/ODrive motors."
echo ""
echo "=========================================="
