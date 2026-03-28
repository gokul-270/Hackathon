"""
ROS2 Motor Interface Adapter
Bridges VehicleMotorController with motor_control_ros2 via topics and services

This adapter implements MotorControllerInterface using ROS2 communication:
- Position commands via /{joint}_position_controller/command topics
- Velocity commands via /{joint}_velocity_controller/command topics (when available)
- Enable/disable via /enable_motors, /disable_motors services
- Status from /joint_states subscription
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy
from std_msgs.msg import Float64
from sensor_msgs.msg import JointState
from std_srvs.srv import Trigger
import threading
import time
import logging
from typing import Dict, Optional
from dataclasses import dataclass
from enum import Enum, auto

# Import abstract interface
try:
    from .motor_controller import (
        MotorControllerInterface,
        MotorStatus,
        ControlMode,
        propagate_motor_error,
    )
except ImportError:
    from motor_controller import (
        MotorControllerInterface,
        MotorStatus,
        ControlMode,
        propagate_motor_error,
    )


class ROS2MotorInterface(MotorControllerInterface):
    """
    ROS2 implementation of MotorControllerInterface

    Communicates with motor_control_ros2 package via:
    - Topics for position/velocity commands
    - Services for enable/disable
    - Subscription for joint states
    """

    # Motor ID to joint name mapping for vehicle motors
    # CAN IDs must match vehicle_motors.yaml
    MOTOR_TO_JOINT = {
        # Simplified test mapping: steering=1,2,3 and drive=4,5,6
        1: 'steering_left',
        2: 'steering_right',
        3: 'steering_front',
        4: 'drive_front',
        5: 'drive_left_back',
        6: 'drive_right_back',
    }

    def __init__(self, node: Node):
        """
        Initialize ROS2 motor interface

        Args:
            node: ROS2 node to use for communication
        """
        self._node = node
        self._logger = logging.getLogger(__name__)

        # Publishers for position commands
        self._position_pubs: Dict[int, any] = {}

        # Publishers for velocity commands
        self._velocity_pubs: Dict[int, any] = {}

        # Service clients
        self._enable_client = None
        self._disable_client = None

        # Joint states cache
        self._joint_states: Dict[str, float] = {}
        self._joint_velocities: Dict[str, float] = {}
        self._joint_efforts: Dict[str, float] = {}
        self._states_lock = threading.Lock()

        # Motor enabled states
        self._motor_enabled: Dict[int, bool] = {}

        self._initialized = False

        # Degraded motor tracking (motor_id -> bool)
        self._degraded: Dict[int, bool] = {}

    def initialize(self) -> bool:
        """Initialize ROS2 communication"""
        try:
            self._logger.info("Initializing ROS2 motor interface...")

            # Create QoS profile with VOLATILE durability (no message replay)
            qos = QoSProfile(depth=10)
            qos.durability = DurabilityPolicy.VOLATILE  # Only NEW messages, no history

            # Create publishers for each motor
            for motor_id, joint_name in self.MOTOR_TO_JOINT.items():
                # Position command publisher
                pos_topic = f'/{joint_name}_position_controller/command'
                self._position_pubs[motor_id] = self._node.create_publisher(Float64, pos_topic, qos)
                self._logger.debug(f"Created position publisher: {pos_topic} (QoS=VOLATILE)")

                # Velocity command publisher
                vel_topic = f'/{joint_name}_velocity_controller/command'
                self._velocity_pubs[motor_id] = self._node.create_publisher(Float64, vel_topic, qos)
                self._logger.debug(f"Created velocity publisher: {vel_topic} (QoS=VOLATILE)")

                # Initialize states
                self._motor_enabled[motor_id] = False

            # Create service clients
            self._enable_client = self._node.create_client(Trigger, '/vehicle/enable_motors')
            self._disable_client = self._node.create_client(Trigger, '/vehicle/disable_motors')

            # Subscribe to joint states
            self._node.create_subscription(
                JointState, '/vehicle/joint_states', self._joint_states_callback, 10
            )

            # Wait for services (with timeout)
            if not self._enable_client.wait_for_service(timeout_sec=2.0):
                self._logger.warning(
                    "Enable service not available yet - motor_control may still be initializing"
                )

            self._initialized = True
            self._logger.info("ROS2 motor interface initialized")
            return True

        except Exception as e:
            self._logger.error(f"Failed to initialize ROS2 motor interface: {e}")
            return False

    def _joint_states_callback(self, msg: JointState):
        """Handle joint states from motor_control_ros2"""
        with self._states_lock:
            for i, name in enumerate(msg.name):
                if i < len(msg.position):
                    self._joint_states[name] = msg.position[i]
                if i < len(msg.velocity):
                    self._joint_velocities[name] = msg.velocity[i]
                if i < len(msg.effort):
                    self._joint_efforts[name] = msg.effort[i]

    def _get_joint_name(self, motor_id: int) -> Optional[str]:
        """Get joint name for motor ID"""
        return self.MOTOR_TO_JOINT.get(motor_id)

    def set_control_mode(self, motor_id: int, mode: ControlMode) -> bool:
        """Set motor control mode (handled by motor_control_ros2)"""
        # motor_control_ros2 handles mode switching internally
        # Just log for debugging
        self._logger.debug(f"Control mode request for motor {motor_id}: {mode}")
        return True

    @propagate_motor_error
    def move_to_position(self, motor_id: int, position: float) -> bool:
        """Move motor to absolute position via topic"""
        if motor_id not in self._position_pubs:
            raise ValueError(f"No publisher for motor {motor_id}")

        msg = Float64()
        msg.data = position
        self._position_pubs[motor_id].publish(msg)

        joint_name = self._get_joint_name(motor_id)
        self._logger.debug(f"Position command: {joint_name} -> {position}")
        return True

    @propagate_motor_error
    def set_velocity(self, motor_id: int, velocity: float) -> bool:
        """Set motor velocity via topic"""
        if motor_id not in self._velocity_pubs:
            raise ValueError(f"No velocity publisher for motor {motor_id}")

        msg = Float64()
        msg.data = velocity
        self._velocity_pubs[motor_id].publish(msg)

        joint_name = self._get_joint_name(motor_id)
        self._logger.debug(f"Velocity command: {joint_name} -> {velocity}")
        return True

    def set_torque(self, motor_id: int, torque: float) -> bool:
        """Set motor torque (not currently supported)"""
        self._logger.warning("Torque control not implemented in motor_control_ros2")
        return False

    def get_status(self, motor_id: int) -> MotorStatus:
        """Get motor status from cached joint states"""
        joint_name = self._get_joint_name(motor_id)

        with self._states_lock:
            position = self._joint_states.get(joint_name, 0.0)
            velocity = self._joint_velocities.get(joint_name, 0.0)
            effort = self._joint_efforts.get(joint_name, 0.0)

        return MotorStatus(
            motor_id=motor_id,
            position=position,
            velocity=velocity,
            torque=effort,
            error_code=0,
            control_mode=ControlMode.POSITION,
            is_enabled=self._motor_enabled.get(motor_id, False),
        )

    def enable_motor(self, motor_id: int) -> bool:
        """Enable motor via service"""
        return self._call_enable_service(True)

    def disable_motor(self, motor_id: int) -> bool:
        """Disable motor via service"""
        return self._call_enable_service(False)

    def _call_enable_service(self, enable: bool) -> bool:
        """Call enable/disable service"""
        try:
            client = self._enable_client if enable else self._disable_client

            if not client.service_is_ready():
                self._logger.warning(f"{'Enable' if enable else 'Disable'} service not ready")
                return False

            request = Trigger.Request()
            future = client.call_async(request)

            # Non-blocking - assume success
            # Mark all motors as enabled/disabled
            for motor_id in self.MOTOR_TO_JOINT.keys():
                self._motor_enabled[motor_id] = enable

            return True

        except Exception as e:
            self._logger.error(f"Service call failed: {e}")
            return False

    def clear_errors(self, motor_id: int) -> bool:
        """Clear motor errors (handled by motor_control_ros2)"""
        self._logger.debug(f"Clear errors request for motor {motor_id}")
        return True

    def enable_all_motors(self) -> bool:
        """Enable all motors"""
        return self._call_enable_service(True)

    def disable_all_motors(self) -> bool:
        """Disable all motors"""
        return self._call_enable_service(False)

    def get_position(self, motor_id: int) -> float:
        """Get current motor position"""
        joint_name = self._get_joint_name(motor_id)
        with self._states_lock:
            return self._joint_states.get(joint_name, 0.0)

    def get_velocity(self, motor_id: int) -> float:
        """Get current motor velocity"""
        joint_name = self._get_joint_name(motor_id)
        with self._states_lock:
            return self._joint_velocities.get(joint_name, 0.0)
