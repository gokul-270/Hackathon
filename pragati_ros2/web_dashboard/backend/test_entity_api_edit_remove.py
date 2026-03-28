import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from pathlib import Path

from backend.app_factory import create_app
from backend.entity_manager import EntityManager
from backend.entity_model import Entity


@pytest.fixture
def test_app():
    # Setup mock entity manager
    app = create_app()
    return app


@pytest.fixture
def mock_mgr():
    mgr = MagicMock(spec=EntityManager)
    return mgr


def test_delete_entity(test_app, mock_mgr):
    with patch("backend.entity_manager.get_entity_manager", return_value=mock_mgr):
        client = TestClient(test_app)

        # Test successful delete
        mock_mgr.remove_entity.return_value = None

        response = client.delete("/api/entities/arm1")
        assert response.status_code == 200
        assert response.json() == {"status": "success"}
        mock_mgr.remove_entity.assert_called_once_with("arm1")


def test_delete_entity_not_found(test_app, mock_mgr):
    with patch("backend.entity_manager.get_entity_manager", return_value=mock_mgr):
        client = TestClient(test_app)

        # Test not found
        mock_mgr.remove_entity.side_effect = KeyError("Entity not found")
        response = client.delete("/api/entities/arm99")
        assert response.status_code == 404
        assert "Entity not found" in response.json()["detail"]


def test_update_entity(test_app, mock_mgr):
    with patch("backend.entity_manager.get_entity_manager", return_value=mock_mgr):
        client = TestClient(test_app)

        # Mock returned entity
        updated_entity = Entity(
            id="arm1", name="Updated Name", entity_type="arm", source="remote", ip="192.168.1.15"
        )
        mock_mgr.update_entity.return_value = updated_entity
        # Mock entity_to_api_dict to return a proper dict
        mock_mgr.entity_to_api_dict.return_value = {
            "id": "arm1",
            "name": "Updated Name",
            "entity_type": "arm",
            "source": "remote",
            "ip": "192.168.1.15",
        }

        response = client.put(
            "/api/entities/arm1",
            json={
                "ip": "192.168.1.15",
                "name": "Updated Name",
                "group_id": "machine-1",
                "slot": "arm-1",
            },
        )
        assert response.status_code == 200
        assert response.json()["ip"] == "192.168.1.15"
        assert response.json()["name"] == "Updated Name"

        # Was it called correctly
        mock_mgr.update_entity.assert_called_once_with(
            "arm1",
            ip="192.168.1.15",
            name="Updated Name",
            group_id="machine-1",
            slot="arm-1",
        )


def test_update_entity_validation_error(test_app, mock_mgr):
    with patch("backend.entity_manager.get_entity_manager", return_value=mock_mgr):
        client = TestClient(test_app)

        mock_mgr.update_entity.side_effect = ValueError("Invalid IPv4 address")
        response = client.put("/api/entities/arm1", json={"ip": "invalid-ip"})
        assert response.status_code == 422
        assert "Invalid IPv4 address" in response.json()["detail"]["error"]
