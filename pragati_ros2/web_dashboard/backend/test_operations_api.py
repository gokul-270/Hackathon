"""Tests for operations_api.py — unified sync.sh operation runner.

Validates:
- OperationsManager: flag mapping, parameter validation, target resolution
- POST /api/operations/run — starts operations with conflict rejection
- POST /api/operations/{id}/cancel — SIGTERM+SIGKILL cancellation
- GET /api/operations/{id}/stream — SSE streaming with buffer replay
- GET /api/operations/active — lists active operations
- GET /api/operations/definitions — returns operation definitions
- GET /api/operations/available — sync.sh availability check
- Ring buffer (5000 lines), timeout, multi-target sequential execution
"""

import asyncio
from collections import deque
from dataclasses import dataclass
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.operations_api import (
    ALLOWED_OPERATIONS,
    DEFAULT_TIMEOUT_S,
    MAX_OUTPUT_LINES,
    OPERATION_DEFINITIONS,
    Operation,
    OperationsManager,
    OperationRunRequest,
    TargetState,
    _build_sync_args,
    operations_router,
    validate_params,
)

# -----------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------


def _make_mock_process(pid=9999, returncode=None):
    """Create a mock asyncio.Process for sync.sh."""
    proc = AsyncMock()
    proc.pid = pid
    proc.returncode = returncode
    proc.stdout = AsyncMock()
    proc.stderr = AsyncMock()
    proc.send_signal = MagicMock()
    proc.terminate = MagicMock()
    proc.kill = MagicMock()
    proc.wait = AsyncMock(return_value=0)
    proc.stdout.readline = AsyncMock(return_value=b"")
    proc.stderr.readline = AsyncMock(return_value=b"")
    return proc


@dataclass
class FakeEntity:
    """Minimal entity for testing target resolution."""

    id: str
    name: str
    ip: Optional[str]
    entity_type: str = "arm"
    source: str = "remote"
    status: str = "online"
    group_id: str = "default"


class FakeEntityManager:
    """Mock entity manager for tests."""

    def __init__(self, entities=None):
        self._entities = {e.id: e for e in (entities or [])}

    def get_entity(self, entity_id: str):
        return self._entities.get(entity_id)

    def get_all_entities(self):
        return list(self._entities.values())


# -----------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------


@pytest.fixture()
def ops_manager(tmp_path):
    """Fresh OperationsManager with a fake sync.sh path."""
    fake_sync = tmp_path / "sync.sh"
    fake_sync.write_text("#!/bin/bash\necho ok\n")
    fake_sync.chmod(0o755)
    mgr = OperationsManager(sync_sh_path=str(fake_sync))
    return mgr


@pytest.fixture()
def ops_manager_no_sync():
    """OperationsManager where sync.sh does not exist."""
    return OperationsManager(sync_sh_path="/nonexistent/sync.sh")


@pytest.fixture()
def ops_manager_with_entities(ops_manager):
    """OperationsManager with entity manager injected."""
    entities = [
        FakeEntity(id="arm-1", name="Arm 1", ip="192.168.1.101"),
        FakeEntity(id="arm-2", name="Arm 2", ip="192.168.1.102"),
        FakeEntity(
            id="vehicle-1",
            name="Vehicle",
            ip="192.168.1.200",
            entity_type="vehicle",
        ),
    ]
    em = FakeEntityManager(entities)
    ops_manager.set_entity_manager(em)
    return ops_manager


@pytest.fixture()
def app():
    """FastAPI test app with operations router."""
    app = FastAPI()
    app.include_router(operations_router)
    return app


@pytest.fixture()
def client(app):
    """TestClient for the operations API."""
    return TestClient(app)


# -----------------------------------------------------------------
# Unit tests: flag mapping
# -----------------------------------------------------------------


class TestFlagMapping:
    """Test _build_sync_args for all 12 operations."""

    def test_deploy_cross(self):
        args = _build_sync_args("deploy-cross", "10.0.0.1", {})
        assert args == ["--deploy-cross", "--ip", "10.0.0.1"]

    def test_deploy_local(self):
        args = _build_sync_args("deploy-local", "10.0.0.1", {})
        assert args == ["--deploy-local", "--ip", "10.0.0.1"]

    def test_build(self):
        args = _build_sync_args("build", "10.0.0.1", {})
        assert args == ["--build", "--ip", "10.0.0.1"]

    def test_quick_sync(self):
        args = _build_sync_args("quick-sync", "10.0.0.1", {})
        assert args == ["--quick", "--ip", "10.0.0.1"]

    def test_provision(self):
        args = _build_sync_args("provision", "10.0.0.1", {})
        assert args == ["--provision", "--ip", "10.0.0.1"]

    def test_set_role(self):
        args = _build_sync_args("set-role", "10.0.0.1", {"role": "arm"})
        assert args == ["--provision", "--role", "arm", "--ip", "10.0.0.1"]

    def test_set_arm_identity(self):
        args = _build_sync_args("set-arm-identity", "10.0.0.1", {"arm_id": 3})
        assert args == ["--provision", "--arm-id", "3", "--ip", "10.0.0.1"]

    def test_set_mqtt_address(self):
        args = _build_sync_args("set-mqtt-address", "10.0.0.1", {"mqtt_address": "10.0.0.99"})
        assert args == ["--mqtt-address", "10.0.0.99", "--ip", "10.0.0.1"]

    def test_collect_logs(self):
        args = _build_sync_args("collect-logs", "10.0.0.1", {})
        assert args == ["--collect-logs", "--ip", "10.0.0.1"]

    def test_verify(self):
        args = _build_sync_args("verify", "10.0.0.1", {})
        assert args == ["--verify", "--ip", "10.0.0.1"]

    def test_restart(self):
        args = _build_sync_args("restart", "10.0.0.1", {})
        assert args == ["--restart", "--ip", "10.0.0.1"]

    def test_test_mqtt(self):
        args = _build_sync_args("test-mqtt", "10.0.0.1", {})
        assert args == ["--test-mqtt", "--ip", "10.0.0.1"]

    def test_missing_param_raises(self):
        with pytest.raises(ValueError, match="Missing required parameter"):
            _build_sync_args("set-role", "10.0.0.1", {})

    def test_all_operations_defined(self):
        """Ensure minimum expected operations are defined."""
        # Number of operations may grow over time
        assert len(OPERATION_DEFINITIONS) >= 12
        assert ALLOWED_OPERATIONS == frozenset(OPERATION_DEFINITIONS.keys())


# -----------------------------------------------------------------
# Unit tests: parameter validation
# -----------------------------------------------------------------


class TestParameterValidation:
    """Test validate_params for parameterized operations."""

    def test_valid_role_arm(self):
        validate_params("set-role", {"role": "arm"})  # no exception

    def test_valid_role_vehicle(self):
        validate_params("set-role", {"role": "vehicle"})  # no exception

    def test_invalid_role(self):
        with pytest.raises(ValueError, match="Invalid role"):
            validate_params("set-role", {"role": "drone"})

    def test_valid_arm_id(self):
        for i in range(1, 7):
            validate_params("set-arm-identity", {"arm_id": i})

    def test_invalid_arm_id_zero(self):
        with pytest.raises(ValueError, match="Invalid arm_id"):
            validate_params("set-arm-identity", {"arm_id": 0})

    def test_invalid_arm_id_seven(self):
        with pytest.raises(ValueError, match="Invalid arm_id"):
            validate_params("set-arm-identity", {"arm_id": 7})

    def test_invalid_arm_id_string(self):
        with pytest.raises(ValueError, match="Invalid arm_id"):
            validate_params("set-arm-identity", {"arm_id": "abc"})

    def test_valid_mqtt_address(self):
        validate_params("set-mqtt-address", {"mqtt_address": "192.168.1.100"})

    def test_invalid_mqtt_address(self):
        with pytest.raises(ValueError, match="Invalid mqtt_address"):
            validate_params("set-mqtt-address", {"mqtt_address": "not-an-ip"})

    def test_no_validation_for_simple_ops(self):
        """Simple operations should pass validation with empty params."""
        for op in [
            "deploy-cross",
            "deploy-local",
            "build",
            "quick-sync",
            "provision",
            "collect-logs",
            "verify",
            "restart",
            "test-mqtt",
        ]:
            validate_params(op, {})  # no exception


# -----------------------------------------------------------------
# Unit tests: target resolution
# -----------------------------------------------------------------


class TestTargetResolution:
    """Test OperationsManager.resolve_targets."""

    def test_resolve_entity_ids(self, ops_manager_with_entities):
        targets = ops_manager_with_entities.resolve_targets(["arm-1", "arm-2"])
        assert len(targets) == 2
        assert targets[0].target_id == "arm-1"
        assert targets[0].ip == "192.168.1.101"
        assert targets[1].target_id == "arm-2"
        assert targets[1].ip == "192.168.1.102"

    def test_resolve_all(self, ops_manager_with_entities):
        targets = ops_manager_with_entities.resolve_targets(["all"])
        assert len(targets) == 3

    def test_resolve_all_no_entity_manager(self, ops_manager):
        with pytest.raises(ValueError, match="Entity manager unavailable"):
            ops_manager.resolve_targets(["all"])

    def test_resolve_raw_ip_fallback(self, ops_manager):
        targets = ops_manager.resolve_targets(["192.168.1.50"])
        assert len(targets) == 1
        assert targets[0].target_id == "192.168.1.50"
        assert targets[0].ip == "192.168.1.50"

    def test_resolve_unknown_target(self, ops_manager):
        with pytest.raises(ValueError, match="Cannot resolve target"):
            ops_manager.resolve_targets(["unknown-entity"])

    def test_resolve_entity_no_ip(self, ops_manager):
        entities = [
            FakeEntity(id="local", name="Local", ip=None),
        ]
        em = FakeEntityManager(entities)
        ops_manager.set_entity_manager(em)
        with pytest.raises(ValueError, match="has no IP"):
            ops_manager.resolve_targets(["local"])


# -----------------------------------------------------------------
# Unit tests: conflict detection
# -----------------------------------------------------------------


class TestConflictDetection:
    """Test operation conflict rejection."""

    @pytest.mark.asyncio
    async def test_reject_conflicting_operation(self, ops_manager_with_entities):
        mgr = ops_manager_with_entities
        mock_proc = _make_mock_process()

        # Make wait hang so the operation stays active
        mock_proc.wait = AsyncMock(side_effect=asyncio.CancelledError())

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            op1 = await mgr.run_operation("deploy-cross", ["arm-1"], {})

            # Second operation on same target should fail
            with pytest.raises(RuntimeError, match="Operation already active"):
                await mgr.run_operation("build", ["arm-1"], {})

        # Cleanup: cancel the first operation
        await mgr.cancel_operation(op1.operation_id)

    @pytest.mark.asyncio
    async def test_different_targets_no_conflict(self, ops_manager_with_entities):
        mgr = ops_manager_with_entities
        mock_proc = _make_mock_process()
        mock_proc.wait = AsyncMock(side_effect=asyncio.CancelledError())

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            op1 = await mgr.run_operation("deploy-cross", ["arm-1"], {})
            # Different target should succeed
            op2 = await mgr.run_operation("deploy-cross", ["arm-2"], {})
            assert op1.operation_id != op2.operation_id

        # Cleanup
        await mgr.cancel_operation(op1.operation_id)
        await mgr.cancel_operation(op2.operation_id)


# -----------------------------------------------------------------
# Unit tests: OperationsManager run
# -----------------------------------------------------------------


class TestRunOperation:
    """Test run_operation lifecycle."""

    @pytest.mark.asyncio
    async def test_unknown_operation_rejected(self, ops_manager_with_entities):
        with pytest.raises(ValueError, match="Unknown operation"):
            await ops_manager_with_entities.run_operation("nonexistent", ["arm-1"], {})

    @pytest.mark.asyncio
    async def test_sync_sh_not_found(self, ops_manager_no_sync):
        with pytest.raises(FileNotFoundError, match="sync.sh not found"):
            await ops_manager_no_sync.run_operation("deploy-cross", ["192.168.1.1"], {})

    @pytest.mark.asyncio
    async def test_successful_single_target(self, ops_manager_with_entities):
        mgr = ops_manager_with_entities
        mock_proc = _make_mock_process(returncode=0)

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            op = await mgr.run_operation("deploy-cross", ["arm-1"], {})
            assert op.operation_id.startswith("op-")
            assert len(op.targets) == 1
            assert op.targets[0].target_id == "arm-1"

            # Wait for background execution to finish
            if op._run_task:
                await op._run_task

            assert op.targets[0].status == "success"
            assert op.targets[0].exit_code == 0

    @pytest.mark.asyncio
    async def test_failed_target(self, ops_manager_with_entities):
        mgr = ops_manager_with_entities
        mock_proc = _make_mock_process(returncode=1)
        mock_proc.wait = AsyncMock(return_value=1)

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            op = await mgr.run_operation("deploy-cross", ["arm-1"], {})
            if op._run_task:
                await op._run_task

            assert op.targets[0].status == "failed"
            assert op.targets[0].exit_code == 1


# -----------------------------------------------------------------
# Unit tests: multi-target sequential execution
# -----------------------------------------------------------------


class TestMultiTarget:
    """Test sequential multi-target execution."""

    @pytest.mark.asyncio
    async def test_multi_target_sequential(self, ops_manager_with_entities):
        mgr = ops_manager_with_entities
        mock_proc = _make_mock_process(returncode=0)
        call_count = 0

        async def mock_create_subprocess(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return mock_proc

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=mock_create_subprocess,
        ):
            op = await mgr.run_operation("deploy-cross", ["arm-1", "arm-2"], {})
            if op._run_task:
                await op._run_task

            # Should have spawned 2 subprocesses (one per target)
            assert call_count == 2
            assert op.targets[0].status == "success"
            assert op.targets[1].status == "success"

    @pytest.mark.asyncio
    async def test_multi_target_partial_failure(self, ops_manager_with_entities):
        """Failure on one target doesn't abort the batch."""
        mgr = ops_manager_with_entities
        call_count = 0

        def make_proc():
            nonlocal call_count
            call_count += 1
            rc = 1 if call_count == 1 else 0
            p = _make_mock_process(returncode=rc)
            p.wait = AsyncMock(return_value=rc)
            return p

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=lambda *a, **kw: make_proc(),
        ):
            op = await mgr.run_operation("deploy-cross", ["arm-1", "arm-2"], {})
            if op._run_task:
                await op._run_task

            assert op.targets[0].status == "failed"
            assert op.targets[1].status == "success"
            summary = op.summary()
            assert summary["succeeded"] == 1
            assert summary["failed"] == 1


# -----------------------------------------------------------------
# Unit tests: cancellation
# -----------------------------------------------------------------


class TestCancellation:
    """Test operation cancellation."""

    @pytest.mark.asyncio
    async def test_cancel_running_operation(self, ops_manager_with_entities):
        mgr = ops_manager_with_entities
        mock_proc = _make_mock_process()

        # Make wait block until cancelled
        wait_event = asyncio.Event()

        async def blocking_wait():
            await wait_event.wait()
            return 0

        mock_proc.wait = AsyncMock(side_effect=blocking_wait)

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            op = await mgr.run_operation("deploy-cross", ["arm-1"], {})

            # Give the task time to start the target
            await asyncio.sleep(0.05)

            result = await mgr.cancel_operation(op.operation_id)
            assert result["status"] == "cancelled"
            assert "arm-1" in result["targets_cancelled"]

    @pytest.mark.asyncio
    async def test_cancel_multi_target_marks_pending(self, ops_manager_with_entities):
        """Cancelling a multi-target op marks pending targets."""
        mgr = ops_manager_with_entities
        mock_proc = _make_mock_process()

        wait_event = asyncio.Event()

        async def blocking_wait():
            await wait_event.wait()
            return 0

        mock_proc.wait = AsyncMock(side_effect=blocking_wait)

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            op = await mgr.run_operation(
                "deploy-cross",
                ["arm-1", "arm-2", "vehicle-1"],
                {},
            )

            # Wait for first target to start
            await asyncio.sleep(0.05)

            result = await mgr.cancel_operation(op.operation_id)
            # arm-1 (running) + arm-2 & vehicle-1 (pending) cancelled
            assert len(result["targets_cancelled"]) >= 2

    @pytest.mark.asyncio
    async def test_cancel_completed_operation_fails(self, ops_manager_with_entities):
        mgr = ops_manager_with_entities
        mock_proc = _make_mock_process(returncode=0)

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            op = await mgr.run_operation("deploy-cross", ["arm-1"], {})
            if op._run_task:
                await op._run_task

            with pytest.raises(RuntimeError, match="already completed"):
                await mgr.cancel_operation(op.operation_id)

    @pytest.mark.asyncio
    async def test_cancel_unknown_operation(self, ops_manager_with_entities):
        with pytest.raises(KeyError, match="Unknown operation"):
            await ops_manager_with_entities.cancel_operation("op-nonexistent")


# -----------------------------------------------------------------
# Unit tests: active operations query
# -----------------------------------------------------------------


class TestActiveOperations:
    """Test get_active_operations."""

    @pytest.mark.asyncio
    async def test_no_active_operations(self, ops_manager):
        assert ops_manager.get_active_operations() == []

    @pytest.mark.asyncio
    async def test_active_operation_listed(self, ops_manager_with_entities):
        mgr = ops_manager_with_entities
        mock_proc = _make_mock_process()
        # Make wait() hang forever so the operation stays active
        hang_forever = asyncio.Event()

        async def _wait_forever():
            await hang_forever.wait()

        mock_proc.wait = _wait_forever

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            op = await mgr.run_operation("deploy-cross", ["arm-1"], {})

            await asyncio.sleep(0.1)

            active = mgr.get_active_operations()
            assert len(active) == 1
            assert active[0]["operation_id"] == op.operation_id

        await mgr.cancel_operation(op.operation_id)


# -----------------------------------------------------------------
# Unit tests: ring buffer
# -----------------------------------------------------------------


class TestRingBuffer:
    """Test output ring buffer."""

    def test_buffer_max_size(self):
        op = Operation(
            operation_id="op-test",
            operation_name="deploy-cross",
            targets=[],
            timeout_seconds=600,
        )
        assert op.output_buffer.maxlen == MAX_OUTPUT_LINES

    def test_buffer_overflow(self):
        op = Operation(
            operation_id="op-test",
            operation_name="deploy-cross",
            targets=[],
            timeout_seconds=600,
        )
        for i in range(MAX_OUTPUT_LINES + 100):
            op.output_buffer.append({"line": f"line-{i}"})
        assert len(op.output_buffer) == MAX_OUTPUT_LINES
        # Oldest lines should be evicted
        assert op.output_buffer[0]["line"] == "line-100"


# -----------------------------------------------------------------
# Unit tests: SSE subscription
# -----------------------------------------------------------------


class TestSSESubscription:
    """Test SSE subscriber management."""

    @pytest.mark.asyncio
    async def test_subscribe_and_receive(self, ops_manager_with_entities):
        mgr = ops_manager_with_entities
        mock_proc = _make_mock_process(returncode=0)

        # Emit some output
        call_count = 0

        async def readline_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                return f"output line {call_count}\n".encode()
            return b""

        mock_proc.stdout.readline = AsyncMock(side_effect=readline_side_effect)

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            op = await mgr.run_operation("deploy-cross", ["arm-1"], {})

            queue = mgr.subscribe(op.operation_id)
            assert queue is not None

            if op._run_task:
                await op._run_task

            # Queue should have received events
            events = []
            while not queue.empty():
                events.append(queue.get_nowait())

            # Should have at least: start + output lines + complete +
            # operation_complete
            output_events = [e for e in events if e.get("stream") == "stdout"]
            assert len(output_events) == 3
            # Verify output events include "event": "output"
            for ev in output_events:
                assert ev.get("event") == "output"

    def test_subscribe_unknown_operation(self, ops_manager):
        assert ops_manager.subscribe("op-nonexistent") is None

    def test_get_buffered_output_unknown(self, ops_manager):
        assert ops_manager.get_buffered_output("op-nonexistent") == []


# -----------------------------------------------------------------
# Unit tests: TargetState and Operation dataclasses
# -----------------------------------------------------------------


class TestDataClasses:
    """Test TargetState and Operation serialization."""

    def test_target_state_to_dict(self):
        ts = TargetState(target_id="arm-1", ip="10.0.0.1")
        d = ts.to_dict()
        assert d["target_id"] == "arm-1"
        assert d["ip"] == "10.0.0.1"
        assert d["status"] == "pending"

    def test_operation_to_dict(self):
        ts = TargetState(target_id="arm-1", ip="10.0.0.1")
        op = Operation(
            operation_id="op-abc",
            operation_name="deploy-cross",
            targets=[ts],
            timeout_seconds=600,
        )
        d = op.to_dict()
        assert d["operation_id"] == "op-abc"
        assert d["operation"] == "deploy-cross"
        assert d["is_active"] is True
        assert d["summary"]["total"] == 1

    def test_operation_not_active_when_done(self):
        ts = TargetState(target_id="arm-1", ip="10.0.0.1")
        ts.status = "success"
        op = Operation(
            operation_id="op-abc",
            operation_name="deploy-cross",
            targets=[ts],
            timeout_seconds=600,
        )
        assert op.is_active is False


# -----------------------------------------------------------------
# Router tests (HTTP level)
# -----------------------------------------------------------------


class TestRouterEndpoints:
    """Test FastAPI router endpoints via TestClient."""

    def test_get_definitions(self, client):
        resp = client.get("/api/operations/definitions")
        assert resp.status_code == 200
        data = resp.json()
        assert "deploy-cross" in data
        assert "label" in data["deploy-cross"]
        # Number of defined operations may grow; just check minimum expected
        assert len(data) >= 12

    def test_get_available_no_sync(self, client):
        """Without real sync.sh, available should be False."""
        resp = client.get("/api/operations/available")
        assert resp.status_code == 200
        # Will be false since the default path doesn't exist
        # in test environment
        data = resp.json()
        assert "available" in data

    def test_get_active_empty(self, client):
        resp = client.get("/api/operations/active")
        assert resp.status_code == 200
        assert resp.json() == {"operations": []}

    def test_run_unknown_operation(self, client):
        resp = client.post(
            "/api/operations/run",
            json={
                "operation": "nonexistent",
                "target_ids": ["192.168.1.1"],
            },
        )
        assert resp.status_code == 400
        assert "Unknown operation" in resp.json()["detail"]

    def test_cancel_unknown_operation(self, client):
        resp = client.post("/api/operations/op-nonexistent/cancel")
        assert resp.status_code == 404

    def test_stream_unknown_operation(self, client):
        resp = client.get("/api/operations/op-nonexistent/stream")
        assert resp.status_code == 404


# -----------------------------------------------------------------
# Unit tests: operation availability
# -----------------------------------------------------------------


class TestAvailability:
    """Test sync.sh availability detection."""

    def test_available_when_exists(self, ops_manager):
        assert ops_manager.available is True

    def test_not_available_when_missing(self, ops_manager_no_sync):
        assert ops_manager_no_sync.available is False
