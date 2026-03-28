"""Tests for the Pragati RPi Agent — lightweight FastAPI entity monitor.

TDD: This file is written FIRST. agent.py is implemented to make these pass.
Uses httpx.AsyncClient with ASGITransport for async FastAPI testing.
All system calls (psutil, subprocess, zeroconf) are mocked.
"""

import asyncio
import json
import os
import subprocess
from unittest.mock import MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

AGENT_MODULE = "rpi_agent.agent"


@pytest.fixture
def _clean_env(monkeypatch):
    """Ensure PRAGATI_AGENT_API_KEY is unset unless a test sets it."""
    monkeypatch.delenv("PRAGATI_AGENT_API_KEY", raising=False)


@pytest.fixture
def app(_clean_env):
    """Import a fresh app instance with auth disabled (no env key)."""
    from rpi_agent.agent import create_app

    return create_app()


@pytest.fixture
def app_with_auth(monkeypatch):
    """App with API-key auth enabled."""
    monkeypatch.setenv("PRAGATI_AGENT_API_KEY", "test-secret-key")
    from rpi_agent.agent import create_app

    return create_app()


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest_asyncio.fixture
async def auth_client(app_with_auth):
    transport = ASGITransport(app=app_with_auth)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


# ===================================================================
# 1.2 — Health endpoint
# ===================================================================


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_metrics(self, client):
        """GET /health returns CPU, memory, temp, disk, uptime, warnings."""
        with (
            patch(f"{AGENT_MODULE}.psutil") as mock_psutil,
            patch(f"{AGENT_MODULE}.time") as mock_time,
            patch(f"{AGENT_MODULE}.platform") as mock_platform,
        ):
            mock_psutil.cpu_percent.return_value = 42.5
            mock_psutil.virtual_memory.return_value = MagicMock(percent=65.3)
            temps = {"cpu_thermal": [MagicMock(current=55.0)]}
            mock_psutil.sensors_temperatures.return_value = temps
            mock_psutil.disk_usage.return_value = MagicMock(percent=38.1)
            mock_psutil.boot_time.return_value = 1000.0
            mock_time.time.return_value = 1120.0
            mock_platform.node.return_value = "pragati-arm-1"

            resp = await client.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["cpu_percent"] == 42.5
        assert data["memory_percent"] == 65.3
        assert data["temperature_c"] == 55.0
        assert data["disk_percent"] == 38.1
        assert data["uptime_seconds"] == 120.0
        assert data["warnings"] == []
        assert data["hostname"] == "pragati-arm-1"

    @pytest.mark.asyncio
    async def test_health_thermal_throttling_warning(self, client):
        """Warnings include thermal_throttling when temp > 80."""
        with (
            patch(f"{AGENT_MODULE}.psutil") as mock_psutil,
            patch(f"{AGENT_MODULE}.time") as mock_time,
        ):
            mock_psutil.cpu_percent.return_value = 90.0
            mock_psutil.virtual_memory.return_value = MagicMock(percent=80.0)
            temps = {"cpu_thermal": [MagicMock(current=85.0)]}
            mock_psutil.sensors_temperatures.return_value = temps
            mock_psutil.disk_usage.return_value = MagicMock(percent=50.0)
            mock_psutil.boot_time.return_value = 0.0
            mock_time.time.return_value = 100.0

            resp = await client.get("/health")

        data = resp.json()
        assert data["temperature_c"] == 85.0
        assert "thermal_throttling" in data["warnings"]

    @pytest.mark.asyncio
    async def test_health_no_temp_sensors(self, client):
        """When no temperature sensors exist, temperature_c is null."""
        with (
            patch(f"{AGENT_MODULE}.psutil") as mock_psutil,
            patch(f"{AGENT_MODULE}.time") as mock_time,
        ):
            mock_psutil.cpu_percent.return_value = 10.0
            mock_psutil.virtual_memory.return_value = MagicMock(percent=30.0)
            mock_psutil.sensors_temperatures.return_value = {}
            mock_psutil.disk_usage.return_value = MagicMock(percent=20.0)
            mock_psutil.boot_time.return_value = 0.0
            mock_time.time.return_value = 60.0

            resp = await client.get("/health")

        data = resp.json()
        assert data["temperature_c"] is None
        assert data["warnings"] == []


# ===================================================================
# 1.3 — ROS2 introspection
# ===================================================================


class TestRos2Introspection:
    """Tests for ROS2 CLI fallback path (dashboard unavailable)."""

    @pytest.mark.asyncio
    async def test_ros2_nodes_success(self, client):
        """GET /ros2/nodes parses ros2 node list output (CLI fallback)."""
        node_output = "/arm1/motion_controller\n/arm1/camera_driver\n"
        with (
            patch(f"{AGENT_MODULE}._query_local_dashboard", return_value=None),
            patch(f"{AGENT_MODULE}._run_ros2_cmd") as mock_cmd,
        ):
            mock_cmd.return_value = MagicMock(stdout=node_output)
            resp = await client.get("/ros2/nodes")

        assert resp.status_code == 200
        nodes = resp.json()
        assert len(nodes) == 2
        assert nodes[0]["name"] == "motion_controller"
        assert nodes[0]["namespace"] == "/arm1"

    @pytest.mark.asyncio
    async def test_ros2_nodes_unavailable(self, client):
        """Returns 503 when both dashboard and ros2 CLI fail."""
        with (
            patch(f"{AGENT_MODULE}._query_local_dashboard", return_value=None),
            patch(
                f"{AGENT_MODULE}._run_ros2_cmd",
                side_effect=FileNotFoundError("ros2 not found"),
            ),
        ):
            resp = await client.get("/ros2/nodes")

        assert resp.status_code == 503
        data = resp.json()
        assert data["error"] == "ros2_unavailable"

    @pytest.mark.asyncio
    async def test_ros2_topics_success(self, client):
        """GET /ros2/topics parses ros2 topic list -t output (CLI fallback)."""
        topic_output = (
            "/arm1/joint_states [sensor_msgs/msg/JointState]\n"
            "/arm1/cmd_vel [geometry_msgs/msg/Twist]\n"
        )
        with (
            patch(f"{AGENT_MODULE}._query_local_dashboard", return_value=None),
            patch(f"{AGENT_MODULE}._run_ros2_cmd") as mock_cmd,
        ):
            mock_cmd.return_value = MagicMock(stdout=topic_output)
            resp = await client.get("/ros2/topics")

        assert resp.status_code == 200
        topics = resp.json()
        assert len(topics) == 2
        assert topics[0]["name"] == "/arm1/joint_states"
        assert topics[0]["type"] == "sensor_msgs/msg/JointState"

    @pytest.mark.asyncio
    async def test_ros2_topics_unavailable(self, client):
        with (
            patch(f"{AGENT_MODULE}._query_local_dashboard", return_value=None),
            patch(
                f"{AGENT_MODULE}._run_ros2_cmd",
                side_effect=FileNotFoundError(),
            ),
        ):
            resp = await client.get("/ros2/topics")
        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_ros2_services_success(self, client):
        """GET /ros2/services parses ros2 service list -t output (CLI fallback)."""
        svc_output = (
            "/arm1/set_mode [pragati_interfaces/srv/SetMode]\n"
            "/arm1/get_state [std_srvs/srv/Trigger]\n"
        )
        with (
            patch(f"{AGENT_MODULE}._query_local_dashboard", return_value=None),
            patch(f"{AGENT_MODULE}._run_ros2_cmd") as mock_cmd,
        ):
            mock_cmd.return_value = MagicMock(stdout=svc_output)
            resp = await client.get("/ros2/services")

        assert resp.status_code == 200
        services = resp.json()
        assert len(services) == 2
        assert services[0]["name"] == "/arm1/set_mode"
        assert services[0]["type"] == "pragati_interfaces/srv/SetMode"

    @pytest.mark.asyncio
    async def test_ros2_services_unavailable(self, client):
        with (
            patch(f"{AGENT_MODULE}._query_local_dashboard", return_value=None),
            patch(
                f"{AGENT_MODULE}._run_ros2_cmd",
                side_effect=FileNotFoundError(),
            ),
        ):
            resp = await client.get("/ros2/services")
        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_ros2_nodes_nonzero_exit(self, client):
        """Non-zero exit code from ros2 CLI treated as unavailable."""
        with (
            patch(f"{AGENT_MODULE}._query_local_dashboard", return_value=None),
            patch(
                f"{AGENT_MODULE}._run_ros2_cmd",
                side_effect=RuntimeError("non-zero exit"),
            ),
        ):
            resp = await client.get("/ros2/nodes")
        assert resp.status_code == 503


# ===================================================================
# 1.4 — Systemd management
# ===================================================================


class TestSystemdManagement:
    @pytest.mark.asyncio
    async def test_list_services(self, client):
        """GET /systemd/services lists all ALLOWED_SERVICES."""
        show_output = "ActiveState=active\nSubState=running\nDescription=Pragati Agent\n"
        with patch(f"{AGENT_MODULE}.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=show_output)
            resp = await client.get("/systemd/services")

        assert resp.status_code == 200
        services = resp.json()
        assert len(services) == 8  # expanded ALLOWED_SERVICES
        names = [s["name"] for s in services]
        assert "pragati-agent" in names
        assert "arm_launch" in names

    @pytest.mark.asyncio
    async def test_restart_pragati_service(self, client):
        """POST restart allowed for services in ALLOWED_SERVICES."""
        with patch(f"{AGENT_MODULE}.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")
            resp = await client.post("/systemd/services/pragati-agent/restart")

        assert resp.status_code == 200
        assert resp.json()["status"] == "restarted"

    @pytest.mark.asyncio
    async def test_restart_non_pragati_forbidden(self, client):
        """POST restart for non-pragati service returns 403."""
        resp = await client.post("/systemd/services/nginx/restart")
        assert resp.status_code == 403
        assert resp.json()["error"] == "forbidden"


# ===================================================================
# 1.5 — Log streaming (SSE)
# ===================================================================


class TestLogStreaming:
    @pytest.mark.asyncio
    async def test_log_stream_returns_sse(self, client):
        """GET /logs/stream returns text/event-stream with journal data."""
        fake_lines = [
            json.dumps({"MESSAGE": "line1", "__REALTIME_TIMESTAMP": "1000"}) + "\n",
            json.dumps({"MESSAGE": "line2", "__REALTIME_TIMESTAMP": "2000"}) + "\n",
        ]

        mock_proc = MagicMock()
        mock_proc.stdout.__iter__ = MagicMock(return_value=iter(fake_lines))
        mock_proc.poll.return_value = None
        mock_proc.kill = MagicMock()
        mock_proc.wait = MagicMock()

        with patch(f"{AGENT_MODULE}.subprocess.Popen") as mock_popen:
            mock_popen.return_value = mock_proc
            resp = await client.get("/logs/stream")

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        # Body should contain SSE formatted data lines
        body = resp.text
        assert "data:" in body


# ===================================================================
# 1.6 — Aggregate status
# ===================================================================


class TestAggregateStatus:
    @pytest.fixture(autouse=True)
    def _reset_status_cache(self):
        """Reset module-level status cache between tests."""
        from rpi_agent.agent import _ros2_backoff, _status_cache

        _status_cache["data"] = None
        _status_cache["timestamp"] = 0.0
        _ros2_backoff["consecutive_failures"] = 0
        _ros2_backoff["backoff_until"] = 0.0

    @pytest.mark.asyncio
    async def test_status_aggregates_health_and_ros2(self, client):
        """GET /status returns combined health + ros2 + systemd."""
        with (
            patch(f"{AGENT_MODULE}.psutil") as mock_psutil,
            patch(f"{AGENT_MODULE}.time") as mock_time,
            patch(
                f"{AGENT_MODULE}._ros2_node_list",
                return_value=[
                    {"name": "node1", "namespace": "/ns", "lifecycle_state": None},
                    {"name": "node2", "namespace": "/ns", "lifecycle_state": None},
                ],
            ),
            patch(
                f"{AGENT_MODULE}._ros2_topic_list",
                return_value=[
                    {
                        "name": "/t1",
                        "type": "std_msgs/msg/String",
                        "publisher_count": None,
                        "subscriber_count": None,
                    }
                ],
            ),
            patch(
                f"{AGENT_MODULE}._ros2_service_list",
                return_value=[{"name": "/s1", "type": "std_srvs/srv/Trigger"}],
            ),
            patch(f"{AGENT_MODULE}._systemd_list_services", return_value=[]),
        ):
            mock_psutil.cpu_percent.return_value = 50.0
            mock_psutil.virtual_memory.return_value = MagicMock(percent=60.0)
            mock_psutil.sensors_temperatures.return_value = {}
            mock_psutil.disk_usage.return_value = MagicMock(percent=40.0)
            mock_psutil.boot_time.return_value = 0.0
            mock_time.time.return_value = 300.0

            resp = await client.get("/status")

        assert resp.status_code == 200
        data = resp.json()
        assert "health" in data
        assert data["ros2"]["available"] is True
        assert data["ros2"]["node_count"] == 2
        assert data["ros2"]["topic_count"] == 1
        assert data["ros2"]["service_count"] == 1
        assert isinstance(data["systemd"], list)

    @pytest.mark.asyncio
    async def test_status_ros2_unavailable(self, client):
        """When ros2 introspection fails, ros2 section shows unavailable."""
        with (
            patch(f"{AGENT_MODULE}.psutil") as mock_psutil,
            patch(f"{AGENT_MODULE}.time") as mock_time,
            patch(
                f"{AGENT_MODULE}._ros2_node_list",
                side_effect=FileNotFoundError("ros2 not found"),
            ),
            patch(f"{AGENT_MODULE}._systemd_list_services", return_value=[]),
        ):
            mock_psutil.cpu_percent.return_value = 50.0
            mock_psutil.virtual_memory.return_value = MagicMock(percent=60.0)
            mock_psutil.sensors_temperatures.return_value = {}
            mock_psutil.disk_usage.return_value = MagicMock(percent=40.0)
            mock_psutil.boot_time.return_value = 0.0
            mock_time.time.return_value = 300.0

            resp = await client.get("/status")

        data = resp.json()
        assert data["ros2"]["available"] is False
        assert data["ros2"]["node_count"] is None

    @pytest.mark.asyncio
    async def test_ros2_backoff_max_caps_at_15_seconds(self, client):
        """ROS2 backoff max constant is reduced to 15 seconds."""
        from rpi_agent.agent import _ROS2_BACKOFF_MAX

        assert _ROS2_BACKOFF_MAX == 15.0

    @pytest.mark.asyncio
    async def test_status_cached_across_rapid_requests(self, client):
        """Rapid /status calls reuse cached response; ROS2 only queried once."""
        call_count = 0

        def fake_node_list():
            nonlocal call_count
            call_count += 1
            return [{"name": "node1", "namespace": "/", "lifecycle_state": None}]

        with (
            patch(f"{AGENT_MODULE}.psutil") as mock_psutil,
            patch(f"{AGENT_MODULE}.time") as mock_time,
            patch(f"{AGENT_MODULE}._ros2_node_list", side_effect=fake_node_list),
            patch(
                f"{AGENT_MODULE}._ros2_topic_list",
                return_value=[
                    {
                        "name": "/t1",
                        "type": "std_msgs/msg/String",
                        "publisher_count": None,
                        "subscriber_count": None,
                    }
                ],
            ),
            patch(
                f"{AGENT_MODULE}._ros2_service_list",
                return_value=[{"name": "/s1", "type": "std_srvs/srv/Trigger"}],
            ),
            patch(f"{AGENT_MODULE}._systemd_list_services", return_value=[]),
        ):
            mock_psutil.cpu_percent.return_value = 50.0
            mock_psutil.virtual_memory.return_value = MagicMock(percent=60.0)
            mock_psutil.sensors_temperatures.return_value = {}
            mock_psutil.disk_usage.return_value = MagicMock(percent=40.0)
            mock_psutil.boot_time.return_value = 0.0
            mock_time.time.return_value = 1000.0

            # First call — cache miss
            resp1 = await client.get("/status")
            assert resp1.status_code == 200
            first_call_count = call_count

            # Second call within TTL — should use cache
            resp2 = await client.get("/status")
            assert resp2.status_code == 200

        assert resp1.json() == resp2.json(), "Cached response should be identical"
        assert call_count == first_call_count, (
            f"_ros2_node_list called {call_count} times; "
            "expected 1 (second call should use cache)"
        )

    @pytest.mark.asyncio
    async def test_status_cache_expires_after_ttl(self, client):
        """Status cache TTL constant is reduced to 10 seconds."""
        from rpi_agent.agent import _STATUS_CACHE_TTL

        assert _STATUS_CACHE_TTL == 10.0


# ===================================================================
# 1.7 — API key auth middleware
# ===================================================================


class TestApiKeyAuth:
    @pytest.mark.asyncio
    async def test_auth_disabled_allows_all(self, client):
        """When no PRAGATI_AGENT_API_KEY set, all endpoints accessible."""
        with (
            patch(f"{AGENT_MODULE}.psutil") as mock_psutil,
            patch(f"{AGENT_MODULE}.time") as mock_time,
        ):
            mock_psutil.cpu_percent.return_value = 10.0
            mock_psutil.virtual_memory.return_value = MagicMock(percent=30.0)
            mock_psutil.sensors_temperatures.return_value = {}
            mock_psutil.disk_usage.return_value = MagicMock(percent=20.0)
            mock_psutil.boot_time.return_value = 0.0
            mock_time.time.return_value = 60.0
            resp = await client.get("/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_auth_enabled_rejects_missing_key(self, auth_client):
        """POST without X-API-Key returns 401 when auth enabled."""
        resp = await auth_client.post("/systemd/services/pragati-arm/restart")
        assert resp.status_code == 401
        assert resp.json()["error"] == "unauthorized"

    @pytest.mark.asyncio
    async def test_auth_enabled_rejects_invalid_key(self, auth_client):
        """POST with wrong X-API-Key returns 401."""
        resp = await auth_client.post(
            "/systemd/services/pragati-arm/restart",
            headers={"X-API-Key": "wrong-key"},
        )
        assert resp.status_code == 401
        assert resp.json()["error"] == "unauthorized"

    @pytest.mark.asyncio
    async def test_auth_enabled_accepts_valid_key(self, auth_client):
        """POST with correct X-API-Key succeeds."""
        with patch(f"{AGENT_MODULE}.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")
            resp = await auth_client.post(
                "/systemd/services/pragati-agent/restart",
                headers={"X-API-Key": "test-secret-key"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_health_exempt_from_auth(self, auth_client):
        """GET /health always accessible even with auth enabled."""
        with (
            patch(f"{AGENT_MODULE}.psutil") as mock_psutil,
            patch(f"{AGENT_MODULE}.time") as mock_time,
        ):
            mock_psutil.cpu_percent.return_value = 10.0
            mock_psutil.virtual_memory.return_value = MagicMock(percent=30.0)
            mock_psutil.sensors_temperatures.return_value = {}
            mock_psutil.disk_usage.return_value = MagicMock(percent=20.0)
            mock_psutil.boot_time.return_value = 0.0
            mock_time.time.return_value = 60.0
            resp = await auth_client.get("/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_requests_bypass_auth(self, auth_client):
        """GET (read-only) requests bypass auth even with key set."""
        with patch(f"{AGENT_MODULE}.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="pragati-arm.service loaded active running Arm\n",
            )
            resp = await auth_client.get("/systemd/services")
        assert resp.status_code == 200


# ===================================================================
# 1.9 — SSE connection limit
# ===================================================================


class TestSSEConnectionLimit:
    @pytest.mark.asyncio
    async def test_fourth_sse_connection_rejected(self, app):
        """4th concurrent SSE connection returns 429."""
        from rpi_agent.agent import _sse_connection_count

        # Simulate 3 active connections by setting the counter
        _sse_connection_count.reset(3)

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            resp = await c.get("/logs/stream")

        assert resp.status_code == 429
        data = resp.json()
        assert data["error"] == "too_many_streams"

        # Reset counter
        _sse_connection_count.reset(0)


# ===================================================================
# 1.11 — Global exception handler
# ===================================================================


class TestGlobalExceptionHandler:
    @pytest.mark.asyncio
    async def test_unhandled_exception_returns_500(self, client):
        """Unhandled exceptions return 500 with error payload."""
        with patch(
            f"{AGENT_MODULE}._collect_health",
            side_effect=RuntimeError("test boom"),
        ):
            resp = await client.get("/health")

        assert resp.status_code == 500
        data = resp.json()
        assert data["error"] == "internal_error"
        assert "test boom" in data["message"]


# ===================================================================
# 1.8 — mDNS advertisement (unit test — no network)
# ===================================================================


class TestMDNSAdvertisement:
    def test_mdns_service_info_created(self):
        """Verify mDNS registration builds correct ServiceInfo."""
        with (
            patch(f"{AGENT_MODULE}.Zeroconf") as mock_zc_cls,
            patch(f"{AGENT_MODULE}.ServiceInfo") as mock_si_cls,
            patch.dict(os.environ, {"PRAGATI_ENTITY_ID": "arm-1"}),
        ):
            from rpi_agent.agent import register_mdns, unregister_mdns

            mock_zc = MagicMock()
            mock_zc_cls.return_value = mock_zc

            register_mdns()
            mock_si_cls.assert_called_once()
            call_kwargs = mock_si_cls.call_args
            # Service type should be _pragati-agent._tcp.local.
            assert "_pragati-agent._tcp.local." in str(call_kwargs)
            mock_zc.register_service.assert_called_once()

            unregister_mdns()
            mock_zc.unregister_service.assert_called_once()
            mock_zc.close.assert_called_once()


# ===================================================================
# Task 1.7 — GET /ros2/nodes/{node_name} detail
# ===================================================================


class TestRos2NodeDetail:
    @pytest.mark.asyncio
    async def test_node_detail_success(self, client):
        """GET /ros2/nodes/{name} returns parsed node info."""
        node_info_output = (
            "/arm1/motion_controller\n"
            "  Subscribers:\n"
            "    /arm1/joint_commands: sensor_msgs/msg/JointState\n"
            "  Publishers:\n"
            "    /arm1/joint_states: sensor_msgs/msg/JointState\n"
            "    /rosout: rcl_interfaces/msg/Log\n"
            "  Service Servers:\n"
            "    /arm1/motion_controller/describe_parameters:"
            " rcl_interfaces/srv/DescribeParameters\n"
            "  Service Clients:\n"
            "\n"
        )
        with patch(f"{AGENT_MODULE}.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=node_info_output)
            resp = await client.get("/ros2/nodes/motion_controller")

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "motion_controller"
        assert len(data["publishers"]) == 2
        assert len(data["subscribers"]) == 1
        assert len(data["service_servers"]) == 1
        assert len(data["service_clients"]) == 0
        assert data["publishers"][0]["topic"] == "/arm1/joint_states"
        assert data["publishers"][0]["type"] == "sensor_msgs/msg/JointState"

    @pytest.mark.asyncio
    async def test_node_detail_not_found(self, client):
        """GET /ros2/nodes/{name} returns 404 for unknown node."""
        with patch(f"{AGENT_MODULE}.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="Unable to find node",
            )
            resp = await client.get("/ros2/nodes/nonexistent")

        assert resp.status_code == 404
        data = resp.json()
        assert data["error"] == "node_not_found"

    @pytest.mark.asyncio
    async def test_node_detail_ros2_unavailable(self, client):
        """GET /ros2/nodes/{name} returns 503 when ROS2 down."""
        with patch(f"{AGENT_MODULE}.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("ros2 not found")
            resp = await client.get("/ros2/nodes/some_node")

        assert resp.status_code == 503
        data = resp.json()
        assert data["error"] == "ros2_unavailable"


# ===================================================================
# Task 1.8 — POST /ros2/nodes/{node_name}/lifecycle/{transition}
# ===================================================================


class TestRos2LifecycleTransition:
    @pytest.mark.asyncio
    async def test_lifecycle_transition_success(self, client):
        """POST lifecycle transition returns success."""
        with patch(f"{AGENT_MODULE}.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Transitioning successful\n",
            )
            resp = await client.post("/ros2/nodes/motion_controller/lifecycle/activate")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["node"] == "motion_controller"
        assert data["transition"] == "activate"

    @pytest.mark.asyncio
    async def test_lifecycle_invalid_transition(self, client):
        """POST with invalid transition name returns 400."""
        resp = await client.post("/ros2/nodes/motion_controller/lifecycle/invalid_action")
        assert resp.status_code == 400
        data = resp.json()
        assert data["error"] == "invalid_transition"

    @pytest.mark.asyncio
    async def test_lifecycle_all_valid_transitions(self, client):
        """All five valid transitions are accepted."""
        valid_transitions = [
            "configure",
            "activate",
            "deactivate",
            "shutdown",
            "cleanup",
        ]
        for transition in valid_transitions:
            with patch(f"{AGENT_MODULE}.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="OK\n")
                resp = await client.post(f"/ros2/nodes/test_node/lifecycle/{transition}")
            assert resp.status_code == 200, f"transition '{transition}' should be valid"

    @pytest.mark.asyncio
    async def test_lifecycle_ros2_unavailable(self, client):
        """POST lifecycle returns 503 when ROS2 down."""
        with patch(f"{AGENT_MODULE}.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("ros2 not found")
            resp = await client.post("/ros2/nodes/motion_controller/lifecycle/activate")
        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_lifecycle_requires_auth(self, auth_client):
        """POST lifecycle requires API key when auth enabled."""
        resp = await auth_client.post("/ros2/nodes/motion_controller/lifecycle/activate")
        assert resp.status_code == 401


# ===================================================================
# Task 1.3 — GET /ros2/parameters grouped by node
# ===================================================================


class TestRos2Parameters:
    @pytest.mark.asyncio
    async def test_parameters_grouped_by_node(self, client):
        """GET /ros2/parameters returns params grouped by node."""

        def run_side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "param list" in cmd_str:
                return MagicMock(
                    returncode=0,
                    stdout="max_velocity\nuse_sim_time\n",
                )
            if "param get" in cmd_str:
                if "max_velocity" in cmd_str:
                    return MagicMock(
                        returncode=0,
                        stdout="Double value is: 1.5\n",
                    )
                if "use_sim_time" in cmd_str:
                    return MagicMock(
                        returncode=0,
                        stdout="Boolean value is: False\n",
                    )
            return MagicMock(returncode=0, stdout="")

        fake_nodes = [{"name": "motion_controller", "namespace": "/arm1", "lifecycle_state": None}]
        with (
            patch(f"{AGENT_MODULE}._ros2_node_list", return_value=fake_nodes),
            patch(f"{AGENT_MODULE}.subprocess.run") as mock_run,
        ):
            mock_run.side_effect = run_side_effect
            resp = await client.get("/ros2/parameters")

        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert len(data["nodes"]) == 1
        node = data["nodes"][0]
        assert node["name"] == "/arm1/motion_controller"
        assert len(node["parameters"]) == 2
        # Check param structure
        param_names = [p["name"] for p in node["parameters"]]
        assert "max_velocity" in param_names
        assert "use_sim_time" in param_names

    @pytest.mark.asyncio
    async def test_parameters_ros2_unavailable(self, client):
        """GET /ros2/parameters returns 503 when ROS2 down."""
        with patch(
            f"{AGENT_MODULE}._ros2_node_list",
            side_effect=FileNotFoundError("ros2 not found"),
        ):
            resp = await client.get("/ros2/parameters")

        assert resp.status_code == 503
        data = resp.json()
        assert data["error"] == "ros2_unavailable"


# ===================================================================
# Task 1.4 — PUT /ros2/parameters/{node_name}
# ===================================================================


class TestRos2ParameterSet:
    @pytest.mark.asyncio
    async def test_set_parameters_success(self, client):
        """PUT /ros2/parameters/{node} sets params and returns results."""
        with patch(f"{AGENT_MODULE}.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Set parameter successful\n",
            )
            resp = await client.put(
                "/ros2/parameters/motion_controller",
                json={
                    "params": [
                        {"name": "max_velocity", "value": "2.0"},
                        {"name": "use_sim_time", "value": "true"},
                    ]
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 2
        assert data["results"][0]["name"] == "max_velocity"
        assert data["results"][0]["success"] is True

    @pytest.mark.asyncio
    async def test_set_parameters_partial_failure(self, client):
        """PUT returns per-param success/failure."""
        call_count = 0

        def run_side_effect(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(returncode=0, stdout="Set parameter successful\n")
            else:
                return MagicMock(
                    returncode=1,
                    stdout="",
                    stderr="Parameter not found",
                )

        with patch(f"{AGENT_MODULE}.subprocess.run") as mock_run:
            mock_run.side_effect = run_side_effect
            resp = await client.put(
                "/ros2/parameters/motion_controller",
                json={
                    "params": [
                        {"name": "max_velocity", "value": "2.0"},
                        {"name": "bad_param", "value": "1"},
                    ]
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["results"][0]["success"] is True
        assert data["results"][1]["success"] is False

    @pytest.mark.asyncio
    async def test_set_parameters_ros2_unavailable(self, client):
        """PUT returns 503 when ROS2 down."""
        with patch(f"{AGENT_MODULE}.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("ros2 not found")
            resp = await client.put(
                "/ros2/parameters/motion_controller",
                json={"params": [{"name": "x", "value": "1"}]},
            )
        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_set_parameters_requires_auth(self, auth_client):
        """PUT parameters requires API key when auth enabled."""
        resp = await auth_client.put(
            "/ros2/parameters/motion_controller",
            json={"params": [{"name": "x", "value": "1"}]},
        )
        assert resp.status_code == 401


# ===================================================================
# Task 1.5 — GET /logs (log file listing)
# ===================================================================


class TestLogFileListing:
    @pytest.mark.asyncio
    async def test_log_listing_returns_files(self, client):
        """GET /logs returns list of log files + journald entry."""
        mock_stat = MagicMock()
        mock_stat.st_size = 12345
        mock_stat.st_mtime = 1700000000.0

        with (
            patch(f"{AGENT_MODULE}.os.environ", {"HOME": "/home/pi"}),
            patch(f"{AGENT_MODULE}.os.path.expanduser") as mock_expand,
            patch(f"{AGENT_MODULE}.os.path.isdir") as mock_isdir,
            patch(f"{AGENT_MODULE}.os.walk") as mock_walk,
            patch(f"{AGENT_MODULE}.os.stat") as mock_os_stat,
        ):
            mock_expand.side_effect = lambda p: p.replace("~", "/home/pi")
            mock_isdir.return_value = True
            mock_walk.return_value = [
                ("/home/pi/pragati_ros2/log", [], ["latest.log"]),
            ]
            mock_os_stat.return_value = mock_stat

            resp = await client.get("/logs")

        assert resp.status_code == 200
        data = resp.json()
        assert "files" in data
        # Should contain at least the file entry + journald entry
        names = [f["name"] for f in data["files"]]
        assert "latest.log" in names
        # Journald special entry
        journald = [f for f in data["files"] if f["path"] == "__journald__"]
        assert len(journald) == 1
        assert journald[0]["size_bytes"] is None

    @pytest.mark.asyncio
    async def test_log_listing_prevents_traversal(self, client):
        """Returned paths must not contain '..' components."""
        mock_stat = MagicMock()
        mock_stat.st_size = 100
        mock_stat.st_mtime = 1700000000.0

        with (
            patch(f"{AGENT_MODULE}.os.environ", {"HOME": "/home/pi"}),
            patch(f"{AGENT_MODULE}.os.path.expanduser") as mock_expand,
            patch(f"{AGENT_MODULE}.os.path.isdir") as mock_isdir,
            patch(f"{AGENT_MODULE}.os.walk") as mock_walk,
            patch(f"{AGENT_MODULE}.os.stat") as mock_os_stat,
        ):
            mock_expand.side_effect = lambda p: p.replace("~", "/home/pi")
            mock_isdir.return_value = True
            mock_walk.return_value = [
                ("/home/pi/pragati_ros2/log", [], ["test.log"]),
            ]
            mock_os_stat.return_value = mock_stat

            resp = await client.get("/logs")

        data = resp.json()
        for f in data["files"]:
            if f["path"] != "__journald__":
                assert ".." not in f["path"]

    @pytest.mark.asyncio
    async def test_log_listing_custom_env_dirs(self, client, monkeypatch):
        """PRAGATI_LOG_DIRS env var overrides defaults."""
        monkeypatch.setenv("PRAGATI_LOG_DIRS", "/var/log/pragati")

        mock_stat = MagicMock()
        mock_stat.st_size = 500
        mock_stat.st_mtime = 1700000000.0

        with (
            patch(f"{AGENT_MODULE}.os.path.isdir") as mock_isdir,
            patch(f"{AGENT_MODULE}.os.walk") as mock_walk,
            patch(f"{AGENT_MODULE}.os.stat") as mock_os_stat,
        ):
            mock_isdir.return_value = True
            mock_walk.return_value = [
                ("/var/log/pragati", [], ["arm.log"]),
            ]
            mock_os_stat.return_value = mock_stat

            resp = await client.get("/logs")

        assert resp.status_code == 200
        data = resp.json()
        names = [f["name"] for f in data["files"]]
        assert "arm.log" in names


# ===================================================================
# Task 1.6 — GET /logs/{log_name}/tail SSE
# ===================================================================


class TestLogTailSSE:
    @pytest.mark.asyncio
    async def test_log_tail_file_success(self, client):
        """GET /logs/{name}/tail streams file content as SSE."""
        fake_lines = ["line1\n", "line2\n"]
        mock_proc = MagicMock()
        mock_proc.stdout.__iter__ = MagicMock(return_value=iter(fake_lines))
        mock_proc.kill = MagicMock()
        mock_proc.wait = MagicMock()

        with (
            patch(
                f"{AGENT_MODULE}._resolve_log_path",
                return_value="/home/pi/pragati_ros2/log/test.log",
            ),
            patch(f"{AGENT_MODULE}.os.path.isfile", return_value=True),
            patch(f"{AGENT_MODULE}.subprocess.Popen") as mock_popen,
        ):
            mock_popen.return_value = mock_proc
            resp = await client.get("/logs/test.log/tail")

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        assert "data:" in resp.text

    @pytest.mark.asyncio
    async def test_log_tail_journald(self, client):
        """GET /logs/__journald__/tail streams journald as SSE."""
        fake_lines = ['{"MESSAGE":"hello"}\n']
        mock_proc = MagicMock()
        mock_proc.stdout.__iter__ = MagicMock(return_value=iter(fake_lines))
        mock_proc.kill = MagicMock()
        mock_proc.wait = MagicMock()

        with patch(f"{AGENT_MODULE}.subprocess.Popen") as mock_popen:
            mock_popen.return_value = mock_proc
            resp = await client.get("/logs/__journald__/tail")

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        assert "data:" in resp.text

    @pytest.mark.asyncio
    async def test_log_tail_not_found(self, client):
        """GET /logs/{name}/tail returns 404 for missing file."""
        with patch(f"{AGENT_MODULE}._resolve_log_path", return_value=None):
            resp = await client.get("/logs/nonexistent.log/tail")

        assert resp.status_code == 404
        data = resp.json()
        assert data["error"] == "log_not_found"

    @pytest.mark.asyncio
    async def test_log_tail_path_traversal_blocked(self, client):
        """GET /logs with '..' in name returns 400 invalid_path."""
        # Use %2e%2e (URL-encoded "..") so Starlette routes it to the
        # handler instead of rejecting at the routing level (which would
        # be 404 from the framework, not our handler).
        resp = await client.get("/logs/%2e%2e/tail")
        assert resp.status_code == 400
        data = resp.json()
        assert data["error"] == "invalid_path"

    @pytest.mark.asyncio
    async def test_log_tail_sse_limit(self, app):
        """Log tail counts against SSE limit."""
        from rpi_agent.agent import _sse_connection_count

        _sse_connection_count.reset(3)
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            resp = await c.get("/logs/test.log/tail")

        assert resp.status_code == 429
        _sse_connection_count.reset(0)


# ===================================================================
# Task 1.1 — GET /ros2/topics/{topic_name}/echo SSE
# ===================================================================


class TestTopicEchoSSE:
    @pytest.mark.asyncio
    async def test_topic_echo_success(self, client):
        """GET /ros2/topics/{name}/echo streams topic messages as SSE."""
        # Mock rclpy entirely since it's not available in test env
        mock_rclpy = MagicMock()
        mock_node = MagicMock()
        mock_rclpy.ok.return_value = True

        # Create a mock message
        mock_msg = MagicMock()
        mock_msg.get_fields_and_field_types.return_value = {"data": "string"}
        mock_msg.data = "hello"

        with (
            patch(f"{AGENT_MODULE}._ensure_rclpy", return_value=mock_node),
            patch(f"{AGENT_MODULE}._rclpy_available", True),
            patch(f"{AGENT_MODULE}._create_echo_generator") as mock_gen,
        ):
            # Return a generator that yields one SSE event then stops
            async def fake_generator(topic, hz):
                yield 'data: {"data": "hello"}\n\n'

            mock_gen.return_value = fake_generator("/joint_states", 10)
            resp = await client.get("/ros2/topics/joint_states/echo")

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

    @pytest.mark.asyncio
    async def test_topic_echo_hz_param(self, client):
        """Query param ?hz=N controls decimation rate."""
        with (
            patch(f"{AGENT_MODULE}._ensure_rclpy", return_value=MagicMock()),
            patch(f"{AGENT_MODULE}._rclpy_available", True),
            patch(f"{AGENT_MODULE}._create_echo_generator") as mock_gen,
        ):

            async def fake_gen(topic, hz):
                yield f'data: {{"hz": {hz}}}\n\n'

            mock_gen.return_value = fake_gen("/test", 5)
            resp = await client.get("/ros2/topics/test_topic/echo?hz=5")

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_topic_echo_hz_clamped_to_max(self, client):
        """Hz values above 30 are clamped to 30."""
        with (
            patch(f"{AGENT_MODULE}._ensure_rclpy", return_value=MagicMock()),
            patch(f"{AGENT_MODULE}._rclpy_available", True),
            patch(f"{AGENT_MODULE}._create_echo_generator") as mock_gen,
        ):

            async def fake_gen(topic, hz):
                yield f'data: {{"hz": {hz}}}\n\n'

            mock_gen.return_value = fake_gen("/test", 30)
            resp = await client.get("/ros2/topics/test_topic/echo?hz=100")

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_topic_echo_ros2_unavailable(self, client):
        """Returns 503 when rclpy is not available."""
        with (
            patch(f"{AGENT_MODULE}._ensure_rclpy", return_value=None),
            patch(f"{AGENT_MODULE}._rclpy_available", False),
        ):
            resp = await client.get("/ros2/topics/test_topic/echo")
        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_topic_echo_sse_limit(self, app):
        """Topic echo counts against SSE connection limit."""
        from rpi_agent.agent import _sse_connection_count

        _sse_connection_count.reset(3)
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            resp = await c.get("/ros2/topics/test_topic/echo")

        assert resp.status_code == 429
        _sse_connection_count.reset(0)


# ===================================================================
# Task 1.2 — POST /ros2/services/{service_name}/call
# ===================================================================


class TestRos2ServiceCall:
    @pytest.mark.asyncio
    async def test_service_call_success(self, client):
        """POST /ros2/services/{name}/call returns response."""
        with patch(f"{AGENT_MODULE}.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout='requester: making request: ...\n\nresponse:\nbool success True\nstring message "done"\n',
            )
            resp = await client.post(
                "/ros2/services/set_mode/call",
                json={
                    "type": "std_srvs/srv/Trigger",
                    "request": {},
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "response" in data
        assert "duration_ms" in data

    @pytest.mark.asyncio
    async def test_service_call_bad_request(self, client):
        """POST with missing 'type' returns 400."""
        resp = await client.post(
            "/ros2/services/set_mode/call",
            json={"request": {}},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["error"] == "bad_request"

    @pytest.mark.asyncio
    async def test_service_call_timeout(self, client):
        """POST returns 408 when service call times out."""
        with patch(f"{AGENT_MODULE}.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="ros2", timeout=5)
            resp = await client.post(
                "/ros2/services/set_mode/call",
                json={
                    "type": "std_srvs/srv/Trigger",
                    "request": {},
                },
            )
        assert resp.status_code == 408
        data = resp.json()
        assert data["error"] == "service_timeout"

    @pytest.mark.asyncio
    async def test_service_call_ros2_unavailable(self, client):
        """POST returns 503 when ROS2 not available."""
        with patch(f"{AGENT_MODULE}.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("ros2 not found")
            resp = await client.post(
                "/ros2/services/set_mode/call",
                json={
                    "type": "std_srvs/srv/Trigger",
                    "request": {},
                },
            )
        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_service_call_requires_auth(self, auth_client):
        """POST service call requires API key when auth enabled."""
        resp = await auth_client.post(
            "/ros2/services/set_mode/call",
            json={
                "type": "std_srvs/srv/Trigger",
                "request": {},
            },
        )
        assert resp.status_code == 401


# ===================================================================
# Task 1.9 — SSE limit enforcement across ALL endpoints
# ===================================================================


class TestSSELimitAllEndpoints:
    @pytest.mark.asyncio
    async def test_log_stream_at_limit_returns_429(self, app):
        """Original /logs/stream also returns 429 at limit."""
        from rpi_agent.agent import _sse_connection_count

        _sse_connection_count.reset(3)
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            resp = await c.get("/logs/stream")
        assert resp.status_code == 429
        _sse_connection_count.reset(0)

    @pytest.mark.asyncio
    async def test_topic_echo_at_limit_returns_429(self, app):
        """Topic echo returns 429 at SSE limit."""
        from rpi_agent.agent import _sse_connection_count

        _sse_connection_count.reset(3)
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            resp = await c.get("/ros2/topics/test_topic/echo")
        assert resp.status_code == 429
        _sse_connection_count.reset(0)

    @pytest.mark.asyncio
    async def test_log_tail_at_limit_returns_429(self, app):
        """Log tail returns 429 at SSE limit."""
        from rpi_agent.agent import _sse_connection_count

        _sse_connection_count.reset(3)
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            resp = await c.get("/logs/test.log/tail")
        assert resp.status_code == 429
        _sse_connection_count.reset(0)


# ===================================================================
# Journal per-unit SSE endpoint — GET /logs/journal/{unit}
# ===================================================================


class TestJournalUnitStream:
    @pytest.mark.asyncio
    async def test_allowed_unit_returns_sse(self, client):
        """GET /logs/journal/{unit} with allowed unit returns SSE stream."""
        fake_lines = [
            json.dumps(
                {
                    "MESSAGE": "Started service",
                    "PRIORITY": "6",
                    "_SYSTEMD_UNIT": "pragati-agent.service",
                    "__REALTIME_TIMESTAMP": "1710000000000000",
                }
            )
            + "\n",
        ]

        mock_proc = MagicMock()
        mock_proc.stdout.__iter__ = MagicMock(return_value=iter(fake_lines))
        mock_proc.poll.return_value = None
        mock_proc.kill = MagicMock()
        mock_proc.wait = MagicMock()

        with patch(f"{AGENT_MODULE}.subprocess.Popen") as mock_popen:
            mock_popen.return_value = mock_proc
            resp = await client.get("/logs/journal/pragati-agent")

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        body = resp.text
        assert "data:" in body
        assert "Started service" in body

        # Verify journalctl was called with the correct unit
        mock_popen.assert_called_once()
        popen_cmd = mock_popen.call_args[0][0]
        assert "-u" in popen_cmd
        assert "pragati-agent.service" in popen_cmd
        assert "--output=json" in popen_cmd
        assert "-f" in popen_cmd

    @pytest.mark.asyncio
    async def test_disallowed_unit_returns_403(self, client):
        """GET /logs/journal/{unit} with disallowed unit returns 403."""
        resp = await client.get("/logs/journal/sshd")

        assert resp.status_code == 403
        data = resp.json()
        assert data["error"] == "forbidden"
        assert "sshd" in data["message"]

    @pytest.mark.asyncio
    async def test_all_allowed_units_accepted(self, client):
        """All 6 allowed units are accepted (not 403)."""
        allowed = [
            "arm_launch",
            "vehicle_launch",
            "pragati-agent",
            "pragati-dashboard",
            "pigpiod",
            "can-watchdog@can0",
        ]
        mock_proc = MagicMock()
        mock_proc.stdout.__iter__ = MagicMock(return_value=iter([]))
        mock_proc.kill = MagicMock()
        mock_proc.wait = MagicMock()

        for unit in allowed:
            with patch(f"{AGENT_MODULE}.subprocess.Popen") as mock_popen:
                mock_popen.return_value = mock_proc
                resp = await client.get(f"/logs/journal/{unit}")
            assert resp.status_code == 200, f"Unit '{unit}' should be allowed"

    @pytest.mark.asyncio
    async def test_journal_sse_limit(self, app):
        """Journal endpoint returns 429 at SSE limit."""
        from rpi_agent.agent import _sse_connection_count

        _sse_connection_count.reset(3)
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            resp = await c.get("/logs/journal/pragati-agent")
        assert resp.status_code == 429
        _sse_connection_count.reset(0)


# ===================================================================
# Dashboard-first ROS2 introspection (local dashboard query)
# ===================================================================


class TestDashboardFirstRos2:
    """Tests for _query_local_dashboard and dashboard-first fallback in
    _ros2_node_list, _ros2_topic_list, _ros2_service_list."""

    def test_query_local_dashboard_nodes_success(self):
        """_query_local_dashboard('nodes') parses nested dict with string
        node names and converts to list of dicts with name/namespace/lifecycle_state."""
        from rpi_agent.agent import _query_local_dashboard

        # Actual API response format from entity_proxy.py: nested dict
        # with string node names (full paths like "/arm1/motion_controller")
        fake_response = json.dumps(
            {
                "entity_id": "local",
                "source": "local",
                "data": {
                    "nodes": [
                        "/arm1/motion_controller",
                        "/arm1/camera_driver",
                        "/motion_planner",
                    ]
                },
            }
        ).encode()

        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_response
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch(f"{AGENT_MODULE}.urlopen", return_value=mock_resp):
            result = _query_local_dashboard("nodes")

        assert result is not None
        assert len(result) == 3
        # Namespaced node: "/arm1/motion_controller" -> ns="/arm1", name="motion_controller"
        assert result[0]["name"] == "motion_controller"
        assert result[0]["namespace"] == "/arm1"
        assert result[0]["lifecycle_state"] is None
        # Another namespaced node
        assert result[1]["name"] == "camera_driver"
        assert result[1]["namespace"] == "/arm1"
        # Root-namespace node: "/motion_planner" -> ns="/", name="motion_planner"
        assert result[2]["name"] == "motion_planner"
        assert result[2]["namespace"] == "/"

    def test_query_local_dashboard_topics_success(self):
        """_query_local_dashboard('topics') parses nested dict with string
        topic names and converts to list of dicts with name/type keys."""
        from rpi_agent.agent import _query_local_dashboard

        fake_response = json.dumps(
            {
                "entity_id": "local",
                "source": "local",
                "data": {
                    "topics": [
                        "/arm1/joint_states",
                        "/cmd_vel",
                    ]
                },
            }
        ).encode()

        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_response
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch(f"{AGENT_MODULE}.urlopen", return_value=mock_resp):
            result = _query_local_dashboard("topics")

        assert result is not None
        assert len(result) == 2
        assert result[0]["name"] == "/arm1/joint_states"
        assert result[0]["type"] is None
        assert result[0]["publisher_count"] is None
        assert result[0]["subscriber_count"] is None

    def test_query_local_dashboard_services_success(self):
        """_query_local_dashboard('services') parses nested dict with string
        service names and converts to list of dicts with name/type keys."""
        from rpi_agent.agent import _query_local_dashboard

        fake_response = json.dumps(
            {
                "entity_id": "local",
                "source": "local",
                "data": {
                    "services": [
                        "/arm1/set_mode",
                        "/emergency_stop",
                    ]
                },
            }
        ).encode()

        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_response
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch(f"{AGENT_MODULE}.urlopen", return_value=mock_resp):
            result = _query_local_dashboard("services")

        assert result is not None
        assert len(result) == 2
        assert result[0]["name"] == "/arm1/set_mode"
        assert result[0]["type"] is None
        assert result[1]["name"] == "/emergency_stop"

    def test_query_local_dashboard_connection_refused(self):
        """_query_local_dashboard returns None when dashboard is down."""
        from rpi_agent.agent import _query_local_dashboard

        with patch(
            f"{AGENT_MODULE}.urlopen",
            side_effect=ConnectionError("Connection refused"),
        ):
            result = _query_local_dashboard("nodes")

        assert result is None

    def test_query_local_dashboard_timeout(self):
        """_query_local_dashboard returns None on timeout."""
        from rpi_agent.agent import _query_local_dashboard
        from urllib.error import URLError

        with patch(
            f"{AGENT_MODULE}.urlopen",
            side_effect=URLError("timed out"),
        ):
            result = _query_local_dashboard("nodes")

        assert result is None

    def test_query_local_dashboard_bad_json(self):
        """_query_local_dashboard returns None on malformed JSON."""
        from rpi_agent.agent import _query_local_dashboard

        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not json"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch(f"{AGENT_MODULE}.urlopen", return_value=mock_resp):
            result = _query_local_dashboard("nodes")

        assert result is None

    def test_query_local_dashboard_missing_data_key(self):
        """_query_local_dashboard returns None when 'data' key missing."""
        from rpi_agent.agent import _query_local_dashboard

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"error": "nope"}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch(f"{AGENT_MODULE}.urlopen", return_value=mock_resp):
            result = _query_local_dashboard("nodes")

        assert result is None

    def test_query_local_dashboard_missing_endpoint_key_in_data(self):
        """_query_local_dashboard returns None when data dict lacks the
        endpoint-specific key (e.g., 'nodes' key missing from data)."""
        from rpi_agent.agent import _query_local_dashboard

        fake_response = json.dumps(
            {
                "entity_id": "local",
                "source": "local",
                "data": {"topics": ["/some_topic"]},  # wrong key for "nodes" endpoint
            }
        ).encode()

        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_response
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch(f"{AGENT_MODULE}.urlopen", return_value=mock_resp):
            result = _query_local_dashboard("nodes")

        assert result is None

    @pytest.mark.asyncio
    async def test_node_list_uses_dashboard_when_available(self, client):
        """GET /ros2/nodes returns data from local dashboard API."""
        dashboard_data = [
            {"name": "motion_controller", "namespace": "/arm1", "lifecycle_state": None},
            {"name": "camera_driver", "namespace": "/arm1", "lifecycle_state": None},
        ]
        with patch(f"{AGENT_MODULE}._query_local_dashboard", return_value=dashboard_data):
            resp = await client.get("/ros2/nodes")

        assert resp.status_code == 200
        nodes = resp.json()
        assert len(nodes) == 2
        assert nodes[0]["name"] == "motion_controller"

    @pytest.mark.asyncio
    async def test_node_list_falls_back_to_cli(self, client):
        """GET /ros2/nodes falls back to CLI when dashboard unavailable."""
        with (
            patch(f"{AGENT_MODULE}._query_local_dashboard", return_value=None),
            patch(f"{AGENT_MODULE}._run_ros2_cmd") as mock_cmd,
        ):
            mock_cmd.return_value = MagicMock(
                stdout="/arm1/motion_controller\n/arm1/camera_driver\n",
                returncode=0,
            )
            resp = await client.get("/ros2/nodes")

        assert resp.status_code == 200
        nodes = resp.json()
        assert len(nodes) == 2
        assert nodes[0]["name"] == "motion_controller"

    @pytest.mark.asyncio
    async def test_topic_list_uses_dashboard_when_available(self, client):
        """GET /ros2/topics returns data from local dashboard API."""
        dashboard_data = [
            {
                "name": "/arm1/joint_states",
                "type": "sensor_msgs/msg/JointState",
                "publisher_count": 1,
                "subscriber_count": 2,
            },
        ]
        with patch(f"{AGENT_MODULE}._query_local_dashboard", return_value=dashboard_data):
            resp = await client.get("/ros2/topics")

        assert resp.status_code == 200
        topics = resp.json()
        assert len(topics) == 1
        assert topics[0]["name"] == "/arm1/joint_states"

    @pytest.mark.asyncio
    async def test_topic_list_falls_back_to_cli(self, client):
        """GET /ros2/topics falls back to CLI when dashboard unavailable."""
        with (
            patch(f"{AGENT_MODULE}._query_local_dashboard", return_value=None),
            patch(f"{AGENT_MODULE}._run_ros2_cmd") as mock_cmd,
        ):
            mock_cmd.return_value = MagicMock(
                stdout="/t1 [std_msgs/msg/String]\n",
                returncode=0,
            )
            resp = await client.get("/ros2/topics")

        assert resp.status_code == 200
        topics = resp.json()
        assert len(topics) == 1
        assert topics[0]["name"] == "/t1"

    @pytest.mark.asyncio
    async def test_service_list_uses_dashboard_when_available(self, client):
        """GET /ros2/services returns data from local dashboard API."""
        dashboard_data = [
            {"name": "/arm1/set_mode", "type": "pragati_interfaces/srv/SetMode"},
        ]
        with patch(f"{AGENT_MODULE}._query_local_dashboard", return_value=dashboard_data):
            resp = await client.get("/ros2/services")

        assert resp.status_code == 200
        services = resp.json()
        assert len(services) == 1
        assert services[0]["name"] == "/arm1/set_mode"

    @pytest.mark.asyncio
    async def test_service_list_falls_back_to_cli(self, client):
        """GET /ros2/services falls back to CLI when dashboard unavailable."""
        with (
            patch(f"{AGENT_MODULE}._query_local_dashboard", return_value=None),
            patch(f"{AGENT_MODULE}._run_ros2_cmd") as mock_cmd,
        ):
            mock_cmd.return_value = MagicMock(
                stdout="/s1 [std_srvs/srv/Trigger]\n",
                returncode=0,
            )
            resp = await client.get("/ros2/services")

        assert resp.status_code == 200
        services = resp.json()
        assert len(services) == 1
        assert services[0]["name"] == "/s1"

    @pytest.mark.asyncio
    async def test_both_dashboard_and_cli_fail(self, client):
        """GET /ros2/nodes returns 503 when both dashboard and CLI fail."""
        with (
            patch(f"{AGENT_MODULE}._query_local_dashboard", return_value=None),
            patch(
                f"{AGENT_MODULE}._run_ros2_cmd",
                side_effect=FileNotFoundError("ros2 not found"),
            ),
        ):
            resp = await client.get("/ros2/nodes")

        assert resp.status_code == 503
        assert resp.json()["error"] == "ros2_unavailable"

    def test_query_local_dashboard_uses_configured_port(self):
        """_query_local_dashboard uses _DASHBOARD_PORT for the URL."""
        from rpi_agent.agent import _query_local_dashboard

        with patch(f"{AGENT_MODULE}._DASHBOARD_PORT", 9999):
            with patch(f"{AGENT_MODULE}.urlopen") as mock_urlopen:
                mock_urlopen.side_effect = ConnectionError("test")
                _query_local_dashboard("nodes")

            call_args = mock_urlopen.call_args
            url = str(call_args[0][0])
            assert "9999" in url


# ---------------------------------------------------------------------------
# Tasks 1.1-1.4: Motor and camera diagnostic subscription tests
# ---------------------------------------------------------------------------


class TestMotorDiagnosticSubscription:
    """Tests for _on_motor_diagnostics callback (task 1.1)."""

    def setup_method(self):
        """Reset module-level state before each test."""
        import rpi_agent.agent as agent_mod

        agent_mod._motor_temperatures = None

    def _make_diag_array(self, entries):
        """Build a mock DiagnosticArray message.

        entries: list of (name, kv_list) where kv_list is [(key, value), ...]
        The hardware_id defaults to name (matching real motor node behavior
        where hardware_id = joint_name and name = "motor/" + joint_name).
        """
        msg = MagicMock()
        statuses = []
        for name, kvs in entries:
            status = MagicMock()
            status.name = name
            status.hardware_id = name  # agent prefers hardware_id as dict key
            kv_objects = []
            for k, v in kvs:
                kv = MagicMock()
                kv.key = k
                kv.value = v
                kv_objects.append(kv)
            status.values = kv_objects
            statuses.append(status)
        msg.status = statuses
        return msg

    def test_motor_temperatures_populated_from_callback(self):
        """Callback populates _motor_temperatures with float values per joint."""
        from rpi_agent.agent import _on_motor_diagnostics
        import rpi_agent.agent as agent_mod

        msg = self._make_diag_array(
            [
                ("joint1", [("temperature_c", "45.2")]),
                ("joint2", [("temperature_c", "50.1")]),
                ("joint3", [("temperature_c", "38.7")]),
            ]
        )
        _on_motor_diagnostics(msg)

        assert agent_mod._motor_temperatures == {
            "joint1": 45.2,
            "joint2": 50.1,
            "joint3": 38.7,
        }

    def test_motor_temperature_updated_on_new_message(self):
        """Second message updates joint1 temperature; other joints retain values."""
        from rpi_agent.agent import _on_motor_diagnostics
        import rpi_agent.agent as agent_mod

        # First message sets all three joints
        first_msg = self._make_diag_array(
            [
                ("joint1", [("temperature_c", "45.2")]),
                ("joint2", [("temperature_c", "50.1")]),
                ("joint3", [("temperature_c", "38.7")]),
            ]
        )
        _on_motor_diagnostics(first_msg)

        # Second message updates joint1 only
        second_msg = self._make_diag_array(
            [
                ("joint1", [("temperature_c", "47.5")]),
                ("joint2", [("temperature_c", "50.1")]),
                ("joint3", [("temperature_c", "38.7")]),
            ]
        )
        _on_motor_diagnostics(second_msg)

        assert agent_mod._motor_temperatures["joint1"] == pytest.approx(47.5)
        assert agent_mod._motor_temperatures["joint2"] == pytest.approx(50.1)
        assert agent_mod._motor_temperatures["joint3"] == pytest.approx(38.7)

    def test_invalid_temperature_value_skipped(self):
        """Non-numeric temperature_c values are silently ignored."""
        from rpi_agent.agent import _on_motor_diagnostics
        import rpi_agent.agent as agent_mod

        msg = self._make_diag_array(
            [
                ("joint1", [("temperature_c", "not-a-number")]),
                ("joint2", [("temperature_c", "50.1")]),
            ]
        )
        _on_motor_diagnostics(msg)

        assert "joint1" not in (agent_mod._motor_temperatures or {})
        assert agent_mod._motor_temperatures == {"joint2": 50.1}

    def test_empty_status_list_does_not_overwrite(self):
        """Message with no matching kv entries does not overwrite existing data."""
        from rpi_agent.agent import _on_motor_diagnostics
        import rpi_agent.agent as agent_mod

        agent_mod._motor_temperatures = {"joint1": 45.0}
        msg = self._make_diag_array([("joint1", [("other_key", "99.0")])])
        _on_motor_diagnostics(msg)

        # temps dict is empty, so _motor_temperatures should NOT be overwritten
        assert agent_mod._motor_temperatures == {"joint1": 45.0}


class TestCameraDiagnosticSubscription:
    """Tests for _on_camera_diagnostics callback (task 1.3)."""

    def setup_method(self):
        """Reset module-level state before each test."""
        import rpi_agent.agent as agent_mod

        agent_mod._camera_temperature_c = None

    def _make_diag_array(self, entries):
        """Build a mock DiagnosticArray message."""
        msg = MagicMock()
        statuses = []
        for name, kvs in entries:
            status = MagicMock()
            status.name = name
            kv_objects = []
            for k, v in kvs:
                kv = MagicMock()
                kv.key = k
                kv.value = v
                kv_objects.append(kv)
            status.values = kv_objects
            statuses.append(status)
        msg.status = statuses
        return msg

    def test_camera_temperature_from_oak_d_entry(self):
        """OAK-D camera status entry sets _camera_temperature_c."""
        from rpi_agent.agent import _on_camera_diagnostics
        import rpi_agent.agent as agent_mod

        msg = self._make_diag_array([("OAK-D Lite: camera_health", [("Temperature (C)", "52.3")])])
        _on_camera_diagnostics(msg)

        assert agent_mod._camera_temperature_c == pytest.approx(52.3)

    def test_non_camera_diagnostics_ignored(self):
        """Status entries unrelated to camera do not set _camera_temperature_c."""
        from rpi_agent.agent import _on_camera_diagnostics
        import rpi_agent.agent as agent_mod

        msg = self._make_diag_array([("cpu_monitor", [("Temperature (C)", "72.0")])])
        _on_camera_diagnostics(msg)

        assert agent_mod._camera_temperature_c is None

    def test_camera_keyword_matches_generic_camera_entry(self):
        """Status entries containing 'camera' in name set _camera_temperature_c."""
        from rpi_agent.agent import _on_camera_diagnostics
        import rpi_agent.agent as agent_mod

        msg = self._make_diag_array([("depth_camera_node", [("Temperature (C)", "48.0")])])
        _on_camera_diagnostics(msg)

        assert agent_mod._camera_temperature_c == pytest.approx(48.0)

    def test_invalid_camera_temperature_silently_ignored(self):
        """Non-numeric Temperature (C) values are silently skipped."""
        from rpi_agent.agent import _on_camera_diagnostics
        import rpi_agent.agent as agent_mod

        msg = self._make_diag_array([("OAK-D Lite: camera_health", [("Temperature (C)", "N/A")])])
        _on_camera_diagnostics(msg)

        assert agent_mod._camera_temperature_c is None

    def test_only_first_matching_entry_used(self):
        """Only the first camera-matching status entry is processed."""
        from rpi_agent.agent import _on_camera_diagnostics
        import rpi_agent.agent as agent_mod

        msg = self._make_diag_array(
            [
                ("OAK-D Lite: camera_health", [("Temperature (C)", "52.3")]),
                ("depth_camera_node", [("Temperature (C)", "99.9")]),
            ]
        )
        _on_camera_diagnostics(msg)

        assert agent_mod._camera_temperature_c == pytest.approx(52.3)


# ---------------------------------------------------------------------------
# Task 1.5: /status endpoint temperature fields tests
# ---------------------------------------------------------------------------


class TestStatusTemperatureFields:
    """Tests for temperature fields in GET /status response (task 1.5)."""

    @pytest.mark.asyncio
    async def test_status_includes_motor_temperatures_when_available(self, client):
        """GET /status includes motor_temperatures and camera_temperature_c in health."""
        motor_data = {"joint1": 45.2, "joint2": 50.1}
        camera_data = 52.3

        mock_health = {
            "cpu_percent": 10.0,
            "memory_percent": 40.0,
            "temperature_c": 55.0,
            "disk_percent": 20.0,
            "uptime_seconds": 3600.0,
            "warnings": [],
            "hostname": "test-rpi",
        }

        with (
            patch(f"{AGENT_MODULE}._motor_temperatures", motor_data),
            patch(f"{AGENT_MODULE}._camera_temperature_c", camera_data),
            patch(f"{AGENT_MODULE}._collect_health", return_value=mock_health),
            patch(f"{AGENT_MODULE}._ros2_node_list", return_value=[]),
            patch(f"{AGENT_MODULE}._ros2_topic_list", return_value=[]),
            patch(f"{AGENT_MODULE}._ros2_service_list", return_value=[]),
            patch(f"{AGENT_MODULE}._systemd_list_services", return_value=[]),
            patch(f"{AGENT_MODULE}._ensure_diagnostic_subscriptions"),
            patch(f"{AGENT_MODULE}._status_cache", {"data": None, "timestamp": 0.0}),
        ):
            resp = await client.get("/status")

        assert resp.status_code == 200
        body = resp.json()
        health = body["health"]
        assert health["motor_temperatures"] == motor_data
        assert health["camera_temperature_c"] == pytest.approx(camera_data)

    @pytest.mark.asyncio
    async def test_status_temperatures_null_when_no_data(self, client):
        """GET /status returns null for temperature fields when no ROS2 data."""
        mock_health = {
            "cpu_percent": 5.0,
            "memory_percent": 30.0,
            "temperature_c": None,
            "disk_percent": 15.0,
            "uptime_seconds": 1800.0,
            "warnings": [],
            "hostname": "test-rpi",
        }

        with (
            patch(f"{AGENT_MODULE}._motor_temperatures", None),
            patch(f"{AGENT_MODULE}._camera_temperature_c", None),
            patch(f"{AGENT_MODULE}._collect_health", return_value=mock_health),
            patch(f"{AGENT_MODULE}._ros2_node_list", return_value=[]),
            patch(f"{AGENT_MODULE}._ros2_topic_list", return_value=[]),
            patch(f"{AGENT_MODULE}._ros2_service_list", return_value=[]),
            patch(f"{AGENT_MODULE}._systemd_list_services", return_value=[]),
            patch(f"{AGENT_MODULE}._ensure_diagnostic_subscriptions"),
            patch(f"{AGENT_MODULE}._status_cache", {"data": None, "timestamp": 0.0}),
        ):
            resp = await client.get("/status")

        assert resp.status_code == 200
        body = resp.json()
        health = body["health"]
        assert health["motor_temperatures"] is None
        assert health["camera_temperature_c"] is None


# ---------------------------------------------------------------------------
# Tasks 4.1-4.4: Topic publish endpoint tests
# ---------------------------------------------------------------------------


class TestTopicPublishEndpoint:
    """Tests for POST /ros2/topics/{topic_name}/publish endpoint."""

    @pytest.mark.asyncio
    async def test_publish_bool_message(self, client):
        """Publishing a Bool message returns 200 with status published."""
        import rpi_agent.agent as agent_module

        agent_module._topic_publishers.clear()

        mock_publisher = MagicMock()
        mock_node = MagicMock()
        mock_node.create_publisher.return_value = mock_publisher

        with (
            patch(f"{AGENT_MODULE}._ensure_rclpy", return_value=mock_node),
            patch(f"{AGENT_MODULE}._rclpy_lock", new=__import__("threading").Lock()),
        ):
            mock_bool_class = MagicMock()
            mock_msg = MagicMock()
            mock_bool_class.return_value = mock_msg

            with patch("importlib.import_module") as mock_import:
                mock_module = MagicMock()
                mock_module.Bool = mock_bool_class
                mock_import.return_value = mock_module

                resp = await client.post(
                    "/ros2/topics/%2Fstart_switch%2Fcommand/publish",
                    json={"message_type": "std_msgs/msg/Bool", "data": {"data": True}},
                )

        assert resp.status_code == 200
        assert resp.json() == {"status": "published"}
        mock_publisher.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_invalid_message_type_returns_400(self, client):
        """A message_type that cannot be imported returns 400."""
        resp = await client.post(
            "/ros2/topics/%2Ftest_topic/publish",
            json={
                "message_type": "nonexistent_msgs/msg/Foo",
                "data": {},
            },
        )

        assert resp.status_code == 400
        body = resp.json()
        assert body["error"] == "invalid_message_type"
        assert "nonexistent_msgs/msg/Foo" in body["message"]

    @pytest.mark.asyncio
    async def test_publish_malformed_data_returns_400(self, client):
        """Data that causes setattr to raise returns 400."""
        import rpi_agent.agent as agent_module

        agent_module._topic_publishers.clear()

        mock_publisher = MagicMock()
        mock_node = MagicMock()
        mock_node.create_publisher.return_value = mock_publisher

        with (
            patch(f"{AGENT_MODULE}._ensure_rclpy", return_value=mock_node),
            patch(f"{AGENT_MODULE}._rclpy_lock", new=__import__("threading").Lock()),
        ):
            mock_bool_class = MagicMock()

            # Create a message instance that raises on any setattr
            mock_msg = MagicMock(spec=[])

            original_setattr = object.__setattr__

            def strict_setattr(obj, name, value):
                if name.startswith("_"):
                    original_setattr(obj, name, value)
                else:
                    raise AttributeError(f"field '{name}' does not exist on Bool")

            mock_bool_class.return_value = mock_msg

            with patch("importlib.import_module") as mock_import:
                mock_module = MagicMock()
                mock_module.Bool = mock_bool_class
                mock_import.return_value = mock_module

                with patch.object(type(mock_msg), "__setattr__", strict_setattr):
                    resp = await client.post(
                        "/ros2/topics/%2Ftest_topic/publish",
                        json={
                            "message_type": "std_msgs/msg/Bool",
                            "data": {"data": "not_a_bool"},
                        },
                    )

        assert resp.status_code == 400
        assert resp.json()["error"] == "bad_data"

    @pytest.mark.asyncio
    async def test_publisher_cached_on_second_publish(self, client):
        """create_publisher is called only once when publishing to the same topic twice."""
        import rpi_agent.agent as agent_module

        agent_module._topic_publishers.clear()

        mock_publisher = MagicMock()
        mock_node = MagicMock()
        mock_node.create_publisher.return_value = mock_publisher

        with (
            patch(f"{AGENT_MODULE}._ensure_rclpy", return_value=mock_node),
            patch(f"{AGENT_MODULE}._rclpy_lock", new=__import__("threading").Lock()),
        ):
            mock_bool_class = MagicMock()
            mock_bool_class.return_value = MagicMock()

            with patch("importlib.import_module") as mock_import:
                mock_module = MagicMock()
                mock_module.Bool = mock_bool_class
                mock_import.return_value = mock_module

                await client.post(
                    "/ros2/topics/%2Fcached_topic/publish",
                    json={"message_type": "std_msgs/msg/Bool", "data": {"data": True}},
                )
                await client.post(
                    "/ros2/topics/%2Fcached_topic/publish",
                    json={"message_type": "std_msgs/msg/Bool", "data": {"data": False}},
                )

        # Publisher should have been created only once; publish called twice
        mock_node.create_publisher.assert_called_once()
        assert mock_publisher.publish.call_count == 2


# ---------------------------------------------------------------------------
# _create_echo_generator — async subprocess + cleanup
# ---------------------------------------------------------------------------


class TestCreateEchoGenerator:
    """Verify _create_echo_generator uses async subprocess, not blocking Popen."""

    @pytest.mark.asyncio
    async def test_uses_async_subprocess(self):
        """Generator must use asyncio.create_subprocess_exec, not subprocess.Popen."""
        from rpi_agent.agent import _create_echo_generator

        mock_node = MagicMock()
        mock_proc = MagicMock()

        # Simulate async subprocess stdout readline
        call_count = 0

        async def _readline():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return b'data: true\n'
            return b""  # EOF

        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline = _readline
        mock_proc.returncode = None

        def _kill():
            pass

        async def _wait():
            mock_proc.returncode = 0

        mock_proc.kill = _kill
        mock_proc.wait = _wait

        with (
            patch(f"{AGENT_MODULE}._ensure_rclpy", return_value=mock_node),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_create,
        ):
            chunks = []
            async for chunk in _create_echo_generator("/test_topic", 10):
                chunks.append(chunk)

        # Must have called asyncio.create_subprocess_exec (not subprocess.Popen)
        mock_create.assert_called_once()
        call_args = mock_create.call_args
        # Should NOT include --once flag
        assert (
            "--once" not in call_args[0]
        ), "--once blocks waiting for a message; echo stream must be continuous"

    @pytest.mark.asyncio
    async def test_cleans_up_subprocess_on_exit(self):
        """Generator must kill and wait on subprocess in finally block."""
        from rpi_agent.agent import _create_echo_generator

        mock_node = MagicMock()
        mock_proc = MagicMock()
        killed = False
        waited = False

        async def _readline():
            return b""  # EOF immediately

        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline = _readline
        mock_proc.returncode = None  # still running

        def _kill():
            nonlocal killed
            killed = True

        async def _wait():
            nonlocal waited
            waited = True
            mock_proc.returncode = -9

        mock_proc.kill = _kill
        mock_proc.wait = _wait

        with (
            patch(f"{AGENT_MODULE}._ensure_rclpy", return_value=mock_node),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        ):
            async for _ in _create_echo_generator("/test_topic", 10):
                pass

        assert killed, "Subprocess must be killed on generator exit"
        assert waited, "Subprocess must be waited on after kill"

    @pytest.mark.asyncio
    async def test_does_not_block_event_loop(self):
        """Verify event loop is not blocked during echo — other coroutines can run."""
        from rpi_agent.agent import _create_echo_generator

        mock_node = MagicMock()
        event_loop_ran = False

        async def fake_create_subprocess(*args, **kwargs):
            proc = MagicMock()
            read_count = 0

            async def _readline():
                nonlocal read_count
                read_count += 1
                if read_count <= 2:
                    # Yield control so other coroutines can run
                    await asyncio.sleep(0)
                    return f'data: msg{read_count}\n'.encode()
                return b""

            proc.stdout = MagicMock()
            proc.stdout.readline = _readline
            proc.returncode = None

            def _kill():
                pass

            async def _wait():
                proc.returncode = -9

            proc.kill = _kill
            proc.wait = _wait
            return proc

        async def concurrent_task():
            nonlocal event_loop_ran
            event_loop_ran = True

        with (
            patch(f"{AGENT_MODULE}._ensure_rclpy", return_value=mock_node),
            patch("asyncio.create_subprocess_exec", side_effect=fake_create_subprocess),
        ):
            # Run echo generator and a concurrent task
            gen = _create_echo_generator("/test_topic", 10)
            task = asyncio.create_task(concurrent_task())
            async for _ in gen:
                pass
            await task

        assert event_loop_ran, "Event loop must not be blocked by echo generator"


# ===================================================================
# Diagnostics self-check endpoint
# ===================================================================


class TestDiagnosticsCheck:
    """Tests for GET /diagnostics/check — agent self-check endpoint."""

    @pytest.mark.asyncio
    async def test_all_checks_pass(self, client):
        """Happy path: rclpy active, sudo works, ROS2 nodes present, CAN up."""
        mock_node = MagicMock()
        mock_ros2_result = MagicMock(stdout="/arm1/controller\n/arm1/picker\n")

        with (
            patch(f"{AGENT_MODULE}._rclpy_available", True),
            patch(f"{AGENT_MODULE}._rclpy_node", mock_node),
            patch(f"{AGENT_MODULE}.subprocess") as mock_subproc,
            patch(f"{AGENT_MODULE}._run_ros2_cmd", return_value=mock_ros2_result),
            patch(f"{AGENT_MODULE}.time") as mock_time,
            patch(f"{AGENT_MODULE}.psutil") as mock_psutil,
            patch(
                "builtins.open",
                MagicMock(
                    return_value=MagicMock(
                        __enter__=MagicMock(
                            return_value=MagicMock(read=MagicMock(return_value="up\n"))
                        ),
                        __exit__=MagicMock(return_value=False),
                    )
                ),
            ),
        ):
            mock_subproc.run.return_value = MagicMock(returncode=0)
            mock_subproc.TimeoutExpired = subprocess.TimeoutExpired
            mock_time.time.return_value = 1200.0
            mock_psutil.boot_time.return_value = 1000.0

            resp = await client.get("/diagnostics/check")

        assert resp.status_code == 200
        data = resp.json()
        assert data["rclpy_available"] is True
        assert data["systemd_sudo"] is True
        assert data["ros2_node_count"] == 2
        assert data["can_bus_up"] is True
        assert data["uptime_seconds"] == pytest.approx(200.0, abs=1.0)

    @pytest.mark.asyncio
    async def test_rclpy_not_available(self, client):
        """rclpy_available is False when _rclpy_available flag is False."""
        mock_ros2_result = MagicMock(stdout="")

        with (
            patch(f"{AGENT_MODULE}._rclpy_available", False),
            patch(f"{AGENT_MODULE}._rclpy_node", None),
            patch(f"{AGENT_MODULE}.subprocess") as mock_subproc,
            patch(f"{AGENT_MODULE}._run_ros2_cmd", return_value=mock_ros2_result),
            patch(f"{AGENT_MODULE}.time") as mock_time,
            patch(f"{AGENT_MODULE}.psutil") as mock_psutil,
            patch(
                "builtins.open",
                MagicMock(
                    return_value=MagicMock(
                        __enter__=MagicMock(
                            return_value=MagicMock(read=MagicMock(return_value="down\n"))
                        ),
                        __exit__=MagicMock(return_value=False),
                    )
                ),
            ),
        ):
            mock_subproc.run.return_value = MagicMock(returncode=0)
            mock_subproc.TimeoutExpired = subprocess.TimeoutExpired
            mock_time.time.return_value = 1100.0
            mock_psutil.boot_time.return_value = 1000.0

            resp = await client.get("/diagnostics/check")

        assert resp.status_code == 200
        data = resp.json()
        assert data["rclpy_available"] is False

    @pytest.mark.asyncio
    async def test_systemd_sudo_fails(self, client):
        """systemd_sudo is False when sudo systemctl returns non-zero."""
        mock_ros2_result = MagicMock(stdout="")

        with (
            patch(f"{AGENT_MODULE}._rclpy_available", False),
            patch(f"{AGENT_MODULE}._rclpy_node", None),
            patch(f"{AGENT_MODULE}.subprocess") as mock_subproc,
            patch(f"{AGENT_MODULE}._run_ros2_cmd", return_value=mock_ros2_result),
            patch(f"{AGENT_MODULE}.time") as mock_time,
            patch(f"{AGENT_MODULE}.psutil") as mock_psutil,
            patch("builtins.open", MagicMock(side_effect=FileNotFoundError)),
        ):
            mock_subproc.run.return_value = MagicMock(returncode=1)
            mock_subproc.TimeoutExpired = subprocess.TimeoutExpired
            mock_time.time.return_value = 1100.0
            mock_psutil.boot_time.return_value = 1000.0

            resp = await client.get("/diagnostics/check")

        assert resp.status_code == 200
        data = resp.json()
        assert data["systemd_sudo"] is False

    @pytest.mark.asyncio
    async def test_systemd_sudo_timeout(self, client):
        """systemd_sudo is False when sudo systemctl times out."""
        mock_ros2_result = MagicMock(stdout="")

        with (
            patch(f"{AGENT_MODULE}._rclpy_available", False),
            patch(f"{AGENT_MODULE}._rclpy_node", None),
            patch(f"{AGENT_MODULE}.subprocess") as mock_subproc,
            patch(f"{AGENT_MODULE}._run_ros2_cmd", return_value=mock_ros2_result),
            patch(f"{AGENT_MODULE}.time") as mock_time,
            patch(f"{AGENT_MODULE}.psutil") as mock_psutil,
            patch("builtins.open", MagicMock(side_effect=FileNotFoundError)),
        ):
            mock_subproc.run.side_effect = subprocess.TimeoutExpired(["sudo"], 3.0)
            mock_subproc.TimeoutExpired = subprocess.TimeoutExpired
            mock_time.time.return_value = 1100.0
            mock_psutil.boot_time.return_value = 1000.0

            resp = await client.get("/diagnostics/check")

        assert resp.status_code == 200
        data = resp.json()
        assert data["systemd_sudo"] is False

    @pytest.mark.asyncio
    async def test_ros2_node_count_failure(self, client):
        """ros2_node_count is -1 when ros2 CLI fails."""
        with (
            patch(f"{AGENT_MODULE}._rclpy_available", False),
            patch(f"{AGENT_MODULE}._rclpy_node", None),
            patch(f"{AGENT_MODULE}.subprocess") as mock_subproc,
            patch(f"{AGENT_MODULE}._run_ros2_cmd", side_effect=RuntimeError("ros2 unavailable")),
            patch(f"{AGENT_MODULE}.time") as mock_time,
            patch(f"{AGENT_MODULE}.psutil") as mock_psutil,
            patch("builtins.open", MagicMock(side_effect=FileNotFoundError)),
        ):
            mock_subproc.run.return_value = MagicMock(returncode=0)
            mock_subproc.TimeoutExpired = subprocess.TimeoutExpired
            mock_time.time.return_value = 1100.0
            mock_psutil.boot_time.return_value = 1000.0

            resp = await client.get("/diagnostics/check")

        assert resp.status_code == 200
        data = resp.json()
        assert data["ros2_node_count"] == -1

    @pytest.mark.asyncio
    async def test_can_bus_not_present(self, client):
        """can_bus_up is None when /sys/class/net/can0/operstate does not exist."""
        mock_ros2_result = MagicMock(stdout="")

        with (
            patch(f"{AGENT_MODULE}._rclpy_available", False),
            patch(f"{AGENT_MODULE}._rclpy_node", None),
            patch(f"{AGENT_MODULE}.subprocess") as mock_subproc,
            patch(f"{AGENT_MODULE}._run_ros2_cmd", return_value=mock_ros2_result),
            patch(f"{AGENT_MODULE}.time") as mock_time,
            patch(f"{AGENT_MODULE}.psutil") as mock_psutil,
            patch("builtins.open", MagicMock(side_effect=FileNotFoundError)),
        ):
            mock_subproc.run.return_value = MagicMock(returncode=0)
            mock_subproc.TimeoutExpired = subprocess.TimeoutExpired
            mock_time.time.return_value = 1100.0
            mock_psutil.boot_time.return_value = 1000.0

            resp = await client.get("/diagnostics/check")

        assert resp.status_code == 200
        data = resp.json()
        assert data["can_bus_up"] is None

    @pytest.mark.asyncio
    async def test_can_bus_down(self, client):
        """can_bus_up is False when operstate is 'down'."""
        mock_ros2_result = MagicMock(stdout="")

        with (
            patch(f"{AGENT_MODULE}._rclpy_available", False),
            patch(f"{AGENT_MODULE}._rclpy_node", None),
            patch(f"{AGENT_MODULE}.subprocess") as mock_subproc,
            patch(f"{AGENT_MODULE}._run_ros2_cmd", return_value=mock_ros2_result),
            patch(f"{AGENT_MODULE}.time") as mock_time,
            patch(f"{AGENT_MODULE}.psutil") as mock_psutil,
            patch(
                "builtins.open",
                MagicMock(
                    return_value=MagicMock(
                        __enter__=MagicMock(
                            return_value=MagicMock(read=MagicMock(return_value="down\n"))
                        ),
                        __exit__=MagicMock(return_value=False),
                    )
                ),
            ),
        ):
            mock_subproc.run.return_value = MagicMock(returncode=0)
            mock_subproc.TimeoutExpired = subprocess.TimeoutExpired
            mock_time.time.return_value = 1100.0
            mock_psutil.boot_time.return_value = 1000.0

            resp = await client.get("/diagnostics/check")

        assert resp.status_code == 200
        data = resp.json()
        assert data["can_bus_up"] is False
