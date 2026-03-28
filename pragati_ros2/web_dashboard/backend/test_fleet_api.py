"""DEPRECATED: Tests for fleet API endpoints (/api/fleet/*). The entity API
(/api/entities/*) replaces fleet endpoints. These tests remain until fleet routes
are removed in a follow-up change.
See openspec/changes/dashboard-entity-core/design.md D7."""

import asyncio
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_FLEET_STATUS = [
    {
        "name": "vehicle",
        "ip": "192.168.1.10",
        "role": "vehicle",
        "status": "online",
        "cpu_percent": 45.2,
        "memory_percent": 62.1,
        "last_seen": "2026-03-08T12:00:00+00:00",
        "operational_state": "IDLE",
        "pick_count": 0,
    },
    {
        "name": "arm1",
        "ip": "192.168.1.11",
        "role": "arm",
        "status": "online",
        "cpu_percent": 30.0,
        "memory_percent": 50.0,
        "last_seen": "2026-03-08T12:00:00+00:00",
        "operational_state": "DETECTING",
        "pick_count": 5,
    },
    {
        "name": "arm2",
        "ip": "192.168.1.12",
        "role": "arm",
        "status": "offline",
        "cpu_percent": None,
        "memory_percent": None,
        "last_seen": None,
        "operational_state": "UNKNOWN",
        "pick_count": 0,
    },
]


def _make_fleet_app(fleet_status=None, fleet_service_available=True):
    """Create a FastAPI app with the fleet_router wired up.

    Patches get_fleet_health_service to return a mock service
    that returns the given fleet_status.
    """
    import backend.fleet_api as mod

    # Reset module state
    mod._dashboard_role = "dev"
    mod._fleet_jobs.clear()

    app = FastAPI()
    app.include_router(mod.fleet_router)

    if fleet_service_available and fleet_status is not None:
        mock_svc = MagicMock()
        mock_svc.get_fleet_status.return_value = fleet_status
    elif fleet_service_available:
        mock_svc = MagicMock()
        mock_svc.get_fleet_status.return_value = []
    else:
        mock_svc = None

    return app, mod, mock_svc


# ---------------------------------------------------------------------------
# GET /api/fleet/status
# ---------------------------------------------------------------------------


class TestFleetStatusEndpoint:
    """Test GET /api/fleet/status returns correct data."""

    def test_returns_fleet_members(self):
        """Status endpoint returns array of fleet members."""
        app, mod, mock_svc = _make_fleet_app(SAMPLE_FLEET_STATUS)
        with patch.object(mod, "_get_fleet_svc", return_value=mock_svc):
            client = TestClient(app)
            resp = client.get("/api/fleet/status")

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        assert "members" in data
        assert len(data["members"]) == 3

    def test_member_schema_fields(self):
        """Each member has required fields in response."""
        app, mod, mock_svc = _make_fleet_app(SAMPLE_FLEET_STATUS)
        with patch.object(mod, "_get_fleet_svc", return_value=mock_svc):
            client = TestClient(app)
            resp = client.get("/api/fleet/status")

        members = resp.json()["members"]
        required_fields = {
            "name",
            "ip",
            "role",
            "status",
            "cpu_percent",
            "memory_percent",
            "last_seen",
            "operational_state",
            "pick_count",
        }
        for member in members:
            assert required_fields.issubset(
                member.keys()
            ), f"Missing fields: {required_fields - member.keys()}"

    def test_online_member_has_metrics(self):
        """Online member includes cpu and memory values."""
        app, mod, mock_svc = _make_fleet_app(SAMPLE_FLEET_STATUS)
        with patch.object(mod, "_get_fleet_svc", return_value=mock_svc):
            client = TestClient(app)
            resp = client.get("/api/fleet/status")

        members = resp.json()["members"]
        vehicle = next(m for m in members if m["name"] == "vehicle")
        assert vehicle["status"] == "online"
        assert vehicle["cpu_percent"] == 45.2
        assert vehicle["memory_percent"] == 62.1

    def test_offline_member_has_null_metrics(self):
        """Offline member has null cpu/memory."""
        app, mod, mock_svc = _make_fleet_app(SAMPLE_FLEET_STATUS)
        with patch.object(mod, "_get_fleet_svc", return_value=mock_svc):
            client = TestClient(app)
            resp = client.get("/api/fleet/status")

        members = resp.json()["members"]
        arm2 = next(m for m in members if m["name"] == "arm2")
        assert arm2["status"] == "offline"
        assert arm2["cpu_percent"] is None
        assert arm2["memory_percent"] is None

    def test_empty_fleet_returns_empty_array(self):
        """No fleet configured returns empty members array."""
        app, mod, mock_svc = _make_fleet_app([])
        with patch.object(mod, "_get_fleet_svc", return_value=mock_svc):
            client = TestClient(app)
            resp = client.get("/api/fleet/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["members"] == []

    def test_service_unavailable_returns_empty(self):
        """FleetHealthService not available returns empty members."""
        app, mod, mock_svc = _make_fleet_app(
            fleet_status=None, fleet_service_available=False
        )
        with patch.object(mod, "_get_fleet_svc", return_value=None):
            client = TestClient(app)
            resp = client.get("/api/fleet/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["members"] == []


# ---------------------------------------------------------------------------
# POST /api/fleet/sync
# ---------------------------------------------------------------------------


class TestFleetSyncEndpoint:
    """Test POST /api/fleet/sync triggers sync per RPi."""

    def test_sync_returns_job_id(self):
        """Sync endpoint returns a job_id string immediately."""
        app, mod, mock_svc = _make_fleet_app(SAMPLE_FLEET_STATUS)
        with patch.object(mod, "_get_fleet_svc", return_value=mock_svc), patch.object(
            mod, "_run_fleet_job", new_callable=AsyncMock
        ):
            client = TestClient(app)
            resp = client.post("/api/fleet/sync")

        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data
        # job_id should be a valid UUID
        uuid.UUID(data["job_id"])

    def test_sync_creates_job_with_pending_members(self):
        """Sync creates a job with per-member pending status."""
        app, mod, mock_svc = _make_fleet_app(SAMPLE_FLEET_STATUS)
        with patch.object(mod, "_get_fleet_svc", return_value=mock_svc), patch.object(
            mod, "_run_fleet_job", new_callable=AsyncMock
        ):
            client = TestClient(app)
            resp = client.post("/api/fleet/sync")

        job_id = resp.json()["job_id"]
        assert job_id in mod._fleet_jobs
        job = mod._fleet_jobs[job_id]
        assert job["type"] == "sync"
        # All members with IPs should have entries
        for entry in job["members"]:
            assert entry["status"] == "pending"

    def test_sync_empty_fleet_returns_error(self):
        """Sync with no fleet members returns 400."""
        app, mod, mock_svc = _make_fleet_app([])
        with patch.object(mod, "_get_fleet_svc", return_value=mock_svc):
            client = TestClient(app)
            resp = client.post("/api/fleet/sync")

        assert resp.status_code == 400
        assert "no fleet members" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# POST /api/fleet/logs
# ---------------------------------------------------------------------------


class TestFleetLogsEndpoint:
    """Test POST /api/fleet/logs triggers log collection per RPi."""

    def test_logs_returns_job_id(self):
        """Logs endpoint returns a job_id string immediately."""
        app, mod, mock_svc = _make_fleet_app(SAMPLE_FLEET_STATUS)
        with patch.object(mod, "_get_fleet_svc", return_value=mock_svc), patch.object(
            mod, "_run_fleet_job", new_callable=AsyncMock
        ):
            client = TestClient(app)
            resp = client.post("/api/fleet/logs")

        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data
        uuid.UUID(data["job_id"])

    def test_logs_creates_job_with_correct_type(self):
        """Logs creates a job with type 'logs'."""
        app, mod, mock_svc = _make_fleet_app(SAMPLE_FLEET_STATUS)
        with patch.object(mod, "_get_fleet_svc", return_value=mock_svc), patch.object(
            mod, "_run_fleet_job", new_callable=AsyncMock
        ):
            client = TestClient(app)
            resp = client.post("/api/fleet/logs")

        job_id = resp.json()["job_id"]
        job = mod._fleet_jobs[job_id]
        assert job["type"] == "logs"

    def test_logs_empty_fleet_returns_error(self):
        """Logs with no fleet members returns 400."""
        app, mod, mock_svc = _make_fleet_app([])
        with patch.object(mod, "_get_fleet_svc", return_value=mock_svc):
            client = TestClient(app)
            resp = client.post("/api/fleet/logs")

        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/fleet/jobs/<job_id>
# ---------------------------------------------------------------------------


class TestFleetJobStatusEndpoint:
    """Test GET /api/fleet/jobs/<job_id> returns per-RPi progress."""

    def test_job_status_returns_job_data(self):
        """Valid job_id returns job type and member statuses."""
        app, mod, mock_svc = _make_fleet_app(SAMPLE_FLEET_STATUS)
        # Manually insert a job
        job_id = str(uuid.uuid4())
        mod._fleet_jobs[job_id] = {
            "type": "sync",
            "status": "running",
            "members": [
                {"name": "vehicle", "ip": "192.168.1.10", "status": "running"},
                {"name": "arm1", "ip": "192.168.1.11", "status": "pending"},
                {"name": "arm2", "ip": "192.168.1.12", "status": "pending"},
            ],
        }

        client = TestClient(app)
        resp = client.get(f"/api/fleet/jobs/{job_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "sync"
        assert data["status"] == "running"
        assert len(data["members"]) == 3

    def test_unknown_job_id_returns_404(self):
        """Unknown job_id returns 404."""
        app, mod, _ = _make_fleet_app()
        client = TestClient(app)
        resp = client.get(f"/api/fleet/jobs/{uuid.uuid4()}")

        assert resp.status_code == 404

    def test_completed_job_shows_all_done(self):
        """Completed job shows overall status as 'completed'."""
        app, mod, mock_svc = _make_fleet_app(SAMPLE_FLEET_STATUS)
        job_id = str(uuid.uuid4())
        mod._fleet_jobs[job_id] = {
            "type": "sync",
            "status": "completed",
            "members": [
                {"name": "vehicle", "ip": "192.168.1.10", "status": "success"},
                {"name": "arm1", "ip": "192.168.1.11", "status": "success"},
            ],
        }

        client = TestClient(app)
        resp = client.get(f"/api/fleet/jobs/{job_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        for m in data["members"]:
            assert m["status"] == "success"

    def test_partial_failure_job(self):
        """Job with mixed results shows partial failure."""
        app, mod, mock_svc = _make_fleet_app(SAMPLE_FLEET_STATUS)
        job_id = str(uuid.uuid4())
        mod._fleet_jobs[job_id] = {
            "type": "sync",
            "status": "completed",
            "members": [
                {"name": "vehicle", "ip": "192.168.1.10", "status": "success"},
                {
                    "name": "arm1",
                    "ip": "192.168.1.11",
                    "status": "failed",
                    "error": "Connection refused",
                },
            ],
        }

        client = TestClient(app)
        resp = client.get(f"/api/fleet/jobs/{job_id}")

        data = resp.json()
        arm1 = next(m for m in data["members"] if m["name"] == "arm1")
        assert arm1["status"] == "failed"
        assert "error" in arm1


# ---------------------------------------------------------------------------
# Subprocess execution (mocked)
# ---------------------------------------------------------------------------


class TestFleetJobExecution:
    """Test _run_fleet_job subprocess execution with mocked asyncio.subprocess."""

    @pytest.mark.asyncio
    async def test_sync_job_runs_sync_sh_per_member(self):
        """Sync job runs sync.sh --deploy-cross for each member."""
        import backend.fleet_api as mod

        mod._fleet_jobs.clear()
        job_id = str(uuid.uuid4())
        mod._fleet_jobs[job_id] = {
            "type": "sync",
            "status": "running",
            "members": [
                {"name": "vehicle", "ip": "192.168.1.10", "status": "pending"},
                {"name": "arm1", "ip": "192.168.1.11", "status": "pending"},
            ],
        }

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"ok", b""))
        mock_proc.returncode = 0

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_proc
        ) as mock_exec:
            await mod._run_fleet_job(job_id)

        # Should have been called once per member
        assert mock_exec.call_count == 2
        # Check that sync.sh was called with correct args
        calls = mock_exec.call_args_list
        for call in calls:
            args = call[0]
            assert "sync.sh" in args[0] or "sync.sh" in str(args)

    @pytest.mark.asyncio
    async def test_logs_job_runs_collect_logs(self):
        """Logs job runs sync.sh --collect-logs for each member."""
        import backend.fleet_api as mod

        mod._fleet_jobs.clear()
        job_id = str(uuid.uuid4())
        mod._fleet_jobs[job_id] = {
            "type": "logs",
            "status": "running",
            "members": [
                {"name": "vehicle", "ip": "192.168.1.10", "status": "pending"},
            ],
        }

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"collected", b""))
        mock_proc.returncode = 0

        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_proc
        ) as mock_exec:
            await mod._run_fleet_job(job_id)

        args = mock_exec.call_args[0]
        assert "--collect-logs" in args

    @pytest.mark.asyncio
    async def test_sync_partial_failure(self):
        """One RPi fails but others continue successfully."""
        import backend.fleet_api as mod

        mod._fleet_jobs.clear()
        job_id = str(uuid.uuid4())
        mod._fleet_jobs[job_id] = {
            "type": "sync",
            "status": "running",
            "members": [
                {"name": "vehicle", "ip": "192.168.1.10", "status": "pending"},
                {"name": "arm1", "ip": "192.168.1.11", "status": "pending"},
            ],
        }

        call_count = 0

        async def _mock_exec(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            proc = AsyncMock()
            if "--ip" in args and "192.168.1.11" in args:
                proc.communicate = AsyncMock(return_value=(b"", b"Connection refused"))
                proc.returncode = 1
            else:
                proc.communicate = AsyncMock(return_value=(b"ok", b""))
                proc.returncode = 0
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=_mock_exec):
            await mod._run_fleet_job(job_id)

        job = mod._fleet_jobs[job_id]
        assert job["status"] == "completed"
        vehicle = next(m for m in job["members"] if m["name"] == "vehicle")
        arm1 = next(m for m in job["members"] if m["name"] == "arm1")
        assert vehicle["status"] == "success"
        assert arm1["status"] == "failed"
        assert "error" in arm1

    @pytest.mark.asyncio
    async def test_subprocess_timeout(self):
        """Subprocess exceeding 120s timeout is marked failed."""
        import backend.fleet_api as mod

        mod._fleet_jobs.clear()
        job_id = str(uuid.uuid4())
        mod._fleet_jobs[job_id] = {
            "type": "sync",
            "status": "running",
            "members": [
                {"name": "arm1", "ip": "192.168.1.11", "status": "pending"},
            ],
        }

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_proc.kill = MagicMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            await mod._run_fleet_job(job_id)

        job = mod._fleet_jobs[job_id]
        arm1 = job["members"][0]
        assert arm1["status"] == "failed"
        assert "timeout" in arm1.get("error", "").lower()
