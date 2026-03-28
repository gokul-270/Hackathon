#!/bin/bash
# Quick test script for veh1 robot

echo "========================================="
echo "veh1 Robot Test Script"
echo "========================================="
echo ""

# Source workspace
echo "1. Sourcing workspace..."
source ~/steering\ control/install/setup.bash

# Check if veh1 package exists
echo "2. Checking veh1 package..."
if ros2 pkg list | grep -q "^veh1$"; then
    echo "   ✓ veh1 package found"
else
    echo "   ✗ veh1 package NOT found!"
    exit 1
fi

# Check executables
echo "3. Checking executables..."
if [ -f ~/steering\ control/install/veh1/lib/veh1/kinematics_node.py ]; then
    echo "   ✓ kinematics_node.py found"
else
    echo "   ✗ kinematics_node.py NOT found!"
fi

if [ -f ~/steering\ control/install/veh1/lib/veh1/joy_teleop.py ]; then
    echo "   ✓ joy_teleop.py found"
else
    echo "   ✗ joy_teleop.py NOT found!"
fi

# Check launch files
echo "4. Checking launch files..."
if [ -f ~/steering\ control/install/veh1/share/veh1/launch/gazebo_with_joy.launch.py ]; then
    echo "   ✓ gazebo_with_joy.launch.py found"
else
    echo "   ✗ gazebo_with_joy.launch.py NOT found!"
fi

# Check URDF
echo "5. Checking URDF..."
if [ -f ~/steering\ control/install/veh1/share/veh1/urdf/vehicle.urdf ]; then
    echo "   ✓ vehicle.urdf found"
else
    echo "   ✗ vehicle.urdf NOT found!"
fi

echo ""
echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo ""
echo "To launch with joystick:"
echo "  ros2 launch veh1 gazebo_with_joy.launch.py"
echo ""
echo "To launch without joystick:"
echo "  ros2 launch veh1 gazebo_with_joy.launch.py use_joystick:=false"
echo ""
echo "To test with command line:"
echo "  ros2 topic pub /cmd_vel geometry_msgs/msg/Twist \"{linear: {x: 0.3}, angular: {z: 0.0}}\""
echo ""
echo "========================================="
