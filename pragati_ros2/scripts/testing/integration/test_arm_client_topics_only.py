#!/usr/bin/env python3
"""
Minimal ARM Client Test - Topics Only
======================================
Tests MQTT → ROS-2 topic publishing without requiring yanthra_move service.
This validates the core bridge functionality.
"""

import time
import sys
import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("ERROR: paho-mqtt not installed")
    sys.exit(1)

# Configuration
MQTT_ADDRESS = 'localhost'
MQTT_PORT = 1883

class SimpleARMClient(Node):
    def __init__(self):
        super().__init__('simple_arm_client_test')

        # Create publishers
        self.start_pub = self.create_publisher(Bool, '/start_switch/command', 10)
        self.shutdown_pub = self.create_publisher(Bool, '/shutdown_switch/command', 10)

        print("✓ ROS-2 publishers created")
        print("  - /start_switch/command")
        print("  - /shutdown_switch/command")

    def publish_start(self, value):
        msg = Bool()
        msg.data = value
        self.start_pub.publish(msg)
        print(f"✓ Published /start_switch/command: {value}")

    def publish_shutdown(self, value):
        msg = Bool()
        msg.data = value
        self.shutdown_pub.publish(msg)
        print(f"✓ Published /shutdown_switch/command: {value}")


# Global node
ros_node = None

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✓ MQTT connected")
        client.subscribe("topic/start_switch_input_arm1")
        client.subscribe("topic/shutdown_switch_input_arm1")
        print("✓ MQTT subscriptions active")
    else:
        print(f"✗ MQTT connection failed: {rc}")

def on_message(client, userdata, msg):
    global ros_node

    print(f"\n📨 MQTT message received: {msg.topic} = {msg.payload}")

    if msg.topic == "topic/start_switch_input_arm1":
        if msg.payload:
            ros_node.publish_start(True)
        else:
            ros_node.publish_start(False)

    elif msg.topic == "topic/shutdown_switch_input_arm1":
        if msg.payload:
            ros_node.publish_shutdown(True)
        else:
            ros_node.publish_shutdown(False)


def main():
    global ros_node

    print("=" * 60)
    print("ARM Client Test - Topics Only")
    print("=" * 60)

    # Initialize ROS-2
    print("\n1. Initializing ROS-2...")
    rclpy.init()
    ros_node = SimpleARMClient()
    print("✓ ROS-2 initialized")

    # Initialize MQTT
    print("\n2. Connecting to MQTT...")
    mqtt_client = mqtt.Client()
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    try:
        mqtt_client.connect(MQTT_ADDRESS, MQTT_PORT, 60)
        mqtt_client.loop_start()
        print(f"✓ MQTT loop started")
    except Exception as e:
        print(f"✗ MQTT connection failed: {e}")
        return 1

    print("\n3. Ready! Listening for MQTT messages...")
    print("   Send test commands with:")
    print("   mosquitto_pub -h localhost -t 'topic/start_switch_input_arm1' -m '1'")
    print("   Press Ctrl+C to exit\n")

    try:
        try:
            while rclpy.ok():
                rclpy.spin_once(ros_node, timeout_sec=0.1)
                time.sleep(0.01)
        except KeyboardInterrupt:
            print("\n\n✓ Shutting down gracefully...")
    finally:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        rclpy.shutdown()
        print("✓ Shutdown complete")
    return 0


if __name__ == '__main__':
    sys.exit(main())
