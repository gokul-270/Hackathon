"""Unit tests for PID tuning node message types and constants.

Tests that ROS2 message types can be instantiated and have the expected fields.
Does NOT test actual ROS2 communication (that requires integration testing).
"""

import json
import math

import pytest


class TestReadPIDMessage:
    """Verify ReadPID service message structure."""

    def test_request_has_motor_id(self):
        from motor_control_msgs.srv import ReadPID

        req = ReadPID.Request()
        req.motor_id = 1
        assert req.motor_id == 1

    def test_response_has_pid_fields(self):
        from motor_control_msgs.srv import ReadPID

        resp = ReadPID.Response()
        resp.success = True
        resp.error_message = ""
        resp.angle_kp = 100
        resp.angle_ki = 50
        resp.speed_kp = 80
        resp.speed_ki = 40
        resp.current_kp = 60
        resp.current_ki = 30

        assert resp.success is True
        assert resp.angle_kp == 100
        assert resp.speed_ki == 40

    def test_response_accepts_failure(self):
        from motor_control_msgs.srv import ReadPID

        resp = ReadPID.Response()
        resp.success = False
        resp.error_message = "motor not found"
        assert resp.success is False
        assert resp.error_message == "motor not found"


class TestWritePIDMessage:
    """Verify WritePID service message structure."""

    def test_request_has_all_gains(self):
        from motor_control_msgs.srv import WritePID

        req = WritePID.Request()
        req.motor_id = 2
        req.angle_kp = 100
        req.angle_ki = 50
        req.speed_kp = 80
        req.speed_ki = 40
        req.current_kp = 60
        req.current_ki = 30

        assert req.motor_id == 2
        assert req.angle_kp == 100

    def test_response_fields(self):
        from motor_control_msgs.srv import WritePID

        resp = WritePID.Response()
        resp.success = True
        resp.error_message = ""
        assert resp.success is True


class TestWritePIDToROMMessage:
    """Verify WritePIDToROM service message structure."""

    def test_request_matches_write_pid(self):
        from motor_control_msgs.srv import WritePIDToROM

        req = WritePIDToROM.Request()
        req.motor_id = 3
        req.angle_kp = 255
        req.angle_ki = 0
        req.speed_kp = 128
        req.speed_ki = 64
        req.current_kp = 32
        req.current_ki = 16

        assert req.motor_id == 3
        assert req.angle_kp == 255
        assert req.current_ki == 16


class TestStepResponseTestAction:
    """Verify StepResponseTest action message structure."""

    def test_goal_fields(self):
        from motor_control_msgs.action import StepResponseTest

        goal = StepResponseTest.Goal()
        goal.motor_id = 1
        goal.step_size_degrees = 45.0
        goal.duration_seconds = 3.0

        assert goal.motor_id == 1
        assert goal.step_size_degrees == pytest.approx(45.0)
        assert goal.duration_seconds == pytest.approx(3.0)

    def test_result_fields(self):
        from motor_control_msgs.action import StepResponseTest

        result = StepResponseTest.Result()
        result.success = True
        result.error_message = ""
        result.timestamps = [0.0, 0.1, 0.2]
        result.positions = [0.0, 22.5, 44.0]
        result.velocities = [0.0, 225.0, 215.0]
        result.currents = [0.0, 1.5, 1.2]
        result.setpoint = 45.0

        assert result.success is True
        assert len(result.timestamps) == 3
        assert result.setpoint == pytest.approx(45.0)

    def test_feedback_fields(self):
        from motor_control_msgs.action import StepResponseTest

        fb = StepResponseTest.Feedback()
        fb.progress_percent = 50.0
        fb.current_position = 22.5
        fb.elapsed_seconds = 1.5

        assert fb.progress_percent == pytest.approx(50.0)


class TestMotorJointMapping:
    """Verify the motor-to-joint name mapping constants."""

    def test_motor_joint_map(self):
        from pid_tuning.pid_tuning_node import MOTOR_JOINT_MAP

        assert MOTOR_JOINT_MAP[1] == "joint5"
        assert MOTOR_JOINT_MAP[2] == "joint3"
        assert MOTOR_JOINT_MAP[3] == "joint4"

    def test_joint_motor_reverse_map(self):
        from pid_tuning.pid_tuning_node import JOINT_MOTOR_MAP

        assert JOINT_MOTOR_MAP["joint5"] == 1
        assert JOINT_MOTOR_MAP["joint3"] == 2
        assert JOINT_MOTOR_MAP["joint4"] == 3


class TestMotorStateJsonFormat:
    """Verify the JSON motor state message structure."""

    def test_state_dict_keys(self):
        """Ensure the JSON state message has the expected keys."""
        state = {
            "motor_id": 1,
            "timestamp": 1234567890.123,
            "position_deg": 45.0,
            "velocity_dps": 10.0,
            "current_a": 1.5,
            "temperature_c": 35.0,
        }
        serialized = json.dumps(state)
        parsed = json.loads(serialized)

        expected_keys = {
            "motor_id",
            "timestamp",
            "position_deg",
            "velocity_dps",
            "current_a",
            "temperature_c",
        }
        assert set(parsed.keys()) == expected_keys

    def test_position_conversion_radians_to_degrees(self):
        """JointState positions are in radians; motor state uses degrees."""
        position_rad = math.pi / 2  # 90 degrees
        position_deg = math.degrees(position_rad)
        assert position_deg == pytest.approx(90.0)


class TestServiceTimeoutConstant:
    """Verify the service timeout constant."""

    def test_timeout_value(self):
        from pid_tuning.pid_tuning_node import DEFAULT_SERVICE_TIMEOUT_SEC

        assert DEFAULT_SERVICE_TIMEOUT_SEC == 5.0
