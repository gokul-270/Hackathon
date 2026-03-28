#!/bin/bash
# Fix simulation_mode on the Raspberry Pi and rebuild
# Run this script on the Pi directly

set -e

echo "🔧 Fixing simulation_mode in production.yaml..."

# Navigate to workspace
cd ~/pragati_ros2

# Backup the original file
cp src/yanthra_move/config/production.yaml src/yanthra_move/config/production.yaml.backup

# Fix simulation_mode: true -> false on line 116
sed -i '116s/simulation_mode: true/simulation_mode: false/' src/yanthra_move/config/production.yaml

# Verify the change
echo "✅ Verifying the fix..."
grep -n "simulation_mode:" src/yanthra_move/config/production.yaml

echo ""
echo "🔨 Rebuilding yanthra_move package..."

# Source ROS2 environment
source /opt/ros/jazzy/setup.bash

# Rebuild with symlink
colcon build --packages-select yanthra_move --symlink-install

echo ""
echo "✅ Build complete!"
echo ""
echo "📝 Next steps:"
echo "   1. Source the workspace: source ~/pragati_ros2/install/setup.bash"
echo "   2. Launch: ros2 launch yanthra_move pragati_complete.launch.py"
echo ""
echo "🎯 Motors should now receive real commands!"
