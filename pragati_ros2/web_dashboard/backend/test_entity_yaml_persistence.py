"""Tests for entities.yaml persistence — group/slot/name overlay.

Covers:
- _load_entities_yaml() merges group/slot/name into existing entities
- _load_entities_yaml() ignores unknown entity IDs
- _load_entities_yaml() handles missing/corrupt/empty YAML gracefully
- _save_entities_yaml() writes correct YAML structure
- _save_entities_yaml() only saves remote entities with group_id
- add_entity_by_ip() triggers YAML save
- update_entity() triggers YAML save on group/slot/name change
- remove_entity() triggers YAML save
- Round-trip: save then reload preserves group/slot/name
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from backend.entity_manager import EntityManager
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
    with patch.object(EntityManager, "_detect_local_ips", return_value=_MOCK_LOCAL_IPS):
        yield


@pytest.fixture
def config_env_path(tmp_path: Path) -> Path:
    p = tmp_path / "config.env"
    p.write_text(SAMPLE_CONFIG_ENV)
    return p


@pytest.fixture
def entities_yaml_path(tmp_path: Path) -> Path:
    return tmp_path / "entities.yaml"


@pytest.fixture
def manager(config_env_path: Path, entities_yaml_path: Path) -> EntityManager:
    return EntityManager(
        config_env_path=config_env_path,
        entities_yaml_path=entities_yaml_path,
    )


def _mock_reachable_agent():
    """Return a mock httpx client that simulates a reachable agent."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# ===================================================================
# _load_entities_yaml()
# ===================================================================


class TestLoadEntitiesYaml:
    """Test loading group/slot/name overlay from entities.yaml."""

    def test_no_yaml_file_no_error(self, config_env_path, tmp_path):
        """Missing entities.yaml does not crash — entities keep defaults."""
        yaml_path = tmp_path / "nonexistent.yaml"
        mgr = EntityManager(
            config_env_path=config_env_path,
            entities_yaml_path=yaml_path,
        )
        arm1 = mgr.get_entity("arm1")
        assert arm1 is not None
        assert arm1.group_id is None
        assert arm1.slot is None

    def test_overlay_group_slot_name(self, config_env_path, tmp_path):
        """entities.yaml overlays group_id, slot, name onto existing entities."""
        yaml_path = tmp_path / "entities.yaml"
        yaml_path.write_text(
            yaml.dump(
                {
                    "entities": [
                        {
                            "id": "arm1",
                            "group_id": "tabletop-lab",
                            "slot": "arm-1",
                            "name": "Left Arm",
                            "membership_state": "approved",
                        },
                        {
                            "id": "vehicle",
                            "group_id": "tabletop-lab",
                            "slot": "vehicle",
                            "name": "Main Vehicle",
                            "membership_state": "approved",
                        },
                    ]
                }
            )
        )
        mgr = EntityManager(
            config_env_path=config_env_path,
            entities_yaml_path=yaml_path,
        )
        arm1 = mgr.get_entity("arm1")
        assert arm1.group_id == "tabletop-lab"
        assert arm1.slot == "arm-1"
        assert arm1.name == "Left Arm"

        vehicle = mgr.get_entity("vehicle")
        assert vehicle.group_id == "tabletop-lab"
        assert vehicle.slot == "vehicle"
        assert vehicle.name == "Main Vehicle"

    def test_overlay_ignores_unknown_ids(self, config_env_path, tmp_path):
        """Entities not in config.env are silently ignored."""
        yaml_path = tmp_path / "entities.yaml"
        yaml_path.write_text(
            yaml.dump(
                {
                    "entities": [
                        {
                            "id": "arm99",
                            "group_id": "ghost-group",
                            "slot": "arm-99",
                            "name": "Ghost",
                        },
                    ]
                }
            )
        )
        mgr = EntityManager(
            config_env_path=config_env_path,
            entities_yaml_path=yaml_path,
        )
        assert mgr.get_entity("arm99") is None

    def test_overlay_does_not_overwrite_ip(self, config_env_path, tmp_path):
        """entities.yaml cannot change IP — config.env is source-of-truth."""
        yaml_path = tmp_path / "entities.yaml"
        yaml_path.write_text(
            yaml.dump(
                {
                    "entities": [
                        {
                            "id": "arm1",
                            "group_id": "lab",
                            "slot": "arm-1",
                            "name": "Renamed",
                        },
                    ]
                }
            )
        )
        mgr = EntityManager(
            config_env_path=config_env_path,
            entities_yaml_path=yaml_path,
        )
        arm1 = mgr.get_entity("arm1")
        assert arm1.ip == "192.168.137.12"  # unchanged from config.env

    def test_corrupt_yaml_no_crash(self, config_env_path, tmp_path):
        """Corrupt YAML file is handled gracefully."""
        yaml_path = tmp_path / "entities.yaml"
        yaml_path.write_text("{{{not valid yaml")
        mgr = EntityManager(
            config_env_path=config_env_path,
            entities_yaml_path=yaml_path,
        )
        # Should still have entities from config.env
        assert mgr.get_entity("arm1") is not None

    def test_empty_yaml_no_crash(self, config_env_path, tmp_path):
        """Empty YAML file is handled gracefully."""
        yaml_path = tmp_path / "entities.yaml"
        yaml_path.write_text("")
        mgr = EntityManager(
            config_env_path=config_env_path,
            entities_yaml_path=yaml_path,
        )
        assert mgr.get_entity("arm1") is not None

    def test_yaml_without_entities_key(self, config_env_path, tmp_path):
        """YAML with wrong structure is handled gracefully."""
        yaml_path = tmp_path / "entities.yaml"
        yaml_path.write_text(yaml.dump({"version": 1}))
        mgr = EntityManager(
            config_env_path=config_env_path,
            entities_yaml_path=yaml_path,
        )
        assert mgr.get_entity("arm1") is not None
        assert mgr.get_entity("arm1").group_id is None


# ===================================================================
# _save_entities_yaml()
# ===================================================================


class TestSaveEntitiesYaml:
    """Test saving entities to entities.yaml."""

    def test_save_creates_file(self, manager, entities_yaml_path):
        """_save_entities_yaml() creates the file if it doesn't exist."""
        assert not entities_yaml_path.exists()
        # Manually set group on an entity and save
        arm1 = manager.get_entity("arm1")
        arm1.group_id = "lab"
        arm1.slot = "arm-1"
        manager._save_entities_yaml()
        assert entities_yaml_path.exists()

    def test_save_correct_structure(self, manager, entities_yaml_path):
        """Saved YAML has correct top-level structure."""
        arm1 = manager.get_entity("arm1")
        arm1.group_id = "tabletop-lab"
        arm1.slot = "arm-1"
        arm1.membership_state = "approved"
        manager._save_entities_yaml()

        data = yaml.safe_load(entities_yaml_path.read_text())
        assert "entities" in data
        assert isinstance(data["entities"], list)
        assert len(data["entities"]) >= 1

        entry = next(e for e in data["entities"] if e["id"] == "arm1")
        assert entry["group_id"] == "tabletop-lab"
        assert entry["slot"] == "arm-1"
        assert entry["entity_type"] == "arm"
        assert entry["membership_state"] == "approved"

    def test_save_excludes_local_entity(self, manager, entities_yaml_path):
        """Local entity is never saved to entities.yaml."""
        local = manager.get_entity("local")
        if local:
            local.group_id = "should-not-appear"
        manager._save_entities_yaml()

        if entities_yaml_path.exists():
            data = yaml.safe_load(entities_yaml_path.read_text())
            ids = [e["id"] for e in data.get("entities", [])]
            assert "local" not in ids

    def test_save_excludes_entities_without_group(self, manager, entities_yaml_path):
        """Entities without group_id are not saved."""
        # arm1 has no group by default
        manager._save_entities_yaml()
        if entities_yaml_path.exists():
            data = yaml.safe_load(entities_yaml_path.read_text())
            ids = [e["id"] for e in data.get("entities", [])]
            assert "arm1" not in ids


# ===================================================================
# Round-trip: save + reload
# ===================================================================


class TestYamlRoundTrip:
    """Test that saving and reloading preserves data."""

    def test_round_trip_preserves_group_slot_name(self, config_env_path, entities_yaml_path):
        """Save from one manager, reload in a new one — data preserved."""
        mgr1 = EntityManager(
            config_env_path=config_env_path,
            entities_yaml_path=entities_yaml_path,
        )
        arm1 = mgr1.get_entity("arm1")
        arm1.group_id = "tabletop-lab"
        arm1.slot = "arm-1"
        arm1.name = "Custom Arm Name"
        arm1.membership_state = "approved"

        vehicle = mgr1.get_entity("vehicle")
        vehicle.group_id = "tabletop-lab"
        vehicle.slot = "vehicle"
        vehicle.name = "Main Vehicle"
        vehicle.membership_state = "approved"

        mgr1._save_entities_yaml()

        # Create new manager from same files
        mgr2 = EntityManager(
            config_env_path=config_env_path,
            entities_yaml_path=entities_yaml_path,
        )
        arm1_reloaded = mgr2.get_entity("arm1")
        assert arm1_reloaded.group_id == "tabletop-lab"
        assert arm1_reloaded.slot == "arm-1"
        assert arm1_reloaded.name == "Custom Arm Name"

        vehicle_reloaded = mgr2.get_entity("vehicle")
        assert vehicle_reloaded.group_id == "tabletop-lab"
        assert vehicle_reloaded.slot == "vehicle"
        assert vehicle_reloaded.name == "Main Vehicle"


# ===================================================================
# Mutation hooks — verify save is triggered
# ===================================================================


class TestMutationHooks:
    """Test that CRUD operations trigger _save_entities_yaml()."""

    @pytest.mark.asyncio
    async def test_add_entity_triggers_save(self, config_env_path, entities_yaml_path):
        """add_entity_by_ip() saves to entities.yaml."""
        mgr = EntityManager(
            config_env_path=config_env_path,
            entities_yaml_path=entities_yaml_path,
        )
        with patch("httpx.AsyncClient", return_value=_mock_reachable_agent()):
            entity = await mgr.add_entity_by_ip(
                ip="10.0.0.50",
                entity_type="arm",
                group_id="test-group",
                slot="arm-3",
                name="Test Arm",
                config_env_path=config_env_path,
            )

        assert entities_yaml_path.exists()
        data = yaml.safe_load(entities_yaml_path.read_text())
        ids = [e["id"] for e in data["entities"]]
        assert entity.id in ids
        entry = next(e for e in data["entities"] if e["id"] == entity.id)
        assert entry["group_id"] == "test-group"
        assert entry["slot"] == "arm-3"

    @pytest.mark.asyncio
    async def test_update_entity_triggers_save(self, config_env_path, entities_yaml_path):
        """update_entity() saves to entities.yaml on group/slot change."""
        mgr = EntityManager(
            config_env_path=config_env_path,
            entities_yaml_path=entities_yaml_path,
        )
        await mgr.update_entity(
            entity_id="arm1",
            group_id="new-group",
            slot="arm-1",
            config_env_path=config_env_path,
        )

        assert entities_yaml_path.exists()
        data = yaml.safe_load(entities_yaml_path.read_text())
        entry = next(e for e in data["entities"] if e["id"] == "arm1")
        assert entry["group_id"] == "new-group"
        assert entry["slot"] == "arm-1"

    @pytest.mark.asyncio
    async def test_remove_entity_triggers_save(self, config_env_path, entities_yaml_path):
        """remove_entity() updates entities.yaml (entity no longer present)."""
        mgr = EntityManager(
            config_env_path=config_env_path,
            entities_yaml_path=entities_yaml_path,
        )
        # First give arm1 a group so it appears in YAML
        arm1 = mgr.get_entity("arm1")
        arm1.group_id = "lab"
        arm1.slot = "arm-1"
        mgr._save_entities_yaml()

        # Verify it's in the YAML
        data = yaml.safe_load(entities_yaml_path.read_text())
        ids = [e["id"] for e in data["entities"]]
        assert "arm1" in ids

        # Now remove
        await mgr.remove_entity("arm1", config_env_path=config_env_path)

        # Verify it's gone from YAML
        data = yaml.safe_load(entities_yaml_path.read_text())
        ids = [e["id"] for e in data["entities"]]
        assert "arm1" not in ids


# ===================================================================
# poll_host / poll_port in entities.yaml
# ===================================================================


class TestYamlPollHostPort:
    """poll_host/poll_port are loaded from, overlaid by, and saved to entities.yaml."""

    def test_create_from_yaml_with_poll_host(self, config_env_path, tmp_path):
        """Entity created from YAML (not in config.env) picks up poll_host/poll_port."""
        # arm99 is NOT in config.env, so it goes through the "Create" path
        yaml_path = tmp_path / "entities.yaml"
        yaml_path.write_text(
            yaml.dump(
                {
                    "entities": [
                        {
                            "id": "arm99",
                            "name": "Remote Arm",
                            "entity_type": "arm",
                            "ip": "10.0.0.99",
                            "poll_host": "172.20.0.1",
                            "poll_port": 18099,
                        },
                    ]
                }
            )
        )
        mgr = EntityManager(
            config_env_path=config_env_path,
            entities_yaml_path=yaml_path,
        )
        arm99 = mgr.get_entity("arm99")
        assert arm99 is not None
        assert arm99.poll_host == "172.20.0.1"
        assert arm99.poll_port == 18099

    def test_overlay_poll_host_when_not_set(self, tmp_path):
        """YAML poll_host/poll_port overlaid onto entity that has no poll overrides."""
        # config.env has ARM_1_IP but no ARM_1_POLL_HOST
        config_path = tmp_path / "config.env"
        config_path.write_text("ARM_1_IP=192.168.137.12\n")

        yaml_path = tmp_path / "entities.yaml"
        yaml_path.write_text(
            yaml.dump(
                {
                    "entities": [
                        {
                            "id": "arm1",
                            "group_id": "lab",
                            "poll_host": "172.20.0.1",
                            "poll_port": 18091,
                        },
                    ]
                }
            )
        )
        mgr = EntityManager(
            config_env_path=config_path,
            entities_yaml_path=yaml_path,
        )
        arm1 = mgr.get_entity("arm1")
        assert arm1.poll_host == "172.20.0.1"
        assert arm1.poll_port == 18091

    def test_config_env_poll_host_takes_priority(self, tmp_path):
        """config.env poll_host/poll_port should NOT be overwritten by YAML."""
        config_path = tmp_path / "config.env"
        config_path.write_text(
            "ARM_1_IP=192.168.137.12\n" "ARM_1_POLL_HOST=10.10.10.10\n" "ARM_1_POLL_PORT=9999\n"
        )

        yaml_path = tmp_path / "entities.yaml"
        yaml_path.write_text(
            yaml.dump(
                {
                    "entities": [
                        {
                            "id": "arm1",
                            "group_id": "lab",
                            "poll_host": "172.20.0.1",
                            "poll_port": 18091,
                        },
                    ]
                }
            )
        )
        mgr = EntityManager(
            config_env_path=config_path,
            entities_yaml_path=yaml_path,
        )
        arm1 = mgr.get_entity("arm1")
        # config.env values should win
        assert arm1.poll_host == "10.10.10.10"
        assert arm1.poll_port == 9999

    def test_save_persists_poll_host_port(self, config_env_path, entities_yaml_path):
        """_save_entities_yaml() includes poll_host/poll_port in saved data."""
        mgr = EntityManager(
            config_env_path=config_env_path,
            entities_yaml_path=entities_yaml_path,
        )
        arm1 = mgr.get_entity("arm1")
        arm1.group_id = "lab"
        arm1.slot = "arm-1"
        arm1.poll_host = "172.20.0.1"
        arm1.poll_port = 18091
        mgr._save_entities_yaml()

        data = yaml.safe_load(entities_yaml_path.read_text())
        entry = next(e for e in data["entities"] if e["id"] == "arm1")
        assert entry["poll_host"] == "172.20.0.1"
        assert entry["poll_port"] == 18091

    def test_roundtrip_poll_host_port(self, tmp_path):
        """Save then reload preserves poll_host/poll_port."""
        config_path = tmp_path / "config.env"
        config_path.write_text("ARM_1_IP=192.168.137.12\n")
        yaml_path = tmp_path / "entities.yaml"

        # Create, set poll, save
        mgr1 = EntityManager(
            config_env_path=config_path,
            entities_yaml_path=yaml_path,
        )
        arm1 = mgr1.get_entity("arm1")
        arm1.group_id = "lab"
        arm1.poll_host = "172.20.0.1"
        arm1.poll_port = 18091
        mgr1._save_entities_yaml()

        # Reload from scratch
        mgr2 = EntityManager(
            config_env_path=config_path,
            entities_yaml_path=yaml_path,
        )
        arm1_reloaded = mgr2.get_entity("arm1")
        assert arm1_reloaded.poll_host == "172.20.0.1"
        assert arm1_reloaded.poll_port == 18091
