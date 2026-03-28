"""Tests for Systemd Service Management API (Tasks 5.1-5.2).

Validates:
- GET /api/systemd/services lists status of all allowed services
- POST /api/systemd/services/{name}/start calls systemctl start
- POST /api/systemd/services/{name}/stop calls systemctl stop
- POST /api/systemd/services/{name}/restart calls systemctl restart
- POST /api/systemd/services/{name}/enable enables auto-start
- POST /api/systemd/services/{name}/disable disables auto-start
- Disallowed service name returns 403
- GET /api/systemd/services/{name}/logs returns journal lines
- GET /api/systemd/services/{name}/logs respects ?lines= parameter
- GET /api/systemd/services/{name}/logs for disallowed service returns 403

All systemctl/journalctl calls are mocked via asyncio.create_subprocess_exec.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.systemd_api import systemd_router

# -----------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------

SYSTEMCTL_SHOW_OUTPUT = "ActiveState=active\n" "SubState=running\n" "UnitFileState=enabled\n"

SYSTEMCTL_SHOW_INACTIVE = "ActiveState=inactive\n" "SubState=dead\n" "UnitFileState=disabled\n"

SYSTEMCTL_SHOW_FAILED = "ActiveState=failed\n" "SubState=failed\n" "UnitFileState=enabled\n"


def _make_mock_process(stdout_text: str = "", returncode: int = 0):
    """Create a mock asyncio.Process with given stdout and returncode."""
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout_text.encode(), b""))
    proc.returncode = returncode
    return proc


def _make_mock_audit_logger():
    """Create a mock AuditLogger."""
    al = MagicMock()
    al.log = MagicMock()
    return al


# -----------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------


@pytest.fixture()
def app():
    """Create a test FastAPI app with the systemd router."""
    _app = FastAPI()
    _app.include_router(systemd_router)
    return _app


@pytest.fixture()
def client(app):
    return TestClient(app)


# -----------------------------------------------------------------
# Tests: GET /api/systemd/services (Task 5.1)
# -----------------------------------------------------------------


class TestListServices:
    """Tests for listing all managed service statuses."""

    @patch("backend.systemd_api.asyncio.create_subprocess_exec")
    def test_list_services_returns_all_allowed(self, mock_exec, client):
        """GET /api/systemd/services returns status for all allowed."""
        # Each service gets a systemctl show call
        mock_exec.return_value = _make_mock_process(SYSTEMCTL_SHOW_OUTPUT)

        resp = client.get("/api/systemd/services")

        assert resp.status_code == 200
        data = resp.json()
        assert "services" in data
        names = [s["name"] for s in data["services"]]
        assert "pragati-dashboard" in names
        assert "pragati-agent" in names
        assert "arm_launch" in names
        assert "vehicle_launch" in names
        assert "pigpiod" in names
        assert "can-watchdog@can0" in names
        assert "field-monitor" in names
        assert "boot_timing.timer" in names

    @patch("backend.systemd_api.asyncio.create_subprocess_exec")
    def test_list_services_includes_status_fields(self, mock_exec, client):
        """Each service entry has name, active_state, enabled, sub_state."""
        mock_exec.return_value = _make_mock_process(SYSTEMCTL_SHOW_OUTPUT)

        resp = client.get("/api/systemd/services")

        data = resp.json()
        svc = data["services"][0]
        assert "name" in svc
        assert "active_state" in svc
        assert "enabled" in svc
        assert "sub_state" in svc

    @patch("backend.systemd_api.asyncio.create_subprocess_exec")
    def test_list_services_parses_active_state(self, mock_exec, client):
        """Active service shows active_state='active' and enabled=True."""
        mock_exec.return_value = _make_mock_process(SYSTEMCTL_SHOW_OUTPUT)

        resp = client.get("/api/systemd/services")

        data = resp.json()
        svc = data["services"][0]
        assert svc["active_state"] == "active"
        assert svc["enabled"] is True
        assert svc["sub_state"] == "running"


# -----------------------------------------------------------------
# Tests: POST start/stop/restart (Task 5.1)
# -----------------------------------------------------------------


class TestStartService:
    """Tests for starting a service."""

    @patch("backend.systemd_api.asyncio.create_subprocess_exec")
    def test_start_service_calls_systemctl(self, mock_exec, client):
        """POST .../start calls systemctl start with correct service."""
        mock_exec.return_value = _make_mock_process()

        resp = client.post("/api/systemd/services/arm_launch/start")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        # Verify systemctl was called with correct args
        mock_exec.assert_called_once()
        call_args = mock_exec.call_args
        args = call_args[0]
        assert "systemctl" in args
        assert "start" in args
        assert "arm_launch.service" in args

    @patch("backend.systemd_api.asyncio.create_subprocess_exec")
    def test_start_service_logs_action(self, mock_exec, client):
        """POST .../start logs the action via audit logger."""
        mock_exec.return_value = _make_mock_process()
        al = _make_mock_audit_logger()

        import backend.systemd_api as mod

        mod.set_audit_logger(al)

        try:
            resp = client.post("/api/systemd/services/arm_launch/start")
            assert resp.status_code == 200
            al.log.assert_called_once()
            log_call = al.log.call_args
            assert log_call[0][0] == "systemd_start"
            assert "arm_launch" in str(log_call[0][1])
        finally:
            mod.set_audit_logger(None)


class TestStopService:
    """Tests for stopping a service."""

    @patch("backend.systemd_api.asyncio.create_subprocess_exec")
    def test_stop_service_calls_systemctl(self, mock_exec, client):
        """POST .../stop calls systemctl stop."""
        mock_exec.return_value = _make_mock_process()

        resp = client.post("/api/systemd/services/vehicle_launch/stop")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        call_args = mock_exec.call_args
        args = call_args[0]
        assert "stop" in args
        assert "vehicle_launch.service" in args


class TestRestartService:
    """Tests for restarting a service."""

    @patch("backend.systemd_api.asyncio.create_subprocess_exec")
    def test_restart_service_calls_systemctl(self, mock_exec, client):
        """POST .../restart calls systemctl restart."""
        mock_exec.return_value = _make_mock_process()

        resp = client.post("/api/systemd/services/pragati-dashboard/restart")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        call_args = mock_exec.call_args
        args = call_args[0]
        assert "restart" in args
        assert "pragati-dashboard.service" in args


# -----------------------------------------------------------------
# Tests: POST enable/disable (Task 5.1)
# -----------------------------------------------------------------


class TestEnableService:
    """Tests for enabling auto-start."""

    @patch("backend.systemd_api.asyncio.create_subprocess_exec")
    def test_enable_service_calls_systemctl(self, mock_exec, client):
        """POST .../enable calls systemctl enable."""
        mock_exec.return_value = _make_mock_process()

        resp = client.post("/api/systemd/services/pigpiod/enable")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        call_args = mock_exec.call_args
        args = call_args[0]
        assert "enable" in args
        assert "pigpiod.service" in args


class TestDisableService:
    """Tests for disabling auto-start."""

    @patch("backend.systemd_api.asyncio.create_subprocess_exec")
    def test_disable_service_calls_systemctl(self, mock_exec, client):
        """POST .../disable calls systemctl disable."""
        mock_exec.return_value = _make_mock_process()

        resp = client.post("/api/systemd/services/pigpiod/disable")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        call_args = mock_exec.call_args
        args = call_args[0]
        assert "disable" in args
        assert "pigpiod.service" in args


# -----------------------------------------------------------------
# Tests: Allowlist enforcement (Task 5.1)
# -----------------------------------------------------------------


class TestAllowlistEnforcement:
    """Disallowed service names return 403."""

    def test_start_disallowed_service_returns_403(self, client):
        """POST .../start for non-allowlisted service returns 403."""
        resp = client.post("/api/systemd/services/sshd/start")
        assert resp.status_code == 403

    def test_stop_disallowed_service_returns_403(self, client):
        """POST .../stop for non-allowlisted service returns 403."""
        resp = client.post("/api/systemd/services/nginx/stop")
        assert resp.status_code == 403

    def test_restart_disallowed_service_returns_403(self, client):
        """POST .../restart for non-allowlisted service returns 403."""
        resp = client.post("/api/systemd/services/docker/restart")
        assert resp.status_code == 403

    def test_enable_disallowed_service_returns_403(self, client):
        """POST .../enable for non-allowlisted service returns 403."""
        resp = client.post("/api/systemd/services/cron/enable")
        assert resp.status_code == 403

    def test_disable_disallowed_service_returns_403(self, client):
        """POST .../disable for non-allowlisted service returns 403."""
        resp = client.post("/api/systemd/services/bluetooth/disable")
        assert resp.status_code == 403


# -----------------------------------------------------------------
# Tests: Expanded allowlist (Tasks 3.1-3.2)
# -----------------------------------------------------------------


class TestExpandedAllowlist:
    """Verify expanded ALLOWED_SERVICES after agent service rename."""

    EXPECTED_SERVICES = [
        "pragati-dashboard",
        "pragati-agent",
        "arm_launch",
        "vehicle_launch",
        "pigpiod",
        "can-watchdog@can0",
        "field-monitor",
        "boot_timing.timer",
    ]

    @pytest.mark.parametrize("service_name", EXPECTED_SERVICES)
    @patch("backend.systemd_api.asyncio.create_subprocess_exec")
    def test_new_service_accepted(self, mock_exec, service_name, client):
        """Each new allowlisted service is accepted by endpoints."""
        mock_exec.return_value = _make_mock_process()

        resp = client.post(f"/api/systemd/services/{service_name}/start")

        assert resp.status_code == 200, (
            f"Service '{service_name}' should be allowed but got " f"{resp.status_code}"
        )

    def test_validate_function_accepts_all_new_services(self):
        """_validate_service_name accepts every expected service."""
        from backend.systemd_api import _validate_service_name

        for name in self.EXPECTED_SERVICES:
            # Should not raise
            _validate_service_name(name)

    def test_allowlist_matches_expected_set(self):
        """ALLOWED_SERVICES contains exactly the expected services."""
        from backend.systemd_api import ALLOWED_SERVICES

        assert set(ALLOWED_SERVICES) == set(self.EXPECTED_SERVICES)

    @pytest.mark.parametrize("removed_service", ["pragati-arm", "pragati-vehicle"])
    def test_removed_services_rejected(self, removed_service, client):
        """Old pragati-arm/pragati-vehicle are no longer allowed."""
        resp = client.post(f"/api/systemd/services/{removed_service}/start")
        assert resp.status_code == 403, (
            f"Removed service '{removed_service}' should be rejected " f"but got {resp.status_code}"
        )

    @pytest.mark.parametrize("bad_service", ["sshd", "nginx", "systemd-journald"])
    def test_unrelated_services_still_rejected(self, bad_service, client):
        """Services outside the allowlist are still rejected."""
        resp = client.post(f"/api/systemd/services/{bad_service}/start")
        assert resp.status_code == 403


# -----------------------------------------------------------------
# Tests: GET logs (Task 5.2)
# -----------------------------------------------------------------


SAMPLE_JOURNAL_OUTPUT = (
    "Mar 07 10:00:01 rpi systemd[1]: Started Pragati ARM.\n"
    "Mar 07 10:00:02 rpi arm_client[123]: Initializing...\n"
    "Mar 07 10:00:03 rpi arm_client[123]: Ready.\n"
)


class TestGetLogs:
    """Tests for the journal log endpoint."""

    @patch("backend.systemd_api.asyncio.create_subprocess_exec")
    def test_get_logs_returns_journal_lines(self, mock_exec, client):
        """GET .../logs returns lines from journalctl."""
        mock_exec.return_value = _make_mock_process(SAMPLE_JOURNAL_OUTPUT)

        resp = client.get("/api/systemd/services/arm_launch/logs")

        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "arm_launch"
        assert "lines" in data
        assert isinstance(data["lines"], list)
        assert len(data["lines"]) == 3
        assert data["count"] == 3

    @patch("backend.systemd_api.asyncio.create_subprocess_exec")
    def test_get_logs_default_200_lines(self, mock_exec, client):
        """GET .../logs without ?lines= uses default of 200."""
        mock_exec.return_value = _make_mock_process("")

        client.get("/api/systemd/services/arm_launch/logs")

        call_args = mock_exec.call_args
        args = call_args[0]
        assert "-n" in args
        # Find the value after -n
        n_idx = list(args).index("-n")
        assert args[n_idx + 1] == "200"

    @patch("backend.systemd_api.asyncio.create_subprocess_exec")
    def test_get_logs_custom_line_count(self, mock_exec, client):
        """GET .../logs?lines=50 passes -n 50 to journalctl."""
        mock_exec.return_value = _make_mock_process("")

        client.get("/api/systemd/services/arm_launch/logs?lines=50")

        call_args = mock_exec.call_args
        args = call_args[0]
        n_idx = list(args).index("-n")
        assert args[n_idx + 1] == "50"

    def test_get_logs_disallowed_service_returns_403(self, client):
        """GET .../logs for non-allowlisted service returns 403."""
        resp = client.get("/api/systemd/services/sshd/logs")
        assert resp.status_code == 403


# -----------------------------------------------------------------
# Tests: _unit_name helper
# -----------------------------------------------------------------


class TestUnitName:
    """Verify _unit_name resolves systemd unit names correctly."""

    def test_plain_name_gets_service_suffix(self):
        from backend.systemd_api import _unit_name

        assert _unit_name("arm_launch") == "arm_launch.service"

    def test_timer_suffix_preserved(self):
        from backend.systemd_api import _unit_name

        assert _unit_name("boot_timing.timer") == "boot_timing.timer"

    def test_service_suffix_preserved(self):
        from backend.systemd_api import _unit_name

        assert _unit_name("pragati-agent.service") == "pragati-agent.service"

    def test_template_instance_gets_service_suffix(self):
        """can-watchdog@can0 has no dot → gets .service appended."""
        from backend.systemd_api import _unit_name

        assert _unit_name("can-watchdog@can0") == "can-watchdog@can0.service"

    @patch("backend.systemd_api.asyncio.create_subprocess_exec")
    def test_timer_unit_queried_correctly(self, mock_exec, client):
        """boot_timing.timer should query the timer unit, not .timer.service."""
        mock_exec.return_value = _make_mock_process(
            "ActiveState=active\nSubState=waiting\nUnitFileState=enabled\n"
        )

        resp = client.get("/api/systemd/services")

        assert resp.status_code == 200
        # Find the boot_timing.timer entry
        data = resp.json()
        bt_entries = [s for s in data["services"] if s["name"] == "boot_timing.timer"]
        assert len(bt_entries) == 1
        assert bt_entries[0]["active_state"] == "active"
        assert bt_entries[0]["sub_state"] == "waiting"


# -----------------------------------------------------------------
# Tests: Time-range filters on GET logs (Phase 4 — Tasks 62-65)
# -----------------------------------------------------------------


class TestLogTimeFilters:
    """Tests for since/until time-range query parameters on the logs endpoint."""

    @patch("backend.systemd_api.asyncio.create_subprocess_exec")
    def test_since_param_maps_to_journalctl_flag(self, mock_exec, client):
        """GET .../logs?since=2024-01-15T10:30:00 passes --since to journalctl."""
        mock_exec.return_value = _make_mock_process("")

        client.get("/api/systemd/services/arm_launch/logs?since=2024-01-15T10:30:00")

        args = list(mock_exec.call_args[0])
        assert "--since" in args
        since_idx = args.index("--since")
        assert args[since_idx + 1] == "2024-01-15T10:30:00"

    @patch("backend.systemd_api.asyncio.create_subprocess_exec")
    def test_until_param_maps_to_journalctl_flag(self, mock_exec, client):
        """GET .../logs?until=2024-01-15T12:00:00 passes --until to journalctl."""
        mock_exec.return_value = _make_mock_process("")

        client.get("/api/systemd/services/arm_launch/logs?until=2024-01-15T12:00:00")

        args = list(mock_exec.call_args[0])
        assert "--until" in args
        until_idx = args.index("--until")
        assert args[until_idx + 1] == "2024-01-15T12:00:00"

    @patch("backend.systemd_api.asyncio.create_subprocess_exec")
    def test_both_since_and_until_passed(self, mock_exec, client):
        """Both --since and --until are passed when both params given."""
        mock_exec.return_value = _make_mock_process("")

        client.get(
            "/api/systemd/services/arm_launch/logs"
            "?since=2024-01-15T10:00:00&until=2024-01-15T12:00:00"
        )

        args = list(mock_exec.call_args[0])
        assert "--since" in args
        assert "--until" in args

    @patch("backend.systemd_api.asyncio.create_subprocess_exec")
    def test_relative_time_since_accepted(self, mock_exec, client):
        """Relative time string like '10 minutes ago' is accepted."""
        mock_exec.return_value = _make_mock_process("")

        resp = client.get("/api/systemd/services/arm_launch/logs?since=10 minutes ago")

        assert resp.status_code == 200
        args = list(mock_exec.call_args[0])
        assert "--since" in args
        since_idx = args.index("--since")
        assert args[since_idx + 1] == "10 minutes ago"

    @patch("backend.systemd_api.asyncio.create_subprocess_exec")
    def test_relative_time_1_hour_ago(self, mock_exec, client):
        """Relative time '1 hour ago' is accepted."""
        mock_exec.return_value = _make_mock_process("")

        resp = client.get("/api/systemd/services/arm_launch/logs?since=1 hour ago")

        assert resp.status_code == 200
        args = list(mock_exec.call_args[0])
        assert "--since" in args

    @patch("backend.systemd_api.asyncio.create_subprocess_exec")
    def test_relative_time_6_hours_ago(self, mock_exec, client):
        """Relative time '6 hours ago' is accepted."""
        mock_exec.return_value = _make_mock_process("")

        resp = client.get("/api/systemd/services/arm_launch/logs?since=6 hours ago")

        assert resp.status_code == 200

    def test_invalid_since_format_returns_400(self, client):
        """Invalid since format like 'not-a-date' returns HTTP 400."""
        resp = client.get("/api/systemd/services/arm_launch/logs?since=not-a-date")

        assert resp.status_code == 400

    def test_invalid_until_format_returns_400(self, client):
        """Invalid until format returns HTTP 400."""
        resp = client.get("/api/systemd/services/arm_launch/logs?until=xyz123")

        assert resp.status_code == 400

    @patch("backend.systemd_api.asyncio.create_subprocess_exec")
    def test_missing_since_until_omits_flags(self, mock_exec, client):
        """Missing since/until params omit --since/--until flags (backward compat)."""
        mock_exec.return_value = _make_mock_process("")

        client.get("/api/systemd/services/arm_launch/logs")

        args = list(mock_exec.call_args[0])
        assert "--since" not in args
        assert "--until" not in args

    @patch("backend.systemd_api.asyncio.create_subprocess_exec")
    def test_iso_date_without_time_accepted(self, mock_exec, client):
        """ISO date without time component like '2024-01-15' is accepted."""
        mock_exec.return_value = _make_mock_process("")

        resp = client.get("/api/systemd/services/arm_launch/logs?since=2024-01-15")

        assert resp.status_code == 200
        args = list(mock_exec.call_args[0])
        assert "--since" in args

    def test_shell_injection_in_since_returns_400(self, client):
        """Semicolons and shell metacharacters in since are rejected."""
        resp = client.get("/api/systemd/services/arm_launch/logs?since=; rm -rf /")

        assert resp.status_code == 400

    @patch("backend.systemd_api.asyncio.create_subprocess_exec")
    def test_relative_time_yesterday_accepted(self, mock_exec, client):
        """Relative time 'yesterday' is accepted."""
        mock_exec.return_value = _make_mock_process("")

        resp = client.get("/api/systemd/services/arm_launch/logs?since=yesterday")

        assert resp.status_code == 200


# -----------------------------------------------------------------
# Tests: _validate_time_param helper (Phase 4)
# -----------------------------------------------------------------


class TestValidateTimeParam:
    """Direct tests for the time parameter validation function."""

    def test_none_returns_none(self):
        from backend.systemd_api import _validate_time_param

        assert _validate_time_param(None) is None

    def test_iso_datetime_accepted(self):
        from backend.systemd_api import _validate_time_param

        assert _validate_time_param("2024-01-15T10:30:00") == "2024-01-15T10:30:00"

    def test_iso_date_only_accepted(self):
        from backend.systemd_api import _validate_time_param

        assert _validate_time_param("2024-01-15") == "2024-01-15"

    def test_relative_minutes_ago_accepted(self):
        from backend.systemd_api import _validate_time_param

        assert _validate_time_param("10 minutes ago") == "10 minutes ago"

    def test_relative_hours_ago_accepted(self):
        from backend.systemd_api import _validate_time_param

        assert _validate_time_param("1 hour ago") == "1 hour ago"

    def test_relative_days_ago_accepted(self):
        from backend.systemd_api import _validate_time_param

        assert _validate_time_param("2 days ago") == "2 days ago"

    def test_yesterday_accepted(self):
        from backend.systemd_api import _validate_time_param

        assert _validate_time_param("yesterday") == "yesterday"

    def test_today_accepted(self):
        from backend.systemd_api import _validate_time_param

        assert _validate_time_param("today") == "today"

    def test_invalid_string_raises(self):
        from backend.systemd_api import _validate_time_param

        with pytest.raises(ValueError):
            _validate_time_param("not-a-date")

    def test_shell_metachar_raises(self):
        from backend.systemd_api import _validate_time_param

        with pytest.raises(ValueError):
            _validate_time_param("; rm -rf /")

    def test_backtick_raises(self):
        from backend.systemd_api import _validate_time_param

        with pytest.raises(ValueError):
            _validate_time_param("`whoami`")

    def test_pipe_raises(self):
        from backend.systemd_api import _validate_time_param

        with pytest.raises(ValueError):
            _validate_time_param("2024-01-15 | cat /etc/passwd")
