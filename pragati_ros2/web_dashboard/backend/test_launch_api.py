"""Tests for ProcessManager, LaunchPhaseTracker, and launch router.

Validates:
- start_process spawns a process and tracks it
- stop_process sends SIGINT and waits
- stop_process escalation (mock process that doesn't die on SIGINT)
- duplicate launch prevention
- get_status returns correct state
- get_output returns buffered lines
- stop_all stops all processes
- Arm launch/stop/status API endpoints
- Vehicle launch/stop/status API endpoints
- Vehicle subsystem detection
- Audit logging of launch/stop actions
- LaunchPhaseTracker phase detection and progress
- Launching status with stability check
- Structured WebSocket phase events
"""

import asyncio
import datetime
import json
import signal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.launch_api import (
    LaunchPhaseTracker,
    ProcessManager,
    launch_router,
    set_audit_logger,
    set_process_manager,
)


# -----------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------


def _make_mock_process(pid=1234, returncode=None):
    """Create a mock asyncio.Process."""
    proc = AsyncMock()
    proc.pid = pid
    proc.returncode = returncode
    proc.stdout = AsyncMock()
    proc.stderr = AsyncMock()
    proc.send_signal = MagicMock()
    proc.terminate = MagicMock()
    proc.kill = MagicMock()
    return proc


# -----------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------


@pytest.fixture()
def manager():
    """Fresh ProcessManager instance."""
    return ProcessManager()


# -----------------------------------------------------------------
# Tests
# -----------------------------------------------------------------


class TestStartProcess:
    """Tests for ProcessManager.start_process."""

    @pytest.mark.asyncio
    async def test_start_process_spawns_and_tracks(self, manager):
        """start_process spawns a subprocess and records pid+status."""
        mock_proc = _make_mock_process(pid=42)
        # stdout/stderr readline return empty to end the reader loops
        mock_proc.stdout.readline = AsyncMock(return_value=b"")
        mock_proc.stderr.readline = AsyncMock(return_value=b"")
        mock_proc.wait = AsyncMock(return_value=0)

        with patch(
            "backend.launch_api.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            await manager.start_process("test_node", "sleep", ["60"])

        status = manager.get_status("test_node")
        assert status is not None
        assert status["pid"] == 42
        # Initial status is "launching", transitions to "running" later
        assert status["status"] == "launching"

    @pytest.mark.asyncio
    async def test_duplicate_launch_raises(self, manager):
        """start_process raises RuntimeError if name already running."""
        mock_proc = _make_mock_process(pid=42)
        mock_proc.stdout.readline = AsyncMock(return_value=b"")
        mock_proc.stderr.readline = AsyncMock(return_value=b"")
        mock_proc.wait = AsyncMock(return_value=0)

        with patch(
            "backend.launch_api.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            await manager.start_process("dup_node", "sleep", ["60"])

            with pytest.raises(RuntimeError, match="already running"):
                await manager.start_process("dup_node", "sleep", ["60"])


class TestStopProcess:
    """Tests for ProcessManager.stop_process."""

    @pytest.mark.asyncio
    async def test_stop_process_sends_sigint(self, manager):
        """stop_process sends SIGINT first."""
        mock_proc = _make_mock_process(pid=99)
        mock_proc.stdout.readline = AsyncMock(return_value=b"")
        mock_proc.stderr.readline = AsyncMock(return_value=b"")
        # Process dies after SIGINT
        mock_proc.wait = AsyncMock(return_value=0)

        with patch(
            "backend.launch_api.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            await manager.start_process("stop_me", "sleep", ["60"])

        # Make wait resolve immediately (process responds to SIGINT)
        mock_proc.wait = AsyncMock(return_value=0)

        await manager.stop_process("stop_me")

        mock_proc.send_signal.assert_any_call(signal.SIGINT)
        status = manager.get_status("stop_me")
        assert status["status"] == "stopped"

    @pytest.mark.asyncio
    async def test_stop_process_escalates_to_sigterm_then_sigkill(
        self, manager
    ):
        """If SIGINT doesn't work, escalate to SIGTERM then SIGKILL."""
        mock_proc = _make_mock_process(pid=100)
        mock_proc.stdout.readline = AsyncMock(return_value=b"")
        mock_proc.stderr.readline = AsyncMock(return_value=b"")
        mock_proc.wait = AsyncMock(return_value=0)

        with patch(
            "backend.launch_api.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            await manager.start_process("stubborn", "sleep", ["60"])

        # Make wait always time out (process ignores signals)
        mock_proc.wait = AsyncMock(
            side_effect=asyncio.TimeoutError()
        )
        # On kill, finally set returncode

        def _on_kill():
            mock_proc.returncode = -9
            mock_proc.wait = AsyncMock(return_value=-9)

        mock_proc.kill = MagicMock(side_effect=lambda: _on_kill())

        await manager.stop_process("stubborn")

        mock_proc.send_signal.assert_any_call(signal.SIGINT)
        mock_proc.terminate.assert_called()
        mock_proc.kill.assert_called()


class TestGetStatus:
    """Tests for ProcessManager.get_status."""

    def test_get_status_unknown_returns_none(self, manager):
        """get_status for unknown process returns None."""
        assert manager.get_status("nonexistent") is None

    @pytest.mark.asyncio
    async def test_get_status_returns_correct_fields(self, manager):
        """get_status returns dict with expected keys."""
        mock_proc = _make_mock_process(pid=77)
        mock_proc.stdout.readline = AsyncMock(return_value=b"")
        mock_proc.stderr.readline = AsyncMock(return_value=b"")
        mock_proc.wait = AsyncMock(return_value=0)

        with patch(
            "backend.launch_api.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            await manager.start_process("status_test", "echo", ["hi"])

        status = manager.get_status("status_test")
        assert "pid" in status
        assert "status" in status
        assert "return_code" in status
        assert "output_buffer" in status


class TestGetOutput:
    """Tests for ProcessManager.get_output."""

    @pytest.mark.asyncio
    async def test_get_output_returns_buffered_lines(self, manager):
        """get_output returns captured stdout/stderr lines."""
        mock_proc = _make_mock_process(pid=55)

        # Simulate 3 lines of stdout then EOF
        stdout_lines = [b"line1\n", b"line2\n", b"line3\n", b""]
        stderr_lines = [b""]
        mock_proc.stdout.readline = AsyncMock(
            side_effect=stdout_lines
        )
        mock_proc.stderr.readline = AsyncMock(
            side_effect=stderr_lines
        )
        mock_proc.wait = AsyncMock(return_value=0)

        with patch(
            "backend.launch_api.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            await manager.start_process("output_test", "echo", ["hi"])

        # Give reader tasks time to process
        await asyncio.sleep(0.1)

        lines = manager.get_output("output_test", last_n=10)
        assert len(lines) >= 3
        assert "line1" in lines[0]
        assert "line2" in lines[1]
        assert "line3" in lines[2]

    def test_get_output_unknown_returns_empty(self, manager):
        """get_output for unknown process returns empty list."""
        assert manager.get_output("ghost") == []

    @pytest.mark.asyncio
    async def test_get_output_respects_last_n(self, manager):
        """get_output with last_n limits the number of returned lines."""
        mock_proc = _make_mock_process(pid=56)

        # 5 lines of output
        stdout_lines = [
            b"a\n", b"b\n", b"c\n", b"d\n", b"e\n", b""
        ]
        mock_proc.stdout.readline = AsyncMock(
            side_effect=stdout_lines
        )
        mock_proc.stderr.readline = AsyncMock(return_value=b"")
        mock_proc.wait = AsyncMock(return_value=0)

        with patch(
            "backend.launch_api.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            await manager.start_process("limit_test", "echo", ["hi"])

        await asyncio.sleep(0.1)

        lines = manager.get_output("limit_test", last_n=2)
        assert len(lines) == 2


class TestStopAll:
    """Tests for ProcessManager.stop_all."""

    @pytest.mark.asyncio
    async def test_stop_all_stops_all_processes(self, manager):
        """stop_all terminates every tracked running process."""
        procs = {}
        for name, pid in [("a", 10), ("b", 20)]:
            proc = _make_mock_process(pid=pid)
            proc.stdout.readline = AsyncMock(return_value=b"")
            proc.stderr.readline = AsyncMock(return_value=b"")
            proc.wait = AsyncMock(return_value=0)
            procs[name] = proc

        with patch(
            "backend.launch_api.asyncio.create_subprocess_exec",
            side_effect=lambda *a, **kw: procs.pop(
                list(procs.keys())[0]
            ),
        ):
            await manager.start_process("a", "sleep", ["60"])
            await manager.start_process("b", "sleep", ["60"])

        await manager.stop_all()

        for name in ["a", "b"]:
            status = manager.get_status(name)
            assert status["status"] in ("stopped", "error")


class TestWebSocketStreaming:
    """Tests for ProcessManager subscribe/unsubscribe/broadcast."""

    @pytest.mark.asyncio
    async def test_subscribe_receives_output_lines(self, manager):
        """Subscriber callback receives structured output messages."""
        received = []

        async def on_line(msg):
            received.append(msg)

        mock_proc = _make_mock_process(pid=70)
        stdout_lines = [b"hello\n", b"world\n", b""]
        mock_proc.stdout.readline = AsyncMock(side_effect=stdout_lines)
        mock_proc.stderr.readline = AsyncMock(return_value=b"")
        mock_proc.wait = AsyncMock(return_value=0)

        manager.subscribe("ws_test", on_line)

        with patch(
            "backend.launch_api.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            await manager.start_process("ws_test", "echo", ["hi"])

        await asyncio.sleep(0.15)

        output_msgs = [
            m for m in received
            if isinstance(m, dict) and m.get("type") == "output"
        ]
        assert len(output_msgs) >= 2
        assert any("hello" in m["data"] for m in output_msgs)
        assert any("world" in m["data"] for m in output_msgs)

    @pytest.mark.asyncio
    async def test_unsubscribe_stops_delivery(self, manager):
        """After unsubscribe, callback no longer receives lines."""
        received = []

        async def on_line(line):
            received.append(line)

        manager.subscribe("unsub_test", on_line)
        manager.unsubscribe("unsub_test", on_line)

        # Manually broadcast — should not be delivered
        await manager._broadcast("unsub_test", "should_not_arrive")
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_get_buffered_output_for_reconnection(self, manager):
        """get_buffered_output returns full buffer for reconnection."""
        mock_proc = _make_mock_process(pid=71)
        stdout_lines = [b"a\n", b"b\n", b"c\n", b""]
        mock_proc.stdout.readline = AsyncMock(side_effect=stdout_lines)
        mock_proc.stderr.readline = AsyncMock(return_value=b"")
        mock_proc.wait = AsyncMock(return_value=0)

        with patch(
            "backend.launch_api.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            await manager.start_process("buf_test", "echo", ["hi"])

        await asyncio.sleep(0.15)

        buffered = await manager.get_buffered_output("buf_test")
        assert len(buffered) >= 3

    @pytest.mark.asyncio
    async def test_dead_subscriber_removed(self, manager):
        """Subscriber that raises is automatically removed."""

        async def bad_callback(line):
            raise ConnectionError("disconnected")

        manager.subscribe("dead_test", bad_callback)
        await manager._broadcast("dead_test", "test_line")

        # Callback should have been removed
        subs = manager._subscribers.get("dead_test", set())
        assert bad_callback not in subs


# -----------------------------------------------------------------
# Router test helpers
# -----------------------------------------------------------------


def _make_app():
    """Create a FastAPI app with launch_router for testing."""
    app = FastAPI()
    app.include_router(launch_router)
    return app


def _mock_process_manager():
    """Create a mock ProcessManager with async methods."""
    pm = MagicMock(spec=ProcessManager)
    pm.start_process = AsyncMock()
    pm.stop_process = AsyncMock()
    pm.get_status = MagicMock(return_value=None)
    pm.get_output = MagicMock(return_value=[])
    pm.get_buffered_output = AsyncMock(return_value=[])
    return pm


def _mock_audit_logger():
    """Create a mock AuditLogger."""
    al = MagicMock()
    al.log = MagicMock()
    return al


# -----------------------------------------------------------------
# Arm Launch Endpoint Tests
# -----------------------------------------------------------------


class TestArmLaunchEndpoint:
    """Tests for POST/GET /api/launch/arm endpoints."""

    def setup_method(self):
        """Set up fresh mocks for each test."""
        self.pm = _mock_process_manager()
        self.al = _mock_audit_logger()
        set_process_manager(self.pm)
        set_audit_logger(self.al)
        self.app = _make_app()
        self.client = TestClient(self.app)

    def teardown_method(self):
        """Clean up module-level state."""
        set_process_manager(None)
        set_audit_logger(None)

    def test_launch_arm_success(self):
        """POST /api/launch/arm returns 200 with launched status."""
        self.pm.start_process.return_value = {"pid": 100, "status": "running"}
        self.pm.get_status.return_value = {
            "status": "running",
            "pid": 100,
            "return_code": None,
        }

        resp = self.client.post(
            "/api/launch/arm",
            json={
                "use_simulation": True,
                "enable_arm_client": True,
                "enable_cotton_detection": False,
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "launched"
        assert "params" in data
        assert data["params"]["enable_cotton_detection"] is False

    def test_launch_arm_defaults(self):
        """POST /api/launch/arm with empty body uses all-true defaults."""
        self.pm.start_process.return_value = {"pid": 101, "status": "running"}

        resp = self.client.post("/api/launch/arm", json={})

        assert resp.status_code == 200
        data = resp.json()
        assert data["params"]["use_simulation"] is True
        assert data["params"]["enable_arm_client"] is True
        assert data["params"]["enable_cotton_detection"] is True

    def test_launch_arm_duplicate_returns_409(self):
        """POST /api/launch/arm returns 409 if arm already running."""
        self.pm.start_process.side_effect = RuntimeError(
            "Process 'arm' is already running"
        )

        resp = self.client.post("/api/launch/arm", json={})

        assert resp.status_code == 409

    def test_stop_arm_success(self):
        """POST /api/launch/arm/stop returns 200 when arm is running."""
        self.pm.get_status.return_value = {
            "status": "running",
            "pid": 100,
            "return_code": None,
        }

        resp = self.client.post("/api/launch/arm/stop")

        assert resp.status_code == 200
        assert resp.json()["status"] == "stopped"
        self.pm.stop_process.assert_called_once_with("arm")

    def test_stop_arm_not_running_returns_404(self):
        """POST /api/launch/arm/stop returns 404 if arm not running."""
        self.pm.get_status.return_value = None

        resp = self.client.post("/api/launch/arm/stop")

        assert resp.status_code == 404

    def test_arm_status(self):
        """GET /api/launch/arm/status returns process status."""
        self.pm.get_status.return_value = {
            "status": "running",
            "pid": 100,
            "return_code": None,
            "output_buffer": [],
        }

        resp = self.client.get("/api/launch/arm/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert data["pid"] == 100
        assert data["return_code"] is None

    def test_arm_status_not_found(self):
        """GET /api/launch/arm/status returns not_running when unknown."""
        self.pm.get_status.return_value = None

        resp = self.client.get("/api/launch/arm/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "not_running"
        assert data["pid"] is None


# -----------------------------------------------------------------
# Vehicle Launch Endpoint Tests
# -----------------------------------------------------------------


class TestVehicleLaunchEndpoint:
    """Tests for POST/GET /api/launch/vehicle endpoints."""

    def setup_method(self):
        self.pm = _mock_process_manager()
        self.al = _mock_audit_logger()
        set_process_manager(self.pm)
        set_audit_logger(self.al)
        self.app = _make_app()
        self.client = TestClient(self.app)

    def teardown_method(self):
        set_process_manager(None)
        set_audit_logger(None)

    def test_launch_vehicle_success(self):
        """POST /api/launch/vehicle returns 200 with launched status."""
        self.pm.start_process.return_value = {
            "pid": 200,
            "status": "running",
        }

        resp = self.client.post("/api/launch/vehicle", json={"params": {}})

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "launched"

    def test_launch_vehicle_empty_body(self):
        """POST /api/launch/vehicle with empty body uses defaults."""
        self.pm.start_process.return_value = {
            "pid": 201,
            "status": "running",
        }

        resp = self.client.post("/api/launch/vehicle", json={})

        assert resp.status_code == 200

    def test_launch_vehicle_duplicate_returns_409(self):
        """POST /api/launch/vehicle returns 409 if already running."""
        self.pm.start_process.side_effect = RuntimeError(
            "Process 'vehicle' is already running"
        )

        resp = self.client.post("/api/launch/vehicle", json={})

        assert resp.status_code == 409

    def test_stop_vehicle_success(self):
        """POST /api/launch/vehicle/stop returns 200 when running."""
        self.pm.get_status.return_value = {
            "status": "running",
            "pid": 200,
            "return_code": None,
        }

        resp = self.client.post("/api/launch/vehicle/stop")

        assert resp.status_code == 200
        assert resp.json()["status"] == "stopped"
        self.pm.stop_process.assert_called_once_with("vehicle")

    def test_stop_vehicle_not_running_returns_404(self):
        """POST /api/launch/vehicle/stop returns 404 if not running."""
        self.pm.get_status.return_value = None

        resp = self.client.post("/api/launch/vehicle/stop")

        assert resp.status_code == 404

    def test_vehicle_status(self):
        """GET /api/launch/vehicle/status returns process status."""
        self.pm.get_status.return_value = {
            "status": "running",
            "pid": 200,
            "return_code": None,
            "output_buffer": [],
        }

        resp = self.client.get("/api/launch/vehicle/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert data["pid"] == 200


# -----------------------------------------------------------------
# Vehicle Subsystem Detection Tests
# -----------------------------------------------------------------


class TestVehicleSubsystems:
    """Tests for GET /api/launch/vehicle/subsystems."""

    def setup_method(self):
        self.pm = _mock_process_manager()
        self.al = _mock_audit_logger()
        set_process_manager(self.pm)
        set_audit_logger(self.al)
        self.app = _make_app()
        self.client = TestClient(self.app)

    def teardown_method(self):
        set_process_manager(None)
        set_audit_logger(None)

    def test_subsystems_all_active(self):
        """Subsystems detected as active when node names in output."""
        self.pm.get_status.return_value = {
            "status": "running",
            "pid": 200,
            "return_code": None,
            "output_buffer": [],
        }
        self.pm.get_output.return_value = [
            "[stdout] [steering_controller] Started",
            "[stdout] [drive_controller] Started",
            "[stdout] [vehicle_state_machine] Running",
            "[stdout] [sensor_fusion] Active",
            "[stdout] [mqtt_bridge] Connected",
        ]

        resp = self.client.get("/api/launch/vehicle/subsystems")

        assert resp.status_code == 200
        data = resp.json()
        subs = {s["name"]: s["status"] for s in data["subsystems"]}
        assert subs["steering_controller"] == "active"
        assert subs["drive_controller"] == "active"
        assert subs["vehicle_state_machine"] == "active"
        assert subs["sensor_fusion"] == "active"
        assert subs["mqtt_bridge"] == "active"

    def test_subsystems_partial_detection(self):
        """Only detected subsystems are active, rest unknown."""
        self.pm.get_status.return_value = {
            "status": "running",
            "pid": 200,
            "return_code": None,
            "output_buffer": [],
        }
        self.pm.get_output.return_value = [
            "[stdout] [steering_controller] Started",
        ]

        resp = self.client.get("/api/launch/vehicle/subsystems")

        assert resp.status_code == 200
        data = resp.json()
        subs = {s["name"]: s["status"] for s in data["subsystems"]}
        assert subs["steering_controller"] == "active"
        assert subs["drive_controller"] == "unknown"
        assert subs["mqtt_bridge"] == "unknown"

    def test_subsystems_vehicle_not_running(self):
        """All subsystems inactive when vehicle not running."""
        self.pm.get_status.return_value = None

        resp = self.client.get("/api/launch/vehicle/subsystems")

        assert resp.status_code == 200
        data = resp.json()
        for sub in data["subsystems"]:
            assert sub["status"] == "inactive"

    def test_subsystems_returns_all_expected(self):
        """Response includes all 5 expected subsystem names."""
        self.pm.get_status.return_value = None

        resp = self.client.get("/api/launch/vehicle/subsystems")

        data = resp.json()
        names = [s["name"] for s in data["subsystems"]]
        assert "steering_controller" in names
        assert "drive_controller" in names
        assert "vehicle_state_machine" in names
        assert "sensor_fusion" in names
        assert "mqtt_bridge" in names
        assert len(names) == 5


# -----------------------------------------------------------------
# Audit Logging Tests
# -----------------------------------------------------------------


class TestAuditLogging:
    """Tests that launch/stop actions are audit-logged."""

    def setup_method(self):
        self.pm = _mock_process_manager()
        self.al = _mock_audit_logger()
        set_process_manager(self.pm)
        set_audit_logger(self.al)
        self.app = _make_app()
        self.client = TestClient(self.app)

    def teardown_method(self):
        set_process_manager(None)
        set_audit_logger(None)

    def test_arm_launch_logged(self):
        """Arm launch action is audit-logged."""
        self.pm.start_process.return_value = {"pid": 100, "status": "running"}

        self.client.post("/api/launch/arm", json={})

        self.al.log.assert_called_once()
        call_args = self.al.log.call_args
        assert call_args[0][0] == "arm_launch"  # action
        assert call_args[0][2] == "launched"  # result

    def test_arm_stop_logged(self):
        """Arm stop action is audit-logged."""
        self.pm.get_status.return_value = {
            "status": "running",
            "pid": 100,
            "return_code": None,
        }

        self.client.post("/api/launch/arm/stop")

        self.al.log.assert_called_once()
        call_args = self.al.log.call_args
        assert call_args[0][0] == "arm_stop"
        assert call_args[0][2] == "stopped"

    def test_vehicle_launch_logged(self):
        """Vehicle launch action is audit-logged."""
        self.pm.start_process.return_value = {
            "pid": 200,
            "status": "running",
        }

        self.client.post("/api/launch/vehicle", json={})

        self.al.log.assert_called_once()
        call_args = self.al.log.call_args
        assert call_args[0][0] == "vehicle_launch"
        assert call_args[0][2] == "launched"

    def test_vehicle_stop_logged(self):
        """Vehicle stop action is audit-logged."""
        self.pm.get_status.return_value = {
            "status": "running",
            "pid": 200,
            "return_code": None,
        }

        self.client.post("/api/launch/vehicle/stop")

        self.al.log.assert_called_once()
        call_args = self.al.log.call_args
        assert call_args[0][0] == "vehicle_stop"
        assert call_args[0][2] == "stopped"

    def test_no_log_when_logger_not_set(self):
        """No crash when audit logger is None."""
        set_audit_logger(None)
        self.pm.start_process.return_value = {"pid": 100, "status": "running"}

        # Should not raise
        resp = self.client.post("/api/launch/arm", json={})
        assert resp.status_code == 200


# -----------------------------------------------------------------
# LaunchPhaseTracker Tests
# -----------------------------------------------------------------


class TestLaunchPhaseTracker:
    """Tests for LaunchPhaseTracker phase detection and progress."""

    def test_initial_phase_is_cleanup(self):
        """Tracker starts in cleanup phase."""
        tracker = LaunchPhaseTracker()
        progress = tracker.get_progress()
        assert progress["current_phase"] == "cleanup"
        assert progress["completed_phases"] == []

    def test_cleanup_detected_by_auto_cleanup_marker(self):
        """'AUTO-CLEANUP:' in output confirms cleanup phase."""
        phases = []

        def on_change(phase, status, ts):
            phases.append((phase, status))

        tracker = LaunchPhaseTracker(on_phase_change=on_change)
        tracker.process_line("AUTO-CLEANUP: removing stale nodes")

        assert ("cleanup", "active") in phases

    def test_cleanup_detected_by_ensuring_clean_launch(self):
        """'Ensuring clean launch' triggers cleanup phase."""
        phases = []

        def on_change(phase, status, ts):
            phases.append((phase, status))

        tracker = LaunchPhaseTracker(on_phase_change=on_change)
        tracker.process_line("Ensuring clean launch environment")

        assert ("cleanup", "active") in phases

    def test_daemon_restart_detected(self):
        """'daemon start' triggers daemon_restart phase."""
        phases = []

        def on_change(phase, status, ts):
            phases.append((phase, status))

        tracker = LaunchPhaseTracker(on_phase_change=on_change)
        # Move past cleanup first
        tracker.process_line("AUTO-CLEANUP: done")
        tracker.process_line("daemon start completed")

        assert ("daemon_restart", "active") in phases
        assert ("cleanup", "complete") in phases

    def test_daemon_restart_by_starting_fresh(self):
        """'Starting fresh daemon' triggers daemon_restart phase."""
        phases = []

        def on_change(phase, status, ts):
            phases.append((phase, status))

        tracker = LaunchPhaseTracker(on_phase_change=on_change)
        tracker.process_line("AUTO-CLEANUP: done")
        tracker.process_line("Starting fresh daemon process")

        assert ("daemon_restart", "active") in phases

    def test_node_startup_detected_by_known_node(self):
        """Known node name triggers node_startup phase."""
        phases = []

        def on_change(phase, status, ts):
            phases.append((phase, status))

        tracker = LaunchPhaseTracker(on_phase_change=on_change)
        tracker.process_line("AUTO-CLEANUP: done")
        tracker.process_line("daemon start")
        tracker.process_line("[robot_state_publisher] started")

        assert ("node_startup", "active") in phases
        assert ("daemon_restart", "complete") in phases

    def test_node_startup_by_joint_state_publisher(self):
        """joint_state_publisher triggers node_startup."""
        phases = []

        def on_change(phase, status, ts):
            phases.append((phase, status))

        tracker = LaunchPhaseTracker(on_phase_change=on_change)
        tracker.process_line("AUTO-CLEANUP: done")
        tracker.process_line("daemon start")
        tracker.process_line("[joint_state_publisher] started")

        assert ("node_startup", "active") in phases

    def test_node_startup_by_mg6010_controller(self):
        """mg6010_controller triggers node_startup."""
        phases = []

        def on_change(phase, status, ts):
            phases.append((phase, status))

        tracker = LaunchPhaseTracker(on_phase_change=on_change)
        tracker.process_line("AUTO-CLEANUP: done")
        tracker.process_line("daemon start")
        tracker.process_line("[mg6010_controller] initialized")

        assert ("node_startup", "active") in phases

    def test_motor_homing_detected(self):
        """'yanthra_move' in output triggers motor_homing phase."""
        phases = []

        def on_change(phase, status, ts):
            phases.append((phase, status))

        tracker = LaunchPhaseTracker(on_phase_change=on_change)
        tracker.process_line("AUTO-CLEANUP: done")
        tracker.process_line("daemon start")
        tracker.process_line("[robot_state_publisher] ok")
        tracker.process_line("[yanthra_move] homing motors")

        assert ("motor_homing", "active") in phases
        assert ("node_startup", "complete") in phases

    def test_get_progress_returns_expected_fields(self):
        """get_progress returns dict with required fields."""
        tracker = LaunchPhaseTracker()
        progress = tracker.get_progress()

        assert "current_phase" in progress
        assert "completed_phases" in progress
        assert "elapsed_time" in progress
        assert "estimated_remaining" in progress

    def test_get_progress_elapsed_time_increases(self):
        """Elapsed time in progress should be non-negative."""
        tracker = LaunchPhaseTracker()
        progress = tracker.get_progress()
        assert progress["elapsed_time"] >= 0.0

    def test_get_progress_estimated_remaining(self):
        """Estimated remaining should decrease as phases complete."""
        tracker = LaunchPhaseTracker()
        initial = tracker.get_progress()

        # After cleanup + daemon
        tracker.process_line("AUTO-CLEANUP: done")
        tracker.process_line("daemon start")
        after_daemon = tracker.get_progress()

        assert after_daemon["estimated_remaining"] < initial["estimated_remaining"]

    def test_phase_callback_receives_iso_timestamp(self):
        """Phase change callback receives ISO 8601 timestamp."""
        timestamps = []

        def on_change(phase, status, ts):
            timestamps.append(ts)

        tracker = LaunchPhaseTracker(on_phase_change=on_change)
        tracker.process_line("AUTO-CLEANUP: starting")

        assert len(timestamps) > 0
        # Validate ISO format by parsing
        datetime.datetime.fromisoformat(timestamps[0])

    def test_phases_advance_sequentially(self):
        """Phases advance in order: cleanup->daemon->nodes->homing."""
        phases = []

        def on_change(phase, status, ts):
            if status == "active":
                phases.append(phase)

        tracker = LaunchPhaseTracker(on_phase_change=on_change)
        tracker.process_line("AUTO-CLEANUP: go")
        tracker.process_line("daemon start")
        tracker.process_line("[robot_state_publisher] up")
        tracker.process_line("[yanthra_move] homing")

        assert phases == [
            "cleanup",
            "daemon_restart",
            "node_startup",
            "motor_homing",
        ]

    def test_completed_phases_tracked(self):
        """Completed phases accumulate in get_progress."""
        tracker = LaunchPhaseTracker()
        tracker.process_line("AUTO-CLEANUP: done")
        tracker.process_line("daemon start")

        progress = tracker.get_progress()
        assert "cleanup" in progress["completed_phases"]
        assert progress["current_phase"] == "daemon_restart"

    def test_process_line_before_current_phase_ignored(self):
        """Lines matching earlier phases don't regress state."""
        phases = []

        def on_change(phase, status, ts):
            phases.append((phase, status))

        tracker = LaunchPhaseTracker(on_phase_change=on_change)
        tracker.process_line("AUTO-CLEANUP: go")
        tracker.process_line("daemon start")
        # This cleanup line should NOT regress back to cleanup
        tracker.process_line("AUTO-CLEANUP: again?")

        active_phases = [p for p, s in phases if s == "active"]
        # cleanup should only appear once as active
        assert active_phases.count("cleanup") == 1

    def test_expected_durations(self):
        """Phase durations match spec: cleanup=5, daemon=2, nodes=1, homing=7."""
        tracker = LaunchPhaseTracker()
        assert tracker.phase_durations["cleanup"] == 5.0
        assert tracker.phase_durations["daemon_restart"] == 2.0
        assert tracker.phase_durations["node_startup"] == 1.0
        assert tracker.phase_durations["motor_homing"] == 7.0
        assert tracker.phase_durations["system_ready"] == 0.0

    def test_no_callback_does_not_crash(self):
        """Tracker works without callback (callback is optional)."""
        tracker = LaunchPhaseTracker()
        tracker.process_line("AUTO-CLEANUP: go")
        tracker.process_line("daemon start")
        progress = tracker.get_progress()
        assert progress["current_phase"] == "daemon_restart"

    def test_mark_ready(self):
        """mark_ready transitions to system_ready phase."""
        phases = []

        def on_change(phase, status, ts):
            phases.append((phase, status))

        tracker = LaunchPhaseTracker(on_phase_change=on_change)
        tracker.process_line("AUTO-CLEANUP: go")
        tracker.process_line("daemon start")
        tracker.process_line("[robot_state_publisher] up")
        tracker.process_line("[yanthra_move] homing")
        tracker.mark_ready()

        assert ("system_ready", "active") in phases
        assert ("motor_homing", "complete") in phases
        progress = tracker.get_progress()
        assert progress["current_phase"] == "system_ready"


# -----------------------------------------------------------------
# Launching Status Tests (Task 1.2)
# -----------------------------------------------------------------


class TestLaunchingStatus:
    """Tests for 'launching' status and stability check."""

    @pytest.mark.asyncio
    async def test_start_process_sets_launching_status(self):
        """start_process initially sets status to 'launching'."""
        manager = ProcessManager()
        mock_proc = _make_mock_process(pid=42)
        mock_proc.stdout.readline = AsyncMock(return_value=b"")
        mock_proc.stderr.readline = AsyncMock(return_value=b"")
        # Never resolve wait so process stays "alive"
        mock_proc.wait = AsyncMock(
            return_value=asyncio.Future()
        )
        mock_proc.wait.return_value = None
        # Make wait hang so _wait_process doesn't complete
        wait_future = asyncio.get_event_loop().create_future()
        mock_proc.wait = AsyncMock(side_effect=[wait_future])

        with patch(
            "backend.launch_api.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            await manager.start_process("test", "sleep", ["60"])

        status = manager.get_status("test")
        assert status["status"] == "launching"

    @pytest.mark.asyncio
    async def test_launching_transitions_to_running_after_stability(
        self,
    ):
        """After stability_seconds of process being alive, status -> 'running'."""
        manager = ProcessManager(stability_seconds=0.3)
        mock_proc = _make_mock_process(pid=43)
        mock_proc.stdout.readline = AsyncMock(return_value=b"")
        mock_proc.stderr.readline = AsyncMock(return_value=b"")

        # Make wait() hang forever (simulate long-running process)
        async def _hang_forever():
            await asyncio.get_event_loop().create_future()

        mock_proc.wait = _hang_forever
        # returncode is None while alive
        mock_proc.returncode = None

        with patch(
            "backend.launch_api.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            await manager.start_process("stable", "sleep", ["60"])

        # Wait for stability check to complete (0.3s + some margin)
        await asyncio.sleep(0.6)

        status = manager.get_status("stable")
        assert status["status"] == "running"

    @pytest.mark.asyncio
    async def test_launching_transitions_to_error_on_death(self):
        """If process dies during stability check, status is 'error'."""
        manager = ProcessManager(stability_seconds=0.5)
        mock_proc = _make_mock_process(pid=44)
        mock_proc.stdout.readline = AsyncMock(return_value=b"")
        mock_proc.stderr.readline = AsyncMock(return_value=b"")
        # Process dies immediately
        mock_proc.wait = AsyncMock(return_value=1)
        mock_proc.returncode = 1

        with patch(
            "backend.launch_api.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            await manager.start_process("dying", "false", [])

        # Give time for wait + stability to notice
        await asyncio.sleep(0.3)

        status = manager.get_status("dying")
        assert status["status"] == "error"

    @pytest.mark.asyncio
    async def test_phase_tracker_attached_to_entry(self):
        """start_process attaches a LaunchPhaseTracker to the entry."""
        manager = ProcessManager()
        mock_proc = _make_mock_process(pid=45)
        mock_proc.stdout.readline = AsyncMock(return_value=b"")
        mock_proc.stderr.readline = AsyncMock(return_value=b"")
        mock_proc.wait = AsyncMock(return_value=0)

        with patch(
            "backend.launch_api.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            await manager.start_process("tracked", "echo", ["hi"])

        entry = manager._registry["tracked"]
        assert "phase_tracker" in entry
        assert isinstance(entry["phase_tracker"], LaunchPhaseTracker)

    @pytest.mark.asyncio
    async def test_stop_process_accepts_launching_status(self):
        """stop_process works when process is in 'launching' state."""
        manager = ProcessManager()
        mock_proc = _make_mock_process(pid=46)
        mock_proc.stdout.readline = AsyncMock(return_value=b"")
        mock_proc.stderr.readline = AsyncMock(return_value=b"")
        never_done = asyncio.get_event_loop().create_future()
        mock_proc.wait = AsyncMock(side_effect=[never_done])
        mock_proc.returncode = None

        with patch(
            "backend.launch_api.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            await manager.start_process("launch_stop", "sleep", ["60"])

        assert manager.get_status("launch_stop")["status"] == "launching"

        # Now make wait resolve for stop_process
        mock_proc.wait = AsyncMock(return_value=0)
        await manager.stop_process("launch_stop")

        status = manager.get_status("launch_stop")
        assert status["status"] == "stopped"

    @pytest.mark.asyncio
    async def test_duplicate_check_includes_launching(self):
        """Cannot start a process with same name if it's 'launching'."""
        manager = ProcessManager()
        mock_proc = _make_mock_process(pid=47)
        mock_proc.stdout.readline = AsyncMock(return_value=b"")
        mock_proc.stderr.readline = AsyncMock(return_value=b"")
        never_done = asyncio.get_event_loop().create_future()
        mock_proc.wait = AsyncMock(side_effect=[never_done])

        with patch(
            "backend.launch_api.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            await manager.start_process("dup_launch", "sleep", ["60"])

            with pytest.raises(RuntimeError, match="already running"):
                await manager.start_process(
                    "dup_launch", "sleep", ["60"]
                )


# -----------------------------------------------------------------
# Structured WebSocket Message Tests (Tasks 1.3 + 1.4)
# -----------------------------------------------------------------


class TestStructuredBroadcast:
    """Tests for structured broadcast messages and phase integration."""

    @pytest.mark.asyncio
    async def test_broadcast_output_sends_structured_dict(self):
        """_broadcast with msg_type='output' sends structured dict."""
        received = []

        async def on_msg(msg):
            received.append(msg)

        manager = ProcessManager()
        manager.subscribe("test", on_msg)
        await manager._broadcast("test", "hello world", msg_type="output")

        assert len(received) == 1
        assert received[0]["type"] == "output"
        assert received[0]["data"] == "hello world"

    @pytest.mark.asyncio
    async def test_broadcast_phase_sends_phase_dict(self):
        """_broadcast with msg_type='phase' sends phase event dict."""
        received = []

        async def on_msg(msg):
            received.append(msg)

        manager = ProcessManager()
        manager.subscribe("test", on_msg)
        await manager._broadcast(
            "test",
            "",
            msg_type="phase",
            phase="cleanup",
            status="active",
            timestamp="2026-03-07T00:00:00+00:00",
        )

        assert len(received) == 1
        msg = received[0]
        assert msg["type"] == "phase"
        assert msg["phase"] == "cleanup"
        assert msg["status"] == "active"
        assert msg["timestamp"] == "2026-03-07T00:00:00+00:00"

    @pytest.mark.asyncio
    async def test_broadcast_default_is_output(self):
        """_broadcast without msg_type defaults to 'output'."""
        received = []

        async def on_msg(msg):
            received.append(msg)

        manager = ProcessManager()
        manager.subscribe("test", on_msg)
        await manager._broadcast("test", "some line")

        assert len(received) == 1
        assert received[0]["type"] == "output"

    @pytest.mark.asyncio
    async def test_read_stream_feeds_phase_tracker(self):
        """_read_stream feeds lines to the phase tracker."""
        manager = ProcessManager()
        mock_proc = _make_mock_process(pid=80)
        stdout_lines = [
            b"AUTO-CLEANUP: removing stale\n",
            b"daemon start\n",
            b"",
        ]
        mock_proc.stdout.readline = AsyncMock(
            side_effect=stdout_lines
        )
        mock_proc.stderr.readline = AsyncMock(return_value=b"")
        mock_proc.wait = AsyncMock(return_value=0)

        with patch(
            "backend.launch_api.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            await manager.start_process("phase_test", "echo", ["hi"])

        await asyncio.sleep(0.15)

        tracker = manager._registry["phase_test"]["phase_tracker"]
        progress = tracker.get_progress()
        assert "cleanup" in progress["completed_phases"]
        assert progress["current_phase"] == "daemon_restart"

    @pytest.mark.asyncio
    async def test_phase_events_broadcast_to_subscribers(self):
        """Phase changes are broadcast as structured phase events."""
        received = []

        async def on_msg(msg):
            received.append(msg)

        manager = ProcessManager()
        mock_proc = _make_mock_process(pid=81)
        stdout_lines = [
            b"AUTO-CLEANUP: go\n",
            b"daemon start\n",
            b"",
        ]
        mock_proc.stdout.readline = AsyncMock(
            side_effect=stdout_lines
        )
        mock_proc.stderr.readline = AsyncMock(return_value=b"")
        mock_proc.wait = AsyncMock(return_value=0)

        manager.subscribe("phase_broadcast", on_msg)

        with patch(
            "backend.launch_api.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            await manager.start_process(
                "phase_broadcast", "echo", ["hi"]
            )

        await asyncio.sleep(0.15)

        # Should have both output and phase messages
        output_msgs = [m for m in received if m["type"] == "output"]
        phase_msgs = [m for m in received if m["type"] == "phase"]

        assert len(output_msgs) >= 2  # at least the 2 stdout lines
        assert len(phase_msgs) >= 2  # cleanup active, daemon active
        # Check phase msg structure
        cleanup_active = [
            m
            for m in phase_msgs
            if m["phase"] == "cleanup" and m["status"] == "active"
        ]
        assert len(cleanup_active) == 1
        assert "timestamp" in cleanup_active[0]

    @pytest.mark.asyncio
    async def test_backward_compat_dead_subscriber_removed(self):
        """Subscriber raising exception is still removed with new format."""

        async def bad_callback(msg):
            raise ConnectionError("disconnected")

        manager = ProcessManager()
        manager.subscribe("dead_test2", bad_callback)
        await manager._broadcast("dead_test2", "test_line")

        subs = manager._subscribers.get("dead_test2", set())
        assert bad_callback not in subs


# -----------------------------------------------------------------
# WebSocket Launch Output Handler Tests (Bug Fix: [object Object])
# -----------------------------------------------------------------


class TestWsLaunchOutputHandler:
    """Tests for handle_launch_output WebSocket handler message formatting.

    Bug: _broadcast sends structured dicts ({"type": "output", "data": "..."})
    but the handler wraps them in {"role": role, "line": <dict>}, creating
    double-wrapped messages. Frontend receives {"role":"arm","line":{"type":"output",
    "data":"..."}}, where data.type is undefined, causing [object Object] display.

    These tests call the actual handle_launch_output handler with a mocked WebSocket
    and ProcessManager to verify the exact JSON shape sent over the wire.
    """

    @pytest.mark.asyncio
    async def test_live_output_dict_sends_flat_message(self):
        """Live structured output must be sent flat with role added, not nested.

        Expected: {"type": "output", "data": "hello", "role": "arm"}
        Bug gave: {"role": "arm", "line": {"type": "output", "data": "hello"}}
        """
        from backend.websocket_handlers import handle_launch_output

        sent_messages = []
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock(
            side_effect=lambda m: sent_messages.append(m)
        )

        manager = ProcessManager()
        manager._registry["arm"] = {
            "process": AsyncMock(),
            "output_buffer": [],
            "phase_tracker": None,
            "started_at": None,
        }

        # The handler loops forever reading from a queue; we need to:
        # 1. Let it start and subscribe
        # 2. Broadcast a message
        # 3. Kill it after it sends
        original_subscribe = manager.subscribe

        async def run_handler():
            try:
                await asyncio.wait_for(
                    handle_launch_output(mock_ws, "arm", lambda: manager),
                    timeout=0.5,
                )
            except (asyncio.TimeoutError, Exception):
                pass

        handler_task = asyncio.create_task(run_handler())
        await asyncio.sleep(0.05)  # Let handler subscribe

        # Broadcast a structured output message
        await manager._broadcast("arm", "hello world")
        await asyncio.sleep(0.05)  # Let handler process

        handler_task.cancel()
        try:
            await handler_task
        except asyncio.CancelledError:
            pass

        # Find the output message (skip any buffered replay messages)
        output_msgs = [
            m for m in sent_messages
            if isinstance(m, dict) and m.get("type") == "output"
        ]
        assert len(output_msgs) >= 1, (
            f"Expected structured output message, got: {sent_messages}"
        )
        msg = output_msgs[0]
        assert msg["type"] == "output"
        assert "hello world" in msg["data"]
        assert msg["role"] == "arm"
        # Must NOT have double-wrapping
        assert "line" not in msg

    @pytest.mark.asyncio
    async def test_live_phase_event_sends_flat_message(self):
        """Phase events must be sent flat with role, not nested in {"line": ...}."""
        from backend.websocket_handlers import handle_launch_output

        sent_messages = []
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock(
            side_effect=lambda m: sent_messages.append(m)
        )

        manager = ProcessManager()
        manager._registry["arm"] = {
            "process": AsyncMock(),
            "output_buffer": [],
            "phase_tracker": None,
            "started_at": None,
        }

        async def run_handler():
            try:
                await asyncio.wait_for(
                    handle_launch_output(mock_ws, "arm", lambda: manager),
                    timeout=0.5,
                )
            except (asyncio.TimeoutError, Exception):
                pass

        handler_task = asyncio.create_task(run_handler())
        await asyncio.sleep(0.05)

        await manager._broadcast(
            "arm",
            "",
            msg_type="phase",
            phase="cleanup",
            status="active",
            timestamp="2026-03-07T10:00:00+00:00",
        )
        await asyncio.sleep(0.05)

        handler_task.cancel()
        try:
            await handler_task
        except asyncio.CancelledError:
            pass

        phase_msgs = [
            m for m in sent_messages
            if isinstance(m, dict) and m.get("type") == "phase"
        ]
        assert len(phase_msgs) >= 1, (
            f"Expected phase message, got: {sent_messages}"
        )
        msg = phase_msgs[0]
        assert msg["type"] == "phase"
        assert msg["phase"] == "cleanup"
        assert msg["status"] == "active"
        assert msg["role"] == "arm"
        assert "line" not in msg

    @pytest.mark.asyncio
    async def test_buffered_output_wrapped_as_structured(self):
        """Buffered output (plain strings) must be sent as structured messages.

        get_buffered_output returns plain strings. The handler must wrap them as
        {"type": "output", "data": "<string>", "role": "arm"} so frontend
        receives a consistent format.
        """
        from backend.websocket_handlers import handle_launch_output

        sent_messages = []
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock(
            side_effect=lambda m: sent_messages.append(m)
        )

        manager = ProcessManager()
        manager._registry["arm"] = {
            "process": AsyncMock(),
            "output_buffer": ["[stdout] line1", "[stderr] line2"],
            "phase_tracker": None,
            "started_at": None,
        }

        async def run_handler():
            try:
                await asyncio.wait_for(
                    handle_launch_output(mock_ws, "arm", lambda: manager),
                    timeout=0.3,
                )
            except (asyncio.TimeoutError, Exception):
                pass

        handler_task = asyncio.create_task(run_handler())
        await asyncio.sleep(0.1)
        handler_task.cancel()
        try:
            await handler_task
        except asyncio.CancelledError:
            pass

        # Buffered output should be sent as structured messages
        assert len(sent_messages) >= 2, (
            f"Expected 2 buffered messages, got: {sent_messages}"
        )
        for msg in sent_messages[:2]:
            assert msg.get("type") == "output", (
                f"Buffered msg should be structured, got: {msg}"
            )
            assert isinstance(msg.get("data"), str)
            assert msg.get("role") == "arm"
            assert "line" not in msg
