#!/bin/bash
# Motor Testing Script for Raspberry Pi
# This script performs Phase 1 individual motor hardware tests
# Run this on the Raspberry Pi, not on local PC

set -e

echo "========================================"
echo "Motor Testing on Raspberry Pi"
echo "========================================"
echo ""

# Source ROS2 environment
echo "Sourcing ROS2 environment..."
if [ -f "/opt/ros/jazzy/setup.bash" ]; then
    source /opt/ros/jazzy/setup.bash
elif [ -f "/opt/ros/humble/setup.bash" ]; then
    source /opt/ros/humble/setup.bash
fi

# Source workspace
if [ -f "$HOME/pragati_ros2/install/setup.bash" ]; then
    source $HOME/pragati_ros2/install/setup.bash
fi

echo "ROS2 Distribution: $ROS_DISTRO"
echo ""

# Check CAN interface
echo "Checking CAN interface..."
if ip link show can0 &> /dev/null; then
    echo "✅ CAN interface exists"
    
    # Check if interface is UP
    if ip link show can0 | grep -q "state UP"; then
        echo "✅ CAN interface is UP"
    else
        echo "⚠️  CAN interface is DOWN. Setting up..."
        sudo ip link set can0 type can bitrate 500000
        sudo ip link set can0 up
        echo "✅ CAN interface configured"
    fi
else
    echo "❌ CAN interface does not exist. Please configure hardware."
    exit 1
fi

echo ""
echo "========================================"
echo "Phase 1: Individual Motor Hardware Tests"
echo "========================================"
echo ""

# Function to test a motor
test_motor() {
    local MOTOR_NUM=$1
    local CAN_ID=$2
    local NODE_ID=$3
    local JOINT_NAME=$4
    
    echo ""
    echo "----------------------------------------"
    echo "Testing Motor $MOTOR_NUM ($JOINT_NAME)"
    echo "CAN ID: $CAN_ID, Node ID: $NODE_ID"
    echo "----------------------------------------"
    
    # Start test node in background
    echo "Starting mg6010_test_node..."
    ros2 run motor_control_ros2 mg6010_test_node \
        --ros-args -p can_id:=$CAN_ID -p node_id:=$NODE_ID &
    TEST_NODE_PID=$!
    
    # Wait for node to initialize
    sleep 3
    
    # Check if node is still running
    if ! kill -0 $TEST_NODE_PID 2>/dev/null; then
        echo "❌ Test node failed to start"
        return 1
    fi
    
    echo ""
    echo "Step 1: Reading motor status..."
    if ros2 service call /mg6010_test/read_status std_srvs/srv/Trigger --timeout 5.0; then
        echo "✅ Status read successful"
    else
        echo "❌ Status read failed"
        kill $TEST_NODE_PID 2>/dev/null
        return 1
    fi
    
    echo ""
    echo "Step 2: Reading encoder position..."
    if ros2 service call /mg6010_test/read_encoder std_srvs/srv/Trigger --timeout 5.0; then
        echo "✅ Encoder read successful"
    else
        echo "❌ Encoder read failed"
        kill $TEST_NODE_PID 2>/dev/null
        return 1
    fi
    
    echo ""
    echo "Step 3: Enabling motor..."
    if ros2 service call /mg6010_test/motor_on std_srvs/srv/Trigger --timeout 5.0; then
        echo "✅ Motor enabled"
    else
        echo "❌ Motor enable failed"
        kill $TEST_NODE_PID 2>/dev/null
        return 1
    fi
    
    sleep 1
    
    echo ""
    echo "Step 4: Testing position control (+1.0 rad)..."
    echo "   Reading initial position..."
    INITIAL_POS=$(ros2 service call /mg6010_test/read_encoder std_srvs/srv/Trigger --timeout 5.0 2>&1 | grep -oP 'position[^\n]*' | head -1 || echo "position_read_failed")
    echo "   Initial: $INITIAL_POS"
    
    if ros2 service call /mg6010_test/position_control motor_control_ros2/srv/PositionControl \
        "{position_rad: 1.0, max_speed_rpm: 100}" --timeout 10.0; then
        echo "✅ Position command sent"
        echo "   Waiting 5 seconds for motor to reach position..."
        sleep 5
        
        echo "   Reading final position..."
        FINAL_POS=$(ros2 service call /mg6010_test/read_encoder std_srvs/srv/Trigger --timeout 5.0 2>&1 | grep -oP 'position[^\n]*' | head -1 || echo "position_read_failed")
        echo "   Final: $FINAL_POS"
        
        # Verify position changed
        if [ "$INITIAL_POS" = "$FINAL_POS" ] || [ "$FINAL_POS" = "position_read_failed" ]; then
            echo "❌ MOTOR DID NOT MOVE - Position unchanged or read failed"
            echo "   This is a FALSE POSITIVE - command succeeded but motor didn't respond"
            kill $TEST_NODE_PID 2>/dev/null
            return 1
        else
            echo "✅ Motor movement VERIFIED - position changed"
        fi
    else
        echo "❌ Position control failed"
        kill $TEST_NODE_PID 2>/dev/null
        return 1
    fi
    
    echo ""
    echo "Step 5: Testing position control (0.0 rad - home)..."
    echo "   Reading current position..."
    BEFORE_HOME=$(ros2 service call /mg6010_test/read_encoder std_srvs/srv/Trigger --timeout 5.0 2>&1 | grep -oP 'position[^\n]*' | head -1 || echo "position_read_failed")
    echo "   Before home: $BEFORE_HOME"
    
    if ros2 service call /mg6010_test/position_control motor_control_ros2/srv/PositionControl \
        "{position_rad: 0.0, max_speed_rpm: 100}" --timeout 10.0; then
        echo "✅ Position command sent"
        echo "   Waiting 5 seconds for motor to reach home..."
        sleep 5
        
        echo "   Reading final position..."
        AFTER_HOME=$(ros2 service call /mg6010_test/read_encoder std_srvs/srv/Trigger --timeout 5.0 2>&1 | grep -oP 'position[^\n]*' | head -1 || echo "position_read_failed")
        echo "   After home: $AFTER_HOME"
        
        # Verify position changed
        if [ "$BEFORE_HOME" = "$AFTER_HOME" ] || [ "$AFTER_HOME" = "position_read_failed" ]; then
            echo "❌ MOTOR DID NOT MOVE - Position unchanged or read failed"
            kill $TEST_NODE_PID 2>/dev/null
            return 1
        else
            echo "✅ Motor return to home VERIFIED"
        fi
    else
        echo "❌ Position control failed"
        kill $TEST_NODE_PID 2>/dev/null
        return 1
    fi
    
    echo ""
    echo "Step 6: Disabling motor..."
    if ros2 service call /mg6010_test/motor_off std_srvs/srv/Trigger --timeout 5.0; then
        echo "✅ Motor disabled"
    else
        echo "⚠️  Motor disable failed (motor may still be enabled)"
    fi
    
    # Kill test node
    echo ""
    echo "Stopping test node..."
    kill $TEST_NODE_PID 2>/dev/null
    wait $TEST_NODE_PID 2>/dev/null
    
    echo ""
    echo "✅ Motor $MOTOR_NUM ($JOINT_NAME) testing complete!"
    
    return 0
}

# Test Motor 1 (Joint 3)
test_motor 1 141 1 "joint3"
MOTOR1_RESULT=$?

sleep 2

# Test Motor 2 (Joint 4)
test_motor 2 142 2 "joint4"
MOTOR2_RESULT=$?

echo ""
echo "========================================"
echo "Test Summary"
echo "========================================"
echo ""

if [ $MOTOR1_RESULT -eq 0 ]; then
    echo "✅ Motor 1 (Joint 3, CAN 141): PASS"
else
    echo "❌ Motor 1 (Joint 3, CAN 141): FAIL"
fi

if [ $MOTOR2_RESULT -eq 0 ]; then
    echo "✅ Motor 2 (Joint 4, CAN 142): PASS"
else
    echo "❌ Motor 2 (Joint 4, CAN 142): FAIL"
fi

echo ""

if [ $MOTOR1_RESULT -eq 0 ] && [ $MOTOR2_RESULT -eq 0 ]; then
    echo "🎉 All motors PASSED Phase 1 testing!"
    echo ""
    echo "Next Steps:"
    echo "1. Proceed to Phase 2: ROS2 Controller Integration Tests"
    echo "2. Run: bash test_motors_phase2_rpi.sh"
    exit 0
else
    echo "⚠️  Some motors failed testing. Please investigate."
    echo ""
    echo "Troubleshooting:"
    echo "- Check CAN connections"
    echo "- Verify motor power supply"
    echo "- Check motor CAN IDs match configuration"
    echo "- Run: candump can0 (to see CAN traffic)"
    exit 1
fi
