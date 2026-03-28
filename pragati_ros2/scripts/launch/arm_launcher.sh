#!/usr/bin/env bash
# arm_launcher.sh - ROS2 ARM (Yanthra Move) Auto Launcher
#
# Launched by arm_launch.service (systemd) on boot.
# ARM_ID and MQTT_ADDRESS are injected by systemd from /etc/default/pragati-arm.
# To configure this RPi's identity: sudo bash setup_arm.sh arm1
#
# Manual launch (for SSH debugging):
#   ARM_ID=arm2 MQTT_ADDRESS=10.42.0.10 bash scripts/launch/arm_launcher.sh

echo "**** ROS2 ARM Control Launcher Script ************************************"

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------
ARM_ID="${ARM_ID:-arm1}"
MQTT_ADDRESS="${MQTT_ADDRESS:-10.42.0.10}"
echo "ARM identity: ARM_ID=${ARM_ID}, MQTT_ADDRESS=${MQTT_ADDRESS}"
echo "To reconfigure: sudo bash setup_arm.sh <arm_id>"

# ---------------------------------------------------------------------------
# CAN interface setup
# ---------------------------------------------------------------------------
echo "Setting up CAN interface..."
sudo ip link set can0 down 2>/dev/null
sudo ip link set can0 up type can bitrate 500000 2>/dev/null && echo "CAN interface can0 is UP" || echo "WARNING: CAN interface setup failed (hardware not connected)"

# ---------------------------------------------------------------------------
# ROS2 workspace
# ---------------------------------------------------------------------------
echo "Sourcing ROS2 environment..."
source /opt/ros/jazzy/setup.bash
source "$HOME/pragati_ros2/install/setup.bash"

# ROS domain/isolation config
# NOTE: systemd services do NOT source ~/.bashrc by default.
# If your interactive SSH shell has ROS_DOMAIN_ID set (e.g., in ~/.bashrc) but the boot service does not,
# ROS2 pub/sub can silently fail due to domain mismatch.
#
# Recommendation:
# - Prefer using unique ROS_DOMAIN_ID per robot (arm1/arm2/vehicle).
# - Avoid forcing ROS_LOCALHOST_ONLY=1 unless you are sure all publishers/subscribers are also localhost-only.
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
export ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-0}"

# RMW (DDS middleware) selection.
# IMPORTANT: systemd does NOT source ~/.bashrc, so this MUST be set explicitly here.
# setup_raspberry_pi.sh writes rmw_cyclonedds_cpp to ~/.bashrc (for SSH sessions),
# but this script is the authoritative config for production (systemd) launches.
# All nodes in this launch MUST use the same RMW or services/topics will be invisible.
export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_cyclonedds_cpp}"

# CycloneDDS shared-memory (iceoryx) transport is broken on RPi 4B / ARM64.
# Without this config, Python nodes cannot discover C++ nodes (arm_client crash loop).
# See config/cyclonedds.xml for details.
CYCLONEDDS_CONFIG="$HOME/pragati_ros2/config/cyclonedds.xml"
if [ -f "$CYCLONEDDS_CONFIG" ]; then
    export CYCLONEDDS_URI="file://${CYCLONEDDS_CONFIG}"
else
    echo "WARNING: CycloneDDS config not found at $CYCLONEDDS_CONFIG — DDS discovery may fail"
fi

echo "ROS_DOMAIN_ID=$ROS_DOMAIN_ID, ROS_LOCALHOST_ONLY=$ROS_LOCALHOST_ONLY, RMW_IMPLEMENTATION=$RMW_IMPLEMENTATION"
echo "CYCLONEDDS_URI=${CYCLONEDDS_URI:-<not set>}"

# Per-arm log directory so logs are identifiable by arm identity.
# Creates ~/.ros/log/<arm_id>/YYYY-MM-DD-HH-MM-SS-us-host-pid/ structure.
export ROS_LOG_DIR="${HOME}/.ros/log/${ARM_ID}"
echo "ROS_LOG_DIR=$ROS_LOG_DIR"

# Boot optimization: 3s post-source sleep removed (was a workaround for ROS2 env settling)

# ---------------------------------------------------------------------------
# Simulation mode (operator override only)
# ---------------------------------------------------------------------------
# Defaults to false (production). To enable simulation on an RPi without
# hardware (e.g., arm2 with no CAN hat / camera), set USE_SIMULATION=true
# in /etc/default/pragati-arm on that specific RPi. This is an explicit
# operator decision — the launcher NEVER auto-detects hardware absence.
USE_SIMULATION="${USE_SIMULATION:-false}"
echo "Simulation mode: ${USE_SIMULATION}"

# ---------------------------------------------------------------------------
# Launch ROS2 ARM Control
# ARM_client.py is launched from inside pragati_complete.launch.py via
# ExecuteProcess with a 5s TimerAction delay -- do NOT launch it here.
# Pass arm_id and mqtt_address so they are forwarded to ARM_client.py.
# ---------------------------------------------------------------------------
echo "**** Starting ROS2 ARM Control (Yanthra Move) ************************************"
ros2 launch yanthra_move pragati_complete.launch.py \
    use_simulation:="${USE_SIMULATION}" \
    continuous_operation:=true \
    enable_cotton_detection:=true \
    depthai_model_path:=/home/ubuntu/pragati_ros2/data/models/yolov112.blob \
    depthai_num_classes:=2 \
    arm_id:="${ARM_ID}" \
    mqtt_address:="${MQTT_ADDRESS}"

echo "**** ARM service exited *********************************************"

# Keep script running (wait for any background jobs)
wait
