#!/usr/bin/env bash
# launcher.sh - ROS2 Vehicle Control and MQTT Bridge Launcher
# This script launches the main vehicle control system and MQTT bridge

echo "**** ROS2 Vehicle Launcher Script ************************************"

# Set up CAN interface
echo "Setting up CAN interface..."
sudo ip link set can0 down
sudo ip link set can0 up type can bitrate 500000 restart-ms 100 berr-reporting on || echo "CAN interface setup failed (may not be connected)"
sudo ip link set can0 txqueuelen 1000 || echo "Failed to set CAN txqueuelen"

# Source ROS2 workspace
echo "Sourcing ROS2 environment..."
source /opt/ros/jazzy/setup.bash
source $HOME/pragati_ros2/install/setup.bash

# ROS2 domain isolation -- ensure consistent domain between systemd and manual launch.
# Values come from systemd Environment= or default to 0 (vehicle domain).
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
export ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-0}"

# RMW (DDS middleware) selection.
# IMPORTANT: systemd does NOT source ~/.bashrc, so this MUST be set explicitly here.
# setup_raspberry_pi.sh writes rmw_cyclonedds_cpp to ~/.bashrc (for SSH sessions),
# but this script is the authoritative config for production (systemd) launches.
# All nodes in this launch MUST use the same RMW or services/topics will be invisible.
export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_cyclonedds_cpp}"

# CycloneDDS shared-memory (iceoryx) transport is broken on RPi 4B / ARM64.
# Without this config, Python nodes cannot discover C++ nodes.
# See config/cyclonedds.xml for details.
CYCLONEDDS_CONFIG="$HOME/pragati_ros2/config/cyclonedds.xml"
if [ -f "$CYCLONEDDS_CONFIG" ]; then
    export CYCLONEDDS_URI="file://${CYCLONEDDS_CONFIG}"
else
    echo "WARNING: CycloneDDS config not found at $CYCLONEDDS_CONFIG — DDS discovery may fail"
fi

echo "ROS_DOMAIN_ID=$ROS_DOMAIN_ID, ROS_LOCALHOST_ONLY=$ROS_LOCALHOST_ONLY, RMW_IMPLEMENTATION=$RMW_IMPLEMENTATION"
echo "CYCLONEDDS_URI=${CYCLONEDDS_URI:-<not set>}"

# Vehicle log directory so logs are identifiable by role.
# Creates ~/.ros/log/vehicle/YYYY-MM-DD-HH-MM-SS-us-host-pid/ structure.
export ROS_LOG_DIR="${HOME}/.ros/log/vehicle"
echo "ROS_LOG_DIR=$ROS_LOG_DIR"

# Boot optimization: 3s post-source sleep removed (was a workaround for ROS2 env settling)

# Launch ROS2 Vehicle Control in background
# NOTE: vehicle_complete.launch.py also launches the MQTT bridge via TimerAction
# (with a 5s delay). Do NOT launch vehicle_mqtt_bridge.py separately here --
# that would create duplicate MQTT bridge instances with conflicting subscriptions.
echo "**** Starting ROS2 Vehicle Control ************************************"
ros2 launch vehicle_control vehicle_complete.launch.py &
VEHICLE_PID=$!
echo "Vehicle Control started with PID: $VEHICLE_PID"

echo "**** All services started *********************************************"

# Keep script running (Type=simple expects this)
wait
