#!/bin/bash
# Test GPIO disable feature on Raspberry Pi
# Run this after copying the updated code to RPi

echo "========================================="
echo "Testing Vehicle Control GPIO Disable"
echo "========================================="
echo ""

# Source ROS2 environment
source ~/pragati_ros2/install/setup.bash

echo "1. Checking config file..."
echo "---"
grep -A3 "enable_gpio" ~/pragati_ros2/install/vehicle_control/share/vehicle_control/config/production.yaml
echo ""

echo "2. Starting vehicle control node (10 second test)..."
echo "   Looking for GPIO disabled warning..."
echo "---"
timeout 10 ros2 run vehicle_control vehicle_control_node 2>&1 | tee /tmp/vehicle_test.log | grep -E "(GPIO|WARN|enable_gpio|initialized)" | head -20
echo ""

echo "3. Checking log for GPIO status..."
echo "---"
grep -i "gpio" /tmp/vehicle_test.log | head -10
echo ""

echo "4. Test Results:"
echo "---"
if grep -q "GPIO DISABLED" /tmp/vehicle_test.log; then
    echo "✅ GPIO disabled warning found - Feature working correctly!"
elif grep -q "GPIO enabled" /tmp/vehicle_test.log; then
    echo "⚠️  GPIO was enabled - check config file"
else
    echo "⚠️  Could not determine GPIO status - check logs manually"
fi

echo ""
echo "5. Motor services available (GPIO should not interfere):"
echo "---"
timeout 5 ros2 service list | grep vehicle
echo ""

echo "========================================="
echo "Test Complete"
echo "========================================="
