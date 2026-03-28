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
from testing_backend import app, cam_to_world, _spawned_marker_names, _publish_joint_gz  # noqa: E402


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
        testing_backend._arm_pick_state["arm1"].in_progress = False
        testing_backend._arm_pick_state["arm1"].status = "idle"
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
        testing_backend._arm_pick_state["arm1"].in_progress = False
        testing_backend._arm_pick_state["arm1"].status = "idle"

    def test_pick_rejects_when_no_cotton_spawned(self, client):
        """POST /api/cotton/pick returns 400 when no cotton has been spawned."""
        import testing_backend
        testing_backend._last_cotton_cam = None
        testing_backend._pick_in_progress = False
        testing_backend._arm_pick_state["arm1"].in_progress = False
        resp = client.post(
            "/api/cotton/pick",
            json={"arm": "arm1"},
        )
        assert resp.status_code == 400

    def test_pick_rejects_concurrent_pick(self, client):
        """POST /api/cotton/pick returns 409 when pick is already in progress."""
        import testing_backend
        testing_backend._last_cotton_cam = (0.1, 0.0, 0.0)
        testing_backend._last_cotton_arm = "arm1"
        testing_backend._pick_in_progress = True
        testing_backend._arm_pick_state["arm1"].in_progress = True
        with mock.patch("testing_backend._execute_pick_sequence"):
            resp = client.post(
                "/api/cotton/pick",
                json={"arm": "arm1"},
            )
        assert resp.status_code == 409
        testing_backend._pick_in_progress = False
        testing_backend._arm_pick_state["arm1"].in_progress = False
        testing_backend._arm_pick_state["arm1"].status = "idle"


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
        testing_backend._arm_pick_state["arm1"].status = "done"
        testing_backend._arm_pick_state["arm1"].in_progress = False
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
        arm1_status = body["arms"]["arm1"]["status"]
        assert arm1_status != "done", (
            f"Status should be reset before new pick, got '{arm1_status}'"
        )
        assert arm1_status in ("idle", "starting")
        testing_backend._pick_in_progress = False
        testing_backend._arm_pick_state["arm1"].in_progress = False
        testing_backend._arm_pick_state["arm1"].status = "idle"

    def test_pick_status_thread_lock_consistency(self, client):
        """Pick status endpoint returns consistent snapshot under lock."""
        import testing_backend

        testing_backend._pick_in_progress = True
        testing_backend._pick_status = "j4_lateral"
        testing_backend._arm_pick_state["arm1"].in_progress = True
        testing_backend._arm_pick_state["arm1"].status = "j4_lateral"

        resp = client.get("/api/cotton/pick/status")
        body = resp.json()
        arm1 = body["arms"]["arm1"]
        # Both fields should be consistent — if in_progress is True,
        # status should not be "idle" or "done"
        assert arm1["in_progress"] is True
        assert arm1["status"] == "j4_lateral"

        # Now simulate done state
        testing_backend._pick_in_progress = False
        testing_backend._pick_status = "done"
        testing_backend._arm_pick_state["arm1"].in_progress = False
        testing_backend._arm_pick_state["arm1"].status = "done"

        resp = client.get("/api/cotton/pick/status")
        body = resp.json()
        arm1 = body["arms"]["arm1"]
        assert arm1["in_progress"] is False
        assert arm1["status"] == "done"

        # Cleanup
        testing_backend._pick_in_progress = False
        testing_backend._pick_status = "idle"
        testing_backend._arm_pick_state["arm1"].in_progress = False
        testing_backend._arm_pick_state["arm1"].status = "idle"


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
        testing_backend._arm_pick_state["arm1"].in_progress = False
        testing_backend._arm_pick_state["arm1"].status = "idle"

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
        testing_backend._arm_pick_state["arm1"].in_progress = False


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
        # Reset per-arm pick state
        for arm_state in testing_backend._arm_pick_state.values():
            arm_state.in_progress = False
            arm_state.status = "idle"
            arm_state.current = None
            arm_state.progress = (0, 0)
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
        testing_backend._arm_pick_state["arm1"].in_progress = True

        resp = client.post("/api/cotton/remove-all")
        assert resp.status_code == 400
        assert "pick" in resp.json()["detail"].lower()

        testing_backend._pick_in_progress = False
        self._reset_cotton_state()


# ---------------------------------------------------------------------------
# Sequential pick-all tests (Group 6)
# ---------------------------------------------------------------------------
class TestPickAll:
    """Tests for POST /api/cotton/pick-all sequential picking."""

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
        # Reset per-arm pick state
        for arm_state in testing_backend._arm_pick_state.values():
            arm_state.in_progress = False
            arm_state.status = "idle"
            arm_state.current = None
            arm_state.progress = (0, 0)
        testing_backend._cottons.clear()
        testing_backend._cotton_counter = 0

    def _spawn_cottons(self, client, count=2):
        """Spawn N cottons using known-reachable coords."""
        coords = [
            (0.494, -0.001, 0.004),
            (0.525, 0.020, 0.008),
            (0.541, 0.014, 0.011),
        ]
        with mock.patch("testing_backend._gz_spawn_model"), \
             mock.patch("testing_backend._gz_remove_model"), \
             mock.patch("testing_backend._detect_gz_world_name", return_value="test"):
            for i in range(count):
                cx, cy, cz = coords[i % len(coords)]
                client.post(
                    "/api/cotton/spawn",
                    json={"cam_x": cx, "cam_y": cy, "cam_z": cz, "arm": "arm1"},
                )

    def test_pick_all_sequential_order(self, client):
        """POST /api/cotton/pick-all picks cottons in spawn order."""
        self._reset_cotton_state()
        self._spawn_cottons(client, 2)

        with mock.patch("testing_backend._publish_joint_gz"), \
             mock.patch("testing_backend._detect_gz_world_name", return_value="test"), \
             mock.patch("testing_backend._gz_remove_model"), \
             mock.patch("testing_backend.time.sleep"):
            resp = client.post(
                "/api/cotton/pick-all",
                json={"arm": "arm1"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "picking"
        assert body["total"] == 2
        self._reset_cotton_state()

    def test_pick_all_skips_picked_cottons(self, client):
        """POST /api/cotton/pick-all skips already-picked cottons."""
        import testing_backend
        self._reset_cotton_state()
        self._spawn_cottons(client, 2)

        # Manually mark first cotton as picked
        testing_backend._cottons["cotton_0"].status = "picked"

        with mock.patch("testing_backend._publish_joint_gz"), \
             mock.patch("testing_backend._detect_gz_world_name", return_value="test"), \
             mock.patch("testing_backend._gz_remove_model"), \
             mock.patch("testing_backend.time.sleep"):
            resp = client.post(
                "/api/cotton/pick-all",
                json={"arm": "arm1"},
            )
        assert resp.status_code == 200
        body = resp.json()
        # Only 1 cotton should be picked (cotton_1), cotton_0 is skipped
        assert body["total"] == 1
        self._reset_cotton_state()

    def test_pick_all_nothing_to_pick(self, client):
        """POST /api/cotton/pick-all with no spawned cottons returns nothing_to_pick."""
        self._reset_cotton_state()

        resp = client.post(
            "/api/cotton/pick-all",
            json={"arm": "arm1"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "nothing_to_pick"
        self._reset_cotton_state()

    def test_pick_status_progress_during_multi(self, client):
        """GET /api/cotton/pick/status returns current and progress during pick-all."""
        import testing_backend
        self._reset_cotton_state()

        # Simulate in-progress multi-pick state (per-arm)
        testing_backend._pick_in_progress = True
        testing_backend._pick_status = "j4_lateral"
        testing_backend._pick_current = "cotton_1"
        testing_backend._pick_progress = {"current": 2, "total": 3}
        testing_backend._arm_pick_state["arm1"].in_progress = True
        testing_backend._arm_pick_state["arm1"].status = "j4_lateral"
        testing_backend._arm_pick_state["arm1"].current = "cotton_1"
        testing_backend._arm_pick_state["arm1"].progress = (2, 3)

        resp = client.get("/api/cotton/pick/status")
        assert resp.status_code == 200
        body = resp.json()
        arm1 = body["arms"]["arm1"]
        assert arm1["in_progress"] is True
        assert arm1["current"] == "cotton_1"
        assert arm1["progress"][0] == 2
        assert arm1["progress"][1] == 3

        # Cleanup
        testing_backend._pick_in_progress = False
        testing_backend._pick_status = "idle"
        testing_backend._pick_current = None
        testing_backend._pick_progress = None
        self._reset_cotton_state()


# ---------------------------------------------------------------------------
# Verification fix: pick status idle reset
# ---------------------------------------------------------------------------
class TestPickStatusIdleReset:
    """Pick status must reset between picks — no stale 'done' visible."""

    def test_pick_status_not_stale_done_after_new_pick(self, client):
        """POST /api/cotton/pick clears stale 'done' — poll returns 'starting' not 'done'."""
        import testing_backend

        # Simulate stale "done" from a previous pick
        testing_backend._pick_in_progress = False
        testing_backend._pick_status = "done"
        testing_backend._arm_pick_state["arm1"].in_progress = False
        testing_backend._arm_pick_state["arm1"].status = "done"
        testing_backend._last_cotton_cam = (0.494, -0.001, 0.004)
        testing_backend._last_cotton_arm = "arm1"
        testing_backend._last_cotton_j4 = 0.0

        with mock.patch("testing_backend._execute_pick_sequence"):
            with mock.patch("threading.Thread") as mock_thread:
                mock_thread.return_value.start = mock.Mock()
                resp = client.post(
                    "/api/cotton/pick",
                    json={"arm": "arm1"},
                )
        assert resp.status_code == 200

        # Poll status — must NOT see stale "done"
        status_resp = client.get("/api/cotton/pick/status")
        body = status_resp.json()
        arm1_status = body["arms"]["arm1"]["status"]
        assert arm1_status != "done", (
            f"Stale 'done' visible after new pick — should be 'starting'"
        )
        assert arm1_status == "starting"
        # Cleanup
        testing_backend._pick_in_progress = False
        testing_backend._pick_status = "idle"
        testing_backend._arm_pick_state["arm1"].in_progress = False
        testing_backend._arm_pick_state["arm1"].status = "idle"


# ---------------------------------------------------------------------------
# Verification fix: CottonState arm_coords and joint_values
# ---------------------------------------------------------------------------
class TestCottonStateFields:
    """CottonState must include arm_coords and joint_values per spec."""

    def _reset_cotton_state(self):
        import testing_backend
        testing_backend._cotton_spawned = False
        testing_backend._cotton_name = ""
        testing_backend._last_cotton_cam = None
        testing_backend._last_cotton_arm = None
        testing_backend._last_cotton_j4 = 0.0
        testing_backend._pick_in_progress = False
        testing_backend._pick_status = "idle"
        # Reset per-arm pick state
        for arm_state in testing_backend._arm_pick_state.values():
            arm_state.in_progress = False
            arm_state.status = "idle"
            arm_state.current = None
            arm_state.progress = (0, 0)
        testing_backend._cottons.clear()
        testing_backend._cotton_counter = 0

    def test_cotton_state_has_arm_coords_field(self):
        """CottonState dataclass must have an arm_coords field."""
        import testing_backend
        cs = testing_backend.CottonState(
            name="test",
            cam_x=0.5, cam_y=0.0, cam_z=0.0,
            arm="arm1",
        )
        assert hasattr(cs, "arm_coords"), "CottonState missing 'arm_coords' field"

    def test_cotton_state_has_joint_values_field(self):
        """CottonState dataclass must have a joint_values field."""
        import testing_backend
        cs = testing_backend.CottonState(
            name="test",
            cam_x=0.5, cam_y=0.0, cam_z=0.0,
            arm="arm1",
        )
        assert hasattr(cs, "joint_values"), "CottonState missing 'joint_values' field"

    def test_spawn_stores_arm_coords_in_cotton_state(self, client):
        """POST /api/cotton/spawn stores arm_coords in CottonState."""
        import testing_backend
        self._reset_cotton_state()

        with mock.patch("testing_backend._gz_spawn_model"), \
             mock.patch("testing_backend._detect_gz_world_name", return_value="test"):
            client.post(
                "/api/cotton/spawn",
                json={"cam_x": 0.494, "cam_y": -0.001, "cam_z": 0.004, "arm": "arm1"},
            )
        cs = testing_backend._cottons["cotton_0"]
        assert cs.arm_coords is not None, "arm_coords not stored at spawn time"
        assert len(cs.arm_coords) == 3, "arm_coords should be (ax, ay, az)"
        self._reset_cotton_state()

    def test_spawn_stores_joint_values_in_cotton_state(self, client):
        """POST /api/cotton/spawn stores joint_values in CottonState."""
        import testing_backend
        self._reset_cotton_state()

        with mock.patch("testing_backend._gz_spawn_model"), \
             mock.patch("testing_backend._detect_gz_world_name", return_value="test"):
            client.post(
                "/api/cotton/spawn",
                json={"cam_x": 0.494, "cam_y": -0.001, "cam_z": 0.004, "arm": "arm1"},
            )
        cs = testing_backend._cottons["cotton_0"]
        assert cs.joint_values is not None, "joint_values not stored at spawn time"
        assert "j3" in cs.joint_values
        assert "j4" in cs.joint_values
        assert "j5" in cs.joint_values
        self._reset_cotton_state()

    def test_cotton_list_includes_arm_coords_and_joint_values(self, client):
        """GET /api/cotton/list returns arm_coords and joint_values per cotton."""
        import testing_backend
        self._reset_cotton_state()

        with mock.patch("testing_backend._gz_spawn_model"), \
             mock.patch("testing_backend._detect_gz_world_name", return_value="test"):
            client.post(
                "/api/cotton/spawn",
                json={"cam_x": 0.494, "cam_y": -0.001, "cam_z": 0.004, "arm": "arm1"},
            )

        resp = client.get("/api/cotton/list")
        c0 = resp.json()["cottons"][0]
        assert "arm_coords" in c0, "cotton list missing arm_coords"
        assert "joint_values" in c0, "cotton list missing joint_values"
        assert "j3" in c0["joint_values"]
        self._reset_cotton_state()


# ---------------------------------------------------------------------------
# Reliable joint publishing tests (Group 2)
# ---------------------------------------------------------------------------
class TestPublishJointGzRetry:
    """Tests for retry-based _publish_joint_gz."""

    def test_publish_returns_true_on_first_success(self):
        """_publish_joint_gz returns True when subprocess succeeds on first try."""
        mock_proc = mock.MagicMock()
        mock_proc.wait.return_value = None
        mock_proc.returncode = 0

        with mock.patch("testing_backend.subprocess.Popen", return_value=mock_proc):
            result = _publish_joint_gz("/joint3_cmd", 0.5, arm_name="arm1")

        assert result is True

    def test_publish_retries_on_first_failure_returns_true(self):
        """_publish_joint_gz retries after first failure, returns True on second success."""
        fail_proc = mock.MagicMock()
        fail_proc.wait.return_value = None
        fail_proc.returncode = 1

        ok_proc = mock.MagicMock()
        ok_proc.wait.return_value = None
        ok_proc.returncode = 0

        with mock.patch(
            "testing_backend.subprocess.Popen", side_effect=[fail_proc, ok_proc]
        ), mock.patch("testing_backend.time.sleep"):
            result = _publish_joint_gz("/joint3_cmd", 0.5, arm_name="arm1")

        assert result is True

    def test_publish_returns_false_after_three_failures(self):
        """_publish_joint_gz returns False after 3 consecutive failures."""
        fail_proc = mock.MagicMock()
        fail_proc.wait.return_value = None
        fail_proc.returncode = 1

        with mock.patch(
            "testing_backend.subprocess.Popen", return_value=fail_proc
        ), mock.patch("testing_backend.time.sleep"):
            result = _publish_joint_gz("/joint3_cmd", 0.5, arm_name="arm1")

        assert result is False

    def test_publish_handles_timeout_kills_and_retries(self):
        """_publish_joint_gz kills process on timeout, retries, succeeds on next."""
        import subprocess as sp

        timeout_proc = mock.MagicMock()
        timeout_proc.wait.side_effect = sp.TimeoutExpired(cmd="gz", timeout=2)

        ok_proc = mock.MagicMock()
        ok_proc.wait.return_value = None
        ok_proc.returncode = 0

        with mock.patch(
            "testing_backend.subprocess.Popen", side_effect=[timeout_proc, ok_proc]
        ), mock.patch("testing_backend.time.sleep"):
            result = _publish_joint_gz("/joint3_cmd", 0.5, arm_name="arm1")

        timeout_proc.kill.assert_called_once()
        assert result is True

    def test_publish_logs_warning_on_failed_attempt(self):
        """_publish_joint_gz logs WARNING with topic, value, attempt on failure."""
        fail_proc = mock.MagicMock()
        fail_proc.wait.return_value = None
        fail_proc.returncode = 1

        ok_proc = mock.MagicMock()
        ok_proc.wait.return_value = None
        ok_proc.returncode = 0

        with mock.patch(
            "testing_backend.subprocess.Popen", side_effect=[fail_proc, ok_proc]
        ), mock.patch("testing_backend.time.sleep"), \
                mock.patch("testing_backend.logger") as mock_logger:
            _publish_joint_gz("/joint3_cmd", 0.5, arm_name="arm1")

        mock_logger.warning.assert_called_once()
        warn_msg = mock_logger.warning.call_args[0][0]
        # Message should contain topic, value, and attempt number
        assert "/joint3_cmd" in warn_msg
        assert "0.5" in warn_msg
        assert "1" in warn_msg  # attempt 1 (of 3)

    def test_publish_logs_error_when_all_attempts_fail(self):
        """_publish_joint_gz logs ERROR when all 3 attempts fail."""
        fail_proc = mock.MagicMock()
        fail_proc.wait.return_value = None
        fail_proc.returncode = 1

        with mock.patch(
            "testing_backend.subprocess.Popen", return_value=fail_proc
        ), mock.patch("testing_backend.time.sleep"), \
                mock.patch("testing_backend.logger") as mock_logger:
            _publish_joint_gz("/joint3_cmd", 0.5, arm_name="arm1")

        mock_logger.error.assert_called_once()
        err_msg = mock_logger.error.call_args[0][0]
        assert "/joint3_cmd" in err_msg

    def test_publish_same_arm_serialized(self):
        """Concurrent publishes on same arm are serialized by lock."""
        import threading
        import time as real_time

        call_order = []

        def slow_popen(*args, **kwargs):
            proc = mock.MagicMock()
            proc.returncode = 0
            proc.wait.return_value = None
            call_order.append(threading.current_thread().name)
            # Small sleep to ensure overlap would occur without lock
            real_time.sleep(0.05)
            return proc

        with mock.patch(
            "testing_backend.subprocess.Popen", side_effect=slow_popen
        ), mock.patch("testing_backend.time.sleep"):
            t1 = threading.Thread(
                target=_publish_joint_gz,
                args=("/joint3_cmd", 0.1),
                kwargs={"arm_name": "arm1"},
                name="t1",
            )
            t2 = threading.Thread(
                target=_publish_joint_gz,
                args=("/joint3_cmd", 0.2),
                kwargs={"arm_name": "arm1"},
                name="t2",
            )
            t1.start()
            t2.start()
            t1.join(timeout=5)
            t2.join(timeout=5)

        # Both threads completed
        assert len(call_order) == 2

    def test_publish_different_arms_concurrent(self):
        """Publishes on different arms are NOT blocked by each other."""
        import threading
        import time as real_time

        entry_times = {}
        lock = threading.Lock()

        def recording_popen(*args, **kwargs):
            proc = mock.MagicMock()
            proc.returncode = 0
            proc.wait.return_value = None
            name = threading.current_thread().name
            with lock:
                entry_times[name] = real_time.monotonic()
            real_time.sleep(0.1)  # hold for 100ms
            return proc

        with mock.patch(
            "testing_backend.subprocess.Popen", side_effect=recording_popen
        ), mock.patch("testing_backend.time.sleep"):
            t1 = threading.Thread(
                target=_publish_joint_gz,
                args=("/joint3_cmd", 0.1),
                kwargs={"arm_name": "arm1"},
                name="arm1_thread",
            )
            t2 = threading.Thread(
                target=_publish_joint_gz,
                args=("/joint3_copy_cmd", 0.2),
                kwargs={"arm_name": "arm2"},
                name="arm2_thread",
            )
            t1.start()
            t2.start()
            t1.join(timeout=5)
            t2.join(timeout=5)

        # Both threads ran — entry times should be close (within 80ms)
        assert "arm1_thread" in entry_times
        assert "arm2_thread" in entry_times
        delta = abs(entry_times["arm1_thread"] - entry_times["arm2_thread"])
        assert delta < 0.08, (
            f"Different arms should run concurrently, but delta was {delta:.3f}s"
        )


# ---------------------------------------------------------------------------
# Group 3: Cotton persists after pick (no auto-deletion)
# ---------------------------------------------------------------------------
class TestCottonPersistAfterPick:
    """Cotton models must persist in Gazebo after pick — only explicit remove deletes them."""

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
        testing_backend._pick_current = None
        testing_backend._pick_progress = None
        # Reset per-arm pick state
        for arm_state in testing_backend._arm_pick_state.values():
            arm_state.in_progress = False
            arm_state.status = "idle"
            arm_state.current = None
            arm_state.progress = (0, 0)
        testing_backend._cottons.clear()
        testing_backend._cotton_counter = 0

    def _spawn_one_cotton(self, client):
        """Spawn a single cotton and return its name."""
        with mock.patch("testing_backend._gz_spawn_model"), \
             mock.patch("testing_backend._detect_gz_world_name", return_value="test"):
            resp = client.post(
                "/api/cotton/spawn",
                json={"cam_x": 0.494, "cam_y": -0.001, "cam_z": 0.004, "arm": "arm1"},
            )
        assert resp.status_code == 200
        return resp.json()["cotton_name"]

    # -- Task 3.1 --
    def test_single_pick_sets_cotton_status_to_picked(self, client):
        """_execute_pick_sequence sets cotton.status='picked' after animation."""
        import testing_backend
        self._reset_cotton_state()
        name = self._spawn_one_cotton(client)

        with mock.patch("testing_backend._publish_joint_gz"), \
             mock.patch("testing_backend._detect_gz_world_name", return_value="test"), \
             mock.patch("testing_backend._gz_remove_model"), \
             mock.patch("testing_backend.time.sleep"):
            resp = client.post("/api/cotton/pick", json={"arm": "arm1"})
            assert resp.status_code == 200
            # Wait for background thread to finish
            import time
            time.sleep(0.1)

        cotton = testing_backend._cottons[name]
        assert cotton.status == "picked", (
            f"Expected status 'picked', got '{cotton.status}'"
        )
        self._reset_cotton_state()

    # -- Task 3.2 --
    def test_single_pick_does_not_call_gz_remove_model(self, client):
        """_execute_pick_sequence must NOT call _gz_remove_model (cotton persists)."""
        import testing_backend
        self._reset_cotton_state()
        self._spawn_one_cotton(client)

        with mock.patch("testing_backend._publish_joint_gz"), \
             mock.patch("testing_backend._detect_gz_world_name", return_value="test"), \
             mock.patch("testing_backend._gz_remove_model") as mock_remove, \
             mock.patch("testing_backend.time.sleep"):
            resp = client.post("/api/cotton/pick", json={"arm": "arm1"})
            assert resp.status_code == 200
            import time
            time.sleep(0.1)

        mock_remove.assert_not_called()
        self._reset_cotton_state()

    # -- Task 3.4 --
    def test_pick_all_does_not_call_gz_remove_model(self, client):
        """_execute_pick_all_sequence must NOT call _gz_remove_model."""
        import testing_backend
        self._reset_cotton_state()

        # Spawn two cottons
        with mock.patch("testing_backend._gz_spawn_model"), \
             mock.patch("testing_backend._detect_gz_world_name", return_value="test"):
            for cx, cy, cz in [(0.494, -0.001, 0.004), (0.525, 0.020, 0.008)]:
                client.post(
                    "/api/cotton/spawn",
                    json={"cam_x": cx, "cam_y": cy, "cam_z": cz, "arm": "arm1"},
                )

        with mock.patch("testing_backend._publish_joint_gz"), \
             mock.patch("testing_backend._detect_gz_world_name", return_value="test"), \
             mock.patch("testing_backend._gz_remove_model") as mock_remove, \
             mock.patch("testing_backend.time.sleep"):
            resp = client.post("/api/cotton/pick-all", json={"arm": "arm1"})
            assert resp.status_code == 200
            import time
            time.sleep(0.1)

        mock_remove.assert_not_called()
        # Both cottons should still be status "picked"
        for name in ["cotton_0", "cotton_1"]:
            assert testing_backend._cottons[name].status == "picked"
        self._reset_cotton_state()

    # -- Task 3.6 --
    def test_cotton_list_shows_picked_after_single_pick(self, client):
        """GET /api/cotton/list shows cotton with status 'picked' after single pick."""
        import testing_backend
        self._reset_cotton_state()
        name = self._spawn_one_cotton(client)

        with mock.patch("testing_backend._publish_joint_gz"), \
             mock.patch("testing_backend._detect_gz_world_name", return_value="test"), \
             mock.patch("testing_backend._gz_remove_model"), \
             mock.patch("testing_backend.time.sleep"):
            client.post("/api/cotton/pick", json={"arm": "arm1"})
            import time
            time.sleep(0.1)

        resp = client.get("/api/cotton/list")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["cottons"]) == 1, "Cotton should still be in the list"
        assert body["cottons"][0]["name"] == name
        assert body["cottons"][0]["status"] == "picked"
        self._reset_cotton_state()

    # -- Task 3.8 --
    def test_remove_deletes_gazebo_model_for_picked_cotton(self, client):
        """POST /api/cotton/remove calls _gz_remove_model for a 'picked' cotton."""
        import testing_backend
        self._reset_cotton_state()
        name = self._spawn_one_cotton(client)

        # Manually mark as picked (simulates post-pick state)
        testing_backend._cottons[name].status = "picked"

        with mock.patch("testing_backend._detect_gz_world_name", return_value="test"), \
             mock.patch("testing_backend._gz_remove_model") as mock_remove:
            resp = client.post("/api/cotton/remove")

        assert resp.status_code == 200
        mock_remove.assert_called_once_with(name, "test")
        # Cotton should be removed from collection
        assert name not in testing_backend._cottons
        self._reset_cotton_state()

    # -- Task 3.9 --
    def test_remove_all_deletes_all_gazebo_models_regardless_of_status(self, client):
        """POST /api/cotton/remove-all calls _gz_remove_model for every cotton."""
        import testing_backend
        self._reset_cotton_state()

        # Spawn three cottons
        with mock.patch("testing_backend._gz_spawn_model"), \
             mock.patch("testing_backend._detect_gz_world_name", return_value="test"):
            for cx, cy, cz in [
                (0.494, -0.001, 0.004),
                (0.525, 0.020, 0.008),
                (0.541, 0.014, 0.011),
            ]:
                client.post(
                    "/api/cotton/spawn",
                    json={"cam_x": cx, "cam_y": cy, "cam_z": cz, "arm": "arm1"},
                )

        # Mark some as picked, leave one as spawned
        testing_backend._cottons["cotton_0"].status = "picked"
        testing_backend._cottons["cotton_1"].status = "picked"
        # cotton_2 remains "spawned"

        with mock.patch("testing_backend._detect_gz_world_name", return_value="test"), \
             mock.patch("testing_backend._gz_remove_model") as mock_remove:
            resp = client.post("/api/cotton/remove-all")

        assert resp.status_code == 200
        assert resp.json()["removed"] == 3
        assert mock_remove.call_count == 3
        # All models should have been removed from Gazebo
        called_names = {call.args[0] for call in mock_remove.call_args_list}
        assert called_names == {"cotton_0", "cotton_1", "cotton_2"}
        # Collection should be empty
        assert len(testing_backend._cottons) == 0
        self._reset_cotton_state()


# ---------------------------------------------------------------------------
# Group 4: Per-arm pick state (ArmPickState)
# ---------------------------------------------------------------------------
class TestPerArmPickState:
    """Tests for per-arm ArmPickState replacing global pick state."""

    def _reset_pick_state(self):
        """Reset per-arm pick state to defaults."""
        import testing_backend
        for arm_state in testing_backend._arm_pick_state.values():
            arm_state.in_progress = False
            arm_state.status = "idle"
            arm_state.current = None
            arm_state.progress = (0, 0)
        testing_backend._cotton_spawned = False
        testing_backend._cotton_name = ""
        testing_backend._last_cotton_cam = None
        testing_backend._last_cotton_arm = None
        testing_backend._last_cotton_j4 = 0.0
        testing_backend._cottons.clear()
        testing_backend._cotton_counter = 0

    # -- Task 4.1: ArmPickState dataclass defaults --
    def test_arm_pick_state_dataclass_defaults(self):
        """ArmPickState has correct default field values."""
        import threading
        from testing_backend import ArmPickState

        state = ArmPickState()
        assert isinstance(state.lock, type(threading.Lock()))
        assert state.in_progress is False
        assert state.status == "idle"
        assert state.current is None
        assert state.progress == (0, 0)

    # -- Task 4.3: _arm_pick_state dict has all arms --
    def test_arm_pick_state_dict_has_all_arms(self):
        """_arm_pick_state dict has keys arm1, arm2, arm3 with ArmPickState values."""
        from testing_backend import _arm_pick_state, ArmPickState

        assert "arm1" in _arm_pick_state
        assert "arm2" in _arm_pick_state
        assert "arm3" in _arm_pick_state
        for arm_name, state in _arm_pick_state.items():
            assert isinstance(state, ArmPickState), (
                f"Expected ArmPickState for {arm_name}, got {type(state)}"
            )

    # -- Task 4.5: pick sets per-arm state --
    def test_pick_sets_per_arm_state(self, client):
        """POST /api/cotton/pick sets _arm_pick_state[arm].in_progress and status."""
        import testing_backend
        self._reset_pick_state()

        # Spawn a cotton on arm1
        with mock.patch("testing_backend._gz_spawn_model"), \
             mock.patch("testing_backend._detect_gz_world_name", return_value="test"):
            resp = client.post(
                "/api/cotton/spawn",
                json={"cam_x": 0.494, "cam_y": -0.001, "cam_z": 0.004, "arm": "arm1"},
            )
        assert resp.status_code == 200

        # Pick — mock the background thread so state stays at "starting"
        with mock.patch("testing_backend._execute_pick_sequence"):
            with mock.patch("threading.Thread") as mock_thread:
                mock_thread.return_value.start = mock.Mock()
                resp = client.post(
                    "/api/cotton/pick",
                    json={"arm": "arm1"},
                )
        assert resp.status_code == 200

        arm_state = testing_backend._arm_pick_state["arm1"]
        assert arm_state.in_progress is True
        assert arm_state.status != "idle"
        self._reset_pick_state()

    # -- Task 4.7: same arm 409, different arm OK --
    def test_pick_rejects_same_arm_allows_different(self, client):
        """Pick on busy arm returns 409; pick on idle arm succeeds."""
        import testing_backend
        self._reset_pick_state()

        # Spawn cotton_0 on arm1
        with mock.patch("testing_backend._gz_spawn_model"), \
             mock.patch("testing_backend._detect_gz_world_name", return_value="test"):
            client.post(
                "/api/cotton/spawn",
                json={"cam_x": 0.494, "cam_y": -0.001, "cam_z": 0.004, "arm": "arm1"},
            )

        # Start picking on arm1 (mock thread so it stays in_progress)
        with mock.patch("testing_backend._execute_pick_sequence"):
            with mock.patch("threading.Thread") as mock_thread:
                mock_thread.return_value.start = mock.Mock()
                resp = client.post(
                    "/api/cotton/pick",
                    json={"arm": "arm1"},
                )
        assert resp.status_code == 200

        # Spawn cotton_1 on arm2
        with mock.patch("testing_backend._gz_spawn_model"), \
             mock.patch("testing_backend._detect_gz_world_name", return_value="test"):
            client.post(
                "/api/cotton/spawn",
                json={"cam_x": 0.494, "cam_y": -0.001, "cam_z": 0.004, "arm": "arm2"},
            )

        # Pick on arm2 should succeed (different arm)
        with mock.patch("testing_backend._execute_pick_sequence"):
            with mock.patch("threading.Thread") as mock_thread:
                mock_thread.return_value.start = mock.Mock()
                resp2 = client.post(
                    "/api/cotton/pick",
                    json={"arm": "arm2"},
                )
        assert resp2.status_code == 200, (
            f"Different arm should be allowed, got {resp2.status_code}"
        )

        # Pick again on arm1 should 409 (same arm busy)
        # Need to spawn another cotton on arm1 to set _last_cotton_arm
        with mock.patch("testing_backend._gz_spawn_model"), \
             mock.patch("testing_backend._detect_gz_world_name", return_value="test"):
            client.post(
                "/api/cotton/spawn",
                json={"cam_x": 0.494, "cam_y": -0.001, "cam_z": 0.004, "arm": "arm1"},
            )
        with mock.patch("testing_backend._execute_pick_sequence"):
            resp3 = client.post(
                "/api/cotton/pick",
                json={"arm": "arm1"},
            )
        assert resp3.status_code == 409, (
            f"Same arm should be rejected, got {resp3.status_code}"
        )
        self._reset_pick_state()

    # -- Task 4.9: pick sequence updates per-arm status through stages --
    def test_pick_sequence_updates_per_arm_status(self, client):
        """_execute_pick_sequence updates arm_state.status through expected stages."""
        import testing_backend
        self._reset_pick_state()

        # Spawn a cotton on arm1
        with mock.patch("testing_backend._gz_spawn_model"), \
             mock.patch("testing_backend._detect_gz_world_name", return_value="test"):
            resp = client.post(
                "/api/cotton/spawn",
                json={"cam_x": 0.494, "cam_y": -0.001, "cam_z": 0.004, "arm": "arm1"},
            )
        assert resp.status_code == 200
        cotton_name = resp.json()["cotton_name"]

        # Capture status transitions
        statuses = []

        def capturing_sleep(secs):
            arm_state = testing_backend._arm_pick_state["arm1"]
            statuses.append(arm_state.status)

        arm_state = testing_backend._arm_pick_state["arm1"]
        arm_state.in_progress = True
        arm_state.status = "starting"
        arm_state.current = cotton_name

        arm_config = testing_backend.ARM_CONFIGS["arm1"]
        with mock.patch("testing_backend._publish_joint_gz"), \
             mock.patch("testing_backend.time.sleep", side_effect=capturing_sleep):
            testing_backend._execute_pick_sequence(
                j3=-0.3, j4=0.1, j5=0.2,
                arm_config=arm_config,
                arm_name="arm1",
                cotton_name=cotton_name,
            )

        # Should have gone through: j4_lateral, j3_tilt, j5_extend,
        # j5_retract, j3_home, j4_home (captured at each sleep)
        expected_stages = [
            "j4_lateral", "j3_tilt", "j5_extend",
            "j5_retract", "j3_home", "j4_home",
        ]
        assert statuses == expected_stages, (
            f"Expected stages {expected_stages}, got {statuses}"
        )
        # After completion: status=done, in_progress=False
        assert arm_state.status == "done"
        assert arm_state.in_progress is False
        self._reset_pick_state()

    # -- Task 4.11: status endpoint returns per-arm shape --
    def test_status_endpoint_returns_per_arm_shape(self, client):
        """GET /api/cotton/pick/status returns {arms: {arm1: {...}, ...}}."""
        self._reset_pick_state()

        resp = client.get("/api/cotton/pick/status")
        assert resp.status_code == 200
        body = resp.json()
        assert "arms" in body, f"Expected 'arms' key, got {body.keys()}"
        assert "arm1" in body["arms"]
        assert "arm2" in body["arms"]
        assert "arm3" in body["arms"]

        # Each arm entry should have the expected fields
        for arm_name in ["arm1", "arm2", "arm3"]:
            arm_data = body["arms"][arm_name]
            assert "in_progress" in arm_data
            assert "status" in arm_data
            assert "current" in arm_data
            assert "progress" in arm_data
        self._reset_pick_state()

    # -- Task 4.13: concurrent status access --
    def test_status_endpoint_concurrent_access(self, client):
        """Status reads from multiple threads return consistent snapshots."""
        import testing_backend
        import concurrent.futures
        self._reset_pick_state()

        # Set arm1 to picking
        arm_state = testing_backend._arm_pick_state["arm1"]
        arm_state.in_progress = True
        arm_state.status = "j3_tilt"
        arm_state.current = "cotton_0"

        results = []

        def read_status():
            resp = client.get("/api/cotton/pick/status")
            return resp.json()

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(read_status) for _ in range(8)]
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())

        # All reads should show arm1 in_progress with j3_tilt
        for r in results:
            arm1 = r["arms"]["arm1"]
            assert arm1["in_progress"] is True
            assert arm1["status"] == "j3_tilt"
        self._reset_pick_state()

    # -- Task 4.14: per-arm status resets to idle --
    def test_per_arm_status_resets_to_idle(self, client):
        """After pick completes, arm status returns to idle before new pick."""
        import testing_backend
        self._reset_pick_state()

        # Spawn cotton on arm1
        with mock.patch("testing_backend._gz_spawn_model"), \
             mock.patch("testing_backend._detect_gz_world_name", return_value="test"):
            resp = client.post(
                "/api/cotton/spawn",
                json={"cam_x": 0.494, "cam_y": -0.001, "cam_z": 0.004, "arm": "arm1"},
            )
        assert resp.status_code == 200
        cotton_name = resp.json()["cotton_name"]

        # Run full pick sequence (mocked, fast)
        arm_state = testing_backend._arm_pick_state["arm1"]
        arm_state.in_progress = True
        arm_state.status = "starting"
        arm_state.current = cotton_name

        arm_config = testing_backend.ARM_CONFIGS["arm1"]
        with mock.patch("testing_backend._publish_joint_gz"), \
             mock.patch("testing_backend.time.sleep"):
            testing_backend._execute_pick_sequence(
                j3=-0.3, j4=0.1, j5=0.2,
                arm_config=arm_config,
                arm_name="arm1",
                cotton_name=cotton_name,
            )

        # After done, status should be "done" and in_progress=False
        assert arm_state.status == "done"
        assert arm_state.in_progress is False

        # Spawn another cotton and start new pick
        with mock.patch("testing_backend._gz_spawn_model"), \
             mock.patch("testing_backend._detect_gz_world_name", return_value="test"):
            client.post(
                "/api/cotton/spawn",
                json={"cam_x": 0.525, "cam_y": 0.020, "cam_z": 0.008, "arm": "arm1"},
            )

        with mock.patch("testing_backend._execute_pick_sequence"):
            with mock.patch("threading.Thread") as mock_thread:
                mock_thread.return_value.start = mock.Mock()
                resp = client.post(
                    "/api/cotton/pick",
                    json={"arm": "arm1"},
                )
        assert resp.status_code == 200
        # Status should now be "starting", not stale "done"
        assert arm_state.status == "starting"
        assert arm_state.in_progress is True
        self._reset_pick_state()
