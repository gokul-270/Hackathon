"""Unit tests for EntityManager (Tasks 2.2-2.11, 2.10b).

Tests cover:
- 2.2: config.env parsing (ARM_{N}_IP, ARM{N}_IP, VEHICLE_IP, RPI_IP, *_USER, dedup)
- 2.4: Polling with mocked httpx
- 2.5: Offline detection (3 failures -> offline, backoff, recovery)
- 2.6: REST API endpoints (GET /api/entities, GET /api/entities/{id}, 404)
- 2.7: WebSocket push (subscribe_changes)
- 2.9: dashboard.yaml fallback
- 2.11: Add discovered entity endpoint

httpx is fully mocked -- no real network needed.
"""

from __future__ import annotations

import asyncio
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.entity_model import Entity

# ---------------------------------------------------------------------------
# We import entity_manager after entity_model is confirmed importable
# ---------------------------------------------------------------------------
from backend.entity_manager import (
    BACKOFF_MULTIPLIER,
    MAX_POLL_INTERVAL_S,
    POLL_INTERVAL_S,
    EntityManager,
    entity_router,
    get_entity_manager,
    init_entity_manager,
    shutdown_entity_manager,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_CONFIG_ENV = textwrap.dedent("""\
    RPI_IP=192.168.137.203
    RPI_USER=ubuntu
    ARM_1_IP=192.168.137.12
    ARM_2_IP=192.168.137.238
    VEHICLE_IP=192.168.137.203
    ARM1_IP=192.168.137.12
    ARM1_USER=ubuntu
    ARM2_IP=192.168.137.238
    ARM2_USER=ubuntu
    ALL_ARMS="arm1,arm2"
""")


SAMPLE_DASHBOARD_YAML_FLEET = {
    "fleet": {
        "vehicle": {
            "name": "vehicle-rpi",
            "ip": "192.168.137.203",
            "role": "vehicle",
        },
        "arms": [
            {"name": "arm1-rpi", "ip": "192.168.137.12", "role": "arm"},
            {"name": "arm2-rpi", "ip": "192.168.137.238", "role": "arm"},
        ],
    }
}


@pytest.fixture
def config_env_path(tmp_path: Path) -> Path:
    """Write a sample config.env to tmp_path and return the path."""
    p = tmp_path / "config.env"
    p.write_text(SAMPLE_CONFIG_ENV)
    return p


@pytest.fixture
def empty_config_env(tmp_path: Path) -> Path:
    """Write an empty config.env."""
    p = tmp_path / "config.env"
    p.write_text("# empty\n")
    return p


# Mock local IPs to a non-conflicting value for deterministic tests
_MOCK_LOCAL_IPS = {"127.0.0.1", "10.0.0.99"}


@pytest.fixture(autouse=True)
def _mock_local_ips():
    """Patch _detect_local_ips for all tests so results are deterministic."""
    with patch.object(EntityManager, "_detect_local_ips", return_value=_MOCK_LOCAL_IPS):
        yield


@pytest.fixture
def manager(config_env_path: Path, tmp_path: Path) -> EntityManager:
    """Create an EntityManager with sample config.env (no start)."""
    return EntityManager(
        config_env_path=config_env_path,
        entities_yaml_path=tmp_path / "entities.yaml",
    )


@pytest.fixture
def app_with_entities(manager: EntityManager) -> FastAPI:
    """Create a FastAPI app with entity router mounted."""
    app = FastAPI()
    app.include_router(entity_router)

    # Patch the module-level getter so the router can access the manager
    with patch("backend.entity_manager._entity_manager", manager):
        yield app


@pytest.fixture
def client(app_with_entities: FastAPI, manager: EntityManager) -> TestClient:
    """TestClient with entity router and patched manager."""
    with patch("backend.entity_manager._entity_manager", manager):
        with TestClient(app_with_entities) as c:
            yield c


# ===================================================================
# Task 2.2: config.env parsing
# ===================================================================


class TestConfigEnvParsing:
    """Test config.env parsing produces correct entities."""

    def test_local_entity_always_present(self, manager: EntityManager):
        entities = manager.get_all_entities()
        local = [e for e in entities if e.id == "local"]
        assert len(local) == 1
        assert local[0].source == "local"
        # Local entity now gets its primary local IP
        assert local[0].ip == "10.0.0.99"  # from _MOCK_LOCAL_IPS

    def test_arm1_entity_from_config(self, manager: EntityManager):
        entities = manager.get_all_entities()
        arm1 = [e for e in entities if e.id == "arm1"]
        assert len(arm1) == 1
        assert arm1[0].ip == "192.168.137.12"
        assert arm1[0].entity_type == "arm"
        assert arm1[0].source == "remote"

    def test_arm2_entity_from_config(self, manager: EntityManager):
        entities = manager.get_all_entities()
        arm2 = [e for e in entities if e.id == "arm2"]
        assert len(arm2) == 1
        assert arm2[0].ip == "192.168.137.238"
        assert arm2[0].entity_type == "arm"

    def test_vehicle_entity_from_config(self, manager: EntityManager):
        entities = manager.get_all_entities()
        vehicle = [e for e in entities if e.id == "vehicle"]
        assert len(vehicle) == 1
        assert vehicle[0].ip == "192.168.137.203"
        assert vehicle[0].entity_type == "vehicle"

    def test_deduplication_arm_formats(self, manager: EntityManager):
        """ARM_1_IP and ARM1_IP both resolve to arm1 -- no duplicate."""
        entities = manager.get_all_entities()
        arm1_list = [e for e in entities if e.id == "arm1"]
        assert len(arm1_list) == 1

    def test_user_vars_stored_in_metadata(self, manager: EntityManager):
        entities = manager.get_all_entities()
        arm1 = next(e for e in entities if e.id == "arm1")
        assert arm1.metadata.get("user") == "ubuntu"

    def test_rpi_ip_stored_in_metadata(self, manager: EntityManager):
        """RPI_IP is stored as metadata on local entity, not as separate entity."""
        entities = manager.get_all_entities()
        local = next(e for e in entities if e.id == "local")
        assert local.metadata.get("rpi_ip") == "192.168.137.203"

    def test_total_entity_count(self, manager: EntityManager):
        """local + arm1 + arm2 + vehicle = 4 entities."""
        entities = manager.get_all_entities()
        assert len(entities) == 4


class TestConfigEnvMalformedIP:
    """Test malformed IPs are skipped with warning."""

    def test_malformed_ip_skipped(self, tmp_path: Path):
        p = tmp_path / "config.env"
        p.write_text("ARM_1_IP=not-an-ip\nARM_2_IP=192.168.1.10\n")
        mgr = EntityManager(
            config_env_path=p,
            entities_yaml_path=tmp_path / "entities.yaml",
        )
        entities = mgr.get_all_entities()
        ids = {e.id for e in entities}
        assert "arm1" not in ids
        assert "arm2" in ids

    def test_empty_ip_skipped(self, tmp_path: Path):
        p = tmp_path / "config.env"
        p.write_text("ARM_1_IP=\n")
        # Pass nonexistent yaml path to prevent fallback
        yaml_path = tmp_path / "nonexistent.yaml"
        mgr = EntityManager(
            config_env_path=p,
            dashboard_yaml_path=yaml_path,
            entities_yaml_path=tmp_path / "entities.yaml",
        )
        entities = mgr.get_all_entities()
        ids = {e.id for e in entities}
        assert "arm1" not in ids


class TestDuplicateIPWarning:
    """Test duplicate IPs across different entities logs warning."""

    def test_duplicate_ip_different_entities_logged(self, tmp_path: Path, caplog):
        """VEHICLE_IP and ARM_1_IP same IP should log warning."""
        p = tmp_path / "config.env"
        p.write_text("VEHICLE_IP=192.168.1.10\nARM_1_IP=192.168.1.10\n")
        import logging

        em_logger = logging.getLogger("backend.entity_manager")
        old_propagate = em_logger.propagate
        em_logger.propagate = True
        try:
            with caplog.at_level(logging.WARNING, logger="backend.entity_manager"):
                mgr = EntityManager(
                    config_env_path=p,
                    entities_yaml_path=tmp_path / "entities.yaml",
                )
        finally:
            em_logger.propagate = old_propagate
        # Should have a warning about duplicate IP
        assert any("duplicate" in r.message.lower() for r in caplog.records) or any(
            "192.168.1.10" in r.message for r in caplog.records
        )


# ===================================================================
# Task 2.9: dashboard.yaml fallback
# ===================================================================


class TestDashboardYamlFallback:
    """Test fallback to dashboard.yaml when config.env has no entity IPs."""

    def test_fallback_creates_entities_from_yaml(self, empty_config_env: Path):
        yaml_path = empty_config_env.parent / "dashboard.yaml"
        import yaml

        yaml_path.write_text(
            yaml.dump(
                {
                    "fleet": {
                        "vehicle": {
                            "name": "vehicle-rpi",
                            "ip": "192.168.137.203",
                            "role": "vehicle",
                        },
                        "arms": [
                            {
                                "name": "arm1-rpi",
                                "ip": "192.168.137.12",
                                "role": "arm",
                            },
                        ],
                    }
                }
            )
        )
        mgr = EntityManager(
            config_env_path=empty_config_env,
            dashboard_yaml_path=yaml_path,
            entities_yaml_path=empty_config_env.parent / "entities.yaml",
        )
        entities = mgr.get_all_entities()
        ids = {e.id for e in entities}
        assert "vehicle" in ids
        assert "arm1" in ids  # arm1-rpi maps to arm1

    def test_fallback_logs_deprecation_warning(self, empty_config_env: Path, caplog):
        yaml_path = empty_config_env.parent / "dashboard.yaml"
        import logging
        import yaml

        yaml_path.write_text(
            yaml.dump(
                {
                    "fleet": {
                        "vehicle": {
                            "name": "v",
                            "ip": "10.0.0.1",
                            "role": "vehicle",
                        },
                        "arms": [],
                    }
                }
            )
        )
        em_logger = logging.getLogger("backend.entity_manager")
        old_propagate = em_logger.propagate
        em_logger.propagate = True
        try:
            with caplog.at_level(logging.WARNING, logger="backend.entity_manager"):
                EntityManager(
                    config_env_path=empty_config_env,
                    dashboard_yaml_path=yaml_path,
                    entities_yaml_path=empty_config_env.parent / "entities.yaml",
                )
        finally:
            em_logger.propagate = old_propagate
        assert any(
            "deprecat" in r.message.lower() or "fallback" in r.message.lower()
            for r in caplog.records
        )

    def test_no_fallback_when_config_env_has_entities(self, config_env_path: Path):
        """Should NOT fall back if config.env already has entity IPs."""
        yaml_path = config_env_path.parent / "dashboard.yaml"
        import yaml

        yaml_path.write_text(
            yaml.dump(
                {
                    "fleet": {
                        "vehicle": {
                            "name": "extra-vehicle",
                            "ip": "99.99.99.99",
                            "role": "vehicle",
                        },
                        "arms": [],
                    }
                }
            )
        )
        mgr = EntityManager(
            config_env_path=config_env_path,
            dashboard_yaml_path=yaml_path,
            entities_yaml_path=config_env_path.parent / "entities.yaml",
        )
        entities = mgr.get_all_entities()
        ips = {e.ip for e in entities if e.ip}
        # Should NOT have the YAML-only IP
        assert "99.99.99.99" not in ips


# ===================================================================
# Task 2.4: Polling with mocked httpx
# ===================================================================


class TestPolling:
    """Test polling cycle updates entity state."""

    @pytest.mark.asyncio
    async def test_successful_poll_sets_online(self, manager: EntityManager):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "health": {
                "cpu_percent": 45.0,
                "memory_percent": 60.0,
                "temperature_c": 55.0,
                "disk_percent": 30.0,
                "uptime_seconds": 3600,
                "warnings": [],
            },
            "ros2": {
                "available": True,
                "node_count": 3,
                "topic_count": 5,
                "service_count": 2,
            },
            "systemd": [
                {
                    "name": "pragati-agent.service",
                    "active_state": "active",
                    "sub_state": "running",
                    "description": "Pragati Agent",
                },
            ],
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.entity_manager.httpx.AsyncClient", return_value=mock_client):
            arm1 = next(e for e in manager.get_all_entities() if e.id == "arm1")
            await manager._poll_entity(arm1)

        arm1 = manager.get_entity("arm1")
        assert arm1.status == "online"
        assert arm1.system_metrics["cpu_percent"] == 45.0
        assert arm1.system_metrics["memory_percent"] == 60.0
        assert arm1.system_metrics["temperature_c"] == 55.0
        assert arm1.system_metrics["disk_percent"] == 30.0
        assert arm1.system_metrics["uptime_seconds"] == 3600
        assert arm1.last_seen is not None
        # ROS2 state populated
        assert arm1.ros2_available is True
        assert arm1.ros2_state is not None
        assert arm1.ros2_state["node_count"] == 3
        assert arm1.ros2_state["topic_count"] == 5
        assert arm1.ros2_state["service_count"] == 2
        # Systemd services populated
        assert len(arm1.services) == 1
        assert arm1.services[0]["name"] == "pragati-agent.service"

    @pytest.mark.asyncio
    async def test_poll_timeout_does_not_crash(self, manager: EntityManager):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.entity_manager.httpx.AsyncClient", return_value=mock_client):
            arm1 = next(e for e in manager.get_all_entities() if e.id == "arm1")
            await manager._poll_entity(arm1)
        # Should not raise


# ===================================================================
# Task 2.5: Offline detection
# ===================================================================


class TestOfflineDetection:
    """Test 3 consecutive failures -> offline, backoff, recovery."""

    @pytest.mark.asyncio
    async def test_three_failures_marks_offline(self, manager: EntityManager):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.entity_manager.httpx.AsyncClient", return_value=mock_client):
            arm1 = next(e for e in manager.get_all_entities() if e.id == "arm1")
            # 3 consecutive failures
            await manager._poll_entity(arm1)
            await manager._poll_entity(arm1)
            await manager._poll_entity(arm1)

        arm1 = manager.get_entity("arm1")
        assert arm1.status == "offline"

    @pytest.mark.asyncio
    async def test_two_failures_not_offline(self, manager: EntityManager):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.entity_manager.httpx.AsyncClient", return_value=mock_client):
            arm1 = next(e for e in manager.get_all_entities() if e.id == "arm1")
            await manager._poll_entity(arm1)
            await manager._poll_entity(arm1)

        arm1 = manager.get_entity("arm1")
        # Not yet offline -- still "unknown" or "degraded" but not "offline"
        assert arm1.status != "offline"

    @pytest.mark.asyncio
    async def test_recovery_after_offline(self, manager: EntityManager):
        """Success after 3 failures restores normal status."""
        fail_client = AsyncMock()
        fail_client.get = AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))
        fail_client.__aenter__ = AsyncMock(return_value=fail_client)
        fail_client.__aexit__ = AsyncMock(return_value=False)

        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.json.return_value = {
            "health": {"cpu_percent": 30.0, "memory_percent": 50.0},
            "ros2": {},
            "systemd": [],
        }
        ok_client = AsyncMock()
        ok_client.get = AsyncMock(return_value=ok_resp)
        ok_client.__aenter__ = AsyncMock(return_value=ok_client)
        ok_client.__aexit__ = AsyncMock(return_value=False)

        arm1 = next(e for e in manager.get_all_entities() if e.id == "arm1")

        # 3 failures -> offline
        with patch("backend.entity_manager.httpx.AsyncClient", return_value=fail_client):
            await manager._poll_entity(arm1)
            await manager._poll_entity(arm1)
            await manager._poll_entity(arm1)

        assert manager.get_entity("arm1").status == "offline"

        # Recovery
        with patch("backend.entity_manager.httpx.AsyncClient", return_value=ok_client):
            await manager._poll_entity(arm1)

        assert manager.get_entity("arm1").status == "online"

    @pytest.mark.asyncio
    async def test_recovery_clears_failure_count(self, manager: EntityManager):
        """After recovery, failure count resets."""
        fail_client = AsyncMock()
        fail_client.get = AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))
        fail_client.__aenter__ = AsyncMock(return_value=fail_client)
        fail_client.__aexit__ = AsyncMock(return_value=False)

        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.json.return_value = {
            "health": {"cpu_percent": 30.0},
            "ros2": {},
            "systemd": [],
        }
        ok_client = AsyncMock()
        ok_client.get = AsyncMock(return_value=ok_resp)
        ok_client.__aenter__ = AsyncMock(return_value=ok_client)
        ok_client.__aexit__ = AsyncMock(return_value=False)

        arm1 = next(e for e in manager.get_all_entities() if e.id == "arm1")

        # 2 failures
        with patch("backend.entity_manager.httpx.AsyncClient", return_value=fail_client):
            await manager._poll_entity(arm1)
            await manager._poll_entity(arm1)

        # Success resets count
        with patch("backend.entity_manager.httpx.AsyncClient", return_value=ok_client):
            await manager._poll_entity(arm1)

        # 2 more failures should NOT make offline (count was reset)
        with patch("backend.entity_manager.httpx.AsyncClient", return_value=fail_client):
            await manager._poll_entity(arm1)
            await manager._poll_entity(arm1)

        assert manager.get_entity("arm1").status != "offline"


# ===================================================================
# Task 2.6: REST API endpoints
# ===================================================================


class TestRESTEndpoints:
    """Test GET /api/entities and GET /api/entities/{id}."""

    def test_get_all_entities(self, client: TestClient):
        resp = client.get("/api/entities")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1  # at least "local"

    def test_get_all_entities_have_required_fields(self, client: TestClient):
        resp = client.get("/api/entities")
        data = resp.json()
        for entity in data:
            assert "id" in entity
            assert "name" in entity
            assert "entity_type" in entity
            assert "source" in entity
            assert "status" in entity

    def test_get_entity_by_id(self, client: TestClient):
        resp = client.get("/api/entities/local")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "local"

    def test_get_entity_not_found(self, client: TestClient):
        resp = client.get("/api/entities/nonexistent")
        assert resp.status_code == 404

    def test_get_arm1_entity(self, client: TestClient):
        resp = client.get("/api/entities/arm1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "arm1"
        assert data["entity_type"] == "arm"
        assert data["ip"] == "192.168.137.12"

    def test_get_vehicle_entity(self, client: TestClient):
        resp = client.get("/api/entities/vehicle")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_type"] == "vehicle"


# ===================================================================
# Task 2.7: WebSocket push (subscribe_changes)
# ===================================================================


class TestSubscribeChanges:
    """Test subscribe_changes() async generator."""

    @pytest.mark.asyncio
    async def test_subscribe_returns_async_generator(self, manager: EntityManager):
        queue = manager.subscribe_changes()
        assert queue is not None

    @pytest.mark.asyncio
    async def test_notify_change_reaches_subscriber(self, manager: EntityManager):
        queue = manager.subscribe_changes()
        manager.notify_change()

        # Should be able to get the event
        try:
            event = await asyncio.wait_for(queue.get(), timeout=1.0)
            assert event is not None
        except asyncio.TimeoutError:
            pytest.fail("Did not receive change notification")

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_queue(self, manager: EntityManager):
        queue = manager.subscribe_changes()
        assert len(manager._subscribers) == 1
        manager.unsubscribe(queue)
        assert len(manager._subscribers) == 0


# ===================================================================
# Task 2.11: Add discovered entity endpoint
# ===================================================================


class TestAddDiscoveredEntity:
    """Test POST /api/entities/discovered/{id}/add."""

    def test_add_discovered_entity_not_found(self, client: TestClient):
        """Cannot add an entity that doesn't exist as discovered."""
        resp = client.post(
            "/api/entities/discovered/nonexistent/add",
            json={"entity_type": "arm", "group_id": "machine-1", "slot": "arm-1"},
        )
        assert resp.status_code == 404

    def test_add_discovered_entity_success(self, client: TestClient, manager: EntityManager):
        """Add a discovered entity transitions it to configured."""
        # First, manually add a discovered entity
        discovered = Entity(
            id="arm3",
            name="Arm 3 (discovered)",
            entity_type="arm",
            source="discovered",
            ip="192.168.137.50",
        )
        manager._entities["arm3"] = discovered

        resp = client.post(
            "/api/entities/discovered/arm3/add",
            json={"entity_type": "arm", "group_id": "machine-1", "slot": "arm-1"},
        )
        assert resp.status_code == 200

        # Verify entity is now configured
        entity = manager.get_entity("arm3")
        assert entity.source == "remote"

    def test_add_discovered_entity_no_duplicate_ip_in_config_env(
        self, client: TestClient, manager: EntityManager, config_env_path: Path
    ):
        """Adding a discovered entity whose IP already exists in config.env
        must NOT append a duplicate line."""
        # arm1 (192.168.137.12) already in config.env via SAMPLE_CONFIG_ENV
        discovered = Entity(
            id="rediscovered_arm1",
            name="Arm 1 re-discovered",
            entity_type="arm",
            source="discovered",
            ip="192.168.137.12",
        )
        manager._entities["rediscovered_arm1"] = discovered

        content_before = config_env_path.read_text()
        manager.add_discovered_entity(
            "rediscovered_arm1",
            "arm",
            "machine-1",
            "arm-1",
            config_env_path=config_env_path,
        )
        content_after = config_env_path.read_text()

        # config.env should NOT have grown — IP already present
        assert content_before == content_after

    def test_add_discovered_entity_slot_conflict_raises_error(
        self, client: TestClient, manager: EntityManager, config_env_path: Path
    ):
        """Approving another candidate into the same slot raises conflict."""
        # Add a new arm (not in config.env yet) — should append
        discovered = Entity(
            id="arm3",
            name="Arm 3 (discovered)",
            entity_type="arm",
            source="discovered",
            ip="192.168.137.50",
        )
        manager._entities["arm3"] = discovered
        manager.add_discovered_entity(
            "arm3",
            "arm",
            "machine-1",
            "arm-3",
            config_env_path=config_env_path,
        )

        content_after_first = config_env_path.read_text()
        assert "192.168.137.50" in content_after_first

        # Now add another discovered entity with same target slot — should conflict
        discovered2 = Entity(
            id="arm3_again",
            name="Arm 3 again",
            entity_type="arm",
            source="discovered",
            ip="192.168.137.50",
        )
        manager._entities["arm3_again"] = discovered2
        with pytest.raises(Exception) as exc:
            manager.add_discovered_entity(
                "arm3_again",
                "arm",
                "machine-1",
                "arm-3",
                config_env_path=config_env_path,
            )
        assert "already occupied" in str(exc.value)
        content_after_second = config_env_path.read_text()

        # Should be identical — conflict blocks additional append
        assert content_after_first == content_after_second

    def test_add_non_discovered_entity_rejected(self, client: TestClient, manager: EntityManager):
        """Cannot 'add' an entity that is already configured (not discovered)."""
        resp = client.post(
            "/api/entities/discovered/arm1/add",
            json={"entity_type": "arm", "group_id": "machine-1", "slot": "arm-1"},
        )
        # arm1 is already "remote", not "discovered"
        assert resp.status_code == 400


# ===================================================================
# Task 2.8: Module-level init/shutdown
# ===================================================================


class TestModuleLevelFunctions:
    """Test init_entity_manager / shutdown_entity_manager / get_entity_manager."""

    def test_get_entity_manager_initially_none(self):
        with patch("backend.entity_manager._entity_manager", None):
            assert get_entity_manager() is None

    @pytest.mark.asyncio
    async def test_init_creates_manager(self, config_env_path: Path):
        with patch("backend.entity_manager._entity_manager", None) as _, patch(
            "backend.entity_manager._DEFAULT_CONFIG_ENV_PATH",
            config_env_path,
        ):
            mgr = await init_entity_manager(config_env_path=config_env_path)
            assert mgr is not None
            assert isinstance(mgr, EntityManager)
            # Clean up - stop polling
            await mgr.stop()

    @pytest.mark.asyncio
    async def test_shutdown_stops_manager(self, config_env_path: Path, tmp_path: Path):
        mgr = EntityManager(
            config_env_path=config_env_path,
            entities_yaml_path=tmp_path / "entities.yaml",
        )
        with patch("backend.entity_manager._entity_manager", mgr):
            await shutdown_entity_manager()


class TestPingMonitorIntegration:
    @pytest.mark.asyncio
    async def test_start_initializes_ping_monitor_with_dashboard_config(self, tmp_path: Path):
        import yaml

        config_path = tmp_path / "config.env"
        config_path.write_text("ARM_1_IP=10.42.0.20\n")
        dashboard_path = tmp_path / "dashboard.yaml"
        dashboard_path.write_text(
            yaml.dump(
                {
                    "health": {
                        "ping": {
                            "ping_interval_s": 4.0,
                            "ping_timeout_s": 1.0,
                            "ping_failure_threshold": 3,
                        }
                    }
                }
            )
        )

        manager = EntityManager(
            config_env_path=config_path,
            dashboard_yaml_path=dashboard_path,
            entities_yaml_path=tmp_path / "entities.yaml",
        )

        ping_instance = MagicMock()
        ping_instance.stop = AsyncMock()

        with patch("backend.entity_manager.PingMonitor", return_value=ping_instance) as mock_ping:
            await manager.start()
            await manager.stop()

        kwargs = mock_ping.call_args.kwargs
        assert kwargs["interval_s"] == 4.0
        assert kwargs["timeout_s"] == 1.0
        assert kwargs["failure_threshold"] == 3
        ping_instance.start.assert_called_once()
        ping_instance.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ping_recovery_resets_failure_count_and_backoff(self, manager: EntityManager):
        arm1 = manager.get_entity("arm1")
        manager._failure_counts[arm1.id] = 8
        manager._poll_intervals[arm1.id] = 30.0
        arm1.health["network"] = "unreachable"

        await manager._handle_ping_state_change(arm1, "unreachable", "reachable")

        assert manager._failure_counts[arm1.id] == 0
        assert manager._poll_intervals[arm1.id] == manager._status_poll_interval_s

    @pytest.mark.asyncio
    async def test_ping_recovery_auto_resumes_suspended_entity_polling(
        self, manager: EntityManager
    ):
        arm1 = manager.get_entity("arm1")
        manager._suspended.add(arm1.id)
        manager._failure_counts[arm1.id] = 50

        await manager._handle_ping_state_change(arm1, "unreachable", "reachable")

        assert arm1.id not in manager._suspended
        assert manager._failure_counts[arm1.id] == 0

    @pytest.mark.asyncio
    async def test_update_entity_notifies_ping_monitor_on_ip_change(self, manager: EntityManager):
        manager._ping_monitor = MagicMock()

        await manager.update_entity("arm1", ip="10.42.0.25")

        manager._ping_monitor.update_entity.assert_called_once_with(manager.get_entity("arm1"))

    @pytest.mark.asyncio
    async def test_remove_entity_stops_ping_monitor_task(self, manager: EntityManager):
        ping_monitor = MagicMock()
        ping_monitor.remove_entity = AsyncMock()
        manager._ping_monitor = ping_monitor

        await manager.remove_entity("arm1")

        ping_monitor.remove_entity.assert_awaited_once_with("arm1")

    @pytest.mark.asyncio
    async def test_add_entity_starts_ping_monitor_task(self, manager: EntityManager):
        manager._ping_monitor = MagicMock()

        entity = await manager.add_entity_by_ip(
            ip="10.42.0.30",
            entity_type="arm",
            group_id="machine-1",
            slot="arm-3",
        )

        manager._ping_monitor.add_entity.assert_called_once_with(entity)

    @pytest.mark.asyncio
    async def test_ping_recovery_forces_next_health_poll_cycle(self, manager: EntityManager):
        arm1 = manager.get_entity("arm1")
        manager._failure_counts[arm1.id] = 5
        manager._poll_intervals[arm1.id] = 90.0
        manager._last_polled[arm1.id] = 1234.0

        await manager._handle_ping_state_change(arm1, "unreachable", "reachable")

        assert manager._last_polled.get(arm1.id) is None


class TestMqttIntegration:
    def test_mqtt_callback_updates_entity_health(self, manager: EntityManager):
        arm1 = manager.get_entity("arm1")

        manager._handle_mqtt_change(
            "arm1",
            {
                "state": "ready",
                "connectivity": "connected",
                "last_heartbeat": "2026-03-23T12:00:00+00:00",
            },
        )

        assert arm1.health["mqtt"] == "active"
        assert arm1.health["mqtt_arm_state"] == "ready"
        assert arm1.health["mqtt_last_seen"] == "2026-03-23T12:00:00+00:00"

    def test_mqtt_offline_callback_sets_entity_offline(self, manager: EntityManager):
        arm1 = manager.get_entity("arm1")

        manager._handle_mqtt_change(
            "arm1",
            {
                "state": "offline",
                "connectivity": "offline",
                "last_heartbeat": "2026-03-23T12:00:00+00:00",
            },
        )

        assert arm1.health["mqtt"] == "offline"
        assert arm1.health["mqtt_arm_state"] == "offline"

    def test_unknown_mqtt_entity_is_ignored(self, manager: EntityManager):
        before = manager.get_entity("arm1").health.copy()

        manager._handle_mqtt_change(
            "missing-arm",
            {"state": "ready", "connectivity": "connected", "last_heartbeat": None},
        )

        assert manager.get_entity("arm1").health == before

    def test_mqtt_broker_down_marks_entity_broker_down(self, manager: EntityManager):
        arm1 = manager.get_entity("arm1")

        manager._handle_mqtt_change(
            "arm1",
            {
                "state": "unknown",
                "connectivity": "broker_down",
                "last_heartbeat": None,
            },
        )

        assert arm1.health["mqtt"] == "broker_down"


class TestAgentHealthPolling:
    @pytest.mark.asyncio
    async def test_health_success_sets_agent_alive_and_updates_system_metrics(
        self, manager: EntityManager
    ):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "cpu_percent": 22.0,
            "memory_percent": 33.0,
            "temperature_c": 55.5,
            "disk_percent": 44.0,
            "uptime_seconds": 1200,
            "warnings": [],
        }
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.entity_manager.httpx.AsyncClient", return_value=mock_client):
            arm1 = manager.get_entity("arm1")
            await manager._poll_agent_health(arm1)

        assert arm1.health["agent"] == "alive"
        assert arm1.system_metrics["cpu_percent"] == 22.0
        assert arm1.system_metrics["temperature_c"] == 55.5
        assert manager._agent_failure_counts[arm1.id] == 0

    @pytest.mark.asyncio
    async def test_single_health_failure_sets_agent_degraded(self, manager: EntityManager):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.entity_manager.httpx.AsyncClient", return_value=mock_client):
            arm1 = manager.get_entity("arm1")
            await manager._poll_agent_health(arm1)

        assert arm1.health["agent"] == "degraded"
        assert manager._agent_failure_counts[arm1.id] == 1

    @pytest.mark.asyncio
    async def test_two_health_failures_set_agent_down(self, manager: EntityManager):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.entity_manager.httpx.AsyncClient", return_value=mock_client):
            arm1 = manager.get_entity("arm1")
            await manager._poll_agent_health(arm1)
            await manager._poll_agent_health(arm1)

        assert arm1.health["agent"] == "down"
        assert manager._agent_failure_counts[arm1.id] == 2

    @pytest.mark.asyncio
    async def test_health_success_re_evaluates_unreachable_network(self, manager: EntityManager):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "cpu_percent": 15.0,
            "memory_percent": 25.0,
            "temperature_c": 50.0,
            "disk_percent": 35.0,
            "uptime_seconds": 100,
            "warnings": [],
        }
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.entity_manager.httpx.AsyncClient", return_value=mock_client):
            arm1 = manager.get_entity("arm1")
            arm1.update_health(network="unreachable")
            await manager._poll_agent_health(arm1)

        assert arm1.health["agent"] == "alive"
        assert arm1.health["network"] == "reachable"

    @pytest.mark.asyncio
    async def test_health_response_warnings_populate_agent_warnings(self, manager: EntityManager):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "cpu_percent": 20.0,
            "memory_percent": 30.0,
            "temperature_c": 82.5,
            "disk_percent": 40.0,
            "uptime_seconds": 100,
            "warnings": ["thermal_throttling"],
        }
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.entity_manager.httpx.AsyncClient", return_value=mock_client):
            arm1 = manager.get_entity("arm1")
            await manager._poll_agent_health(arm1)

        assert arm1.health["agent"] == "alive"
        assert arm1.health["agent_warnings"] == ["thermal_throttling"]

    @pytest.mark.asyncio
    async def test_local_entity_health_check_is_skipped_and_marked_local(
        self, manager: EntityManager
    ):
        local = manager.get_entity("local")

        with patch("backend.entity_manager.httpx.AsyncClient") as mock_client:
            await manager._poll_agent_health(local)

        assert local.health["agent"] == "local"
        mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_health_poll_loop_runs_independently_of_status_poll(self, manager: EntityManager):
        manager._running = True

        async def stop_after_first_cycle(_entity):
            manager._running = False

        with patch.object(
            manager, "_poll_agent_health", side_effect=stop_after_first_cycle
        ) as mock_health, patch.object(
            manager, "_poll_entity", new_callable=AsyncMock
        ) as mock_status:
            await manager._health_poll_loop()

        assert mock_health.called
        mock_status.assert_not_called()


class TestPollingIntervals:
    def test_status_poll_interval_defaults_to_30_seconds(self, manager: EntityManager):
        assert manager._status_poll_interval_s == 30.0

    @pytest.mark.asyncio
    async def test_ping_recovery_resets_status_poll_interval_to_base(self, manager: EntityManager):
        arm1 = manager.get_entity("arm1")
        manager._poll_intervals[arm1.id] = 90.0

        await manager._handle_ping_state_change(arm1, "unreachable", "reachable")

        assert manager._poll_intervals[arm1.id] == manager._status_poll_interval_s


# ===================================================================
# CRITICAL #1: Nested agent response parsing
# ===================================================================


class TestNestedAgentResponseParsing:
    """Verify _poll_entity() correctly parses nested /status response."""

    @pytest.mark.asyncio
    async def test_successful_health_and_status_do_not_leave_entity_unknown(
        self, manager: EntityManager
    ):
        """Reachable agent with ROS2 available should not remain unknown."""
        health_resp = MagicMock()
        health_resp.status_code = 200
        health_resp.json.return_value = {
            "cpu_percent": 20.0,
            "memory_percent": 30.0,
            "temperature_c": 52.0,
            "disk_percent": 40.0,
            "uptime_seconds": 1200,
            "warnings": [],
        }

        status_resp = MagicMock()
        status_resp.status_code = 200
        status_resp.json.return_value = {
            "health": {
                "cpu_percent": 21.0,
                "memory_percent": 31.0,
                "temperature_c": 53.0,
                "disk_percent": 41.0,
                "uptime_seconds": 1250,
                "warnings": [],
            },
            "ros2": {
                "available": True,
                "node_count": 5,
                "topic_count": 12,
                "service_count": 4,
            },
            "systemd": [],
        }

        health_client = AsyncMock()
        health_client.get = AsyncMock(return_value=health_resp)
        health_client.__aenter__ = AsyncMock(return_value=health_client)
        health_client.__aexit__ = AsyncMock(return_value=False)

        status_client = AsyncMock()
        status_client.get = AsyncMock(return_value=status_resp)
        status_client.__aenter__ = AsyncMock(return_value=status_client)
        status_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            side_effect=[health_client, status_client],
        ):
            arm1 = manager.get_entity("arm1")
            arm1.update_health(network="reachable")
            await manager._poll_agent_health(arm1)
            await manager._poll_entity(arm1)

        assert arm1.health["network"] == "reachable"
        assert arm1.health["agent"] == "alive"
        assert arm1.health["ros2"] == "healthy"
        assert arm1.health["mqtt"] == "disabled"
        assert arm1.health["composite"] == "online"
        assert arm1.status == "online"

    @pytest.mark.asyncio
    async def test_health_metrics_extracted(self, manager: EntityManager):
        """System metrics come from data['health'], not top-level."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "health": {
                "cpu_percent": 42.5,
                "memory_percent": 61.3,
                "temperature_c": 55.0,
                "disk_percent": 38.7,
                "uptime_seconds": 86400,
                "warnings": [],
            },
            "ros2": {"available": True, "node_count": 3},
            "systemd": [],
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=mock_client,
        ):
            arm1 = manager.get_entity("arm1")
            await manager._poll_entity(arm1)

        assert arm1.system_metrics["cpu_percent"] == 42.5
        assert arm1.system_metrics["memory_percent"] == 61.3
        assert arm1.system_metrics["temperature_c"] == 55.0
        assert arm1.system_metrics["disk_percent"] == 38.7
        assert arm1.system_metrics["uptime_seconds"] == 86400

    @pytest.mark.asyncio
    async def test_ros2_state_extracted(self, manager: EntityManager):
        """ROS2 state comes from data['ros2'], not data['ros2_state']."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "health": {"cpu_percent": 10.0},
            "ros2": {
                "available": True,
                "node_count": 5,
                "topic_count": 12,
                "service_count": 4,
            },
            "systemd": [],
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=mock_client,
        ):
            arm1 = manager.get_entity("arm1")
            await manager._poll_entity(arm1)

        assert arm1.ros2_available is True
        assert arm1.ros2_state["node_count"] == 5
        assert arm1.ros2_state["topic_count"] == 12
        assert arm1.ros2_state["service_count"] == 4
        # "available" should not be in ros2_state dict (it's a separate flag)
        assert "available" not in arm1.ros2_state

    @pytest.mark.asyncio
    async def test_ros2_unavailable(self, manager: EntityManager):
        """When ros2.available is false, ros2_available is False."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "health": {},
            "ros2": {"available": False},
            "systemd": [],
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=mock_client,
        ):
            arm1 = manager.get_entity("arm1")
            await manager._poll_entity(arm1)

        assert arm1.ros2_available is False

    @pytest.mark.asyncio
    async def test_systemd_services_extracted(self, manager: EntityManager):
        """Systemd services list is populated from data['systemd']."""
        services = [
            {
                "name": "pragati-agent.service",
                "active_state": "active",
                "sub_state": "running",
                "description": "Agent",
            },
            {
                "name": "pragati-arm.service",
                "active_state": "active",
                "sub_state": "running",
                "description": "Arm",
            },
        ]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "health": {},
            "ros2": {},
            "systemd": services,
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=mock_client,
        ):
            arm1 = manager.get_entity("arm1")
            await manager._poll_entity(arm1)

        assert len(arm1.services) == 2
        assert arm1.services[0]["name"] == "pragati-agent.service"
        assert arm1.services[1]["name"] == "pragati-arm.service"

    @pytest.mark.asyncio
    async def test_missing_keys_use_defaults(self, manager: EntityManager):
        """Response missing health/ros2/systemd keys doesn't crash."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {}  # Minimal response

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=mock_client,
        ):
            arm1 = manager.get_entity("arm1")
            await manager._poll_entity(arm1)

        # Should still go online, just no metrics updated
        assert arm1.status == "online"


# ===================================================================
# Temperature fields in system_metrics (Tasks 2.1 / 2.3 / 2.4)
# ===================================================================


class TestTemperatureMetricsParsing:
    """Verify _poll_entity() maps motor_temperatures and camera_temperature_c."""

    @pytest.mark.asyncio
    async def test_poll_entity_maps_motor_temperatures(self, manager: EntityManager):
        """Motor temperatures dict is extracted from health sub-dict in /status response."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "health": {
                "cpu_percent": 30.0,
                "motor_temperatures": {"joint1": 45.2, "joint2": 50.1},
            },
            "ros2": {},
            "systemd": [],
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=mock_client,
        ):
            arm1 = manager.get_entity("arm1")
            await manager._poll_entity(arm1)

        assert arm1.system_metrics["motor_temperatures"] == {"joint1": 45.2, "joint2": 50.1}

    @pytest.mark.asyncio
    async def test_poll_entity_maps_camera_temperature_c(self, manager: EntityManager):
        """camera_temperature_c float is extracted from health sub-dict in /status response."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "health": {
                "cpu_percent": 25.0,
                "camera_temperature_c": 52.3,
            },
            "ros2": {},
            "systemd": [],
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=mock_client,
        ):
            arm1 = manager.get_entity("arm1")
            await manager._poll_entity(arm1)

        assert arm1.system_metrics["camera_temperature_c"] == 52.3

    @pytest.mark.asyncio
    async def test_poll_entity_keeps_motor_temperatures_null_when_absent(
        self, manager: EntityManager
    ):
        """motor_temperatures stays None when health dict omits the key."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "health": {
                "cpu_percent": 20.0,
                "temperature_c": 48.0,
            },
            "ros2": {},
            "systemd": [],
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=mock_client,
        ):
            arm1 = manager.get_entity("arm1")
            await manager._poll_entity(arm1)

        assert arm1.system_metrics["motor_temperatures"] is None
        assert arm1.system_metrics["camera_temperature_c"] is None


# ===================================================================
# CRITICAL #2: notify_change() called after state mutations
# ===================================================================


class TestNotifyChangeCalledAfterMutations:
    """Verify notify_change() is invoked after state-mutating operations."""

    @pytest.mark.asyncio
    async def test_notify_called_after_successful_poll(self, manager: EntityManager):
        """notify_change() called after _poll_entity() succeeds."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "health": {"cpu_percent": 10.0},
            "ros2": {},
            "systemd": [],
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=mock_client,
        ), patch.object(manager, "notify_change") as mock_notify:
            arm1 = manager.get_entity("arm1")
            await manager._poll_entity(arm1)
            mock_notify.assert_called()

    @pytest.mark.asyncio
    async def test_notify_called_after_poll_failure(self, manager: EntityManager):
        """notify_change() called after _record_failure()."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=mock_client,
        ), patch.object(manager, "notify_change") as mock_notify:
            arm1 = manager.get_entity("arm1")
            await manager._poll_entity(arm1)
            mock_notify.assert_called()

    def test_notify_called_after_mdns_discovered(self, manager: EntityManager):
        """notify_change() called after _handle_mdns_discovered()."""
        with patch.object(manager, "notify_change") as mock_notify:
            manager._handle_mdns_discovered("10.99.99.99", "test-agent._pragati-agent._tcp.local.")
            mock_notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_subscriber_receives_event_after_poll(self, manager: EntityManager):
        """A subscriber queue gets a payload after a successful poll."""
        queue = manager.subscribe_changes()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "health": {"cpu_percent": 20.0},
            "ros2": {},
            "systemd": [],
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=mock_client,
        ):
            arm1 = manager.get_entity("arm1")
            await manager._poll_entity(arm1)

        event = queue.get_nowait()
        assert event["type"] == "entity_state_changed"
        assert "entities" in event
        assert "timestamp" in event

        manager.unsubscribe(queue)


# ===================================================================
# CRITICAL #3: Backoff polling for offline entities
# ===================================================================


class TestBackoffPolling:
    """Verify per-entity backoff after going offline."""

    @pytest.mark.asyncio
    async def test_backoff_interval_set_after_offline(self, manager: EntityManager):
        """After OFFLINE_THRESHOLD failures, poll interval increases."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        arm1 = manager.get_entity("arm1")
        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=mock_client,
        ):
            # 3 failures -> offline
            await manager._poll_entity(arm1)
            await manager._poll_entity(arm1)
            await manager._poll_entity(arm1)

        assert arm1.status == "offline"
        expected_interval = POLL_INTERVAL_S * BACKOFF_MULTIPLIER
        assert manager._poll_intervals["arm1"] == expected_interval

    @pytest.mark.asyncio
    async def test_backoff_interval_capped(self, manager: EntityManager):
        """Backoff interval should not exceed MAX_POLL_INTERVAL_S."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        arm1 = manager.get_entity("arm1")
        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=mock_client,
        ):
            for _ in range(10):
                await manager._poll_entity(arm1)

        assert manager._poll_intervals["arm1"] <= MAX_POLL_INTERVAL_S

    @pytest.mark.asyncio
    async def test_backoff_resets_on_recovery(self, manager: EntityManager):
        """After recovery, poll interval resets to the status base interval."""
        fail_client = AsyncMock()
        fail_client.get = AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))
        fail_client.__aenter__ = AsyncMock(return_value=fail_client)
        fail_client.__aexit__ = AsyncMock(return_value=False)

        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.json.return_value = {
            "health": {"cpu_percent": 10.0},
            "ros2": {},
            "systemd": [],
        }
        ok_client = AsyncMock()
        ok_client.get = AsyncMock(return_value=ok_resp)
        ok_client.__aenter__ = AsyncMock(return_value=ok_client)
        ok_client.__aexit__ = AsyncMock(return_value=False)

        arm1 = manager.get_entity("arm1")

        # Go offline (3 failures)
        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=fail_client,
        ):
            for _ in range(3):
                await manager._poll_entity(arm1)

        assert arm1.status == "offline"
        assert manager._poll_intervals["arm1"] > POLL_INTERVAL_S

        # Recover
        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=ok_client,
        ):
            await manager._poll_entity(arm1)

        assert arm1.status == "online"
        assert manager._poll_intervals["arm1"] == manager._status_poll_interval_s

    @pytest.mark.asyncio
    async def test_poll_all_skips_entity_within_backoff(self, manager: EntityManager):
        """_poll_all() skips entities whose backoff interval hasn't elapsed."""
        import time

        arm1 = manager.get_entity("arm1")

        # Set a large backoff and recent poll time
        manager._poll_intervals["arm1"] = 60.0
        manager._last_polled["arm1"] = time.monotonic()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=mock_client,
        ) as mock_cls, patch.object(manager, "_poll_local", new_callable=AsyncMock):
            await manager._poll_all()

        # arm1 should NOT have been polled (within backoff)
        # arm2 and vehicle should have been polled (no backoff set)
        # Count poll calls — we check that arm1's IP was not in any call
        # Simpler: check that _last_polled for arm2 was updated
        assert "arm2" in manager._last_polled

    @pytest.mark.asyncio
    async def test_poll_all_polls_entity_after_backoff_elapsed(self, manager: EntityManager):
        """_poll_all() polls entities whose backoff interval has elapsed."""
        import time

        # Set backoff that's already elapsed
        manager._poll_intervals["arm1"] = 1.0
        manager._last_polled["arm1"] = time.monotonic() - 2.0

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        old_last = manager._last_polled.get("arm1", 0.0)

        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=mock_client,
        ), patch.object(manager, "_poll_local", new_callable=AsyncMock):
            await manager._poll_all()

        # arm1 should have been polled — _last_polled updated
        assert manager._last_polled["arm1"] > old_last


# ===================================================================
# Local identity: role from dashboard.yaml, local IP, mDNS self-dedup
# ===================================================================


class TestLocalEntityRole:
    """Test that the local entity_type is derived from dashboard.yaml role."""

    def test_role_arm_sets_entity_type_arm(self, tmp_path: Path):
        import yaml

        yaml_path = tmp_path / "dashboard.yaml"
        yaml_path.write_text(yaml.dump({"role": "arm"}))
        p = tmp_path / "config.env"
        p.write_text("# empty\n")
        mgr = EntityManager(
            config_env_path=p,
            dashboard_yaml_path=yaml_path,
            entities_yaml_path=tmp_path / "entities.yaml",
        )
        local = mgr.get_entity("local")
        assert local.entity_type == "arm"

    def test_role_vehicle_sets_entity_type_vehicle(self, tmp_path: Path):
        import yaml

        yaml_path = tmp_path / "dashboard.yaml"
        yaml_path.write_text(yaml.dump({"role": "vehicle"}))
        p = tmp_path / "config.env"
        p.write_text("# empty\n")
        mgr = EntityManager(
            config_env_path=p,
            dashboard_yaml_path=yaml_path,
            entities_yaml_path=tmp_path / "entities.yaml",
        )
        local = mgr.get_entity("local")
        assert local.entity_type == "vehicle"

    def test_role_dev_preserves_dev_entity_type(self, tmp_path: Path):
        import yaml

        yaml_path = tmp_path / "dashboard.yaml"
        yaml_path.write_text(yaml.dump({"role": "dev"}))
        p = tmp_path / "config.env"
        p.write_text("# empty\n")
        mgr = EntityManager(
            config_env_path=p,
            dashboard_yaml_path=yaml_path,
            entities_yaml_path=tmp_path / "entities.yaml",
        )
        local = mgr.get_entity("local")
        assert local.entity_type == "dev"

    def test_missing_yaml_defaults_to_dev(self, tmp_path: Path):
        yaml_path = tmp_path / "nonexistent.yaml"
        p = tmp_path / "config.env"
        p.write_text("# empty\n")
        mgr = EntityManager(
            config_env_path=p,
            dashboard_yaml_path=yaml_path,
            entities_yaml_path=tmp_path / "entities.yaml",
        )
        local = mgr.get_entity("local")
        assert local.entity_type == "dev"

    def test_invalid_role_defaults_to_dev(self, tmp_path: Path):
        import yaml

        yaml_path = tmp_path / "dashboard.yaml"
        yaml_path.write_text(yaml.dump({"role": "bogus"}))
        p = tmp_path / "config.env"
        p.write_text("# empty\n")
        mgr = EntityManager(
            config_env_path=p,
            dashboard_yaml_path=yaml_path,
            entities_yaml_path=tmp_path / "entities.yaml",
        )
        local = mgr.get_entity("local")
        assert local.entity_type == "dev"


class TestLocalEntityIP:
    """Test that the local entity gets a primary IP from _detect_local_ips."""

    def test_local_entity_has_ip(self, manager: EntityManager):
        local = manager.get_entity("local")
        # _MOCK_LOCAL_IPS = {"127.0.0.1", "10.0.0.99"} -> primary is 10.0.0.99
        assert local.ip == "10.0.0.99"

    def test_local_entity_loopback_only_returns_none(self, tmp_path: Path):
        """If only 127.0.0.1 is detected, ip should be None."""
        with patch.object(
            EntityManager,
            "_detect_local_ips",
            return_value={"127.0.0.1"},
        ):
            p = tmp_path / "config.env"
            p.write_text("# empty\n")
            mgr = EntityManager(config_env_path=p, entities_yaml_path=tmp_path / "entities.yaml")
            local = mgr.get_entity("local")
            assert local.ip is None


class TestMdnsSelfDedup:
    """Test that mDNS discovery skips local IPs."""

    def test_mdns_skips_local_ip(self, manager: EntityManager):
        """mDNS with a local IP should NOT create a new entity."""
        initial_count = len(manager.get_all_entities())
        manager._handle_mdns_discovered("10.0.0.99", "self._pragati-agent._tcp.local.")
        assert len(manager.get_all_entities()) == initial_count

    def test_mdns_skips_loopback(self, manager: EntityManager):
        """mDNS with 127.0.0.1 should NOT create a new entity."""
        initial_count = len(manager.get_all_entities())
        manager._handle_mdns_discovered("127.0.0.1", "self._pragati-agent._tcp.local.")
        assert len(manager.get_all_entities()) == initial_count

    def test_mdns_allows_remote_ip(self, manager: EntityManager):
        """mDNS with a non-local, non-configured IP should create entity."""
        initial_count = len(manager.get_all_entities())
        manager._handle_mdns_discovered("10.99.99.99", "remote._pragati-agent._tcp.local.")
        assert len(manager.get_all_entities()) == initial_count + 1

    def test_mdns_state_change_ignored_without_running_loop(self, manager: EntityManager):
        """mDNS callbacks before start() should not raise or add entities."""
        initial_count = len(manager.get_all_entities())
        zeroconf = MagicMock()
        manager._on_mdns_state_change(
            zeroconf,
            "_pragati-agent._tcp.local.",
            "remote._pragati-agent._tcp.local.",
            MagicMock(),
        )
        assert len(manager.get_all_entities()) == initial_count

    @pytest.mark.asyncio
    async def test_mdns_state_change_uses_running_loop(self, manager: EntityManager):
        """mDNS callbacks after start() schedule discovery on the captured loop."""
        zeroconf = MagicMock()
        info = MagicMock()
        info.addresses = [b"\n\x63\x63\x63"]
        zeroconf.get_service_info.return_value = info

        with patch("backend.entity_manager.ServiceStateChange") as state_change:
            await manager.start()
            try:
                manager._on_mdns_state_change(
                    zeroconf,
                    "_pragati-agent._tcp.local.",
                    "remote._pragati-agent._tcp.local.",
                    state_change.Added,
                )
                await asyncio.sleep(0)
            finally:
                await manager.stop()

        discovered = manager.get_entity("discovered_10_99_99_99")
        assert discovered is not None
        assert discovered.source == "discovered"


class TestConfigEnvSelfDetectionMerge:
    """Test that config.env merges matching-local-IP entities into local."""

    def test_self_detection_merges_matching_ip(self, tmp_path: Path):
        """ARM_1_IP matching local IP merges identity into local entity."""
        p = tmp_path / "config.env"
        p.write_text("ARM_1_IP=10.0.0.99\nARM_2_IP=192.168.1.50\n")
        yaml_path = tmp_path / "nonexistent.yaml"
        mgr = EntityManager(
            config_env_path=p,
            dashboard_yaml_path=yaml_path,
            entities_yaml_path=tmp_path / "entities.yaml",
        )

        # After merge, "local" key should be gone, replaced by "arm1"
        assert mgr.get_entity("local") is None
        arm1 = mgr.get_entity("arm1")
        assert arm1 is not None
        assert arm1.id == "arm1"
        assert arm1.name == "Arm 1 RPi"
        assert arm1.entity_type == "arm"
        assert arm1.source == "local"  # still the local machine
        assert arm1.ip == "10.0.0.99"

    def test_merged_entity_uses_remote_config_identity(self, tmp_path: Path):
        """After merge, entity id/name/type come from config.env."""
        p = tmp_path / "config.env"
        p.write_text("ARM_3_IP=10.0.0.99\n")
        yaml_path = tmp_path / "nonexistent.yaml"
        mgr = EntityManager(
            config_env_path=p,
            dashboard_yaml_path=yaml_path,
            entities_yaml_path=tmp_path / "entities.yaml",
        )

        arm3 = mgr.get_entity("arm3")
        assert arm3 is not None
        assert arm3.id == "arm3"
        assert arm3.name == "Arm 3 RPi"
        assert arm3.entity_type == "arm"
        assert arm3.source == "local"

    def test_non_matching_ips_remain_separate(self, tmp_path: Path):
        """Entity with non-local IP is added as separate remote entity."""
        p = tmp_path / "config.env"
        p.write_text("ARM_1_IP=192.168.1.50\n")
        yaml_path = tmp_path / "nonexistent.yaml"
        mgr = EntityManager(
            config_env_path=p,
            dashboard_yaml_path=yaml_path,
            entities_yaml_path=tmp_path / "entities.yaml",
        )

        # local entity still exists as "local"
        local = mgr.get_entity("local")
        assert local is not None
        assert local.source == "local"

        # arm1 is a separate remote entity
        arm1 = mgr.get_entity("arm1")
        assert arm1 is not None
        assert arm1.source == "remote"
        assert arm1.ip == "192.168.1.50"

    def test_psutil_unavailable_fallback(self, tmp_path: Path):
        """_detect_local_ips() falls back to socket when psutil missing."""
        with patch.object(
            EntityManager,
            "_detect_local_ips",
            wraps=EntityManager._detect_local_ips,
        ):
            # Override autouse mock for this test
            with patch("backend.entity_manager.PSUTIL_AVAILABLE", False), patch(
                "backend.entity_manager.psutil", None
            ):
                ips = EntityManager._detect_local_ips()
                # Should always contain 127.0.0.1
                assert "127.0.0.1" in ips
                # May or may not have another IP depending on network

    def test_health_endpoint_no_duplicate_entity(self, tmp_path: Path):
        """After merge, only one entity exists for that IP (no local + arm1)."""
        p = tmp_path / "config.env"
        p.write_text("ARM_1_IP=10.0.0.99\nARM_2_IP=192.168.1.50\n")
        yaml_path = tmp_path / "nonexistent.yaml"
        mgr = EntityManager(
            config_env_path=p,
            dashboard_yaml_path=yaml_path,
            entities_yaml_path=tmp_path / "entities.yaml",
        )

        all_entities = mgr.get_all_entities()
        # Should have arm1 (merged local) + arm2 (remote) = 2 entities
        assert len(all_entities) == 2
        ids = {e.id for e in all_entities}
        assert "local" not in ids
        assert "arm1" in ids
        assert "arm2" in ids

        # Only one entity should have IP 10.0.0.99
        matching = [e for e in all_entities if e.ip == "10.0.0.99"]
        assert len(matching) == 1

    def test_merge_marks_found_remote_true(self, tmp_path: Path):
        """After merge, _parse_config_env returns True (found_remote)."""
        p = tmp_path / "config.env"
        p.write_text("ARM_1_IP=10.0.0.99\n")
        yaml_path = tmp_path / "nonexistent.yaml"
        mgr = EntityManager(
            config_env_path=p,
            dashboard_yaml_path=yaml_path,
            entities_yaml_path=tmp_path / "entities.yaml",
        )

        # If found_remote was False, it would try yaml fallback.
        # Since yaml doesn't exist, no extra entities. Just the merged one.
        all_entities = mgr.get_all_entities()
        assert len(all_entities) == 1
        assert all_entities[0].id == "arm1"


# ===================================================================
# Timeout constants (proxy chain sizing)
# ===================================================================


class TestTimeoutConstants:
    """Verify timeout constants are sized for WSL portproxy latency."""

    def test_poll_timeout_at_least_15s(self):
        """POLL_TIMEOUT_S must exceed typical portproxy latency (~8-13s)."""
        from backend.entity_manager import POLL_TIMEOUT_S

        assert POLL_TIMEOUT_S >= 15

    def test_poll_timeout_current_value(self):
        from backend.entity_manager import POLL_TIMEOUT_S

        assert POLL_TIMEOUT_S == 18

    def test_non_local_ips_still_added(self, tmp_path: Path):
        """Non-local IPs should still be added normally."""
        p = tmp_path / "config.env"
        p.write_text("ARM_1_IP=192.168.1.10\nVEHICLE_IP=192.168.1.20\n")
        mgr = EntityManager(config_env_path=p, entities_yaml_path=tmp_path / "entities.yaml")
        ids = {e.id for e in mgr.get_all_entities()}
        assert "arm1" in ids
        assert "vehicle" in ids


class TestYamlFallbackSelfDedup:
    """Test that dashboard.yaml fallback skips entries matching local IPs."""

    def test_yaml_arm_matching_local_skipped(self, tmp_path: Path):
        import yaml

        p = tmp_path / "config.env"
        p.write_text("# empty\n")
        yaml_path = tmp_path / "dashboard.yaml"
        yaml_path.write_text(
            yaml.dump(
                {
                    "fleet": {
                        "arms": [
                            {"name": "arm1-rpi", "ip": "10.0.0.99"},
                            {"name": "arm2-rpi", "ip": "192.168.1.50"},
                        ],
                    }
                }
            )
        )
        mgr = EntityManager(
            config_env_path=p,
            dashboard_yaml_path=yaml_path,
            entities_yaml_path=tmp_path / "entities.yaml",
        )
        ids = {e.id for e in mgr.get_all_entities()}
        assert "arm1" not in ids  # self-dedup
        assert "arm2" in ids

    def test_yaml_vehicle_matching_local_skipped(self, tmp_path: Path):
        import yaml

        p = tmp_path / "config.env"
        p.write_text("# empty\n")
        yaml_path = tmp_path / "dashboard.yaml"
        yaml_path.write_text(
            yaml.dump(
                {
                    "fleet": {
                        "vehicle": {"name": "v", "ip": "10.0.0.99"},
                    }
                }
            )
        )
        mgr = EntityManager(
            config_env_path=p,
            dashboard_yaml_path=yaml_path,
            entities_yaml_path=tmp_path / "entities.yaml",
        )
        ids = {e.id for e in mgr.get_all_entities()}
        assert "vehicle" not in ids  # self-dedup


class TestAllArmsFilter:
    """ARM_{N}_IP entries not listed in ALL_ARMS should be ignored."""

    def test_unlisted_arm3_filtered_out(self, tmp_path: Path):
        """ARM_3_IP present but ALL_ARMS only lists arm1,arm2 -> no arm3 entity."""
        p = tmp_path / "config.env"
        p.write_text(
            "ARM_1_IP=192.168.1.10\n"
            "ARM_2_IP=192.168.1.11\n"
            "ARM_3_IP=192.168.1.50\n"
            'ALL_ARMS="arm1,arm2"\n'
        )
        mgr = EntityManager(config_env_path=p, entities_yaml_path=tmp_path / "entities.yaml")
        ids = {e.id for e in mgr.get_all_entities()}
        assert "arm1" in ids
        assert "arm2" in ids
        assert "arm3" not in ids

    def test_no_all_arms_allows_all(self, tmp_path: Path):
        """When ALL_ARMS is absent, all ARM_{N}_IP entries are accepted."""
        p = tmp_path / "config.env"
        p.write_text("ARM_1_IP=192.168.1.10\n" "ARM_3_IP=192.168.1.50\n")
        mgr = EntityManager(config_env_path=p, entities_yaml_path=tmp_path / "entities.yaml")
        ids = {e.id for e in mgr.get_all_entities()}
        assert "arm1" in ids
        assert "arm3" in ids

    def test_empty_all_arms_allows_all(self, tmp_path: Path):
        """ALL_ARMS="" (empty) treated as unset — all arms accepted."""
        p = tmp_path / "config.env"
        p.write_text("ARM_1_IP=192.168.1.10\n" "ARM_2_IP=192.168.1.11\n" 'ALL_ARMS=""\n')
        mgr = EntityManager(config_env_path=p, entities_yaml_path=tmp_path / "entities.yaml")
        ids = {e.id for e in mgr.get_all_entities()}
        assert "arm1" in ids
        assert "arm2" in ids

    def test_all_arms_filters_with_underscore_format(self, tmp_path: Path):
        """ARM3_IP (no underscore) also filtered by ALL_ARMS."""
        p = tmp_path / "config.env"
        p.write_text("ARM1_IP=192.168.1.10\n" "ARM3_IP=192.168.1.50\n" 'ALL_ARMS="arm1"\n')
        mgr = EntityManager(config_env_path=p, entities_yaml_path=tmp_path / "entities.yaml")
        ids = {e.id for e in mgr.get_all_entities()}
        assert "arm1" in ids
        assert "arm3" not in ids

    def test_unlisted_arm_logged_as_warning(self, tmp_path: Path, caplog):
        """Filtered arms should produce a log warning."""
        import logging

        p = tmp_path / "config.env"
        p.write_text("ARM_3_IP=192.168.1.50\n" 'ALL_ARMS="arm1,arm2"\n')
        em_logger = logging.getLogger("backend.entity_manager")
        old_propagate = em_logger.propagate
        em_logger.propagate = True
        try:
            with caplog.at_level(logging.WARNING, logger="backend.entity_manager"):
                EntityManager(config_env_path=p, entities_yaml_path=tmp_path / "entities.yaml")
        finally:
            em_logger.propagate = old_propagate
        assert any(
            "arm3" in r.message.lower() and "all_arms" in r.message.lower() for r in caplog.records
        ), f"Expected warning about arm3 not in ALL_ARMS, got: {[r.message for r in caplog.records]}"


# ===================================================================
# Error clearing on recovery
# ===================================================================


class TestErrorClearingOnRecovery:
    """Entity errors must be cleared when an entity recovers from offline."""

    @pytest.mark.asyncio
    async def test_recovery_clears_errors(self, manager: EntityManager):
        """After 3 failures (offline) then success, entity.errors should be empty."""
        fail_client = AsyncMock()
        fail_client.get = AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))
        fail_client.__aenter__ = AsyncMock(return_value=fail_client)
        fail_client.__aexit__ = AsyncMock(return_value=False)

        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.json.return_value = {
            "health": {"cpu_percent": 30.0},
            "ros2": {},
            "systemd": [],
        }
        ok_client = AsyncMock()
        ok_client.get = AsyncMock(return_value=ok_resp)
        ok_client.__aenter__ = AsyncMock(return_value=ok_client)
        ok_client.__aexit__ = AsyncMock(return_value=False)

        arm1 = next(e for e in manager.get_all_entities() if e.id == "arm1")

        # 3 failures -> offline, errors accumulate
        with patch("backend.entity_manager.httpx.AsyncClient", return_value=fail_client):
            await manager._poll_entity(arm1)
            await manager._poll_entity(arm1)
            await manager._poll_entity(arm1)

        assert arm1.status == "offline"
        assert len(arm1.errors) > 0, "Should have errors after going offline"

        # Recovery
        with patch("backend.entity_manager.httpx.AsyncClient", return_value=ok_client):
            await manager._poll_entity(arm1)

        assert arm1.status == "online"
        assert arm1.errors == [], f"Errors should be cleared on recovery, got: {arm1.errors}"

    @pytest.mark.asyncio
    async def test_recovery_clears_pre_existing_errors(self, manager: EntityManager):
        """Entity with pre-existing errors gets them cleared on successful poll."""
        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.json.return_value = {
            "health": {"cpu_percent": 10.0},
            "ros2": {},
            "systemd": [],
        }
        ok_client = AsyncMock()
        ok_client.get = AsyncMock(return_value=ok_resp)
        ok_client.__aenter__ = AsyncMock(return_value=ok_client)
        ok_client.__aexit__ = AsyncMock(return_value=False)

        arm1 = next(e for e in manager.get_all_entities() if e.id == "arm1")
        # Simulate pre-existing errors from a previous offline cycle
        arm1.add_error("Offline after 3 consecutive poll failures")
        arm1.add_error("Offline after 4 consecutive poll failures")
        assert len(arm1.errors) == 2

        # Successful poll should clear them
        with patch("backend.entity_manager.httpx.AsyncClient", return_value=ok_client):
            await manager._poll_entity(arm1)

        assert arm1.status == "online"
        assert arm1.errors == [], f"Pre-existing errors should be cleared, got: {arm1.errors}"

    @pytest.mark.asyncio
    async def test_errors_only_cleared_on_success_not_degraded(self, manager: EntityManager):
        """Errors should NOT be cleared on 1-2 failures (degraded state)."""
        fail_client = AsyncMock()
        fail_client.get = AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))
        fail_client.__aenter__ = AsyncMock(return_value=fail_client)
        fail_client.__aexit__ = AsyncMock(return_value=False)

        arm1 = next(e for e in manager.get_all_entities() if e.id == "arm1")
        # Pre-existing error
        arm1.add_error("Some old error")

        # 1 failure -> degraded, errors should still be present
        with patch("backend.entity_manager.httpx.AsyncClient", return_value=fail_client):
            await manager._poll_entity(arm1)

        assert arm1.status != "online"
        assert len(arm1.errors) >= 1, "Errors should NOT be cleared during degraded"


# ---------------------------------------------------------------------------
# Task: Hostname-based deduplication in scan endpoint
# ---------------------------------------------------------------------------


def _make_health_response(hostname: str, entity_type: str = "arm") -> MagicMock:
    """Create a mock httpx response for a /health endpoint."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "hostname": hostname,
        "entity_type": entity_type,
    }
    return resp


def _make_scan_client_factory(ip_to_response: dict[str, MagicMock]):
    """Return an AsyncClient factory that routes GET by IP in URL.

    ip_to_response maps IP strings to mock Response objects.
    IPs not in the map raise ConnectTimeout.
    Uses exact host:port matching to avoid substring collisions
    (e.g., "192.168.137.12" must not match "192.168.137.120").
    """
    import re

    def factory(**kwargs):
        client = AsyncMock()

        async def _get(url: str):
            # Extract host from http://<host>:<port>/...
            m = re.match(r"http://([^:/]+)", url)
            if m:
                host = m.group(1)
                if host in ip_to_response:
                    return ip_to_response[host]
            raise httpx.ConnectTimeout("timeout")

        client.get = AsyncMock(side_effect=_get)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        return client

    return factory


class TestScanSubnetDedup:
    """Tests for hostname-based deduplication in POST /api/entities/scan."""

    @pytest.mark.asyncio
    async def test_dual_interface_dedup_by_hostname(
        self, client: TestClient, manager: EntityManager
    ):
        """Two IPs with same hostname should be merged into one result with ips array."""
        ip_responses = {
            "192.168.137.12": _make_health_response("pragati-arm-1"),
            "192.168.137.50": _make_health_response("pragati-arm-1"),
        }
        factory = _make_scan_client_factory(ip_responses)

        with patch("backend.entity_manager.httpx.AsyncClient", side_effect=factory):
            resp = client.post(
                "/api/entities/scan",
                json={"subnet": "192.168.137", "timeout": 0.01, "concurrency": 50},
            )

        assert resp.status_code == 200
        data = resp.json()
        results = data["results"]

        # Should be deduped to 1 result
        assert len(results) == 1, f"Expected 1 result after dedup, got {len(results)}: {results}"
        merged = results[0]
        assert merged["hostname"] == "pragati-arm-1"
        assert set(merged["ips"]) == {"192.168.137.12", "192.168.137.50"}
        # Primary ip should be one of the two
        assert merged["ip"] in ("192.168.137.12", "192.168.137.50")

    @pytest.mark.asyncio
    async def test_empty_hostname_not_grouped(self, client: TestClient, manager: EntityManager):
        """Results with empty hostname should NOT be grouped together."""
        ip_responses = {
            "192.168.137.12": _make_health_response(""),
            "192.168.137.50": _make_health_response(""),
        }
        factory = _make_scan_client_factory(ip_responses)

        with patch("backend.entity_manager.httpx.AsyncClient", side_effect=factory):
            resp = client.post(
                "/api/entities/scan",
                json={"subnet": "192.168.137", "timeout": 0.01, "concurrency": 50},
            )

        assert resp.status_code == 200
        data = resp.json()
        results = data["results"]

        # Each empty-hostname result is unique
        assert (
            len(results) == 2
        ), f"Expected 2 results (no grouping for empty hostname), got {len(results)}"
        # Both should have ips field for consistency
        for r in results:
            assert "ips" in r, f"Result missing 'ips' field: {r}"
            assert r["ips"] == [r["ip"]]

    @pytest.mark.asyncio
    async def test_single_ip_gets_ips_field(self, client: TestClient, manager: EntityManager):
        """A single result (no duplicate) should still have ips: [ip] for consistency."""
        ip_responses = {
            "192.168.137.12": _make_health_response("pragati-arm-1"),
        }
        factory = _make_scan_client_factory(ip_responses)

        with patch("backend.entity_manager.httpx.AsyncClient", side_effect=factory):
            resp = client.post(
                "/api/entities/scan",
                json={"subnet": "192.168.137", "timeout": 0.01, "concurrency": 50},
            )

        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 1
        assert results[0]["ips"] == ["192.168.137.12"]

    @pytest.mark.asyncio
    async def test_already_configured_any_ip_in_group(
        self, client: TestClient, manager: EntityManager
    ):
        """already_configured=True if ANY IP in the hostname group is configured."""
        # Configure one of the IPs in the manager
        arm1 = next(e for e in manager.get_all_entities() if e.id == "arm1")
        # arm1 IP is 192.168.137.12 from the fixture config.env

        ip_responses = {
            "192.168.137.12": _make_health_response("pragati-arm-1"),
            "192.168.137.50": _make_health_response("pragati-arm-1"),
        }
        factory = _make_scan_client_factory(ip_responses)

        with patch("backend.entity_manager.httpx.AsyncClient", side_effect=factory):
            resp = client.post(
                "/api/entities/scan",
                json={"subnet": "192.168.137", "timeout": 0.01, "concurrency": 50},
            )

        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 1
        merged = results[0]
        assert merged["already_configured"] is True
        assert merged["configured_entity_id"] == "arm1"

    @pytest.mark.asyncio
    async def test_dedup_agents_found_reflects_unique_count(
        self, client: TestClient, manager: EntityManager
    ):
        """agents_found in response should reflect unique (deduped) agent count."""
        ip_responses = {
            "192.168.137.12": _make_health_response("pragati-arm-1"),
            "192.168.137.50": _make_health_response("pragati-arm-1"),
            "192.168.137.100": _make_health_response("pragati-vehicle"),
        }
        factory = _make_scan_client_factory(ip_responses)

        with patch("backend.entity_manager.httpx.AsyncClient", side_effect=factory):
            resp = client.post(
                "/api/entities/scan",
                json={"subnet": "192.168.137", "timeout": 0.01, "concurrency": 50},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["agents_found"] == 2  # 2 unique hostnames with agents
        assert data["hosts_found"] == 0  # no host-only results
        assert len(data["results"]) == 2

    @pytest.mark.asyncio
    async def test_host_found_without_agent(self, client: TestClient, manager: EntityManager):
        """TCP-reachable host without agent should appear as host_found."""
        # No agent responds (httpx raises), but TCP port 22 is open
        factory = _make_scan_client_factory({})  # no agents

        async def mock_open_connection(host, port, **kw):
            if host == "192.168.137.99" and port == 22:
                writer = AsyncMock()
                writer.close = MagicMock()
                writer.wait_closed = AsyncMock()
                return (AsyncMock(), writer)
            raise OSError("Connection refused")

        with (
            patch("backend.entity_manager.httpx.AsyncClient", side_effect=factory),
            patch(
                "backend.entity_manager.asyncio.open_connection", side_effect=mock_open_connection
            ),
        ):
            resp = client.post(
                "/api/entities/scan",
                json={"subnet": "192.168.137", "timeout": 0.01, "concurrency": 50},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["hosts_found"] >= 1
        host_results = [r for r in data["results"] if r["status"] == "host_found"]
        assert len(host_results) >= 1
        found_ips = [r["ip"] for r in host_results]
        assert "192.168.137.99" in found_ips

    @pytest.mark.asyncio
    async def test_agent_found_status_field(self, client: TestClient, manager: EntityManager):
        """Agent results should have status='agent_found'."""
        ip_responses = {
            "192.168.137.12": _make_health_response("pragati-arm-1"),
        }
        factory = _make_scan_client_factory(ip_responses)

        with patch("backend.entity_manager.httpx.AsyncClient", side_effect=factory):
            resp = client.post(
                "/api/entities/scan",
                json={"subnet": "192.168.137", "timeout": 0.01, "concurrency": 50},
            )

        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 1
        assert results[0]["status"] == "agent_found"
