#!/usr/bin/env python3
"""
Tests for cam_markers backend endpoints and FK helper.

These are RED tests — they describe the expected behaviour before the
implementation exists. They should ALL FAIL on first run.

Run: python3 -m pytest test_cam_markers_backend.py -v
"""

import sys
import types
import unittest.mock as mock

# ---------------------------------------------------------------------------
# Stub out rclpy and related packages before any import of testing_backend
# ---------------------------------------------------------------------------
for mod_name in [
    "rclpy",
    "geometry_msgs",
    "geometry_msgs.msg",
    "std_msgs",
    "std_msgs.msg",
]:
    sys.modules.setdefault(mod_name, types.ModuleType(mod_name))

# Give geometry_msgs.msg.Twist and std_msgs.msg.Float64 stub classes
sys.modules["geometry_msgs.msg"].Twist = type("Twist", (), {})
sys.modules["std_msgs.msg"].Float64 = type("Float64", (), {"data": 0.0})

import pytest
from fastapi.testclient import TestClient

# Import the symbols under test — will ImportError until implementation exists
from testing_backend import app, cam_to_world, _spawned_marker_names  # noqa: E402


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_marker_list():
    """Reset the in-memory marker list before every test."""
    _spawned_marker_names.clear()
    yield
    _spawned_marker_names.clear()


# ---------------------------------------------------------------------------
# Task 1.6 — FK world-frame computation
# ---------------------------------------------------------------------------
class TestCamToWorld:
    def test_cam_to_world_origin_returns_camera_world_origin(self):
        """cam_to_world(0, 0, 0) must equal the camera's world-frame position."""
        wx, wy, wz = cam_to_world(0.0, 0.0, 0.0)
        assert abs(wx - 1.55) < 1e-4, f"wx={wx}"
        assert abs(wy - (-0.90)) < 1e-4, f"wy={wy}"
        assert abs(wz - 0.75) < 1e-4, f"wz={wz}"

    def test_cam_to_world_known_point_matches_reference(self):
        """cam_to_world with a known point matches hand-computed reference values."""
        # cam_x=1, cam_y=0, cam_z=0
        # wx = 0.9659*1 + 0.2588*0 + 1.55  = 2.5159
        # wy = 0 - 0.90                      = -0.90
        # wz = -0.2588*1 + 0.9659*0 + 0.75  = 0.4912
        wx, wy, wz = cam_to_world(1.0, 0.0, 0.0)
        assert abs(wx - 2.5159) < 1e-3, f"wx={wx}"
        assert abs(wy - (-0.90)) < 1e-3, f"wy={wy}"
        assert abs(wz - 0.4912) < 1e-3, f"wz={wz}"


# ---------------------------------------------------------------------------
# Task 1.2 — POST /api/cam_markers/place: happy path
# ---------------------------------------------------------------------------
class TestCamMarkersPlace:
    def test_place_returns_200_with_valid_coords(self, client):
        """Valid cam coords → 200 response with a marker_name field."""
        with mock.patch("testing_backend.subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="data: true", stderr="")
            resp = client.post(
                "/api/cam_markers/place",
                json={"cam_x": 0.5, "cam_y": 0.1, "cam_z": 0.3},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "marker_name" in body
        assert body["marker_name"].startswith("cam_marker_")

    def test_place_calls_gz_service_create(self, client):
        """Valid cam coords → gz service /world/.../create is called once."""
        with mock.patch("testing_backend.subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="data: true", stderr="")
            client.post(
                "/api/cam_markers/place",
                json={"cam_x": 0.5, "cam_y": 0.1, "cam_z": 0.3},
            )
        assert mock_run.called
        call_args = mock_run.call_args[0][0]  # first positional arg = list
        assert "gz" in call_args
        assert "create" in " ".join(call_args)

    def test_place_appends_marker_name_to_internal_list(self, client):
        """Successful place → marker name appears in _spawned_marker_names."""
        with mock.patch("testing_backend.subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="data: true", stderr="")
            resp = client.post(
                "/api/cam_markers/place",
                json={"cam_x": 0.0, "cam_y": 0.0, "cam_z": 0.0},
            )
        assert resp.status_code == 200
        name = resp.json()["marker_name"]
        assert name in _spawned_marker_names


# ---------------------------------------------------------------------------
# Task 1.3 — POST /api/cam_markers/place: missing coords → 422
# ---------------------------------------------------------------------------
class TestCamMarkersPlaceValidation:
    def test_place_missing_cam_x_returns_422(self, client):
        """Missing cam_x → 422 Unprocessable Entity."""
        resp = client.post(
            "/api/cam_markers/place",
            json={"cam_y": 0.1, "cam_z": 0.3},
        )
        assert resp.status_code == 422

    def test_place_empty_body_returns_422(self, client):
        """Empty body → 422 Unprocessable Entity."""
        resp = client.post("/api/cam_markers/place", json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Task 1.4 — POST /api/cam_markers/clear: removes previously placed markers
# ---------------------------------------------------------------------------
class TestCamMarkersClear:
    def test_clear_calls_gz_service_remove_for_each_marker(self, client):
        """clear calls gz service remove once per marker in the internal list."""
        _spawned_marker_names.extend(["cam_marker_aaa", "cam_marker_bbb"])
        with mock.patch("testing_backend._detect_gz_world_name", return_value="empty"), \
             mock.patch("testing_backend.subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="data: true", stderr="")
            resp = client.post("/api/cam_markers/clear")
        assert resp.status_code == 200
        assert mock_run.call_count == 2
        all_calls = " ".join(" ".join(c[0][0]) for c in mock_run.call_args_list)
        assert "cam_marker_aaa" in all_calls
        assert "cam_marker_bbb" in all_calls

    def test_clear_empties_internal_list(self, client):
        """After clear, _spawned_marker_names must be empty."""
        _spawned_marker_names.extend(["cam_marker_ccc"])
        with mock.patch("testing_backend._detect_gz_world_name", return_value="empty"), \
             mock.patch("testing_backend.subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="data: true", stderr="")
            client.post("/api/cam_markers/clear")
        assert len(_spawned_marker_names) == 0


# ---------------------------------------------------------------------------
# Task 1.5 — POST /api/cam_markers/clear: empty list → 200, no gz calls
# ---------------------------------------------------------------------------
class TestCamMarkersClearEmpty:
    def test_clear_with_no_markers_returns_200(self, client):
        """clear with no markers placed returns 200."""
        resp = client.post("/api/cam_markers/clear")
        assert resp.status_code == 200

    def test_clear_with_no_markers_makes_no_gz_calls(self, client):
        """clear with no markers makes zero subprocess.run calls for gz remove."""
        with mock.patch("testing_backend._detect_gz_world_name", return_value="empty"), \
             mock.patch("testing_backend.subprocess.run") as mock_run:
            client.post("/api/cam_markers/clear")
        mock_run.assert_not_called()
