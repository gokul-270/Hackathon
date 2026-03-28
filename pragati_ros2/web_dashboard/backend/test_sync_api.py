"""Tests for sync_api.py — sync.sh integration backend.

Validates:
- GET /api/sync/available — detects sync.sh presence
- POST /api/sync/run — spawns sync.sh with operation + IP
- POST /api/sync/cancel — sends SIGINT to running sync
- GET /api/sync/status — returns current operation state
- GET /api/sync/config — returns saved config
- PUT /api/sync/config — persists target IPs
- Recent IPs tracking from run calls
- subscribe/unsubscribe output callbacks
"""

import asyncio
import signal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.sync_api import SyncManager, sync_router


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


# -----------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------


@pytest.fixture()
def tmp_data_dir(tmp_path):
    """Temporary data directory for config persistence."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture()
def sync_manager(tmp_path, tmp_data_dir):
    """Fresh SyncManager with a fake sync.sh path."""
    fake_sync = tmp_path / "sync.sh"
    fake_sync.write_text("#!/bin/bash\necho ok\n")
    fake_sync.chmod(0o755)
    mgr = SyncManager(
        sync_sh_path=str(fake_sync), data_dir=str(tmp_data_dir)
    )
    return mgr


@pytest.fixture()
def sync_manager_no_sync(tmp_data_dir):
    """SyncManager where sync.sh does not exist."""
    return SyncManager(
        sync_sh_path="/nonexistent/sync.sh",
        data_dir=str(tmp_data_dir),
    )


@pytest.fixture()
def client(sync_manager):
    """FastAPI test client with sync router."""
    import backend.sync_api as _mod

    orig_manager = _mod._sync_manager
    _mod._sync_manager = sync_manager
    app = FastAPI()
    app.include_router(sync_router)
    yield TestClient(app)
    _mod._sync_manager = orig_manager


@pytest.fixture()
def client_no_sync(sync_manager_no_sync):
    """FastAPI test client where sync.sh is unavailable."""
    import backend.sync_api as _mod

    orig_manager = _mod._sync_manager
    _mod._sync_manager = sync_manager_no_sync
    app = FastAPI()
    app.include_router(sync_router)
    yield TestClient(app)
    _mod._sync_manager = orig_manager


# -----------------------------------------------------------------
# Task 6.1 Tests — Core endpoints
# -----------------------------------------------------------------


class TestSyncAvailable:
    """GET /api/sync/available."""

    def test_available_when_sync_sh_exists(self, client, sync_manager):
        """Returns available=true when sync.sh exists."""
        resp = client.get("/api/sync/available")
        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is True
        assert body["path"] is not None
        assert "sync.sh" in body["path"]

    def test_unavailable_when_sync_sh_missing(self, client_no_sync):
        """Returns available=false when sync.sh does not exist."""
        resp = client_no_sync.get("/api/sync/available")
        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is False
        assert body["path"] is None


class TestSyncRun:
    """POST /api/sync/run."""

    def test_run_starts_subprocess(self, client, sync_manager):
        """Starts a sync operation and returns status=started."""
        mock_proc = _make_mock_process(pid=1234)

        with patch(
            "backend.sync_api.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=mock_proc),
        ):
            resp = client.post(
                "/api/sync/run",
                json={
                    "operation": "deploy-cross",
                    "target_ip": "192.168.1.100",
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "started"
        assert body["operation"] == "deploy-cross"
        assert body["target_ip"] == "192.168.1.100"

    def test_run_rejects_concurrent_operation(
        self, client, sync_manager
    ):
        """Returns 409 if an operation is already in progress."""
        mock_proc = _make_mock_process(pid=1234)
        # Process stays running (returncode stays None)
        mock_proc.returncode = None
        mock_proc.stdout.readline = AsyncMock(
            side_effect=[asyncio.CancelledError()]
        )
        mock_proc.stderr.readline = AsyncMock(
            side_effect=[asyncio.CancelledError()]
        )
        mock_proc.wait = AsyncMock(side_effect=[asyncio.CancelledError()])

        with patch(
            "backend.sync_api.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=mock_proc),
        ):
            resp1 = client.post(
                "/api/sync/run",
                json={
                    "operation": "deploy-cross",
                    "target_ip": "192.168.1.100",
                },
            )
            assert resp1.status_code == 200

            # Manually mark as running since mock won't complete
            sync_manager._running = True

            resp2 = client.post(
                "/api/sync/run",
                json={
                    "operation": "build",
                    "target_ip": "192.168.1.101",
                },
            )

        assert resp2.status_code == 409

    def test_run_rejects_invalid_operation(self, client):
        """Returns 400 for operations not in the allowlist."""
        resp = client.post(
            "/api/sync/run",
            json={
                "operation": "rm-rf",
                "target_ip": "192.168.1.100",
            },
        )
        assert resp.status_code == 400

    def test_run_rejects_invalid_ip(self, client):
        """Returns 400 for IPs that don't match IPv4 pattern."""
        resp = client.post(
            "/api/sync/run",
            json={
                "operation": "deploy-cross",
                "target_ip": "not-an-ip",
            },
        )
        assert resp.status_code == 400

    def test_run_returns_503_when_sync_sh_unavailable(
        self, client_no_sync
    ):
        """Returns 503 when sync.sh is not found."""
        resp = client_no_sync.post(
            "/api/sync/run",
            json={
                "operation": "deploy-cross",
                "target_ip": "192.168.1.100",
            },
        )
        assert resp.status_code == 503


class TestSyncCancel:
    """POST /api/sync/cancel."""

    def test_cancel_sends_sigint(self, client, sync_manager):
        """Sends SIGINT to running sync process."""
        mock_proc = _make_mock_process(pid=5555)
        mock_proc.returncode = None

        with patch(
            "backend.sync_api.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=mock_proc),
        ):
            client.post(
                "/api/sync/run",
                json={
                    "operation": "build",
                    "target_ip": "10.0.0.1",
                },
            )
            # Mark as running
            sync_manager._running = True
            sync_manager._process = mock_proc

            resp = client.post("/api/sync/cancel")

        assert resp.status_code == 200
        mock_proc.send_signal.assert_called_with(signal.SIGINT)

    def test_cancel_when_no_operation_returns_404(self, client):
        """Returns 404 if no operation is running."""
        resp = client.post("/api/sync/cancel")
        assert resp.status_code == 404


class TestSyncStatus:
    """GET /api/sync/status."""

    def test_status_returns_idle_initially(self, client):
        """Returns running=false when no operation is active."""
        resp = client.get("/api/sync/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["running"] is False
        assert body["operation"] is None
        assert body["target_ip"] is None
        assert body["exit_code"] is None
        assert body["output_lines"] == 0

    def test_status_returns_running_during_operation(
        self, client, sync_manager
    ):
        """Returns running=true during an active operation."""
        mock_proc = _make_mock_process(pid=7777)
        mock_proc.returncode = None

        with patch(
            "backend.sync_api.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=mock_proc),
        ):
            client.post(
                "/api/sync/run",
                json={
                    "operation": "provision",
                    "target_ip": "192.168.1.50",
                },
            )
            sync_manager._running = True
            sync_manager._operation = "provision"
            sync_manager._target_ip = "192.168.1.50"

            resp = client.get("/api/sync/status")

        assert resp.status_code == 200
        body = resp.json()
        assert body["running"] is True
        assert body["operation"] == "provision"
        assert body["target_ip"] == "192.168.1.50"


# -----------------------------------------------------------------
# Task 6.2 Tests — Config persistence
# -----------------------------------------------------------------


class TestSyncConfig:
    """GET/PUT /api/sync/config."""

    def test_config_get_returns_defaults(self, client):
        """Returns empty lists when no config file exists."""
        resp = client.get("/api/sync/config")
        assert resp.status_code == 200
        body = resp.json()
        assert body["target_ips"] == []
        assert body["recent_ips"] == []

    def test_config_put_persists_ips(self, client, tmp_data_dir):
        """PUT saves IPs and GET returns them."""
        resp = client.put(
            "/api/sync/config",
            json={"target_ips": ["192.168.1.10", "10.0.0.5"]},
        )
        assert resp.status_code == 200

        resp2 = client.get("/api/sync/config")
        body = resp2.json()
        assert body["target_ips"] == ["192.168.1.10", "10.0.0.5"]

    def test_config_put_validates_ips(self, client):
        """PUT rejects invalid IPs."""
        resp = client.put(
            "/api/sync/config",
            json={"target_ips": ["192.168.1.10", "bad-ip"]},
        )
        assert resp.status_code == 400

    def test_recent_ips_tracked_from_run(
        self, client, sync_manager
    ):
        """Running operations adds IPs to recent_ips list."""
        mock_proc = _make_mock_process(pid=8888)

        with patch(
            "backend.sync_api.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=mock_proc),
        ):
            client.post(
                "/api/sync/run",
                json={
                    "operation": "deploy-cross",
                    "target_ip": "192.168.1.200",
                },
            )
            # Reset running state to allow next run
            sync_manager._running = False
            sync_manager._process = None

            client.post(
                "/api/sync/run",
                json={
                    "operation": "build",
                    "target_ip": "10.0.0.99",
                },
            )

        resp = client.get("/api/sync/config")
        body = resp.json()
        assert "192.168.1.200" in body["recent_ips"]
        assert "10.0.0.99" in body["recent_ips"]


# -----------------------------------------------------------------
# Task 6.3 Tests — Output subscription
# -----------------------------------------------------------------


class TestSyncOutputSubscription:
    """subscribe_output / unsubscribe_output on SyncManager."""

    @pytest.mark.asyncio
    async def test_subscribe_receives_output(self, sync_manager):
        """Subscriber callback receives output lines."""
        received = []

        async def on_line(line):
            received.append(line)

        sync_manager.subscribe_output(on_line)

        # Simulate broadcast
        await sync_manager._broadcast_output("hello world")
        assert len(received) == 1
        assert received[0] == "hello world"

    @pytest.mark.asyncio
    async def test_unsubscribe_stops_delivery(self, sync_manager):
        """After unsubscribe, callback stops receiving."""
        received = []

        async def on_line(line):
            received.append(line)

        sync_manager.subscribe_output(on_line)
        sync_manager.unsubscribe_output(on_line)

        await sync_manager._broadcast_output("should not arrive")
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_dead_subscriber_removed(self, sync_manager):
        """Subscriber that raises is automatically removed."""

        async def bad_callback(line):
            raise ConnectionError("disconnected")

        sync_manager.subscribe_output(bad_callback)
        await sync_manager._broadcast_output("test line")

        assert bad_callback not in sync_manager._output_subscribers
