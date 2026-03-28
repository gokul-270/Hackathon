"""Unit tests for polling suspension and resume.

Tests cover:
- Entity gets suspended after SUSPEND_THRESHOLD consecutive failures
- _poll_all() skips suspended entities
- resume_polling() clears suspension state correctly
- REST endpoints for resume-polling (single and group)
- Auto-resume on add/update with IP change
- entity_to_api_dict() includes polling_suspended flag
"""

from __future__ import annotations

import asyncio
import textwrap
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.entity_model import Entity
from backend.entity_manager import (
    OFFLINE_THRESHOLD,
    POLL_INTERVAL_S,
    SUSPEND_THRESHOLD,
    EntityManager,
    entity_router,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_CONFIG_ENV = textwrap.dedent("""\
    ARM_1_IP=192.168.1.10
    ARM_2_IP=192.168.1.11
    VEHICLE_IP=192.168.1.20
""")


@pytest.fixture(autouse=True)
def _mock_local_ips():
    """Prevent real local-IP detection from interfering with tests."""
    with patch.object(EntityManager, "_detect_local_ips", return_value={"127.0.0.1", "10.0.0.99"}):
        yield


@pytest.fixture()
def config_env_path(tmp_path):
    p = tmp_path / "config.env"
    p.write_text(SAMPLE_CONFIG_ENV)
    return p


@pytest.fixture()
def manager(config_env_path, tmp_path):
    return EntityManager(
        config_env_path=config_env_path,
        entities_yaml_path=tmp_path / "entities.yaml",
    )


@pytest.fixture()
def app_with_entities(manager):
    app = FastAPI()
    # entity_router already has prefix="/api/entities" — do NOT add another
    app.include_router(entity_router)
    with patch("backend.entity_manager._entity_manager", manager):
        yield app


@pytest.fixture()
def client(app_with_entities, manager):
    with patch("backend.entity_manager._entity_manager", manager):
        with TestClient(app_with_entities) as c:
            yield c


def _make_failing_httpx_client():
    """Return a mock httpx.AsyncClient that always raises ConnectTimeout."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


def _make_successful_httpx_client(extra_health=None):
    """Return a mock httpx.AsyncClient that returns a healthy response."""
    health_data = {
        "cpu_percent": 10.0,
        "memory_percent": 30.0,
        "temperature_c": 45.0,
        "disk_percent": 20.0,
        "uptime_seconds": 3600,
        "warnings": [],
        "hostname": "test-host",
    }
    if extra_health:
        health_data.update(extra_health)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "health": health_data,
        "ros2": {"nodes": [], "topics": []},
        "systemd": {"services": {}},
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# ---------------------------------------------------------------------------
# Tests: Suspension after SUSPEND_THRESHOLD failures
# ---------------------------------------------------------------------------


class TestPollingSuspension:
    """Entity polling is suspended after SUSPEND_THRESHOLD consecutive failures."""

    @pytest.mark.asyncio
    async def test_entity_suspended_after_threshold_failures(self, manager):
        """After SUSPEND_THRESHOLD poll failures, entity is added to _suspended."""
        arm1 = manager._entities["arm1"]
        failing_client = _make_failing_httpx_client()

        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=failing_client,
        ):
            for _ in range(SUSPEND_THRESHOLD):
                await manager._poll_entity(arm1)

        assert arm1.id in manager._suspended
        assert arm1.status == "offline"

    def test_suspend_threshold_is_fifty(self):
        assert SUSPEND_THRESHOLD == 50

    @pytest.mark.asyncio
    async def test_entity_not_suspended_before_threshold(self, manager):
        """Entity is NOT suspended before reaching SUSPEND_THRESHOLD."""
        arm1 = manager._entities["arm1"]
        failing_client = _make_failing_httpx_client()

        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=failing_client,
        ):
            for _ in range(SUSPEND_THRESHOLD - 1):
                await manager._poll_entity(arm1)

        assert arm1.id not in manager._suspended
        # Should be offline (past OFFLINE_THRESHOLD) but not suspended
        assert arm1.status == "offline"

    @pytest.mark.asyncio
    async def test_suspension_error_message_added(self, manager):
        """Suspended entity has a 'suspended' error in its errors list."""
        arm1 = manager._entities["arm1"]
        failing_client = _make_failing_httpx_client()

        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=failing_client,
        ):
            for _ in range(SUSPEND_THRESHOLD):
                await manager._poll_entity(arm1)

        suspended_errors = [e for e in arm1.errors if "suspended" in e.lower()]
        assert len(suspended_errors) >= 1

    @pytest.mark.asyncio
    async def test_offline_before_suspended(self, manager):
        """Entity goes offline at OFFLINE_THRESHOLD, then suspended at SUSPEND_THRESHOLD."""
        arm1 = manager._entities["arm1"]
        failing_client = _make_failing_httpx_client()

        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=failing_client,
        ):
            for i in range(SUSPEND_THRESHOLD):
                await manager._poll_entity(arm1)

                if OFFLINE_THRESHOLD <= (i + 1) < SUSPEND_THRESHOLD:
                    assert arm1.status == "offline"
                    assert arm1.id not in manager._suspended

        # After all failures
        assert arm1.id in manager._suspended
        assert arm1.status == "offline"


# ---------------------------------------------------------------------------
# Tests: _poll_all() skips suspended entities
# ---------------------------------------------------------------------------


class TestPollAllSkipsSuspended:
    """_poll_all() must skip entities in the _suspended set."""

    @pytest.mark.asyncio
    async def test_suspended_entity_not_polled(self, manager):
        """A suspended entity is never passed to _poll_entity."""
        arm1 = manager._entities["arm1"]
        manager._suspended.add(arm1.id)

        with patch.object(manager, "_poll_entity", new_callable=AsyncMock) as mock_poll:
            with patch.object(manager, "_poll_local", new_callable=AsyncMock):
                await manager._poll_all()

        # arm1 should NOT appear in any _poll_entity calls
        polled_ids = [call.args[0].id for call in mock_poll.call_args_list]
        assert arm1.id not in polled_ids

    @pytest.mark.asyncio
    async def test_non_suspended_entities_still_polled(self, manager):
        """Non-suspended entities with IPs are still polled normally."""
        arm1 = manager._entities["arm1"]
        arm2 = manager._entities["arm2"]
        manager._suspended.add(arm1.id)

        with patch.object(manager, "_poll_entity", new_callable=AsyncMock) as mock_poll:
            with patch.object(manager, "_poll_local", new_callable=AsyncMock):
                await manager._poll_all()

        polled_ids = [call.args[0].id for call in mock_poll.call_args_list]
        assert arm1.id not in polled_ids
        assert arm2.id in polled_ids


# ---------------------------------------------------------------------------
# Tests: resume_polling()
# ---------------------------------------------------------------------------


class TestResumePolling:
    """resume_polling() clears suspension state and resets counters."""

    def test_resume_clears_suspended_set(self, manager):
        arm1 = manager._entities["arm1"]
        manager._suspended.add(arm1.id)
        manager._failure_counts[arm1.id] = SUSPEND_THRESHOLD

        manager.resume_polling(arm1.id)

        assert arm1.id not in manager._suspended

    def test_resume_resets_failure_count(self, manager):
        arm1 = manager._entities["arm1"]
        manager._suspended.add(arm1.id)
        manager._failure_counts[arm1.id] = SUSPEND_THRESHOLD

        manager.resume_polling(arm1.id)

        assert manager._failure_counts[arm1.id] == 0

    def test_resume_resets_poll_interval(self, manager):
        arm1 = manager._entities["arm1"]
        manager._suspended.add(arm1.id)
        manager._poll_intervals[arm1.id] = 90

        manager.resume_polling(arm1.id)

        assert manager._poll_intervals[arm1.id] == manager._status_poll_interval_s

    def test_resume_forces_immediate_poll(self, manager):
        """Clearing _last_polled ensures the entity is polled on next cycle."""
        arm1 = manager._entities["arm1"]
        manager._suspended.add(arm1.id)
        manager._last_polled[arm1.id] = 999999.0

        manager.resume_polling(arm1.id)

        assert arm1.id not in manager._last_polled

    def test_resume_sets_status_unknown(self, manager):
        arm1 = manager._entities["arm1"]
        arm1.status = "offline"
        manager._suspended.add(arm1.id)

        manager.resume_polling(arm1.id)

        assert arm1.status == "unknown"

    def test_resume_clears_suspension_errors(self, manager):
        arm1 = manager._entities["arm1"]
        arm1.errors = [
            "Polling suspended after 10 consecutive failures",
            "Some other error",
        ]
        manager._suspended.add(arm1.id)

        manager.resume_polling(arm1.id)

        assert not any("suspended" in e.lower() for e in arm1.errors)
        assert "Some other error" in arm1.errors

    def test_resume_returns_true_if_was_suspended(self, manager):
        arm1 = manager._entities["arm1"]
        manager._suspended.add(arm1.id)

        result = manager.resume_polling(arm1.id)

        assert result is True

    def test_resume_returns_false_if_not_suspended(self, manager):
        arm1 = manager._entities["arm1"]
        # Not adding to _suspended

        result = manager.resume_polling(arm1.id)

        assert result is False

    def test_resume_nonexistent_entity_raises(self, manager):
        with pytest.raises(KeyError, match="not found"):
            manager.resume_polling("nonexistent-entity")

    def test_resume_triggers_notify_change(self, manager):
        arm1 = manager._entities["arm1"]
        manager._suspended.add(arm1.id)

        with patch.object(manager, "notify_change") as mock_notify:
            manager.resume_polling(arm1.id)

        mock_notify.assert_called_once()

    def test_resume_no_notify_if_not_suspended(self, manager):
        """If entity wasn't suspended, notify_change is NOT called."""
        arm1 = manager._entities["arm1"]

        with patch.object(manager, "notify_change") as mock_notify:
            manager.resume_polling(arm1.id)

        mock_notify.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: REST endpoints for resume-polling
# ---------------------------------------------------------------------------


class TestResumePollEndpoints:
    """REST API endpoints for resuming polling."""

    def test_resume_single_entity_200(self, client, manager):
        arm1 = manager._entities["arm1"]
        manager._suspended.add(arm1.id)

        resp = client.post(f"/api/entities/{arm1.id}/resume-polling")

        assert resp.status_code == 200
        body = resp.json()
        assert body["entity_id"] == arm1.id
        assert body["was_suspended"] is True
        assert body["status"] == "resumed"

    def test_resume_single_entity_not_suspended(self, client, manager):
        arm1 = manager._entities["arm1"]

        resp = client.post(f"/api/entities/{arm1.id}/resume-polling")

        assert resp.status_code == 200
        body = resp.json()
        assert body["was_suspended"] is False

    def test_resume_single_entity_not_found(self, client):
        resp = client.post("/api/entities/no-such-entity/resume-polling")

        assert resp.status_code == 404

    def test_resume_group_all(self, client, manager):
        """POST /resume-polling with no group_id resumes all suspended."""
        arm1 = manager._entities["arm1"]
        arm2 = manager._entities["arm2"]
        manager._suspended.add(arm1.id)
        manager._suspended.add(arm2.id)

        resp = client.post("/api/entities/resume-polling")

        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 2
        assert set(body["resumed"]) == {arm1.id, arm2.id}
        assert len(manager._suspended) == 0

    def test_resume_group_filtered(self, client, manager):
        """POST /resume-polling?group_id=X only resumes entities in that group."""
        arm1 = manager._entities["arm1"]
        arm2 = manager._entities["arm2"]
        arm1.group_id = "lab-1"
        arm2.group_id = "lab-2"
        manager._suspended.add(arm1.id)
        manager._suspended.add(arm2.id)

        resp = client.post("/api/entities/resume-polling?group_id=lab-1")

        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        assert body["resumed"] == [arm1.id]
        # arm2 should still be suspended
        assert arm2.id in manager._suspended

    def test_resume_group_none_suspended(self, client, manager):
        """POST /resume-polling when nothing is suspended returns count=0."""
        resp = client.post("/api/entities/resume-polling")

        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 0
        assert body["resumed"] == []


# ---------------------------------------------------------------------------
# Tests: entity_to_api_dict()
# ---------------------------------------------------------------------------


class TestEntityToApiDict:
    """entity_to_api_dict() enriches serialization with polling_suspended."""

    def test_includes_polling_suspended_false(self, manager):
        arm1 = manager._entities["arm1"]
        d = manager.entity_to_api_dict(arm1)

        assert "polling_suspended" in d
        assert d["polling_suspended"] is False

    def test_includes_polling_suspended_true(self, manager):
        arm1 = manager._entities["arm1"]
        manager._suspended.add(arm1.id)

        d = manager.entity_to_api_dict(arm1)

        assert d["polling_suspended"] is True

    def test_preserves_entity_fields(self, manager):
        """entity_to_api_dict still includes all base Entity fields."""
        arm1 = manager._entities["arm1"]
        base_dict = arm1.to_dict()
        api_dict = manager.entity_to_api_dict(arm1)

        for key in base_dict:
            assert key in api_dict, f"Missing key: {key}"
            assert api_dict[key] == base_dict[key]


# ---------------------------------------------------------------------------
# Tests: Auto-resume on add/update
# ---------------------------------------------------------------------------


class TestAutoResume:
    """Suspended state is cleared when entity is added or IP is updated."""

    @pytest.mark.asyncio
    async def test_add_entity_clears_suspension(self, manager):
        """Adding an entity with an ID that was previously suspended clears it."""
        # Simulate a prior entity that was suspended and removed
        manager._suspended.add("arm3")

        await manager.add_entity_by_ip(
            ip="192.168.1.30",
            entity_type="arm",
            group_id="lab-1",
            slot="arm-3",
            name="arm3",
        )

        assert "arm3" not in manager._suspended

    @pytest.mark.asyncio
    async def test_update_ip_clears_suspension(self, manager):
        """Updating an entity's IP address clears its suspension."""
        arm1 = manager._entities["arm1"]
        manager._suspended.add(arm1.id)
        manager._failure_counts[arm1.id] = SUSPEND_THRESHOLD

        await manager.update_entity(arm1.id, ip="192.168.1.99")

        assert arm1.id not in manager._suspended
        assert manager._failure_counts[arm1.id] == 0

    @pytest.mark.asyncio
    async def test_update_group_does_not_clear_suspension(self, manager):
        """Updating group/slot without IP change does NOT clear suspension."""
        arm1 = manager._entities["arm1"]
        manager._suspended.add(arm1.id)

        await manager.update_entity(arm1.id, group_id="new-group", slot="arm-1")

        assert arm1.id in manager._suspended


# ---------------------------------------------------------------------------
# Tests: API endpoints return polling_suspended in response
# ---------------------------------------------------------------------------


class TestApiResponsesIncludeSuspended:
    """All entity API responses include the polling_suspended field."""

    def test_get_all_entities_includes_suspended_flag(self, client, manager):
        arm1 = manager._entities["arm1"]
        manager._suspended.add(arm1.id)

        resp = client.get("/api/entities")
        assert resp.status_code == 200

        entities = resp.json()
        arm1_data = next(e for e in entities if e["id"] == arm1.id)
        assert arm1_data["polling_suspended"] is True

        # Non-suspended entity
        arm2_data = next(e for e in entities if e["id"] == "arm2")
        assert arm2_data["polling_suspended"] is False

    def test_get_single_entity_includes_suspended_flag(self, client, manager):
        arm1 = manager._entities["arm1"]
        manager._suspended.add(arm1.id)

        resp = client.get(f"/api/entities/{arm1.id}")
        assert resp.status_code == 200
        assert resp.json()["polling_suspended"] is True
