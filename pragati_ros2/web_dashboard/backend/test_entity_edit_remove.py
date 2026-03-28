import pytest
import asyncio
from pathlib import Path
from unittest.mock import patch

from backend.entity_manager import EntityManager
from backend.entity_model import Entity


@pytest.fixture
def tmp_config_env(tmp_path: Path):
    p = tmp_path / "config.env"
    p.write_text("ARM_1_IP=192.168.1.10\nVEHICLE_IP=192.168.1.20\n")
    return p


@pytest.fixture
def manager(tmp_config_env, tmp_path):
    mgr = EntityManager(
        config_env_path=tmp_config_env,
        entities_yaml_path=tmp_path / "entities.yaml",
    )
    return mgr


@pytest.mark.asyncio
async def test_remove_entity(manager: EntityManager, tmp_config_env: Path):
    # arm1 exists from config
    assert "arm1" in manager._entities

    subscriber_queue = manager.subscribe_changes()

    await manager.remove_entity("arm1", config_env_path=tmp_config_env)

    assert "arm1" not in manager._entities

    # Check file
    content = tmp_config_env.read_text()
    assert "ARM_1_IP" not in content
    assert "VEHICLE_IP=192.168.1.20" in content

    # Check websocket notification via queue
    event = await asyncio.wait_for(subscriber_queue.get(), timeout=1.0)
    assert event["type"] == "entity_removed"
    assert event["entity_id"] == "arm1"


@pytest.mark.asyncio
async def test_remove_nonexistent_entity(manager: EntityManager):
    with pytest.raises(KeyError) as exc:
        await manager.remove_entity("arm99")
    assert "not found" in str(exc.value)


@pytest.mark.asyncio
async def test_update_entity(manager: EntityManager, tmp_config_env: Path):
    subscriber_queue = manager.subscribe_changes()

    updated = await manager.update_entity(
        "arm1",
        ip="192.168.1.15",
        name="New Name",
        group_id="machine-1",
        slot="arm-1",
        config_env_path=tmp_config_env,
    )

    assert updated.ip == "192.168.1.15"
    assert updated.name == "New Name"
    assert updated.group_id == "machine-1"
    assert updated.slot == "arm-1"
    assert manager._entities["arm1"].ip == "192.168.1.15"

    # Check file
    content = tmp_config_env.read_text()
    assert "ARM_1_IP=192.168.1.15" in content
    assert "ARM_1_IP=192.168.1.10" not in content

    # Check websocket notification via queue
    event = await asyncio.wait_for(subscriber_queue.get(), timeout=1.0)
    assert event["type"] == "entity_updated"
    assert event["entity"]["id"] == "arm1"
    assert event["entity"]["ip"] == "192.168.1.15"


@pytest.mark.asyncio
async def test_update_entity_group_slot_only(manager: EntityManager):
    updated = await manager.update_entity(
        "arm1",
        group_id="tabletop-lab",
        slot="arm-2",
    )
    assert updated.group_id == "tabletop-lab"
    assert updated.slot == "arm-2"


@pytest.mark.asyncio
async def test_update_entity_custom_group_and_arm_n_slot(manager: EntityManager):
    updated = await manager.update_entity(
        "arm1",
        group_id="machine-2",
        slot="arm-10",
    )
    assert updated.group_id == "machine-2"
    assert updated.slot == "arm-10"


@pytest.mark.asyncio
async def test_update_entity_slot_conflict_raises(manager: EntityManager):
    manager._entities["arm1"].group_id = "machine-1"
    manager._entities["arm1"].slot = "arm-1"
    manager._entities["vehicle"].group_id = "machine-1"
    manager._entities["vehicle"].slot = "vehicle"

    manager._entities["arm2"] = Entity(
        id="arm2",
        name="Arm 2",
        entity_type="arm",
        source="remote",
        ip="192.168.1.30",
        group_id="machine-1",
        slot="arm-2",
    )

    with pytest.raises(Exception) as exc:
        await manager.update_entity("arm2", group_id="machine-1", slot="arm-1")
    assert "already occupied" in str(exc.value)


@pytest.mark.asyncio
async def test_update_entity_invalid_arm_slot_rejected(manager: EntityManager):
    with pytest.raises(ValueError) as exc:
        await manager.update_entity("arm1", group_id="machine-1", slot="vehicle")
    assert "Invalid slot" in str(exc.value)
