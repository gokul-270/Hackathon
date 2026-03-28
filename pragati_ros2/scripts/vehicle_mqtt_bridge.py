#!/usr/bin/env python3
"""
Vehicle MQTT Bridge - ARM Status MQTT-to-ROS2 Bridge for Vehicle RPi
=====================================================================
Subscribes to ARM status MQTT topics and forwards them to ROS2 for
vehicle_control_node consumption. Start/shutdown commands are published
directly to MQTT by vehicle_control_node and no longer pass through
this bridge.

MQTT Topics (Subscribe):
  - topic/ArmStatus_<arm_id>     : Status from ARM (ready/busy/ACK/error/UNINITIALISED)

ROS2 Topics (Publish):
  - /vehicle/arm_status          : String (ARM status for vehicle to use)

Configuration:
  - MQTT broker runs on localhost (vehicle RPi)
  - ARM RPi connects to vehicle's broker at 192.168.1.40:1883
"""

import time
import threading
import sys
import os
import logging
from datetime import datetime

# Setup file logging with timestamped filenames
LOG_DIR = os.path.expanduser('~/pragati_ros2/logs')
os.makedirs(LOG_DIR, exist_ok=True)

# Create timestamped log file to prevent overwrites
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
LOG_FILE = os.path.join(LOG_DIR, f'vehicle_mqtt_bridge_{timestamp}.log')

# Implement log rotation: keep only last 10 log files
import glob
log_files = sorted(glob.glob(os.path.join(LOG_DIR, 'vehicle_mqtt_bridge_*.log')))
if len(log_files) > 10:
    for old_log in log_files[:-10]:
        try:
            os.remove(old_log)
            print(f"Removed old log file: {old_log}")
        except Exception as e:
            print(f"Warning: Could not remove old log {old_log}: {e}")

# Configure logging to both file and console
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('VEHICLE_MQTT_BRIDGE')
logger.info(f"Vehicle MQTT Bridge started. Logging to: {LOG_FILE}")

# ROS2 imports
import rclpy
from rclpy.node import Node
from rclpy.executors import SingleThreadedExecutor
from std_msgs.msg import String

# MQTT import
try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("ERROR: paho-mqtt not installed. Run: pip3 install paho-mqtt")
    sys.exit(1)

# ==============================================
# CONFIGURATION
# ==============================================
DEBUG = True

# MQTT Configuration
MQTT_BROKER = 'localhost'  # Vehicle runs the broker locally
MQTT_PORT = 1883
CLIENT_ID = 'vehicle_mqtt_bridge'

# ARM Configuration - List of all ARM client IDs
ARM_CLIENT_IDS = ['arm1', 'arm2']  # Add more ARM IDs as needed

# Recovery Configuration
MQTT_RECONNECT_INTERVAL = 5.0  # seconds between reconnection attempts
PUBLISH_RETRY_COUNT = 3  # Number of retries for failed publishes
HEALTH_CHECK_INTERVAL = 10.0  # seconds
MAX_MQTT_DISCONNECT_TIME = 60.0  # seconds before warning

# MQTT reason code lookup table
MQTT_RC_CODES = {
    0: "Connection successful",
    1: "Incorrect protocol version",
    2: "Invalid client identifier",
    3: "Server unavailable",
    4: "Bad username or password",
    5: "Not authorized",
    7: "Connection lost (keepalive timeout or network failure)",
}

# ==============================================
# GLOBAL STATE
# ==============================================
mqtt_client = None
ros_node = None
arm_statuses = {}  # Dictionary to store status of each ARM: {'arm5': 'ready', 'arm6': 'busy'}

# Recovery state
mqtt_connected = False
last_mqtt_disconnect_time = None
connection_recovery_active = False
publish_failure_count = 0

# MQTT reconnection tracking
mqtt_connection_count = 0  # Track total connections (initial + reconnects)
mqtt_reconnect_count = 0   # Track only reconnections (excludes initial)


# ==============================================
# HELPER FUNCTIONS
# ==============================================
def log_info(msg):
    """Print info messages - now uses logger"""
    if DEBUG:
        logger.info(msg)


# ==============================================
# MQTT CALLBACKS
# ==============================================
def on_connect(client, userdata, flags, rc):
    """MQTT connection callback"""
    global mqtt_connected, last_mqtt_disconnect_time, publish_failure_count
    global mqtt_connection_count, mqtt_reconnect_count

    mqtt_connection_count += 1

    if rc == 0:
        # Determine if this is initial connection or reconnection
        is_reconnect = mqtt_connection_count > 1

        if is_reconnect:
            mqtt_reconnect_count += 1
            logger.warning(f"MQTT RECONNECTED successfully (reconnect #{mqtt_reconnect_count}, total connections: {mqtt_connection_count})")
        else:
            log_info("MQTT Connected to broker (initial connection)")

        mqtt_connected = True
        last_mqtt_disconnect_time = None
        publish_failure_count = 0

        # Clear retained ArmStatus messages (stale LWT "offline" from
        # previous sessions) so the bridge doesn't report arms as offline
        # when they are actually connected and publishing live status.
        for arm_id in ARM_CLIENT_IDS:
            arm_status_topic = f'topic/ArmStatus_{arm_id}'
            client.publish(arm_status_topic, payload='', retain=True)
            log_info(f"Cleared retained message on {arm_status_topic}")

        # Subscribe to all ARM status topics
        for arm_id in ARM_CLIENT_IDS:
            arm_status_topic = f'topic/ArmStatus_{arm_id}'
            result, mid = client.subscribe(arm_status_topic)
            if result == mqtt.MQTT_ERR_SUCCESS:
                log_info(f"Subscribed to {arm_status_topic}")
            else:
                logger.error(f"Failed to subscribe to {arm_status_topic}: error {result}")
    else:
        mqtt_connected = False
        rc_desc = MQTT_RC_CODES.get(rc, "Unknown reason code")
        logger.error(f"MQTT connection failed (code={rc}: {rc_desc})")


def on_message(client, userdata, msg):
    """MQTT message received callback - handle ARM status"""
    global arm_statuses, ros_node

    topic = msg.topic
    payload = msg.payload.decode('utf-8')

    log_info(f"📥 MQTT received: {topic} = {payload}")

    # Handle ARM status updates from any ARM
    for arm_id in ARM_CLIENT_IDS:
        if topic == f'topic/ArmStatus_{arm_id}':
            arm_statuses[arm_id] = payload

            # Publish individual ARM status to ROS2
            if ros_node is not None:
                status_msg = String()
                status_msg.data = f"{arm_id}:{payload}"  # Format: "arm5:ready"
                ros_node.arm_status_pub.publish(status_msg)
                log_info(f"📤 Published {arm_id} status to ROS2: {payload}")
            break


def on_disconnect(client, userdata, rc):
    """MQTT disconnection callback"""
    global mqtt_connected, last_mqtt_disconnect_time, mqtt_reconnect_count

    mqtt_connected = False
    last_mqtt_disconnect_time = time.time()

    if rc != 0:
        rc_desc = MQTT_RC_CODES.get(rc, "Unknown reason code")
        logger.warning(f"MQTT UNEXPECTED DISCONNECT (code={rc}: {rc_desc}). Auto-reconnect will attempt to restore connection... (previous reconnects: {mqtt_reconnect_count})")
    else:
        log_info("MQTT disconnected cleanly")


# ==============================================
# MQTT PUBLISH WITH RETRY
# ==============================================
def publish_with_retry(topic, payload):
    """Publish MQTT message with retry logic.

    Attempts up to PUBLISH_RETRY_COUNT times with 0.5s delay between retries.
    Returns True on success, False on failure.
    """
    global publish_failure_count, mqtt_client, mqtt_connected

    if not mqtt_connected:
        logger.error(f"Cannot publish to {topic} -- MQTT not connected")
        return False

    for attempt in range(1, PUBLISH_RETRY_COUNT + 1):
        try:
            result = mqtt_client.publish(topic, payload, retain=False)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.debug(f"Published to {topic}: {payload}")
                return True
            else:
                logger.warning(f"Publish to {topic} failed (rc={result.rc}), attempt {attempt}/{PUBLISH_RETRY_COUNT}")
        except Exception as e:
            logger.warning(f"Publish to {topic} exception (attempt {attempt}/{PUBLISH_RETRY_COUNT}): {e}")

        if attempt < PUBLISH_RETRY_COUNT:
            time.sleep(0.5)

    # All retries exhausted
    publish_failure_count += 1
    logger.error(f"Failed to publish to {topic} after {PUBLISH_RETRY_COUNT} attempts")
    return False


# ==============================================
# MQTT HEALTH CHECK
# ==============================================
def check_mqtt_health():
    """Log current MQTT connection health status.

    Called periodically from the health monitor thread.
    Logs connection state, time since disconnect, publish failures,
    and per-arm last-seen status.
    """
    global mqtt_connected, last_mqtt_disconnect_time, publish_failure_count, arm_statuses

    if mqtt_connected:
        disconnect_info = ""
        if last_mqtt_disconnect_time is not None:
            time_since = time.time() - last_mqtt_disconnect_time
            disconnect_info = f", last disconnect {time_since:.0f}s ago"
        logger.debug(f"MQTT health: connected, publish failures={publish_failure_count}{disconnect_info}")
    else:
        if last_mqtt_disconnect_time is not None:
            disconnect_duration = time.time() - last_mqtt_disconnect_time
            if disconnect_duration > MAX_MQTT_DISCONNECT_TIME:
                logger.error(f"MQTT health: DISCONNECTED for {disconnect_duration:.0f}s (exceeds {MAX_MQTT_DISCONNECT_TIME}s threshold), publish failures={publish_failure_count}")
            else:
                logger.warning(f"MQTT health: disconnected for {disconnect_duration:.0f}s, publish failures={publish_failure_count}")
        else:
            logger.warning(f"MQTT health: disconnected (no prior connection), publish failures={publish_failure_count}")

    # Log per-arm status
    if arm_statuses:
        for arm_id, status in arm_statuses.items():
            logger.debug(f"MQTT health: {arm_id} last status = {status}")
    else:
        logger.debug("MQTT health: no ARM status received yet")


# ==============================================
# ROS2 NODE CLASS
# ==============================================
class VehicleMQTTBridge(Node):
    """ROS2 node for vehicle MQTT bridge"""

    def __init__(self):
        super().__init__('vehicle_mqtt_bridge')

        # Publishers (to ROS2)
        self.arm_status_pub = self.create_publisher(String, '/vehicle/arm_status', 10)

        log_info("ROS2 Vehicle MQTT Bridge initialized (arm status only)")
        log_info("   Publishers: /vehicle/arm_status")


# ==============================================
# MQTT SETUP
# ==============================================
def setup_mqtt():
    """Setup MQTT connection to local broker with auto-reconnect"""
    global mqtt_client

    log_info("Setting up MQTT connection...")
    mqtt_client = mqtt.Client(client_id=CLIENT_ID)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.on_disconnect = on_disconnect

    # Enable automatic reconnection with exponential backoff
    mqtt_client.reconnect_delay_set(min_delay=1, max_delay=60)

    retry_count = 0
    max_initial_retries = 10

    while retry_count < max_initial_retries:
        try:
            log_info(f"Connecting to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}... (attempt {retry_count + 1})")
            mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            mqtt_client.loop_start()  # Start network loop in background thread
            log_info("✅ MQTT connection started")
            return True
        except Exception as e:
            retry_count += 1
            if retry_count >= max_initial_retries:
                print(f"❌ Failed to connect to MQTT broker after {max_initial_retries} attempts: {e}")
                return False
            else:
                print(f"⚠️ Connection attempt {retry_count} failed: {e}, retrying...")
                time.sleep(MQTT_RECONNECT_INTERVAL)


# ==============================================
# MAIN
# ==============================================
def main():
    global ros_node, mqtt_client

    print("=" * 60)
    print("Vehicle MQTT Bridge - ROS2 ↔ MQTT")
    print("=" * 60)

    # Initialize ROS2
    try:
        rclpy.init()
        ros_node = VehicleMQTTBridge()
        log_info("✅ ROS2 initialized")
    except Exception as e:
        print(f"❌ Failed to initialize ROS2: {e}")
        return 1

    # Setup MQTT
    if not setup_mqtt():
        rclpy.shutdown()
        return 1

    # Wait for MQTT connection
    time.sleep(2)

    log_info("=" * 60)
    log_info("Vehicle MQTT Bridge is running (arm status only)")
    log_info("=" * 60)
    log_info("MQTT → ROS2:")
    for arm_id in ARM_CLIENT_IDS:
        log_info(f"  topic/ArmStatus_{arm_id} → /vehicle/arm_status")
    log_info("=" * 60)

    # Start health monitoring thread
    def health_monitor():
        """Background thread for health monitoring"""
        while rclpy.ok():
            try:
                check_mqtt_health()
                time.sleep(HEALTH_CHECK_INTERVAL)
            except Exception as e:
                print(f"❌ Health monitor error: {e}")

    health_thread = threading.Thread(target=health_monitor, daemon=True)
    health_thread.start()
    log_info("✅ Health monitoring thread started")

    # Run ROS2 spin
    executor = SingleThreadedExecutor()
    executor.add_node(ros_node)

    try:
        executor.spin()
    except KeyboardInterrupt:
        log_info("Shutting down...")
    finally:
        # Cleanup
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        ros_node.destroy_node()
        rclpy.shutdown()

    return 0


if __name__ == '__main__':
    sys.exit(main())
