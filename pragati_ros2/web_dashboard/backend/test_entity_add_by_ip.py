"""Tests for POST /api/entities — add entity by IP address.

Covers:
- Valid IP + reachable agent → 201 + Entity JSON
- Invalid IP format → 422
- Duplicate IP → 409 with existing_entity_id
- Unreachable agent → entity still created (no reachability check on add)
- Missing `ip` field → 422
- Invalid `entity_type` → 422
- Auto-generated name for arm (next number)
- Auto-generated name for vehicle
- Vehicle already exists → 409
- Custom name provided → used as-is
- notify_entity_added WebSocket broadcast
- Integration round-trip: POST → GET → verify entity in list
"""

from __future__ import annotations

import asyncio
import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.entity_manager import (
    AGENT_PORT,
    EntityManager,
    entity_router,
)
from backend.entity_model import Entity

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_CONFIG_ENV = textwrap.dedent("""\
    ARM_1_IP=192.168.137.12
    ARM_2_IP=192.168.137.238
    VEHICLE_IP=192.168.137.203
""")

_MOCK_LOCAL_IPS = {"127.0.0.1", "10.0.0.99"}


@pytest.fixture(autouse=True)
def _mock_local_ips():
    """Patch _detect_local_ips for all tests."""
    with patch.object(EntityManager, "_detect_local_ips", return_value=_MOCK_LOCAL_IPS):
        yield


@pytest.fixture
def config_env_path(tmp_path: Path) -> Path:
    p = tmp_path / "config.env"
    p.write_text(SAMPLE_CONFIG_ENV)
    return p


@pytest.fixture
def manager(config_env_path: Path, tmp_path: Path) -> EntityManager:
    yaml_path = tmp_path / "entities.yaml"
    return EntityManager(config_env_path=config_env_path, entities_yaml_path=yaml_path)


def _mock_reachable_agent():
    """Return a mock httpx client that simulates a reachable agent."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


def _mock_unreachable_agent():
    """Return a mock httpx client that simulates an unreachable agent."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


@pytest.fixture
def app(manager: EntityManager) -> FastAPI:
    app = FastAPI()
    app.include_router(entity_router)
    with patch("backend.entity_manager._entity_manager", manager):
        yield app


@pytest.fixture
def client(app: FastAPI, manager: EntityManager) -> TestClient:
    with patch("backend.entity_manager._entity_manager", manager):
        with TestClient(app) as c:
            yield c


# ===================================================================
# Task 1.1: POST /api/entities tests (RED)
# ===================================================================


class TestAddEntityByIP:
    """Test POST /api/entities endpoint."""

    def test_valid_ip_reachable_agent_returns_201(self, client: TestClient, manager: EntityManager):
        """Happy path: valid IP, reachable agent → 201 with Entity JSON."""
        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=_mock_reachable_agent(),
        ):
            resp = client.post(
                "/api/entities",
                json={
                    "ip": "192.168.137.50",
                    "entity_type": "arm",
                    "group_id": "machine-1",
                    "slot": "arm-1",
                },
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["ip"] == "192.168.137.50"
        assert data["entity_type"] == "arm"
        assert data["source"] == "remote"
        assert data["status"] == "unknown"
        assert data["group_id"] == "machine-1"
        assert data["slot"] == "arm-1"
        assert "id" in data

    def test_missing_group_or_slot_returns_422(self, client: TestClient):
        """Approved manual add requires both group_id and slot."""
        resp_missing_group = client.post(
            "/api/entities",
            json={
                "ip": "192.168.137.50",
                "entity_type": "arm",
                "slot": "arm-1",
            },
        )
        assert resp_missing_group.status_code == 422

        resp_missing_slot = client.post(
            "/api/entities",
            json={
                "ip": "192.168.137.50",
                "entity_type": "arm",
                "group_id": "machine-1",
            },
        )
        assert resp_missing_slot.status_code == 422

    def test_invalid_slot_for_arm_returns_422(self, client: TestClient):
        """Arm entities require slot format arm-N."""
        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=_mock_reachable_agent(),
        ):
            resp = client.post(
                "/api/entities",
                json={
                    "ip": "192.168.137.50",
                    "entity_type": "arm",
                    "group_id": "machine-1",
                    "slot": "vehicle",
                },
            )
        assert resp.status_code == 422

    def test_arm_n_slot_is_allowed(self, client: TestClient):
        """Arm slots allow arm-N beyond fixed arm-1/arm-2."""
        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=_mock_reachable_agent(),
        ):
            resp = client.post(
                "/api/entities",
                json={
                    "ip": "192.168.137.60",
                    "entity_type": "arm",
                    "group_id": "machine-2",
                    "slot": "arm-10",
                },
            )
        assert resp.status_code == 201
        assert resp.json()["slot"] == "arm-10"

    def test_invalid_ip_format_returns_422(self, client: TestClient):
        """Invalid IP format → 422 with error message."""
        resp = client.post(
            "/api/entities",
            json={
                "ip": "not-an-ip",
                "entity_type": "arm",
                "group_id": "machine-1",
                "slot": "arm-1",
            },
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "Invalid IPv4 address" in detail["error"]

    def test_invalid_ip_octets_out_of_range(self, client: TestClient):
        """IP with octets > 255 → 422."""
        resp = client.post(
            "/api/entities",
            json={
                "ip": "999.1.2.3",
                "entity_type": "arm",
                "group_id": "machine-1",
                "slot": "arm-1",
            },
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "Invalid IPv4 address" in detail["error"]

    def test_duplicate_ip_returns_409(self, client: TestClient, manager: EntityManager):
        """IP already in fleet → 409 with existing_entity_id."""
        # arm1 has IP 192.168.137.12
        resp = client.post(
            "/api/entities",
            json={
                "ip": "192.168.137.12",
                "entity_type": "arm",
                "group_id": "machine-1",
                "slot": "arm-1",
            },
        )
        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert "already exists" in detail["error"]
        assert detail["existing_entity_id"] == "arm1"

    def test_slot_conflict_returns_409(self, client: TestClient, manager: EntityManager):
        """Conflicting approved slot assignment is rejected."""
        existing = manager.get_entity("arm1")
        assert existing is not None
        existing.group_id = "machine-1"
        existing.slot = "arm-1"
        existing.membership_state = "approved"

        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=_mock_reachable_agent(),
        ):
            resp = client.post(
                "/api/entities",
                json={
                    "ip": "192.168.137.250",
                    "entity_type": "arm",
                    "group_id": "machine-1",
                    "slot": "arm-1",
                },
            )

        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert "already occupied" in detail["error"]
        assert detail["existing_entity_id"] == "arm1"

    def test_unreachable_agent_still_creates_entity(self, client: TestClient):
        """Agent not responding → entity still created (reachability not checked on add)."""
        resp = client.post(
            "/api/entities",
            json={
                "ip": "192.168.137.99",
                "entity_type": "arm",
                "group_id": "machine-1",
                "slot": "arm-1",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["ip"] == "192.168.137.99"
        assert data["entity_type"] == "arm"
        assert data["status"] == "unknown"

    def test_missing_ip_field_returns_422(self, client: TestClient):
        """Missing ip field → 422 (FastAPI validation)."""
        resp = client.post(
            "/api/entities",
            json={"entity_type": "arm", "group_id": "machine-1", "slot": "arm-1"},
        )
        assert resp.status_code == 422

    def test_missing_entity_type_returns_422(self, client: TestClient):
        """Missing entity_type field → 422 (FastAPI validation)."""
        resp = client.post(
            "/api/entities",
            json={"ip": "192.168.137.50", "group_id": "machine-1", "slot": "arm-1"},
        )
        assert resp.status_code == 422

    def test_invalid_entity_type_returns_422(self, client: TestClient):
        """Invalid entity_type (not arm/vehicle) → 422."""
        resp = client.post(
            "/api/entities",
            json={
                "ip": "192.168.137.50",
                "entity_type": "drone",
                "group_id": "machine-1",
                "slot": "arm-1",
            },
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "entity_type must be" in detail["error"]

    def test_auto_name_arm_next_number(self, client: TestClient, manager: EntityManager):
        """With arm1 and arm2 existing, next arm gets arm3 / 'Arm 3 RPi'."""
        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=_mock_reachable_agent(),
        ):
            resp = client.post(
                "/api/entities",
                json={
                    "ip": "192.168.137.50",
                    "entity_type": "arm",
                    "group_id": "machine-1",
                    "slot": "arm-3",
                },
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "arm3"
        assert data["name"] == "Arm 3 RPi"

    def test_auto_name_vehicle(self, client: TestClient, tmp_path: Path):
        """Vehicle auto-name is 'Vehicle RPi'."""
        # Create manager without an existing vehicle
        p = tmp_path / "config_no_vehicle.env"
        p.write_text("ARM_1_IP=192.168.137.12\n")
        mgr = EntityManager(
            config_env_path=p,
            entities_yaml_path=tmp_path / "entities.yaml",
        )

        app = FastAPI()
        app.include_router(entity_router)
        with patch("backend.entity_manager._entity_manager", mgr):
            with TestClient(app) as c:
                with patch(
                    "backend.entity_manager.httpx.AsyncClient",
                    return_value=_mock_reachable_agent(),
                ):
                    resp = c.post(
                        "/api/entities",
                        json={
                            "ip": "192.168.137.203",
                            "entity_type": "vehicle",
                            "group_id": "machine-1",
                            "slot": "vehicle",
                        },
                    )
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "vehicle"
        assert data["name"] == "Vehicle RPi"

    def test_vehicle_in_different_group_succeeds(self, client: TestClient, manager: EntityManager):
        """Adding a vehicle to a different group is allowed (one vehicle per group, not global)."""
        # manager already has 'vehicle' in tabletop-lab from config.env
        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=_mock_reachable_agent(),
        ):
            resp = client.post(
                "/api/entities",
                json={
                    "ip": "192.168.137.99",
                    "entity_type": "vehicle",
                    "group_id": "machine-1",
                    "slot": "vehicle",
                },
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["entity_type"] == "vehicle"
        assert data["group_id"] == "machine-1"

    def test_vehicle_same_group_slot_conflict_returns_409(
        self, client: TestClient, manager: EntityManager
    ):
        """Adding a second vehicle to the same group → 409 SlotConflictError."""
        # Add first vehicle in machine-1
        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=_mock_reachable_agent(),
        ):
            r1 = client.post(
                "/api/entities",
                json={
                    "ip": "192.168.137.99",
                    "entity_type": "vehicle",
                    "group_id": "machine-1",
                    "slot": "vehicle",
                },
            )
        assert r1.status_code == 201
        # Attempt to add a second vehicle to the same group/slot
        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=_mock_reachable_agent(),
        ):
            r2 = client.post(
                "/api/entities",
                json={
                    "ip": "192.168.137.88",
                    "entity_type": "vehicle",
                    "group_id": "machine-1",
                    "slot": "vehicle",
                },
            )
        assert r2.status_code == 409
        detail = r2.json()["detail"]
        assert "slot" in detail["error"].lower() or "already" in detail["error"].lower()

    def test_custom_name_used(self, client: TestClient, manager: EntityManager):
        """When name is provided, it's used instead of auto-generated."""
        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=_mock_reachable_agent(),
        ):
            resp = client.post(
                "/api/entities",
                json={
                    "ip": "192.168.137.50",
                    "entity_type": "arm",
                    "name": "My Custom Arm",
                    "group_id": "machine-1",
                    "slot": "arm-3",
                },
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "My Custom Arm"

    def test_entity_persisted_to_config_env(
        self, client: TestClient, manager: EntityManager, config_env_path: Path
    ):
        """After adding, entity IP is persisted to config.env."""
        with patch(
            "backend.entity_manager._DEFAULT_CONFIG_ENV_PATH",
            config_env_path,
        ), patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=_mock_reachable_agent(),
        ):
            resp = client.post(
                "/api/entities",
                json={
                    "ip": "192.168.137.50",
                    "entity_type": "arm",
                    "group_id": "machine-1",
                    "slot": "arm-3",
                },
            )
        assert resp.status_code == 201
        content = config_env_path.read_text()
        assert "192.168.137.50" in content

    def test_entity_appears_in_get_all(self, client: TestClient, manager: EntityManager):
        """After adding, entity appears in GET /api/entities."""
        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=_mock_reachable_agent(),
        ):
            resp = client.post(
                "/api/entities",
                json={
                    "ip": "192.168.137.50",
                    "entity_type": "arm",
                    "group_id": "machine-1",
                    "slot": "arm-3",
                },
            )
        assert resp.status_code == 201
        entity_id = resp.json()["id"]

        # Now GET all entities
        get_resp = client.get("/api/entities")
        assert get_resp.status_code == 200
        ids = [e["id"] for e in get_resp.json()]
        assert entity_id in ids


class TestAddEntityWebSocketNotification:
    """Test that adding an entity broadcasts via WebSocket."""

    @pytest.mark.asyncio
    async def test_notify_entity_added_broadcast(self, manager: EntityManager):
        """notify_entity_added sends entity_added event to subscribers."""
        queue = manager.subscribe_changes()

        entity = Entity(
            id="arm3",
            name="Arm 3 RPi",
            entity_type="arm",
            source="remote",
            ip="192.168.137.50",
        )
        manager.notify_entity_added(entity)

        event = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert event["type"] == "entity_added"
        assert event["entity"]["id"] == "arm3"
        assert event["entity"]["ip"] == "192.168.137.50"
        assert "timestamp" in event

        manager.unsubscribe(queue)

    @pytest.mark.asyncio
    async def test_add_entity_triggers_notification(
        self, manager: EntityManager, config_env_path: Path
    ):
        """Full add_entity_by_ip() call triggers entity_added notification."""
        queue = manager.subscribe_changes()

        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=_mock_reachable_agent(),
        ):
            entity = await manager.add_entity_by_ip(
                ip="192.168.137.50",
                entity_type="arm",
                group_id="machine-1",
                slot="arm-3",
                config_env_path=config_env_path,
            )

        # Should have at least one entity_added event
        event = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert event["type"] == "entity_added"
        assert event["entity"]["id"] == entity.id

        manager.unsubscribe(queue)


class TestAddEntityIntegration:
    """Integration: POST → GET round-trip."""

    def test_post_then_get_entity(self, client: TestClient, manager: EntityManager):
        """POST creates entity, GET retrieves it."""
        with patch(
            "backend.entity_manager.httpx.AsyncClient",
            return_value=_mock_reachable_agent(),
        ):
            post_resp = client.post(
                "/api/entities",
                json={
                    "ip": "192.168.137.50",
                    "entity_type": "arm",
                    "group_id": "machine-1",
                    "slot": "arm-3",
                },
            )
        assert post_resp.status_code == 201
        entity_id = post_resp.json()["id"]

        get_resp = client.get(f"/api/entities/{entity_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["id"] == entity_id
        assert data["ip"] == "192.168.137.50"
        assert data["entity_type"] == "arm"
        assert data["source"] == "remote"
