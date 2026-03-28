"""Tests for systemd service management endpoints in the Pragati RPi Agent.

Covers:
  - POST /systemd/services/{name}/{action} (start/stop/enable/disable/restart)
  - GET /systemd/services/{name}/logs

Uses the same fixtures and patterns as test_agent.py and test_agent_motor_rosbag.py.
All subprocess calls are mocked — no systemd or journalctl required.
"""

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
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as c:
        yield c


@pytest_asyncio.fixture
async def auth_client(app_with_auth):
    transport = ASGITransport(app=app_with_auth)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as c:
        yield c


AUTH_HEADER = {"X-API-Key": "test-secret-key"}


# ---------------------------------------------------------------------------
# Helpers for subprocess mock returns
# ---------------------------------------------------------------------------


def _mock_subprocess_ok(stdout="", stderr=""):
    """Return a MagicMock resembling a successful subprocess.run result."""
    return MagicMock(returncode=0, stdout=stdout, stderr=stderr)


def _mock_subprocess_fail(stdout="", stderr="error"):
    """Return a MagicMock resembling a failed subprocess.run result."""
    return MagicMock(returncode=1, stdout=stdout, stderr=stderr)


# ===================================================================
# Service Management — POST /systemd/services/{name}/{action}
# ===================================================================


class TestServiceManagement:
    """Tests for start/stop/enable/disable/restart actions on systemd services."""

    # -- Happy path: each valid action on an allowed service ---------------

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_service_start_success(self, mock_run, client):
        """POST /systemd/services/arm_launch/start returns 200 with started status."""
        mock_run.return_value = _mock_subprocess_ok()
        resp = await client.post("/systemd/services/arm_launch/start")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "started"
        assert data["service"] == "arm_launch"

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_service_stop_success(self, mock_run, client):
        """POST /systemd/services/arm_launch/stop returns 200 with stopped status."""
        mock_run.return_value = _mock_subprocess_ok()
        resp = await client.post("/systemd/services/arm_launch/stop")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "stopped"
        assert data["service"] == "arm_launch"

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_service_enable_success(self, mock_run, client):
        """POST /systemd/services/arm_launch/enable returns 200 with enabled status."""
        mock_run.return_value = _mock_subprocess_ok()
        resp = await client.post("/systemd/services/arm_launch/enable")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "enabled"
        assert data["service"] == "arm_launch"

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_service_disable_success(self, mock_run, client):
        """POST /systemd/services/arm_launch/disable returns 200 with disabled status."""
        mock_run.return_value = _mock_subprocess_ok()
        resp = await client.post("/systemd/services/arm_launch/disable")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "disabled"
        assert data["service"] == "arm_launch"

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_service_restart_success(self, mock_run, client):
        """POST /systemd/services/arm_launch/restart returns 200 with restarted."""
        mock_run.return_value = _mock_subprocess_ok()
        resp = await client.post("/systemd/services/arm_launch/restart")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "restarted"
        assert data["service"] == "arm_launch"

    # -- All allowed services should be accepted --------------------------

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_service_action_pragati_dashboard(self, mock_run, client):
        """pragati-dashboard is in the allowed list."""
        mock_run.return_value = _mock_subprocess_ok()
        resp = await client.post("/systemd/services/pragati-dashboard/start")
        assert resp.status_code == 200
        assert resp.json()["service"] == "pragati-dashboard"

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_service_action_pragati_agent(self, mock_run, client):
        """pragati-agent is in the allowed list."""
        mock_run.return_value = _mock_subprocess_ok()
        resp = await client.post("/systemd/services/pragati-agent/stop")
        assert resp.status_code == 200
        assert resp.json()["service"] == "pragati-agent"

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_service_action_vehicle_launch(self, mock_run, client):
        """vehicle_launch is in the allowed list."""
        mock_run.return_value = _mock_subprocess_ok()
        resp = await client.post("/systemd/services/vehicle_launch/enable")
        assert resp.status_code == 200
        assert resp.json()["service"] == "vehicle_launch"

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_service_action_pigpiod(self, mock_run, client):
        """pigpiod is in the allowed list."""
        mock_run.return_value = _mock_subprocess_ok()
        resp = await client.post("/systemd/services/pigpiod/restart")
        assert resp.status_code == 200
        assert resp.json()["service"] == "pigpiod"

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_service_action_can_watchdog(self, mock_run, client):
        """can-watchdog@can0 is in the allowed list (template instance)."""
        mock_run.return_value = _mock_subprocess_ok()
        resp = await client.post("/systemd/services/can-watchdog@can0/start")
        assert resp.status_code == 200
        assert resp.json()["service"] == "can-watchdog@can0"

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_service_action_field_monitor(self, mock_run, client):
        """field-monitor is in the allowed list."""
        mock_run.return_value = _mock_subprocess_ok()
        resp = await client.post("/systemd/services/field-monitor/stop")
        assert resp.status_code == 200
        assert resp.json()["service"] == "field-monitor"

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_service_action_boot_timing(self, mock_run, client):
        """boot_timing is in the allowed list."""
        mock_run.return_value = _mock_subprocess_ok()
        resp = await client.post("/systemd/services/boot_timing/disable")
        assert resp.status_code == 200
        assert resp.json()["service"] == "boot_timing"

    # -- Disallowed services -> 403 ----------------------------------------

    @pytest.mark.asyncio
    async def test_service_action_disallowed_service(self, client):
        """POST /systemd/services/sshd/start returns 403 for non-allowed service."""
        resp = await client.post("/systemd/services/sshd/start")
        assert resp.status_code == 403
        data = resp.json()
        assert data["error"] == "forbidden"
        assert (
            "sshd" in data["message"].lower()
            or "not allowed" in data["message"].lower()
        )

    @pytest.mark.asyncio
    async def test_service_action_disallowed_nginx(self, client):
        """POST /systemd/services/nginx/stop returns 403."""
        resp = await client.post("/systemd/services/nginx/stop")
        assert resp.status_code == 403
        assert resp.json()["error"] == "forbidden"

    @pytest.mark.asyncio
    async def test_service_action_disallowed_systemd_journald(self, client):
        """Critical system services must be blocked."""
        resp = await client.post("/systemd/services/systemd-journald/restart")
        assert resp.status_code == 403
        assert resp.json()["error"] == "forbidden"

    # -- Invalid actions -> 400 --------------------------------------------

    @pytest.mark.asyncio
    async def test_service_action_invalid_action(self, client):
        """POST /systemd/services/arm_launch/kill returns 400."""
        resp = await client.post("/systemd/services/arm_launch/kill")
        assert resp.status_code == 400
        data = resp.json()
        assert data["error"] in ("invalid_action", "bad_request")
        assert "kill" in data["message"].lower() or "allowed" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_service_action_invalid_action_reload(self, client):
        """reload is not in the allowed actions set."""
        resp = await client.post("/systemd/services/arm_launch/reload")
        assert resp.status_code == 400
        assert resp.json()["error"] in ("invalid_action", "bad_request")

    @pytest.mark.asyncio
    async def test_service_action_invalid_action_status(self, client):
        """status is not in the allowed actions set (it's a GET concept)."""
        resp = await client.post("/systemd/services/arm_launch/status")
        assert resp.status_code == 400
        assert resp.json()["error"] in ("invalid_action", "bad_request")

    # -- Auth: requires auth when API key is configured --------------------

    @pytest.mark.asyncio
    async def test_service_action_requires_auth(self, auth_client):
        """POST without X-API-Key returns 401 when auth is enabled."""
        resp = await auth_client.post("/systemd/services/arm_launch/start")
        assert resp.status_code == 401
        assert resp.json()["error"] == "unauthorized"

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_service_action_with_auth(self, mock_run, auth_client):
        """POST with correct X-API-Key returns 200."""
        mock_run.return_value = _mock_subprocess_ok()
        resp = await auth_client.post(
            "/systemd/services/arm_launch/start",
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "started"
        assert data["service"] == "arm_launch"

    @pytest.mark.asyncio
    async def test_service_action_wrong_auth_key(self, auth_client):
        """POST with wrong X-API-Key returns 401."""
        resp = await auth_client.post(
            "/systemd/services/arm_launch/start",
            headers={"X-API-Key": "wrong-key"},
        )
        assert resp.status_code == 401

    # -- Subprocess failure -> 502 -----------------------------------------

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_service_action_subprocess_failure(self, mock_run, client):
        """subprocess.run returns rc=1 -> 502 with stderr message."""
        mock_run.return_value = _mock_subprocess_fail(
            stderr="Failed to start arm_launch.service: Unit not found."
        )
        resp = await client.post("/systemd/services/arm_launch/start")
        assert resp.status_code == 502
        data = resp.json()
        assert data["error"] == "systemctl_failed"
        assert (
            "arm_launch" in data.get("message", "")
            or "not found" in data.get("message", "").lower()
        )

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_service_action_subprocess_failure_stop(self, mock_run, client):
        """Stop failure also returns 502."""
        mock_run.return_value = _mock_subprocess_fail(
            stderr="Failed to stop arm_launch.service"
        )
        resp = await client.post("/systemd/services/arm_launch/stop")
        assert resp.status_code == 502
        data = resp.json()
        assert data["error"] == "systemctl_failed"

    # -- Verify correct systemctl command is called ------------------------

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_service_action_calls_systemctl_correctly(self, mock_run, client):
        """Verify the subprocess.run call uses correct systemctl arguments."""
        mock_run.return_value = _mock_subprocess_ok()
        await client.post("/systemd/services/arm_launch/start")
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        cmd = call_args[0][0] if call_args[0] else call_args[1].get("args", [])
        assert cmd[0] == "systemctl"
        assert "start" in cmd
        assert "arm_launch" in cmd

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_service_enable_calls_systemctl_enable(self, mock_run, client):
        """Verify enable action uses 'systemctl enable'."""
        mock_run.return_value = _mock_subprocess_ok()
        await client.post("/systemd/services/pragati-dashboard/enable")
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        cmd = call_args[0][0] if call_args[0] else call_args[1].get("args", [])
        assert cmd[0] == "systemctl"
        assert "enable" in cmd
        assert "pragati-dashboard" in cmd


# ===================================================================
# Service Logs — GET /systemd/services/{name}/logs
# ===================================================================


class TestServiceLogs:
    """Tests for the journalctl log retrieval endpoint."""

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_service_logs_success(self, mock_run, client):
        """GET /systemd/services/arm_launch/logs returns JSON with log lines."""
        log_output = (
            "2026-03-09T10:00:01+0000 arm_launch[1234]: Node started\n"
            "2026-03-09T10:00:02+0000 arm_launch[1234]: Connecting to CAN bus\n"
            "2026-03-09T10:00:03+0000 arm_launch[1234]: Ready\n"
        )
        mock_run.return_value = _mock_subprocess_ok(stdout=log_output)
        resp = await client.get("/systemd/services/arm_launch/logs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "arm_launch"
        assert "logs" in data
        assert isinstance(data["logs"], list)
        assert len(data["logs"]) == 3
        assert "Node started" in data["logs"][0]
        assert "Ready" in data["logs"][2]

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_service_logs_default_lines(self, mock_run, client):
        """Default lines parameter is 100."""
        mock_run.return_value = _mock_subprocess_ok(stdout="line1\n")
        resp = await client.get("/systemd/services/arm_launch/logs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["lines"] == 100
        # Verify journalctl was called with -n 100
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        cmd = call_args[0][0] if call_args[0] else call_args[1].get("args", [])
        assert "-n" in cmd
        n_idx = cmd.index("-n")
        assert cmd[n_idx + 1] == "100"

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_service_logs_custom_lines(self, mock_run, client):
        """GET with lines=50 passes -n 50 to journalctl."""
        mock_run.return_value = _mock_subprocess_ok(stdout="line1\nline2\n")
        resp = await client.get(
            "/systemd/services/arm_launch/logs", params={"lines": 50}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["lines"] == 50
        # Verify journalctl was called with -n 50
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        cmd = call_args[0][0] if call_args[0] else call_args[1].get("args", [])
        assert "-n" in cmd
        n_idx = cmd.index("-n")
        assert cmd[n_idx + 1] == "50"

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_service_logs_uses_journalctl(self, mock_run, client):
        """Verify the subprocess call uses journalctl with correct arguments."""
        mock_run.return_value = _mock_subprocess_ok(stdout="")
        await client.get("/systemd/services/arm_launch/logs", params={"lines": 25})
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        cmd = call_args[0][0] if call_args[0] else call_args[1].get("args", [])
        assert cmd[0] == "journalctl"
        assert "-u" in cmd
        # The -u argument should reference the service name with .service suffix
        u_idx = cmd.index("-u")
        assert "arm_launch" in cmd[u_idx + 1]
        assert "--no-pager" in cmd
        assert "--output=short-iso" in cmd

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_service_logs_empty_output(self, mock_run, client):
        """Empty journalctl output returns empty logs list."""
        mock_run.return_value = _mock_subprocess_ok(stdout="")
        resp = await client.get("/systemd/services/arm_launch/logs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["logs"] == []

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_service_logs_strips_empty_lines(self, mock_run, client):
        """Blank lines in journalctl output are filtered out."""
        mock_run.return_value = _mock_subprocess_ok(stdout="line1\n\n\nline2\n\n")
        resp = await client.get("/systemd/services/arm_launch/logs")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["logs"]) == 2
        assert data["logs"][0] == "line1"
        assert data["logs"][1] == "line2"

    # -- Disallowed services -> 403 ----------------------------------------

    @pytest.mark.asyncio
    async def test_service_logs_disallowed_service(self, client):
        """GET /systemd/services/sshd/logs returns 403 for non-allowed service."""
        resp = await client.get("/systemd/services/sshd/logs")
        assert resp.status_code == 403
        data = resp.json()
        assert data["error"] == "forbidden"

    @pytest.mark.asyncio
    async def test_service_logs_disallowed_nginx(self, client):
        """GET /systemd/services/nginx/logs returns 403."""
        resp = await client.get("/systemd/services/nginx/logs")
        assert resp.status_code == 403
        assert resp.json()["error"] == "forbidden"

    # -- Subprocess failure ------------------------------------------------

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_service_logs_subprocess_failure(self, mock_run, client):
        """journalctl returns rc=1 -> error response."""
        mock_run.return_value = _mock_subprocess_fail(stderr="No journal files found")
        resp = await client.get("/systemd/services/arm_launch/logs")
        assert resp.status_code == 502
        data = resp.json()
        assert data["error"] == "journalctl_failed"

    # -- All allowed services can fetch logs --------------------------------

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_service_logs_pragati_dashboard(self, mock_run, client):
        """pragati-dashboard logs are accessible."""
        mock_run.return_value = _mock_subprocess_ok(stdout="log line\n")
        resp = await client.get("/systemd/services/pragati-dashboard/logs")
        assert resp.status_code == 200
        assert resp.json()["service"] == "pragati-dashboard"

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_service_logs_can_watchdog(self, mock_run, client):
        """can-watchdog@can0 logs are accessible (template instance)."""
        mock_run.return_value = _mock_subprocess_ok(stdout="watchdog ok\n")
        resp = await client.get("/systemd/services/can-watchdog@can0/logs")
        assert resp.status_code == 200
        assert resp.json()["service"] == "can-watchdog@can0"

    # -- Logs endpoint is GET, so no auth required (read-only) -------------

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_service_logs_no_auth_needed_for_get(self, mock_run, auth_client):
        """GET requests don't require auth (only POST/PUT/DELETE/PATCH do)."""
        mock_run.return_value = _mock_subprocess_ok(stdout="log line\n")
        resp = await auth_client.get("/systemd/services/arm_launch/logs")
        assert resp.status_code == 200

    # -- Lines parameter validation ----------------------------------------

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_service_logs_lines_param_one(self, mock_run, client):
        """lines=1 is valid and passed through."""
        mock_run.return_value = _mock_subprocess_ok(stdout="single line\n")
        resp = await client.get(
            "/systemd/services/arm_launch/logs", params={"lines": 1}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["lines"] == 1

    @pytest.mark.asyncio
    @patch(f"{AGENT_MODULE}.subprocess.run")
    async def test_service_logs_lines_param_large(self, mock_run, client):
        """lines=1000 is valid and passed through."""
        mock_run.return_value = _mock_subprocess_ok(stdout="line\n")
        resp = await client.get(
            "/systemd/services/arm_launch/logs", params={"lines": 1000}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["lines"] == 1000


# ===================================================================
# System Control — POST /system/reboot, POST /system/shutdown
# ===================================================================


class TestSystemControl:
    """Tests for POST /system/reboot and POST /system/shutdown."""

    @pytest.mark.asyncio
    async def test_reboot_success(self, client):
        """Reboot with correct token succeeds."""
        with patch(f"{AGENT_MODULE}.subprocess.Popen") as mock_popen:
            resp = await client.post("/system/reboot", json={"token": "REBOOT"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "rebooting"
        mock_popen.assert_called_once()
        # Verify the command used
        args = mock_popen.call_args[0][0]
        assert "reboot" in args

    @pytest.mark.asyncio
    async def test_reboot_wrong_token(self, client):
        """Reboot with wrong token returns 403."""
        resp = await client.post("/system/reboot", json={"token": "wrong"})
        assert resp.status_code == 403
        assert resp.json()["error"] == "forbidden"

    @pytest.mark.asyncio
    async def test_reboot_missing_token(self, client):
        """Reboot with no token returns 422 or 403."""
        resp = await client.post("/system/reboot", json={})
        assert resp.status_code in (403, 422)

    @pytest.mark.asyncio
    async def test_reboot_requires_auth(self, auth_client):
        """Reboot without API key returns 401."""
        resp = await auth_client.post("/system/reboot", json={"token": "REBOOT"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_reboot_with_auth(self, auth_client):
        """Reboot with API key + correct token succeeds."""
        with patch(f"{AGENT_MODULE}.subprocess.Popen"):
            resp = await auth_client.post(
                "/system/reboot",
                json={"token": "REBOOT"},
                headers=AUTH_HEADER,
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_shutdown_success(self, client):
        """Shutdown with correct token succeeds."""
        with patch(f"{AGENT_MODULE}.subprocess.Popen") as mock_popen:
            resp = await client.post("/system/shutdown", json={"token": "SHUTDOWN"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "shutting_down"
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert "shutdown" in " ".join(args)

    @pytest.mark.asyncio
    async def test_shutdown_wrong_token(self, client):
        """Shutdown with wrong token returns 403."""
        resp = await client.post("/system/shutdown", json={"token": "wrong"})
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_shutdown_missing_token(self, client):
        """Shutdown with no token returns 403 or 422."""
        resp = await client.post("/system/shutdown", json={})
        assert resp.status_code in (403, 422)

    @pytest.mark.asyncio
    async def test_shutdown_requires_auth(self, auth_client):
        """Shutdown without API key returns 401."""
        resp = await auth_client.post("/system/shutdown", json={"token": "SHUTDOWN"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_shutdown_with_auth(self, auth_client):
        """Shutdown with API key + correct token succeeds."""
        with patch(f"{AGENT_MODULE}.subprocess.Popen"):
            resp = await auth_client.post(
                "/system/shutdown",
                json={"token": "SHUTDOWN"},
                headers=AUTH_HEADER,
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_reboot_token_case_sensitive(self, client):
        """Token is case-sensitive."""
        resp = await client.post("/system/reboot", json={"token": "reboot"})
        assert resp.status_code == 403


# ===================================================================
# Self-Protection — pragati-agent stop/disable warning
# ===================================================================


class TestSelfProtection:
    """Tests for self-protection when stopping/disabling pragati-agent."""

    @pytest.mark.asyncio
    async def test_stop_pragati_agent_includes_warning(self, client):
        """Stopping pragati-agent returns warning about remote management loss."""
        with patch(f"{AGENT_MODULE}.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            resp = await client.post("/systemd/services/pragati-agent/stop")
        assert resp.status_code == 200
        data = resp.json()
        assert "warning" in data
        assert (
            "remote" in data["warning"].lower()
            or "management" in data["warning"].lower()
        )

    @pytest.mark.asyncio
    async def test_disable_pragati_agent_includes_warning(self, client):
        """Disabling pragati-agent returns warning."""
        with patch(f"{AGENT_MODULE}.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            resp = await client.post("/systemd/services/pragati-agent/disable")
        assert resp.status_code == 200
        data = resp.json()
        assert "warning" in data

    @pytest.mark.asyncio
    async def test_start_pragati_agent_no_warning(self, client):
        """Starting pragati-agent does NOT include warning."""
        with patch(f"{AGENT_MODULE}.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            resp = await client.post("/systemd/services/pragati-agent/start")
        assert resp.status_code == 200
        data = resp.json()
        assert "warning" not in data
