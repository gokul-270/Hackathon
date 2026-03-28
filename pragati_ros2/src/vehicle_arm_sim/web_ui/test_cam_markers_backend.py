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
    def test_cam_to_world_returns_finite_values(self):
        """cam_to_world(0, 0, 0) must return finite world coordinates."""
        wx, wy, wz = cam_to_world(0.0, 0.0, 0.0)
        import math
        assert math.isfinite(wx), f"wx={wx}"
        assert math.isfinite(wy), f"wy={wy}"
        assert math.isfinite(wz), f"wz={wz}"

    def test_cam_to_world_deterministic(self):
        """Two calls with same inputs return identical results."""
        r1 = cam_to_world(0.1, -0.02, 0.05)
        r2 = cam_to_world(0.1, -0.02, 0.05)
        assert r1 == r2


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


# ---------------------------------------------------------------------------
# Cotton spawn endpoint tests
# ---------------------------------------------------------------------------
class TestCottonSpawn:
    def test_spawn_returns_200_with_world_coords(self, client):
        """POST /api/cotton/spawn with valid cam coords returns 200 + world position."""
        with mock.patch("testing_backend.subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="data: true", stderr="")
            resp = client.post(
                "/api/cotton/spawn",
                json={"cam_x": 0.494, "cam_y": -0.001, "cam_z": 0.004, "arm": "arm1", "j4_pos": 0.0},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "world_x" in body
        assert "world_y" in body
        assert "world_z" in body

    def test_spawn_calls_gz_create(self, client):
        """POST /api/cotton/spawn calls gz service create."""
        with mock.patch("testing_backend.subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="data: true", stderr="")
            client.post(
                "/api/cotton/spawn",
                json={"cam_x": 0.494, "cam_y": -0.001, "cam_z": 0.004, "arm": "arm1", "j4_pos": 0.0},
            )
        assert mock_run.called
        call_args = " ".join(mock_run.call_args_list[-1][0][0])
        assert "create" in call_args


# ---------------------------------------------------------------------------
# Cotton remove endpoint tests
# ---------------------------------------------------------------------------
class TestCottonRemove:
    def test_remove_returns_200(self, client):
        """POST /api/cotton/remove returns 200."""
        with mock.patch("testing_backend._detect_gz_world_name", return_value="empty"), \
             mock.patch("testing_backend.subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="data: true", stderr="")
            resp = client.post("/api/cotton/remove")
        assert resp.status_code == 200

    def test_remove_clears_cotton_state(self, client):
        """After remove, _cotton_spawned is False."""
        import testing_backend
        testing_backend._cotton_spawned = True
        with mock.patch("testing_backend._detect_gz_world_name", return_value="empty"), \
             mock.patch("testing_backend.subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="data: true", stderr="")
            client.post("/api/cotton/remove")
        assert testing_backend._cotton_spawned is False


# ---------------------------------------------------------------------------
# Cotton compute endpoint tests
# ---------------------------------------------------------------------------
class TestCottonCompute:
    def test_compute_returns_polar_values(self, client):
        """POST /api/cotton/compute returns r, theta, phi, j3, j4, j5, reachable."""
        resp = client.post(
            "/api/cotton/compute",
            json={"cam_x": 0.328, "cam_y": -0.011, "cam_z": -0.003, "arm": "arm1", "j4_pos": 0.0},
        )
        assert resp.status_code == 200
        body = resp.json()
        for key in ("r", "theta", "phi", "j3", "j4", "j5", "reachable"):
            assert key in body, f"Missing key: {key}"

    def test_compute_unreachable_returns_reachable_false(self, client):
        """Extreme camera coords produce reachable=false."""
        resp = client.post(
            "/api/cotton/compute",
            json={"cam_x": 10.0, "cam_y": 10.0, "cam_z": 10.0, "arm": "arm1", "j4_pos": 0.0},
        )
        assert resp.status_code == 200
        assert resp.json()["reachable"] is False


# ---------------------------------------------------------------------------
# Cotton pick endpoint tests
# ---------------------------------------------------------------------------
class TestCottonPick:
    def test_pick_returns_200_with_sequence_info(self, client):
        """POST /api/cotton/pick returns 200 with computed joint values and status."""
        import testing_backend
        testing_backend._last_cotton_cam = (0.328, -0.011, -0.003)
        testing_backend._last_cotton_arm = "arm1"
        testing_backend._last_cotton_j4 = 0.0
        testing_backend._pick_in_progress = False
        with mock.patch("testing_backend._execute_pick_sequence"):
            resp = client.post(
                "/api/cotton/pick",
                json={"arm": "arm1", "enable_phi_compensation": False},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "j3" in body
        assert "j4" in body
        assert "j5" in body
        assert body["status"] == "picking"
        testing_backend._pick_in_progress = False

    def test_pick_rejects_when_no_cotton_spawned(self, client):
        """POST /api/cotton/pick returns 400 when no cotton has been spawned."""
        import testing_backend
        testing_backend._last_cotton_cam = None
        testing_backend._pick_in_progress = False
        resp = client.post(
            "/api/cotton/pick",
            json={"arm": "arm1"},
        )
        assert resp.status_code == 400

    def test_pick_rejects_concurrent_pick(self, client):
        """POST /api/cotton/pick returns 409 when pick is already in progress."""
        import testing_backend
        testing_backend._last_cotton_cam = (0.1, 0.0, 0.0)
        testing_backend._pick_in_progress = True
        with mock.patch("testing_backend._execute_pick_sequence"):
            resp = client.post(
                "/api/cotton/pick",
                json={"arm": "arm1"},
            )
        assert resp.status_code == 409
        testing_backend._pick_in_progress = False


# ---------------------------------------------------------------------------
# Pick status reliability tests (Group 1)
# ---------------------------------------------------------------------------
class TestPickStatusReliability:
    def test_pick_status_resets_to_idle_between_picks(self, client):
        """GET /api/cotton/pick/status returns 'idle' immediately after new pick starts."""
        import testing_backend

        # Simulate a completed previous pick
        testing_backend._pick_status = "done"
        testing_backend._pick_in_progress = False
        testing_backend._last_cotton_cam = (0.494, -0.001, 0.004)
        testing_backend._last_cotton_arm = "arm1"
        testing_backend._last_cotton_j4 = 0.0

        # Start a new pick (mock the background thread so it doesn't run)
        with mock.patch("testing_backend._execute_pick_sequence"):
            with mock.patch("threading.Thread") as mock_thread:
                mock_thread.return_value.start = mock.Mock()
                resp = client.post(
                    "/api/cotton/pick",
                    json={"arm": "arm1"},
                )
        assert resp.status_code == 200

        # Status should NOT be "done" from the previous pick
        status_resp = client.get("/api/cotton/pick/status")
        body = status_resp.json()
        assert body["status"] != "done", (
            f"Status should be reset before new pick, got '{body['status']}'"
        )
        assert body["status"] in ("idle", "starting")
        testing_backend._pick_in_progress = False

    def test_pick_status_thread_lock_consistency(self, client):
        """Pick status endpoint returns consistent snapshot under lock."""
        import testing_backend

        testing_backend._pick_in_progress = True
        testing_backend._pick_status = "j4_lateral"

        resp = client.get("/api/cotton/pick/status")
        body = resp.json()
        # Both fields should be consistent — if in_progress is True,
        # status should not be "idle" or "done"
        assert body["in_progress"] is True
        assert body["status"] == "j4_lateral"

        # Now simulate done state
        testing_backend._pick_in_progress = False
        testing_backend._pick_status = "done"

        resp = client.get("/api/cotton/pick/status")
        body = resp.json()
        assert body["in_progress"] is False
        assert body["status"] == "done"

        # Cleanup
        testing_backend._pick_in_progress = False
        testing_backend._pick_status = "idle"


# ---------------------------------------------------------------------------
# Reachable target validation tests (Group 3)
# ---------------------------------------------------------------------------
class TestReachableTargetValidation:
    def test_spawn_unreachable_j3_above_arm(self, client):
        """POST /api/cotton/spawn returns 400 when target is above arm (phi > 0)."""
        # cam coords that produce positive phi (unreachable — above arm)
        # Using the OLD default coords which are unreachable with correct transform
        # cam(0.10, -0.10, 0.0) → az positive → phi positive → J3 out of range
        with mock.patch("testing_backend._gz_spawn_model"):
            resp = client.post(
                "/api/cotton/spawn",
                json={"cam_x": 0.10, "cam_y": -0.10, "cam_z": 0.0, "arm": "arm1"},
            )
        assert resp.status_code == 400
        body = resp.json()
        assert "unreachable" in body["detail"].lower() or "out of range" in body["detail"].lower()

    def test_spawn_unreachable_j5_too_close(self, client):
        """POST /api/cotton/spawn returns 400 when target is too close (r < HARDWARE_OFFSET)."""
        # Very small cam coords → small r → J5 negative
        with mock.patch("testing_backend._gz_spawn_model"):
            resp = client.post(
                "/api/cotton/spawn",
                json={"cam_x": 0.05, "cam_y": 0.05, "cam_z": 0.0, "arm": "arm1"},
            )
        assert resp.status_code == 400
        body = resp.json()
        assert "unreachable" in body["detail"].lower() or "out of range" in body["detail"].lower()

    def test_spawn_reachable_returns_200(self, client):
        """POST /api/cotton/spawn returns 200 with cotton name for valid coords."""
        # Known reachable coords from real arm log
        with mock.patch("testing_backend._gz_spawn_model"):
            with mock.patch("testing_backend._detect_gz_world_name", return_value="test"):
                with mock.patch("testing_backend._gz_remove_model"):
                    resp = client.post(
                        "/api/cotton/spawn",
                        json={"cam_x": 0.494, "cam_y": -0.001, "cam_z": 0.004, "arm": "arm1"},
                    )
        assert resp.status_code == 200
        body = resp.json()
        assert "cotton_name" in body
        assert body["status"] == "ok"

    def test_pick_after_remove_rejected(self, client):
        """POST /api/cotton/pick returns 400 after cotton has been removed."""
        import testing_backend

        # Spawn a cotton
        testing_backend._last_cotton_cam = (0.494, -0.001, 0.004)
        testing_backend._last_cotton_arm = "arm1"
        testing_backend._last_cotton_j4 = 0.0
        testing_backend._cotton_spawned = True
        testing_backend._pick_in_progress = False

        # Remove it
        with mock.patch("testing_backend._detect_gz_world_name", return_value="test"):
            with mock.patch("testing_backend._gz_remove_model"):
                client.post("/api/cotton/remove")

        # Now try to pick — should be rejected
        resp = client.post(
            "/api/cotton/pick",
            json={"arm": "arm1"},
        )
        assert resp.status_code == 400
        testing_backend._pick_in_progress = False


# ---------------------------------------------------------------------------
# Multi-cotton backend state tests (Group 4)
# ---------------------------------------------------------------------------
class TestMultiCottonState:
    """Tests for multi-cotton collection management."""

    def _reset_cotton_state(self):
        """Reset all cotton globals to clean state."""
        import testing_backend
        testing_backend._cotton_spawned = False
        testing_backend._cotton_name = ""
        testing_backend._last_cotton_cam = None
        testing_backend._last_cotton_arm = None
        testing_backend._last_cotton_j4 = 0.0
        testing_backend._pick_in_progress = False
        testing_backend._pick_status = "idle"
        # Reset multi-cotton collection if it exists
        if hasattr(testing_backend, "_cottons"):
            testing_backend._cottons.clear()
        if hasattr(testing_backend, "_cotton_counter"):
            testing_backend._cotton_counter = 0

    def test_spawn_multiple_cottons_unique_names(self, client):
        """Three spawns produce cotton_0, cotton_1, cotton_2."""
        self._reset_cotton_state()
        names = []
        with mock.patch("testing_backend._gz_spawn_model"), \
             mock.patch("testing_backend._gz_remove_model"), \
             mock.patch("testing_backend._detect_gz_world_name", return_value="test"):
            for _ in range(3):
                resp = client.post(
                    "/api/cotton/spawn",
                    json={"cam_x": 0.494, "cam_y": -0.001, "cam_z": 0.004, "arm": "arm1"},
                )
                assert resp.status_code == 200
                names.append(resp.json()["cotton_name"])
        assert names == ["cotton_0", "cotton_1", "cotton_2"]
        self._reset_cotton_state()

    def test_cotton_counter_no_reset_after_remove(self, client):
        """Counter continues after remove — spawn, remove, spawn gives cotton_0, cotton_1."""
        self._reset_cotton_state()
        with mock.patch("testing_backend._gz_spawn_model"), \
             mock.patch("testing_backend._gz_remove_model"), \
             mock.patch("testing_backend._detect_gz_world_name", return_value="test"):
            # Spawn cotton_0
            resp = client.post(
                "/api/cotton/spawn",
                json={"cam_x": 0.494, "cam_y": -0.001, "cam_z": 0.004, "arm": "arm1"},
            )
            assert resp.json()["cotton_name"] == "cotton_0"

            # Remove it
            client.post("/api/cotton/remove")

            # Spawn again — should be cotton_1, not cotton_0
            resp = client.post(
                "/api/cotton/spawn",
                json={"cam_x": 0.525, "cam_y": 0.020, "cam_z": 0.008, "arm": "arm1"},
            )
            assert resp.json()["cotton_name"] == "cotton_1"
        self._reset_cotton_state()

    def test_cotton_list_endpoint(self, client):
        """GET /api/cotton/list returns all cottons with coords and status."""
        self._reset_cotton_state()
        with mock.patch("testing_backend._gz_spawn_model"), \
             mock.patch("testing_backend._gz_remove_model"), \
             mock.patch("testing_backend._detect_gz_world_name", return_value="test"):
            # Spawn two cottons
            client.post(
                "/api/cotton/spawn",
                json={"cam_x": 0.494, "cam_y": -0.001, "cam_z": 0.004, "arm": "arm1"},
            )
            client.post(
                "/api/cotton/spawn",
                json={"cam_x": 0.525, "cam_y": 0.020, "cam_z": 0.008, "arm": "arm1"},
            )

        resp = client.get("/api/cotton/list")
        assert resp.status_code == 200
        body = resp.json()
        assert "cottons" in body
        assert len(body["cottons"]) == 2
        # Each cotton should have name, cam coords, status
        c0 = body["cottons"][0]
        assert c0["name"] == "cotton_0"
        assert "cam_x" in c0
        assert "status" in c0
        assert c0["status"] == "spawned"
        self._reset_cotton_state()

    def test_remove_all_deletes_all_cottons(self, client):
        """POST /api/cotton/remove-all clears the collection."""
        self._reset_cotton_state()
        with mock.patch("testing_backend._gz_spawn_model"), \
             mock.patch("testing_backend._gz_remove_model"), \
             mock.patch("testing_backend._detect_gz_world_name", return_value="test"):
            # Spawn two cottons
            client.post(
                "/api/cotton/spawn",
                json={"cam_x": 0.494, "cam_y": -0.001, "cam_z": 0.004, "arm": "arm1"},
            )
            client.post(
                "/api/cotton/spawn",
                json={"cam_x": 0.525, "cam_y": 0.020, "cam_z": 0.008, "arm": "arm1"},
            )

            # Remove all
            resp = client.post("/api/cotton/remove-all")
        assert resp.status_code == 200
        assert resp.json()["removed"] == 2

        # List should be empty
        resp = client.get("/api/cotton/list")
        assert len(resp.json()["cottons"]) == 0
        self._reset_cotton_state()

    def test_remove_all_blocked_during_pick(self, client):
        """POST /api/cotton/remove-all returns 400 during active pick."""
        import testing_backend
        self._reset_cotton_state()
        testing_backend._pick_in_progress = True

        resp = client.post("/api/cotton/remove-all")
        assert resp.status_code == 400
        assert "pick" in resp.json()["detail"].lower()

        testing_backend._pick_in_progress = False
        self._reset_cotton_state()
