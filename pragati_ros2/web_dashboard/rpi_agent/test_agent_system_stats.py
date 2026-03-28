"""Tests for agent system stats endpoints — GET /system/processes and GET /system/stats.

TDD: Tests for the new system stats and process list endpoints.
Uses httpx.AsyncClient with ASGITransport for async FastAPI testing.
All psutil calls are mocked.
"""

import time
from unittest.mock import MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport

AGENT_MODULE = "rpi_agent.agent"


@pytest.fixture
def _clean_env(monkeypatch):
    """Ensure PRAGATI_AGENT_API_KEY is unset."""
    monkeypatch.delenv("PRAGATI_AGENT_API_KEY", raising=False)


@pytest.fixture
def app(_clean_env):
    """Import a fresh app instance with auth disabled."""
    from rpi_agent.agent import create_app

    return create_app()


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as c:
        yield c


def _reset_caches():
    """Reset the agent module's stats caches between tests."""
    import rpi_agent.agent as agent_mod

    agent_mod._process_cache["data"] = []
    agent_mod._process_cache["timestamp"] = 0.0
    agent_mod._stats_cache["data"] = {}
    agent_mod._stats_cache["timestamp"] = 0.0


def _make_mock_proc(pid, name, cpu_percent, rss_bytes, status):
    """Create a mock psutil process for process_iter."""
    proc = MagicMock()
    proc.info = {
        "pid": pid,
        "name": name,
        "cpu_percent": cpu_percent,
        "memory_info": MagicMock(rss=rss_bytes),
        "status": status,
    }
    return proc


# ===================================================================
# 4.1 — GET /system/processes
# ===================================================================


class TestSystemProcesses:
    @pytest.fixture(autouse=True)
    def _reset(self):
        _reset_caches()
        yield
        _reset_caches()

    @pytest.mark.asyncio
    async def test_returns_top_15_processes_sorted(self, client):
        """Response is a JSON array of up to 15 processes sorted by cpu_percent desc."""
        # Create 20 mock processes
        procs = [
            _make_mock_proc(
                pid=i,
                name=f"proc{i}",
                cpu_percent=float(i),
                rss_bytes=i * 1024 * 1024,
                status="running",
            )
            for i in range(1, 21)
        ]

        with patch(f"{AGENT_MODULE}.psutil") as mock_psutil:
            mock_psutil.process_iter.return_value = procs
            mock_psutil.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
            mock_psutil.AccessDenied = type("AccessDenied", (Exception,), {})
            mock_psutil.ZombieProcess = type("ZombieProcess", (Exception,), {})

            resp = await client.get("/system/processes")

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 15

        # Verify sorted by cpu_percent descending
        cpu_values = [p["cpu_percent"] for p in data]
        assert cpu_values == sorted(cpu_values, reverse=True)

        # Top entry should be proc20 (highest cpu)
        assert data[0]["pid"] == 20
        assert data[0]["name"] == "proc20"
        assert data[0]["cpu_percent"] == 20.0

    @pytest.mark.asyncio
    async def test_field_schema(self, client):
        """Each process entry has pid, name, cpu_percent, memory_mb, status."""
        proc = _make_mock_proc(
            pid=42,
            name="python3",
            cpu_percent=12.5,
            rss_bytes=100 * 1024 * 1024,
            status="sleeping",
        )

        with patch(f"{AGENT_MODULE}.psutil") as mock_psutil:
            mock_psutil.process_iter.return_value = [proc]
            mock_psutil.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
            mock_psutil.AccessDenied = type("AccessDenied", (Exception,), {})
            mock_psutil.ZombieProcess = type("ZombieProcess", (Exception,), {})

            resp = await client.get("/system/processes")

        data = resp.json()
        assert len(data) == 1
        entry = data[0]
        assert entry["pid"] == 42
        assert entry["name"] == "python3"
        assert entry["cpu_percent"] == 12.5
        assert entry["memory_mb"] == 100.0
        assert entry["status"] == "sleeping"

    @pytest.mark.asyncio
    async def test_fewer_than_15_processes(self, client):
        """If fewer than 15 processes, return all of them."""
        procs = [
            _make_mock_proc(
                pid=i,
                name=f"p{i}",
                cpu_percent=float(i),
                rss_bytes=1024,
                status="running",
            )
            for i in range(1, 4)
        ]

        with patch(f"{AGENT_MODULE}.psutil") as mock_psutil:
            mock_psutil.process_iter.return_value = procs
            mock_psutil.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
            mock_psutil.AccessDenied = type("AccessDenied", (Exception,), {})
            mock_psutil.ZombieProcess = type("ZombieProcess", (Exception,), {})

            resp = await client.get("/system/processes")

        data = resp.json()
        assert len(data) == 3

    @pytest.mark.asyncio
    async def test_cache_serves_same_data(self, client):
        """Two requests within 3s return identical data from cache."""
        procs = [
            _make_mock_proc(
                pid=1, name="cached", cpu_percent=5.0, rss_bytes=1024, status="running"
            )
        ]

        with patch(f"{AGENT_MODULE}.psutil") as mock_psutil:
            mock_psutil.process_iter.return_value = procs
            mock_psutil.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
            mock_psutil.AccessDenied = type("AccessDenied", (Exception,), {})
            mock_psutil.ZombieProcess = type("ZombieProcess", (Exception,), {})

            resp1 = await client.get("/system/processes")
            # Change return value — should not be used due to cache
            mock_psutil.process_iter.return_value = [
                _make_mock_proc(
                    pid=99,
                    name="new",
                    cpu_percent=99.0,
                    rss_bytes=1024,
                    status="running",
                )
            ]
            resp2 = await client.get("/system/processes")

        assert resp1.json() == resp2.json()
        # process_iter should have been called only once
        assert mock_psutil.process_iter.call_count == 1

    @pytest.mark.asyncio
    async def test_cache_expires_after_3s(self, client):
        """After 3s, fresh data is collected."""
        procs1 = [
            _make_mock_proc(
                pid=1, name="old", cpu_percent=1.0, rss_bytes=1024, status="running"
            )
        ]
        procs2 = [
            _make_mock_proc(
                pid=2, name="new", cpu_percent=2.0, rss_bytes=2048, status="running"
            )
        ]

        import rpi_agent.agent as agent_mod

        with patch(f"{AGENT_MODULE}.psutil") as mock_psutil:
            mock_psutil.process_iter.return_value = procs1
            mock_psutil.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
            mock_psutil.AccessDenied = type("AccessDenied", (Exception,), {})
            mock_psutil.ZombieProcess = type("ZombieProcess", (Exception,), {})

            resp1 = await client.get("/system/processes")
            assert resp1.json()[0]["name"] == "old"

            # Manually expire the cache
            agent_mod._process_cache["timestamp"] = time.time() - 4.0

            mock_psutil.process_iter.return_value = procs2
            resp2 = await client.get("/system/processes")

        assert resp2.json()[0]["name"] == "new"
        assert mock_psutil.process_iter.call_count == 2


# ===================================================================
# 4.2 — GET /system/stats
# ===================================================================


class TestSystemStats:
    @pytest.fixture(autouse=True)
    def _reset(self):
        _reset_caches()
        yield
        _reset_caches()

    @pytest.mark.asyncio
    async def test_returns_system_stats(self, client):
        """GET /system/stats returns cpu_percent, memory, disk, temp fields."""
        with patch(f"{AGENT_MODULE}.psutil") as mock_psutil:
            mock_psutil.cpu_percent.return_value = 45.2
            mock_psutil.virtual_memory.return_value = MagicMock(
                used=4 * 1024**3, total=8 * 1024**3
            )
            mock_psutil.disk_usage.return_value = MagicMock(
                used=30 * 1024**3, total=64 * 1024**3
            )
            mock_psutil.sensors_temperatures.return_value = {
                "cpu_thermal": [MagicMock(current=52.3)]
            }

            resp = await client.get("/system/stats")

        assert resp.status_code == 200
        data = resp.json()
        assert data["cpu_percent"] == 45.2
        assert data["memory_used"] == 4 * 1024**3
        assert data["memory_total"] == 8 * 1024**3
        assert data["disk_used"] == 30 * 1024**3
        assert data["disk_total"] == 64 * 1024**3
        assert data["cpu_temp"] == 52.3

    @pytest.mark.asyncio
    async def test_null_temp_when_no_sensors(self, client):
        """cpu_temp is null when no thermal sensors are available."""
        with patch(f"{AGENT_MODULE}.psutil") as mock_psutil:
            mock_psutil.cpu_percent.return_value = 10.0
            mock_psutil.virtual_memory.return_value = MagicMock(
                used=1024**3, total=4 * 1024**3
            )
            mock_psutil.disk_usage.return_value = MagicMock(
                used=10 * 1024**3, total=32 * 1024**3
            )
            mock_psutil.sensors_temperatures.return_value = {}

            resp = await client.get("/system/stats")

        data = resp.json()
        assert data["cpu_temp"] is None

    @pytest.mark.asyncio
    async def test_null_temp_when_sensors_none(self, client):
        """cpu_temp is null when sensors_temperatures returns None."""
        with patch(f"{AGENT_MODULE}.psutil") as mock_psutil:
            mock_psutil.cpu_percent.return_value = 10.0
            mock_psutil.virtual_memory.return_value = MagicMock(
                used=1024**3, total=4 * 1024**3
            )
            mock_psutil.disk_usage.return_value = MagicMock(
                used=10 * 1024**3, total=32 * 1024**3
            )
            mock_psutil.sensors_temperatures.return_value = None

            resp = await client.get("/system/stats")

        data = resp.json()
        assert data["cpu_temp"] is None

    @pytest.mark.asyncio
    async def test_cache_serves_same_data(self, client):
        """Two requests within 3s return identical cached data."""
        with patch(f"{AGENT_MODULE}.psutil") as mock_psutil:
            mock_psutil.cpu_percent.return_value = 50.0
            mock_psutil.virtual_memory.return_value = MagicMock(
                used=2 * 1024**3, total=4 * 1024**3
            )
            mock_psutil.disk_usage.return_value = MagicMock(
                used=15 * 1024**3, total=32 * 1024**3
            )
            mock_psutil.sensors_temperatures.return_value = {
                "cpu_thermal": [MagicMock(current=45.0)]
            }

            resp1 = await client.get("/system/stats")
            # Change return values — should not affect cached response
            mock_psutil.cpu_percent.return_value = 99.0
            resp2 = await client.get("/system/stats")

        assert resp1.json() == resp2.json()
        assert resp1.json()["cpu_percent"] == 50.0
        # cpu_percent should only have been called once (for cache fill)
        assert mock_psutil.cpu_percent.call_count == 1

    @pytest.mark.asyncio
    async def test_cache_expires_after_3s(self, client):
        """After 3s, fresh data is collected."""
        import rpi_agent.agent as agent_mod

        with patch(f"{AGENT_MODULE}.psutil") as mock_psutil:
            mock_psutil.cpu_percent.return_value = 30.0
            mock_psutil.virtual_memory.return_value = MagicMock(
                used=1024**3, total=4 * 1024**3
            )
            mock_psutil.disk_usage.return_value = MagicMock(
                used=10 * 1024**3, total=32 * 1024**3
            )
            mock_psutil.sensors_temperatures.return_value = {}

            resp1 = await client.get("/system/stats")
            assert resp1.json()["cpu_percent"] == 30.0

            # Expire cache
            agent_mod._stats_cache["timestamp"] = time.time() - 4.0

            mock_psutil.cpu_percent.return_value = 80.0
            resp2 = await client.get("/system/stats")

        assert resp2.json()["cpu_percent"] == 80.0
        assert mock_psutil.cpu_percent.call_count == 2

    @pytest.mark.asyncio
    async def test_field_types(self, client):
        """Verify response field types match spec."""
        with patch(f"{AGENT_MODULE}.psutil") as mock_psutil:
            mock_psutil.cpu_percent.return_value = 25.5
            mock_psutil.virtual_memory.return_value = MagicMock(
                used=2 * 1024**3, total=8 * 1024**3
            )
            mock_psutil.disk_usage.return_value = MagicMock(
                used=20 * 1024**3, total=64 * 1024**3
            )
            mock_psutil.sensors_temperatures.return_value = {
                "cpu_thermal": [MagicMock(current=55.0)]
            }

            resp = await client.get("/system/stats")

        data = resp.json()
        assert isinstance(data["cpu_percent"], float)
        assert isinstance(data["memory_used"], int)
        assert isinstance(data["memory_total"], int)
        assert isinstance(data["disk_used"], int)
        assert isinstance(data["disk_total"], int)
        assert isinstance(data["cpu_temp"], float)
