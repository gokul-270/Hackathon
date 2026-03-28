"""
Tests for the Pragati Web UI FastAPI backend.

Covers pure-function logic, the VelocityRampingEngine, pattern registry
validation, and WebSocket protocol handling.

Task mapping
------------
10.1 — Pure-function tests (RDP, points_to_commands, helpers)
10.2 — WebSocket protocol (ping, get_patterns, start/stop, cmd_vel_owner)
10.3 — VelocityRampingEngine (speed_scale, state machine, publish)
10.4 — Pattern registry structure validation
10.5 — Draw-path WebSocket flow
10.6 — Recording & auto-record helpers
"""

import asyncio
import math
import sys
from pathlib import Path

import pytest

# Ensure web_ui dir is on sys.path so `import backend` works when
# pytest is invoked from the repository root.
_WEB_UI_DIR = str(Path(__file__).resolve().parent.parent)
if _WEB_UI_DIR not in sys.path:
    sys.path.insert(0, _WEB_UI_DIR)

from backend import (  # noqa: E402
    PATTERN_REGISTRY,
    VelocityRampingEngine,
    _estimate_duration,
    _perpendicular_distance,
    _quaternion_to_yaw,
    points_to_commands,
    rdp_simplify,
    state,
)


# ---------------------------------------------------------------------------
# Lightweight test doubles (also defined in conftest.py for fixtures)
# ---------------------------------------------------------------------------

class _MockTwist:
    """Minimal stand-in for geometry_msgs.msg.Twist."""

    class _Vec3:
        def __init__(self):
            self.x = 0.0
            self.y = 0.0
            self.z = 0.0

    def __init__(self):
        self.linear = self._Vec3()
        self.angular = self._Vec3()


class MockPublisher:
    """Records every Twist message published for assertion."""

    def __init__(self):
        self.messages: list = []

    def publish(self, msg):
        self.messages.append(msg)


# ===================================================================
# 10.1 — Pure-function tests
# ===================================================================


class TestRdpSimplify:
    """Task 10.1: Ramer-Douglas-Peucker path simplification."""

    def test_single_point_returned_as_is(self):
        """A single point cannot be simplified further."""
        pts = [{"x": 0, "y": 0}]
        assert rdp_simplify(pts) == pts

    def test_two_points_returned_as_is(self):
        """Two points are already minimal."""
        pts = [{"x": 0, "y": 0}, {"x": 1, "y": 1}]
        assert rdp_simplify(pts) == pts

    def test_collinear_points_collapse_to_endpoints(self):
        """Straight-line points collapse to first and last."""
        pts = [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 2, "y": 0}, {"x": 3, "y": 0}]
        result = rdp_simplify(pts, epsilon=0.1)
        assert len(result) == 2
        assert result[0] == pts[0]
        assert result[-1] == pts[-1]

    def test_l_shape_keeps_corner(self):
        """An L-shaped path must keep the corner point."""
        pts = [{"x": 0, "y": 0}, {"x": 5, "y": 0}, {"x": 5, "y": 5}]
        result = rdp_simplify(pts, epsilon=0.1)
        assert len(result) == 3  # all three points significant


class TestPointsToCommands:
    """Task 10.1: Turn-then-drive command generation."""

    def test_less_than_two_points_returns_empty(self):
        """Fewer than 2 points produce no commands."""
        assert points_to_commands([]) == []
        assert points_to_commands([{"x": 0, "y": 0}]) == []

    def test_two_points_along_x_axis_single_drive(self):
        """Two points along +X need only a drive command (no turn)."""
        pts = [{"x": 0, "y": 0}, {"x": 3, "y": 0}]
        cmds = points_to_commands(pts, drive_speed=1.0, turn_rate=1.0)
        # Starting heading is 0 (facing +X), so no turn needed
        assert len(cmds) == 1
        twist, dur = cmds[0]
        assert twist.linear.x == pytest.approx(1.0)
        assert dur == pytest.approx(3.0)

    def test_90_degree_turn_produces_turn_then_drive(self):
        """A 90-degree left turn should emit a turn command then a drive."""
        pts = [{"x": 0, "y": 0}, {"x": 0, "y": 2}]
        cmds = points_to_commands(pts, drive_speed=1.0, turn_rate=1.0)
        # Heading to (0,2) is pi/2 from initial heading 0 => turn + drive
        assert len(cmds) == 2
        turn_twist, turn_dur = cmds[0]
        assert turn_twist.angular.z != 0.0
        assert turn_dur == pytest.approx(math.pi / 2, rel=0.01)
        drive_twist, drive_dur = cmds[1]
        assert drive_twist.linear.x == pytest.approx(1.0)
        assert drive_dur == pytest.approx(2.0)


class TestPerpendicularDistance:
    """Task 10.1: Helper for RDP algorithm."""

    def test_point_on_line_returns_zero(self):
        """A point sitting on the segment has zero perpendicular distance."""
        d = _perpendicular_distance(1, 0, 0, 0, 2, 0)
        assert d == pytest.approx(0.0)

    def test_point_off_line_returns_correct_distance(self):
        """Distance from (1,1) to segment (0,0)-(2,0) is 1.0."""
        d = _perpendicular_distance(1, 1, 0, 0, 2, 0)
        assert d == pytest.approx(1.0)

    def test_degenerate_segment_returns_euclidean(self):
        """When segment has zero length, return distance to the point."""
        d = _perpendicular_distance(3, 4, 0, 0, 0, 0)
        assert d == pytest.approx(5.0)


class TestEstimateDuration:
    """Task 10.1: Duration summation helper."""

    def test_sums_durations(self):
        """Should sum the second element of each tuple."""
        cmds = [("ignored", 1.5), ("ignored", 2.5), ("ignored", 0.5)]
        assert _estimate_duration(cmds) == pytest.approx(4.5)

    def test_empty_list_returns_zero(self):
        assert _estimate_duration([]) == pytest.approx(0.0)


# ===================================================================
# 10.3 — VelocityRampingEngine tests
# ===================================================================


class TestVelocityRampingEngine:
    """Task 10.3: Engine speed-scale, state machine, and publish behaviour."""

    def test_speed_scale_clamps_low(self, engine):
        """Values below 0.25 are clamped to 0.25."""
        engine.speed_scale = 0.1
        assert engine.speed_scale == pytest.approx(0.25)

    def test_speed_scale_clamps_high(self, engine):
        """Values above 2.0 are clamped to 2.0."""
        engine.speed_scale = 5.0
        assert engine.speed_scale == pytest.approx(2.0)

    def test_speed_scale_within_range(self, engine):
        """Values within [0.25, 2.0] are kept as-is."""
        engine.speed_scale = 1.5
        assert engine.speed_scale == pytest.approx(1.5)

    def test_get_status_shape(self, engine):
        """get_status() returns all expected keys."""
        status = engine.get_status()
        expected_keys = {
            "type", "pattern_name", "progress_percent",
            "current_segment", "total_segments", "elapsed_time", "state",
        }
        assert set(status.keys()) == expected_keys
        assert status["type"] == "pattern_status"
        assert status["state"] == "idle"

    def test_interpolate_returns_start_at_t0(self, engine):
        """At t=0 interpolation returns v0."""
        assert engine._interpolate(0.0, 1.0, 0.0, 1.0) == pytest.approx(0.0)

    def test_interpolate_returns_end_at_ramp(self, engine):
        """At t>=ramp interpolation returns v1."""
        assert engine._interpolate(0.0, 1.0, 1.0, 1.0) == pytest.approx(1.0)

    def test_interpolate_midpoint(self, engine):
        """At t=ramp/2 interpolation returns midpoint."""
        assert engine._interpolate(0.0, 2.0, 0.5, 1.0) == pytest.approx(1.0)

    def test_interpolate_zero_ramp_returns_v1(self, engine):
        """With ramp=0 the target value is returned immediately."""
        assert engine._interpolate(0.0, 5.0, 0.0, 0.0) == pytest.approx(5.0)

    @pytest.mark.asyncio
    async def test_execute_completes(self, mock_publisher):
        """After executing a short command list the state becomes 'completed'."""
        engine = VelocityRampingEngine(mock_publisher, ramp_duration=0.0)
        twist = _MockTwist()
        twist.linear.x = 0.5
        cmds = [(twist, 0.05)]
        result = await engine.execute(cmds, name="test")
        assert result == "completed"
        assert engine.state == "completed"

    @pytest.mark.asyncio
    async def test_stop_sets_stopped_state(self, mock_publisher):
        """Calling stop() while executing sets state to 'stopped'."""
        engine = VelocityRampingEngine(mock_publisher, ramp_duration=0.0)
        twist = _MockTwist()
        twist.linear.x = 0.3
        cmds = [(twist, 10.0)]  # long enough to stop mid-execution

        async def run_and_stop():
            task = asyncio.create_task(engine.execute(cmds, name="long"))
            await asyncio.sleep(0.1)
            engine.stop()
            return await task

        result = await run_and_stop()
        assert result == "stopped"
        assert engine.state == "stopped"

    @pytest.mark.asyncio
    async def test_speed_scale_affects_published_values(self, mock_publisher):
        """Published linear.x should be scaled by speed_scale.

        Task 10.3: verify scaling is applied to outgoing Twist messages.
        """
        import backend
        # Temporarily enable HAS_RCLPY so _publish actually calls publisher.publish
        original = backend.HAS_RCLPY
        backend.HAS_RCLPY = True
        try:
            engine = VelocityRampingEngine(mock_publisher, ramp_duration=0.0)
            engine.speed_scale = 2.0
            twist = _MockTwist()
            twist.linear.x = 1.0
            cmds = [(twist, 0.06)]  # just over one publish interval
            await engine.execute(cmds, name="scale_test")
            # At least one message should have been published
            assert len(mock_publisher.messages) > 0
            # Check the first message is scaled
            msg = mock_publisher.messages[0]
            assert msg.linear.x == pytest.approx(2.0, abs=0.01)
        finally:
            backend.HAS_RCLPY = original


# ===================================================================
# 10.4 — Pattern registry tests
# ===================================================================


class TestPatternRegistry:
    """Task 10.4: Validate structure and completeness of PATTERN_REGISTRY."""

    EXPECTED_PATTERNS = {
        "letter_P", "letter_D", "letter_L", "letter_U", "letter_S",
        "letter_Z", "letter_8", "letter_O",
        "circle", "figure_eight", "square", "diamond",
        "row_traversal", "s_pattern",
    }

    VALID_CATEGORIES = {"letter", "geometric", "field"}

    def test_all_expected_patterns_exist(self):
        """Every expected pattern name is present in the registry."""
        assert self.EXPECTED_PATTERNS.issubset(set(PATTERN_REGISTRY.keys()))

    def test_entry_has_required_keys(self):
        """Each registry entry has func, category, args, estimated_duration."""
        for name, entry in PATTERN_REGISTRY.items():
            for key in ("func", "category", "args", "estimated_duration"):
                assert key in entry, f"'{name}' missing key '{key}'"

    def test_categories_are_valid(self):
        """Every pattern's category is one of the allowed values."""
        for name, entry in PATTERN_REGISTRY.items():
            assert entry["category"] in self.VALID_CATEGORIES, (
                f"'{name}' has invalid category '{entry['category']}'"
            )

    def test_estimated_durations_are_positive(self):
        """Every estimated duration is a positive number."""
        for name, entry in PATTERN_REGISTRY.items():
            assert entry["estimated_duration"] > 0, (
                f"'{name}' has non-positive duration {entry['estimated_duration']}"
            )


# ===================================================================
# 10.2 / 10.5 — WebSocket protocol tests
# ===================================================================


class TestWebSocketProtocol:
    """Tasks 10.2, 10.5: WebSocket message handling via Starlette TestClient."""

    def test_ping_pong(self, ws_client):
        """Sending 'ping' receives 'pong'."""
        with ws_client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"

    def test_get_patterns(self, ws_client):
        """Requesting patterns returns a pattern_list with expected names."""
        with ws_client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "get_patterns"})
            data = ws.receive_json()
            assert data["type"] == "pattern_list"
            names = {p["name"] for p in data["patterns"]}
            assert "circle" in names
            assert "letter_P" in names

    def test_set_speed_scale_clamped(self, ws_client):
        """Speed-scale values are clamped and acknowledged."""
        with ws_client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "set_speed_scale", "value": 99.0})
            data = ws.receive_json()
            assert data["type"] == "speed_scale_set"
            assert data["value"] == pytest.approx(2.0)

    def test_start_pattern_invalid_name(self, ws_client):
        """Starting an unknown pattern returns an error."""
        with ws_client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "start_pattern", "name": "nonexistent"})
            data = ws.receive_json()
            assert data["type"] == "error"
            assert "nonexistent" in data["message"].lower() or "unknown" in data["message"].lower()

    def test_stop_pattern_when_idle(self, ws_client):
        """Stopping when nothing is running returns an ack."""
        with ws_client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "stop_pattern"})
            # May receive cmd_vel_owner broadcast first, then ack
            messages = []
            data = ws.receive_json()
            messages.append(data)
            # Could get two messages: cmd_vel_owner + ack
            if data["type"] != "ack":
                data = ws.receive_json()
                messages.append(data)
            ack = next(m for m in messages if m["type"] == "ack")
            assert ack["action"] == "stop_pattern"

    def test_set_auto_record(self, ws_client):
        """Toggling auto-record returns the new status."""
        with ws_client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "set_auto_record", "enabled": True})
            data = ws.receive_json()
            assert data["type"] == "auto_record_status"
            assert data["enabled"] is True

    def test_draw_path_too_few_points(self, ws_client):
        """Drawing with fewer than 2 points returns an error.

        Task 10.5: draw_path validation.
        """
        with ws_client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "draw_path", "points": [{"x": 0, "y": 0}]})
            data = ws.receive_json()
            assert data["type"] == "error"
            assert "2 points" in data["message"].lower() or "at least" in data["message"].lower()

    def test_unknown_message_type(self, ws_client):
        """An unrecognized message type returns an error."""
        with ws_client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "bogus_command"})
            data = ws.receive_json()
            assert data["type"] == "error"
            assert "unknown" in data["message"].lower()


# ===================================================================
# 10.7 — Quaternion-to-yaw conversion tests
# ===================================================================


class TestQuaternionToYaw:
    """Pure-math tests for _quaternion_to_yaw."""

    def test_identity_quaternion_returns_zero(self):
        """Identity quaternion (0,0,0,1) should produce yaw = 0."""
        yaw = _quaternion_to_yaw(0, 0, 0, 1)
        assert yaw == pytest.approx(0.0)

    def test_90_degree_yaw(self):
        """Quaternion for 90-degree rotation about Z should give yaw ≈ π/2."""
        yaw = _quaternion_to_yaw(0, 0, 0.7071067811865476, 0.7071067811865476)
        assert yaw == pytest.approx(math.pi / 2, abs=1e-4)

    def test_180_degree_yaw(self):
        """Quaternion for 180-degree rotation about Z → |yaw| ≈ π."""
        yaw = _quaternion_to_yaw(0, 0, 1, 0)
        assert abs(yaw) == pytest.approx(math.pi, abs=1e-4)

    def test_negative_yaw(self):
        """Quaternion for -90-degree rotation about Z → yaw ≈ -π/2."""
        yaw = _quaternion_to_yaw(0, 0, -0.7071067811865476, 0.7071067811865476)
        assert yaw == pytest.approx(-math.pi / 2, abs=1e-4)


# ===================================================================
# 10.8 — Teleport WebSocket tests
# ===================================================================


class TestTeleportWebSocket:
    """WebSocket tests for the teleport handler."""

    @staticmethod
    def _collect_until(ws, target_type, max_messages=10):
        """Receive messages until one matches *target_type* or limit hit."""
        collected = []
        for _ in range(max_messages):
            msg = ws.receive_json()
            collected.append(msg)
            if msg["type"] == target_type:
                return collected
        return collected

    def test_teleport_preset_start(self, ws_client):
        """Teleporting to 'start' preset succeeds."""
        with ws_client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "teleport", "target": "start"})
            msgs = self._collect_until(ws, "teleport_result")
            result = next(m for m in msgs if m["type"] == "teleport_result")
            assert result["success"] is True

    def test_teleport_preset_end(self, ws_client):
        """Teleporting to 'end' preset succeeds."""
        with ws_client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "teleport", "target": "end"})
            msgs = self._collect_until(ws, "teleport_result")
            result = next(m for m in msgs if m["type"] == "teleport_result")
            assert result["success"] is True

    def test_teleport_preset_spawn(self, ws_client):
        """Teleporting to 'spawn' preset succeeds."""
        with ws_client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "teleport", "target": "spawn"})
            msgs = self._collect_until(ws, "teleport_result")
            result = next(m for m in msgs if m["type"] == "teleport_result")
            assert result["success"] is True

    def test_teleport_custom(self, ws_client):
        """Teleporting to custom coordinates succeeds."""
        with ws_client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "teleport", "target": "custom",
                          "x": 5.0, "y": 3.0, "yaw": 1.57})
            msgs = self._collect_until(ws, "teleport_result")
            result = next(m for m in msgs if m["type"] == "teleport_result")
            assert result["success"] is True

    def test_teleport_unknown_target(self, ws_client):
        """Teleporting to an unknown target returns success: False."""
        with ws_client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "teleport", "target": "moon"})
            msgs = self._collect_until(ws, "teleport_result")
            result = next(m for m in msgs if m["type"] == "teleport_result")
            assert result["success"] is False


# ===================================================================
# 10.9 — Precision Move WebSocket tests
# ===================================================================


class TestPrecisionMoveWebSocket:
    """WebSocket tests for precision move and cancel handlers."""

    @staticmethod
    def _collect_until(ws, target_type, max_messages=10):
        """Receive messages until one matches *target_type* or limit hit."""
        collected = []
        for _ in range(max_messages):
            msg = ws.receive_json()
            collected.append(msg)
            if msg["type"] == target_type:
                return collected
        return collected

    def test_precision_move_unknown_action(self, ws_client):
        """An unknown precision-move action returns state='failed'."""
        with ws_client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "precision_move", "action": "fly_away"})
            msgs = self._collect_until(ws, "precision_move_status")
            result = next(m for m in msgs if m["type"] == "precision_move_status")
            assert result["state"] == "failed"

    def test_cancel_move_when_no_move_running(self, ws_client):
        """Cancelling when no move is running returns ack with note."""
        with ws_client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "cancel_move"})
            msgs = self._collect_until(ws, "ack")
            result = next(m for m in msgs if m["type"] == "ack")
            assert result["action"] == "cancel_move"
            assert result["note"] == "no move running"
