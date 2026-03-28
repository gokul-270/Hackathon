"""Full pipeline integration test using launch_testing.

Launches all 3 pipeline nodes via pragati_complete.launch.py with simulation
overrides, sends a start trigger, and verifies the full picking cycle
(detection -> IK -> motor commands -> feedback) completes end-to-end.

motor_control_ros2 runs with simulation_mode=true which activates the
ConfigurableMockCANInterface + MotorPhysicsSimulator.  This means /joint_states
(merged via joint_state_publisher) MUST reflect real simulated position changes
when motor commands are sent.  If positions don't change, the test FAILS —
there is no soft-check fallback.

Validates: FR-DET-001 (detection), PERF-ARM-001 (arm motion) in simulation.
"""

import os
import time
import unittest

import launch
import launch_testing
import launch_testing.actions
from launch.actions import IncludeLaunchDescription, SetEnvironmentVariable
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool, Float64
from cotton_detection_msgs.msg import DetectionResult

# Set env var at import time to ensure it's available when
# launch_testing evaluates generate_launch_description() of included files.
os.environ["PRAGATI_SKIP_CLEANUP"] = "1"


# Timeouts
NODE_READY_TIMEOUT_SEC = 60
CYCLE_TIMEOUT_SEC = 120
TRIGGER_RETRY_SEC = 2.0
# Motor physics simulator settling time — need to wait for positions to settle
MOTOR_SETTLE_SEC = 30


def generate_test_description():
    """Launch pragati_complete.launch.py with simulation overrides."""
    pragati_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            [
                PathJoinSubstitution(
                    [
                        FindPackageShare("yanthra_move"),
                        "launch",
                        "pragati_complete.launch.py",
                    ]
                )
            ]
        ),
        launch_arguments={
            "use_simulation": "true",
            "continuous_operation": "false",
            "enable_arm_client": "false",
            "skip_cleanup": "true",
        }.items(),
    )

    return (
        launch.LaunchDescription(
            [
                SetEnvironmentVariable("PRAGATI_SKIP_CLEANUP", "1"),
                pragati_launch,
                launch_testing.actions.ReadyToTest(),
            ]
        ),
        {"pragati_launch": pragati_launch},
    )


class TestFullPipeline(unittest.TestCase):
    """End-to-end pipeline test: trigger -> detection -> motion -> feedback."""

    @classmethod
    def setUpClass(cls):
        try:
            rclpy.init()
        except RuntimeError:
            pass  # Already initialized by launch_testing framework

    @classmethod
    def tearDownClass(cls):
        try:
            rclpy.shutdown()
        except RuntimeError:
            pass  # Already shut down by launch_testing framework

    def setUp(self):
        self.node = Node("test_full_pipeline")
        self.joint_states_received = []
        self.motor_joint_states_received = []
        self.detection_results_received = []
        self.joint_cmds_received = {
            "joint3": [],
            "joint4": [],
            "joint5": [],
        }

        # Subscribe to /joint_states (merged output from joint_state_publisher)
        self.joint_sub = self.node.create_subscription(
            JointState,
            "/joint_states",
            self._joint_states_cb,
            QoSProfile(depth=50, reliability=ReliabilityPolicy.RELIABLE),
        )

        # Subscribe to /motor_joint_states (direct from motor_control simulation)
        # This lets us verify motor_control is actually in sim mode and producing
        # position feedback independently of joint_state_publisher merging.
        self.motor_joint_sub = self.node.create_subscription(
            JointState,
            "/motor_joint_states",
            self._motor_joint_states_cb,
            QoSProfile(depth=50, reliability=ReliabilityPolicy.RELIABLE),
        )

        # Subscribe to detection results
        # QoS must match cotton_detection_node publisher:
        # Reliable, KeepLast(10), Volatile
        detection_qos = QoSProfile(
            depth=50,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )
        self.detection_sub = self.node.create_subscription(
            DetectionResult,
            "/cotton_detection/results",
            self._detection_results_cb,
            detection_qos,
        )

        # Subscribe to joint position commands (verify yanthra_move sends them)
        for joint_name in ["joint3", "joint4", "joint5"]:
            topic = f"/{joint_name}_position_controller/command"
            self.node.create_subscription(
                Float64,
                topic,
                lambda msg, jn=joint_name: self.joint_cmds_received[jn].append(msg.data),
                QoSProfile(
                    depth=50,
                    reliability=ReliabilityPolicy.RELIABLE,
                    durability=DurabilityPolicy.VOLATILE,
                ),
            )

        # Publisher for start trigger
        self.start_pub = self.node.create_publisher(
            Bool,
            "/start_switch/command",
            QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE),
        )

    def tearDown(self):
        self.node.destroy_node()

    def _joint_states_cb(self, msg):
        self.joint_states_received.append(msg)

    def _motor_joint_states_cb(self, msg):
        self.motor_joint_states_received.append(msg)

    def _detection_results_cb(self, msg):
        self.detection_results_received.append(msg)

    def _spin_until(self, condition, timeout_sec, poll_interval=0.1):
        """Spin the node until condition() returns True or timeout."""
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            rclpy.spin_once(self.node, timeout_sec=poll_interval)
            if condition():
                return True
        return False

    def _is_yanthra_move_ready(self):
        """Check if yanthra_move node is present in the ROS2 graph."""
        node_names = self.node.get_node_names()
        return "yanthra_move" in node_names

    def test_01_nodes_ready(self):
        """Verify all pipeline nodes ready AND motor_control in sim mode."""
        # Wait for /joint_states (from joint_state_publisher, which merges
        # /motor_joint_states from motor_control)
        has_joint_states = self._spin_until(
            lambda: len(self.joint_states_received) > 0,
            NODE_READY_TIMEOUT_SEC,
        )
        self.assertTrue(
            has_joint_states,
            f"/joint_states not received within {NODE_READY_TIMEOUT_SEC}s "
            "-- motor_control_node or joint_state_publisher not running",
        )

        # CRITICAL: Verify motor_control is publishing on /motor_joint_states.
        # This proves it entered simulation_mode and the MockCAN interface is
        # active.  Without this check, motor_control could be silently running
        # in hardware mode with zero motors and the test would still pass on
        # static joint_state_publisher output — that's a false positive.
        has_motor_states = self._spin_until(
            lambda: len(self.motor_joint_states_received) > 0,
            NODE_READY_TIMEOUT_SEC,
        )
        self.assertTrue(
            has_motor_states,
            "/motor_joint_states not received within "
            f"{NODE_READY_TIMEOUT_SEC}s -- motor_control_node is NOT in "
            "simulation mode. Check that simulation_mode parameter is "
            "forwarded to mg6010_controller_node in pragati_complete.launch.py",
        )

        # Verify motor_control is publishing joint names (not empty)
        last_motor_msg = self.motor_joint_states_received[-1]
        self.assertGreater(
            len(last_motor_msg.name),
            0,
            "/motor_joint_states has no joint names — motor_control may have "
            "0 motors initialized despite simulation_mode=true",
        )
        self.node.get_logger().info(
            f"motor_control sim mode verified: publishing {last_motor_msg.name}"
        )

        # Wait for /cotton_detection/detect service
        service_ready = self._spin_until(
            lambda: any(
                "/cotton_detection/detect" in name
                for name, _ in self.node.get_service_names_and_types()
            ),
            NODE_READY_TIMEOUT_SEC,
        )
        self.assertTrue(
            service_ready,
            "/cotton_detection/detect service not available within "
            f"{NODE_READY_TIMEOUT_SEC}s -- cotton_detection_node not running",
        )

    def test_02_full_cycle_with_detection(self):
        """Send start trigger and verify complete picking cycle.

        This test verifies the ENTIRE pipeline with REAL assertions:
        1. Wait for all nodes ready (including yanthra_move)
        2. Send start trigger (retries until yanthra_move accepts it)
        3. ASSERT detection results published to /cotton_detection/results
        4. ASSERT joint position commands sent by yanthra_move
        5. ASSERT /joint_states reflect non-zero position changes from
           motor_control's physics simulator
        """
        # Wait for yanthra_move node in the graph
        ym_ready = self._spin_until(
            self._is_yanthra_move_ready,
            NODE_READY_TIMEOUT_SEC,
        )
        self.assertTrue(
            ym_ready,
            "yanthra_move node not in ROS2 graph within " f"{NODE_READY_TIMEOUT_SEC}s",
        )

        self.node.get_logger().info("yanthra_move found, waiting for initialization...")

        # Wait for motor_control sim mode (must be verified before trigger)
        motor_sim_ready = self._spin_until(
            lambda: len(self.motor_joint_states_received) > 0,
            NODE_READY_TIMEOUT_SEC,
        )
        self.assertTrue(
            motor_sim_ready,
            "motor_control not publishing /motor_joint_states — " "simulation_mode not active",
        )

        # Wait for joint_states to be flowing
        nodes_ready = self._spin_until(
            lambda: len(self.joint_states_received) > 0,
            NODE_READY_TIMEOUT_SEC,
        )
        self.assertTrue(nodes_ready, "/joint_states not flowing")

        # Record initial state
        initial_positions = list(self.joint_states_received[-1].position)
        initial_names = list(self.joint_states_received[-1].name)
        self.node.get_logger().info(
            f"Initial joint state: {dict(zip(initial_names, initial_positions))}"
        )
        self.joint_states_received.clear()
        self.detection_results_received.clear()
        for k in self.joint_cmds_received:
            self.joint_cmds_received[k].clear()

        # Publish trigger repeatedly until joint commands prove the cycle ran.
        #
        # IMPORTANT: We break on joint commands, NOT detection results.
        # yanthra_move performs a warm-up detection BEFORE enabling
        # START_SWITCH processing, so detection results alone don't mean
        # the picking cycle started — they could be warm-up results.
        # Joint position commands only appear during the actual cycle
        # (after IK computation), so they are the definitive indicator.
        #
        # We also clear detection_results that arrived before the first
        # trigger to filter out warm-up results.
        trigger_msg = Bool()
        trigger_msg.data = True

        deadline = time.monotonic() + CYCLE_TIMEOUT_SEC
        last_trigger_time = 0.0
        first_trigger_sent = False

        def has_joint_cmds():
            return any(len(v) > 0 for v in self.joint_cmds_received.values())

        while time.monotonic() < deadline:
            now = time.monotonic()

            if now - last_trigger_time >= TRIGGER_RETRY_SEC:
                # Clear any warm-up detection results before first trigger
                if not first_trigger_sent:
                    warmup_count = len(self.detection_results_received)
                    if warmup_count > 0:
                        self.node.get_logger().info(
                            f"Clearing {warmup_count} warm-up detection "
                            "result(s) before sending first trigger"
                        )
                    self.detection_results_received.clear()
                    first_trigger_sent = True

                self.start_pub.publish(trigger_msg)
                self.node.get_logger().info("Published start trigger to /start_switch/command")
                last_trigger_time = now

            rclpy.spin_once(self.node, timeout_sec=0.1)

            # Joint commands are the definitive proof the cycle ran
            if has_joint_cmds():
                break

        self.assertTrue(
            has_joint_cmds(),
            "No joint position commands received on "
            "/joint{3,4,5}_position_controller/command within "
            f"{CYCLE_TIMEOUT_SEC}s — yanthra_move did not generate "
            "motor commands. Either the start trigger was never "
            "accepted, or detection → IK → command pipeline failed.",
        )
        cmd_summary = {k: len(v) for k, v in self.joint_cmds_received.items() if v}
        self.node.get_logger().info(f"Joint commands received: {cmd_summary}")

        # Drain pending callbacks — the detection result may be queued but
        # undelivered if the joint command callback fired first.
        for _ in range(20):
            rclpy.spin_once(self.node, timeout_sec=0.05)
            if self.detection_results_received:
                break

        # Verify detection results have actual content.
        # These should only be cycle-triggered detections (warm-up was cleared).
        self.assertGreater(
            len(self.detection_results_received),
            0,
            "No detection results received during cycle — but joint commands "
            "were received, which is contradictory. Possible QoS mismatch.",
        )
        det_msg = self.detection_results_received[0]
        self.node.get_logger().info(
            f"Detection: successful={det_msg.detection_successful}, "
            f"count={det_msg.total_count}, positions={len(det_msg.positions)}"
        )
        self.assertTrue(
            det_msg.detection_successful,
            "Detection was not successful — cotton_detection_node simulation "
            "should always return simulated cotton positions",
        )
        self.assertGreater(
            det_msg.total_count,
            0,
            "Detection returned 0 cotton positions — simulation is broken",
        )

        # CRITICAL: Verify joint positions actually changed.
        # motor_control in simulation_mode uses MotorPhysicsSimulator which
        # applies first-order dynamics to commanded positions. The positions
        # MUST change. If they don't, either:
        # - simulation_mode isn't reaching motor_control (parameter bug)
        # - joint_state_publisher isn't merging /motor_joint_states
        # - physics simulator isn't stepping (timer issue)
        MOTOR_JOINTS = {"joint3", "joint4", "joint5"}

        def moved_joints():
            """Return set of motor joints whose position changed > 0.001."""
            moved = set()
            for msg in self.joint_states_received:
                if len(msg.position) == 0 or len(initial_positions) == 0:
                    continue
                for i, pos in enumerate(msg.position):
                    if i < len(initial_positions) and i < len(msg.name):
                        if msg.name[i] in MOTOR_JOINTS and abs(pos - initial_positions[i]) > 0.001:
                            moved.add(msg.name[i])
            return moved

        def has_position_change():
            # At least one motor joint must move — IK strategy may not
            # require all joints for the simulated cotton positions.
            return len(moved_joints()) > 0

        position_changed = self._spin_until(
            has_position_change,
            min(MOTOR_SETTLE_SEC, max(5, deadline - time.monotonic())),
        )

        # Log what we actually saw for debugging
        if self.joint_states_received:
            last_js = self.joint_states_received[-1]
            final_positions = list(last_js.position)
            final_names = list(last_js.name)
            self.node.get_logger().info(
                f"Final joint state: {dict(zip(final_names, final_positions))}"
            )
            deltas = {}
            for i, name in enumerate(final_names):
                if i < len(initial_positions):
                    deltas[name] = round(final_positions[i] - initial_positions[i], 6)
            self.node.get_logger().info(f"Position deltas: {deltas}")

        # Also log motor_joint_states directly to isolate motor_control output
        if self.motor_joint_states_received:
            last_mjs = self.motor_joint_states_received[-1]
            self.node.get_logger().info(
                f"Motor joint states (direct): " f"{dict(zip(last_mjs.name, last_mjs.position))}"
            )

        actually_moved = moved_joints()
        unmoved = MOTOR_JOINTS - actually_moved
        self.assertTrue(
            position_changed,
            "No motor joints moved. "
            "motor_control simulation_mode physics simulator is not producing "
            "position feedback for any joint (joint3, joint4, joint5). "
            "Check: simulation_mode parameter, joint_state_publisher merging, "
            "or physics simulator timer.",
        )

        self.node.get_logger().info(
            "FULL PIPELINE VERIFIED: detection -> IK -> motor commands "
            "-> simulated motor physics -> joint position feedback "
            f"({len(actually_moved)}/{len(MOTOR_JOINTS)} motor joints moved: "
            f"{actually_moved}"
            f"{', unmoved: ' + str(unmoved) if unmoved else ''})"
        )
