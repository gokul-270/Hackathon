"""Integration tests for operations API — HTTP-level lifecycle tests.

Validates end-to-end operation flows via httpx.AsyncClient against a
real FastAPI app with the operations router:

- Full lifecycle: run → subscribe → complete → verify events
- Multi-target sequential execution via HTTP
- Cancel mid-operation via HTTP
- Conflict detection (HTTP 409)

NOTE: The SSE /stream endpoint replays buffered output then streams
live events.  The operation_complete event is only sent to live
subscribers, NOT stored in the output buffer.  Therefore streaming
tests subscribe BEFORE the operation finishes so the queue receives
the live operation_complete event.
"""

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.operations_api import (
    OperationsManager,
    operations_router,
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


class FakeEntityManager:
    """Mock entity manager for tests."""

    def __init__(self, entities=None):
        self._entities = {e.id: e for e in (entities or [])}

    def get_entity(self, entity_id: str):
        return self._entities.get(entity_id)

    def get_all_entities(self):
        return list(self._entities.values())


def _parse_sse_body(body: str) -> List[Dict[str, Any]]:
    """Parse SSE text into a list of event dicts.

    Only handles ``data: {...}`` lines; ignores comments and
    keepalives.
    """
    events: List[Dict[str, Any]] = []
    for raw_line in body.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("data: "):
            payload = stripped[len("data: ") :]
            try:
                events.append(json.loads(payload))
            except json.JSONDecodeError:
                continue
    return events


async def _drain_queue(
    queue: asyncio.Queue,
    timeout: float = 2.0,
) -> List[Dict[str, Any]]:
    """Drain all events from a subscriber queue.

    Reads until ``operation_complete`` is received or *timeout*
    seconds elapse with no new event.
    """
    events: List[Dict[str, Any]] = []
    try:
        while True:
            ev = await asyncio.wait_for(queue.get(), timeout=timeout)
            events.append(ev)
            if ev.get("event") == "operation_complete":
                break
    except asyncio.TimeoutError:
        pass
    return events


# -----------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------


@pytest.fixture()
def _fake_entities():
    """Standard set of fake entities."""
    return [
        FakeEntity(
            id="test-target-1",
            name="Target 1",
            ip="192.168.1.101",
        ),
        FakeEntity(
            id="test-target-2",
            name="Target 2",
            ip="192.168.1.102",
        ),
    ]


@pytest.fixture()
def _ops_manager(tmp_path, _fake_entities):
    """Fresh OperationsManager with fake sync.sh and entities."""
    fake_sync = tmp_path / "sync.sh"
    fake_sync.write_text("#!/bin/bash\necho ok\n")
    fake_sync.chmod(0o755)
    mgr = OperationsManager(sync_sh_path=str(fake_sync))
    em = FakeEntityManager(_fake_entities)
    mgr.set_entity_manager(em)
    return mgr


@pytest.fixture()
def app(_ops_manager):
    """FastAPI test app wired to a fresh OperationsManager."""
    test_app = FastAPI()
    test_app.include_router(operations_router)

    import backend.operations_api as ops_mod

    original_manager = ops_mod._operations_manager
    ops_mod._operations_manager = _ops_manager

    yield test_app

    ops_mod._operations_manager = original_manager


@pytest_asyncio.fixture()
async def client(app):
    """httpx AsyncClient bound to the test FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# -----------------------------------------------------------------
# 1. Full operation lifecycle: run → stream → complete
# -----------------------------------------------------------------


class TestFullLifecycle:
    """POST /run, subscribe to manager queue, verify events."""

    @pytest.mark.asyncio
    async def test_run_stream_complete(self, client, _ops_manager):
        """Start op, capture SSE events, verify completion."""
        mock_proc = _make_mock_process(returncode=0)

        # Simulate 3 stdout lines then EOF
        line_idx = 0

        async def readline_side_effect():
            nonlocal line_idx
            line_idx += 1
            if line_idx <= 3:
                return f"line {line_idx}\n".encode()
            return b""

        mock_proc.stdout.readline = AsyncMock(
            side_effect=readline_side_effect,
        )

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            # POST /run
            resp = await client.post(
                "/api/operations/run",
                json={
                    "operation": "deploy-cross",
                    "target_ids": ["test-target-1"],
                    "params": {},
                },
            )
            assert resp.status_code == 200
            body = resp.json()
            assert "operation_id" in body
            assert body["status"] == "started"
            op_id = body["operation_id"]

            # Subscribe to the manager queue so we get live
            # events including operation_complete.
            queue = _ops_manager.subscribe(op_id)
            assert queue is not None

            # Wait for the background task to finish
            op = _ops_manager.get_operation(op_id)
            assert op is not None
            if op._run_task:
                await op._run_task

            # Drain the subscriber queue
            events = await _drain_queue(queue)

            # Should contain stdout output lines
            stdout_events = [e for e in events if e.get("stream") == "stdout"]
            assert len(stdout_events) == 3
            assert stdout_events[0]["line"] == "line 1"
            assert stdout_events[2]["line"] == "line 3"

            # Should contain operation_complete
            complete_events = [e for e in events if e.get("event") == "operation_complete"]
            assert len(complete_events) == 1
            summary = complete_events[0]["summary"]
            assert summary["succeeded"] == 1
            assert summary["failed"] == 0

            # Operation should no longer be active
            active_resp = await client.get("/api/operations/active")
            active_ids = [o["operation_id"] for o in active_resp.json()["operations"]]
            assert op_id not in active_ids

    @pytest.mark.asyncio
    async def test_run_returns_target_list(self, client, _ops_manager):
        """POST /run response includes resolved target IDs."""
        mock_proc = _make_mock_process(returncode=0)
        # Make stdout.readline return empty bytes immediately to exit the read loop
        mock_proc.stdout.readline = AsyncMock(return_value=b"")
        mock_proc.stderr.readline = AsyncMock(return_value=b"")
        # Make wait() return immediately
        mock_proc.wait = AsyncMock(return_value=0)

        async def mock_subprocess(*args, **kwargs):
            return mock_proc

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=mock_subprocess,
        ):
            resp = await client.post(
                "/api/operations/run",
                json={
                    "operation": "verify",
                    "target_ids": ["test-target-1"],
                    "params": {},
                },
            )
            assert resp.status_code == 200
            body = resp.json()
            # API returns target objects with details, not just IDs
            assert len(body["targets"]) == 1
            assert body["targets"][0]["target_id"] == "test-target-1"

            # Cleanup — wait for background task with timeout
            op = _ops_manager.get_operation(body["operation_id"])
            if op and op._run_task:
                try:
                    await asyncio.wait_for(op._run_task, timeout=5.0)
                except asyncio.TimeoutError:
                    pass

    @pytest.mark.asyncio
    async def test_stream_replays_buffer(self, client, _ops_manager):
        """GET /stream replays buffered output for a
        completed operation."""
        mock_proc = _make_mock_process(returncode=0)
        line_idx = 0

        async def readline_side_effect():
            nonlocal line_idx
            line_idx += 1
            if line_idx <= 2:
                return f"buf {line_idx}\n".encode()
            return b""

        mock_proc.stdout.readline = AsyncMock(
            side_effect=readline_side_effect,
        )

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            resp = await client.post(
                "/api/operations/run",
                json={
                    "operation": "deploy-cross",
                    "target_ids": ["test-target-1"],
                    "params": {},
                },
            )
            op_id = resp.json()["operation_id"]
            op = _ops_manager.get_operation(op_id)
            if op and op._run_task:
                await op._run_task

            # Verify buffered output is available
            buffered = _ops_manager.get_buffered_output(op_id)
            stdout_buf = [e for e in buffered if e.get("stream") == "stdout"]
            assert len(stdout_buf) == 2
            assert stdout_buf[0]["line"] == "buf 1"
            assert stdout_buf[1]["line"] == "buf 2"


# -----------------------------------------------------------------
# 2. Multi-target sequential execution
# -----------------------------------------------------------------


class TestMultiTargetHTTP:
    """Run an operation against 2 targets via HTTP endpoints."""

    @pytest.mark.asyncio
    async def test_multi_target_sequential_via_http(self, client, _ops_manager):
        """Both targets execute sequentially and succeed."""
        call_order: List[str] = []

        def make_proc():
            proc = _make_mock_process(returncode=0)

            async def fake_readline():
                return b""

            proc.stdout.readline = AsyncMock(
                side_effect=fake_readline,
            )
            return proc

        async def mock_subprocess(*args, **kwargs):
            ip_arg = [a for a in args if isinstance(a, str) and a.startswith("192.168")]
            if ip_arg:
                call_order.append(ip_arg[0])
            return make_proc()

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=mock_subprocess,
        ):
            resp = await client.post(
                "/api/operations/run",
                json={
                    "operation": "deploy-cross",
                    "target_ids": [
                        "test-target-1",
                        "test-target-2",
                    ],
                    "params": {},
                },
            )
            assert resp.status_code == 200
            body = resp.json()
            op_id = body["operation_id"]
            assert len(body["targets"]) == 2

            op = _ops_manager.get_operation(op_id)
            if op and op._run_task:
                await op._run_task

            for target in op.targets:
                assert target.status == "success"
                assert target.exit_code == 0

            assert len(call_order) == 2
            assert call_order[0] == "192.168.1.101"
            assert call_order[1] == "192.168.1.102"

    @pytest.mark.asyncio
    async def test_multi_target_completion_event(self, client, _ops_manager):
        """operation_complete arrives after all targets done."""
        mock_proc = _make_mock_process(returncode=0)

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            resp = await client.post(
                "/api/operations/run",
                json={
                    "operation": "deploy-cross",
                    "target_ids": [
                        "test-target-1",
                        "test-target-2",
                    ],
                    "params": {},
                },
            )
            assert resp.status_code == 200
            op_id = resp.json()["operation_id"]

            # Subscribe before the task finishes
            queue = _ops_manager.subscribe(op_id)
            assert queue is not None

            op = _ops_manager.get_operation(op_id)
            if op and op._run_task:
                await op._run_task

            events = await _drain_queue(queue)
            complete = [e for e in events if e.get("event") == "operation_complete"]
            assert len(complete) == 1
            assert complete[0]["summary"]["succeeded"] == 2
            assert complete[0]["summary"]["total"] == 2


# -----------------------------------------------------------------
# 3. Cancel mid-operation
# -----------------------------------------------------------------


class TestCancelHTTP:
    """Cancel a running operation via POST /cancel."""

    @pytest.mark.asyncio
    async def test_cancel_running_operation(self, client, _ops_manager):
        """Start a hanging op, cancel it, verify response."""
        mock_proc = _make_mock_process()

        wait_event = asyncio.Event()

        async def blocking_wait():
            await wait_event.wait()
            return 0

        mock_proc.wait = AsyncMock(side_effect=blocking_wait)

        stdout_event = asyncio.Event()

        async def blocking_readline():
            await stdout_event.wait()
            return b""

        mock_proc.stdout.readline = AsyncMock(
            side_effect=blocking_readline,
        )

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            resp = await client.post(
                "/api/operations/run",
                json={
                    "operation": "deploy-cross",
                    "target_ids": ["test-target-1"],
                    "params": {},
                },
            )
            assert resp.status_code == 200
            op_id = resp.json()["operation_id"]

            # Let the background task start the subprocess
            await asyncio.sleep(0.05)

            # Verify it appears in the active list
            active_resp = await client.get("/api/operations/active")
            active_ids = [o["operation_id"] for o in active_resp.json()["operations"]]
            assert op_id in active_ids

            # Cancel via HTTP
            cancel_resp = await client.post(f"/api/operations/{op_id}/cancel")
            assert cancel_resp.status_code == 200
            cancel_body = cancel_resp.json()
            assert cancel_body["status"] == "cancelled"
            assert "test-target-1" in cancel_body["targets_cancelled"]

            # Unblock the mock so background task can exit
            wait_event.set()
            stdout_event.set()

    @pytest.mark.asyncio
    async def test_cancel_already_completed_returns_409(self, client, _ops_manager):
        """Cancelling a finished operation returns HTTP 409."""
        mock_proc = _make_mock_process(returncode=0)

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            resp = await client.post(
                "/api/operations/run",
                json={
                    "operation": "deploy-cross",
                    "target_ids": ["test-target-1"],
                    "params": {},
                },
            )
            op_id = resp.json()["operation_id"]

            op = _ops_manager.get_operation(op_id)
            if op and op._run_task:
                await op._run_task

            cancel_resp = await client.post(f"/api/operations/{op_id}/cancel")
            assert cancel_resp.status_code == 409

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_returns_404(self, client):
        """Cancelling unknown operation ID returns 404."""
        resp = await client.post("/api/operations/op-nonexistent/cancel")
        assert resp.status_code == 404


# -----------------------------------------------------------------
# 4. Conflict detection (HTTP 409)
# -----------------------------------------------------------------


class TestConflictHTTP:
    """Verify HTTP 409 when targeting an already-busy entity."""

    @pytest.mark.asyncio
    async def test_conflict_same_target_returns_409(self, client, _ops_manager):
        """Second op on same target gets HTTP 409."""
        mock_proc = _make_mock_process()

        wait_event = asyncio.Event()

        async def blocking_wait():
            await wait_event.wait()
            return 0

        mock_proc.wait = AsyncMock(side_effect=blocking_wait)

        stdout_event = asyncio.Event()

        async def blocking_readline():
            await stdout_event.wait()
            return b""

        mock_proc.stdout.readline = AsyncMock(
            side_effect=blocking_readline,
        )

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            resp1 = await client.post(
                "/api/operations/run",
                json={
                    "operation": "deploy-cross",
                    "target_ids": ["test-target-1"],
                    "params": {},
                },
            )
            assert resp1.status_code == 200
            op1_id = resp1.json()["operation_id"]

            await asyncio.sleep(0.02)

            # Same target — should get 409
            resp2 = await client.post(
                "/api/operations/run",
                json={
                    "operation": "build",
                    "target_ids": ["test-target-1"],
                    "params": {},
                },
            )
            assert resp2.status_code == 409
            assert "already active" in resp2.json()["detail"]

            # Cleanup
            await client.post(f"/api/operations/{op1_id}/cancel")
            wait_event.set()
            stdout_event.set()

    @pytest.mark.asyncio
    async def test_different_targets_no_conflict(self, client, _ops_manager):
        """Ops on different targets start without conflict."""
        mock_proc = _make_mock_process()

        wait_event = asyncio.Event()

        async def blocking_wait():
            await wait_event.wait()
            return 0

        mock_proc.wait = AsyncMock(side_effect=blocking_wait)

        stdout_event = asyncio.Event()

        async def blocking_readline():
            await stdout_event.wait()
            return b""

        mock_proc.stdout.readline = AsyncMock(
            side_effect=blocking_readline,
        )

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            resp1 = await client.post(
                "/api/operations/run",
                json={
                    "operation": "deploy-cross",
                    "target_ids": ["test-target-1"],
                    "params": {},
                },
            )
            assert resp1.status_code == 200

            await asyncio.sleep(0.02)

            resp2 = await client.post(
                "/api/operations/run",
                json={
                    "operation": "deploy-cross",
                    "target_ids": ["test-target-2"],
                    "params": {},
                },
            )
            assert resp2.status_code == 200

            op1_id = resp1.json()["operation_id"]
            op2_id = resp2.json()["operation_id"]
            assert op1_id != op2_id

            # Cleanup
            await client.post(f"/api/operations/{op1_id}/cancel")
            await client.post(f"/api/operations/{op2_id}/cancel")
            wait_event.set()
            stdout_event.set()

    @pytest.mark.asyncio
    async def test_conflict_clears_after_completion(self, client, _ops_manager):
        """After op completes, same target is available."""
        mock_proc = _make_mock_process(returncode=0)

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            resp1 = await client.post(
                "/api/operations/run",
                json={
                    "operation": "deploy-cross",
                    "target_ids": ["test-target-1"],
                    "params": {},
                },
            )
            assert resp1.status_code == 200
            op = _ops_manager.get_operation(resp1.json()["operation_id"])
            if op and op._run_task:
                await op._run_task

            # Same target should now succeed
            resp2 = await client.post(
                "/api/operations/run",
                json={
                    "operation": "build",
                    "target_ids": ["test-target-1"],
                    "params": {},
                },
            )
            assert resp2.status_code == 200

            op2 = _ops_manager.get_operation(resp2.json()["operation_id"])
            if op2 and op2._run_task:
                await op2._run_task
