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
        """cam_to_world with a non-zero input must return finite non-zero world coordinates."""
        import math
        wx, wy, wz = cam_to_world(0.3, -0.065, 0.0)
        assert math.isfinite(wx), f"wx={wx}"
        assert math.isfinite(wy), f"wy={wy}"
        assert math.isfinite(wz), f"wz={wz}"
        magnitude = math.sqrt(wx ** 2 + wy ** 2 + wz ** 2)
        assert magnitude > 0.0, (
            f"cam_to_world(0.3, -0.065, 0.0) returned zero-magnitude world vector "
            f"({wx}, {wy}, {wz}); FK must produce a non-zero position for non-zero input"
        )

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
        cmd_str = " ".join(call_args)
        assert "gz" in call_args, "Command must start with 'gz'"
        assert "create" in cmd_str, "Command must contain 'create' subcommand"
        assert any("/world/" in str(a) for a in call_args), (
            f"gz service call must use a /world/... service path; got args={call_args}"
        )

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
        """POST /api/cotton/spawn with valid cam coords returns 200 + finite world position."""
        import math
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
        assert math.isfinite(body["world_x"]), f"world_x must be finite, got {body['world_x']}"
        assert math.isfinite(body["world_y"]), f"world_y must be finite, got {body['world_y']}"
        assert math.isfinite(body["world_z"]), f"world_z must be finite, got {body['world_z']}"
        # World coords must be non-zero for a known-reachable cam point
        total_mag = abs(body["world_x"]) + abs(body["world_y"]) + abs(body["world_z"])
        assert total_mag > 0.01, (
            f"World coords should be non-trivial for cam(0.494, -0.001, 0.004), "
            f"got ({body['world_x']}, {body['world_y']}, {body['world_z']})"
        )

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
        """POST /api/cotton/compute returns r, theta, phi, j3, j4, j5, reachable with finite values."""
        import math
        resp = client.post(
            "/api/cotton/compute",
            json={"cam_x": 0.328, "cam_y": -0.011, "cam_z": -0.003, "arm": "arm1", "j4_pos": 0.0},
        )
        assert resp.status_code == 200
        body = resp.json()
        for key in ("r", "theta", "phi", "j3", "j4", "j5", "reachable"):
            assert key in body, f"Missing key: {key}"
        # Numeric fields must be finite (not None, NaN, or Inf)
        for key in ("r", "theta", "phi", "j3", "j4", "j5"):
            assert isinstance(body[key], float), (
                f"{key} must be float, got {type(body[key])}"
            )
            assert math.isfinite(body[key]), (
                f"{key} must be finite, got {body[key]}"
            )
        assert isinstance(body["reachable"], bool), (
            f"reachable must be bool, got {type(body['reachable'])}"
        )
        # r must be positive (polar radius)
        assert body["r"] > 0, f"r must be positive, got {body['r']}"

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
    def test_pick_returns_200_with_compute_only_response(self, client):
        """POST /api/cotton/pick returns 200 with computed finite joint values and 'ready' status."""
        import math
        import testing_backend
        testing_backend._last_cotton_cam = (0.328, -0.011, -0.003)
        testing_backend._last_cotton_arm = "arm1"
        testing_backend._last_cotton_j4 = 0.0
        resp = client.post(
            "/api/cotton/pick",
            json={"arm": "arm1", "enable_phi_compensation": False},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "j3" in body
        assert "j4" in body
        assert "j5" in body
        assert body["status"] == "ready"
        # Joint values must be finite floats, not None or garbage
        for key in ("j3", "j4", "j5"):
            assert isinstance(body[key], float), (
                f"{key} must be float, got {type(body[key])}"
            )
            assert math.isfinite(body[key]), (
                f"{key} must be finite, got {body[key]}"
            )

    def test_pick_rejects_when_no_cotton_spawned(self, client):
        """POST /api/cotton/pick returns 400 when no cotton has been spawned."""
        import testing_backend
        testing_backend._last_cotton_cam = None
        resp = client.post(
            "/api/cotton/pick",
            json={"arm": "arm1"},
        )
        assert resp.status_code == 400


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


# ---------------------------------------------------------------------------
# Sequential pick-all tests (Group 6)
# ---------------------------------------------------------------------------
class TestPickAll:
    """Tests for POST /api/cotton/pick-all compute-only picking."""

    def _reset_cotton_state(self):
        """Reset all cotton globals to clean state."""
        import testing_backend
        testing_backend._cotton_spawned = False
        testing_backend._cotton_name = ""
        testing_backend._last_cotton_cam = None
        testing_backend._last_cotton_arm = None
        testing_backend._last_cotton_j4 = 0.0
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

    def test_pick_all_returns_ready_with_arm_groupings(self, client):
        """POST /api/cotton/pick-all returns ready status with arm groupings."""
        self._reset_cotton_state()
        self._spawn_cottons(client, 2)

        resp = client.post(
            "/api/cotton/pick-all",
            json={"arm": "arm1"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ready"
        self._reset_cotton_state()

    def test_pick_all_skips_picked_cottons(self, client):
        """POST /api/cotton/pick-all skips already-picked cottons."""
        import testing_backend
        self._reset_cotton_state()
        self._spawn_cottons(client, 2)

        # Manually mark first cotton as picked
        testing_backend._cottons["cotton_0"].status = "picked"

        resp = client.post(
            "/api/cotton/pick-all",
            json={"arm": "arm1"},
        )
        assert resp.status_code == 200
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
        testing_backend._cottons.clear()
        testing_backend._cotton_counter = 0

    def test_cotton_state_has_arm_coords_field(self):
        """CottonState dataclass must declare arm_coords as a field (not just an attribute)."""
        from dataclasses import fields
        import testing_backend
        field_names = {f.name for f in fields(testing_backend.CottonState)}
        assert "arm_coords" in field_names, (
            f"CottonState is missing 'arm_coords' declared field; fields={field_names!r}"
        )

    def test_cotton_state_has_joint_values_field(self):
        """CottonState dataclass must declare joint_values as a field (not just an attribute)."""
        from dataclasses import fields
        import testing_backend
        field_names = {f.name for f in fields(testing_backend.CottonState)}
        assert "joint_values" in field_names, (
            f"CottonState is missing 'joint_values' declared field; fields={field_names!r}"
        )

    def test_spawn_stores_arm_coords_in_cotton_state(self, client):
        """POST /api/cotton/spawn stores arm_coords in CottonState with non-zero values."""
        import math
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
        magnitude = math.sqrt(sum(x ** 2 for x in cs.arm_coords))
        assert magnitude > 0.0, (
            f"arm_coords must be non-zero for non-zero cam input; got {cs.arm_coords}"
        )
        self._reset_cotton_state()

    def test_spawn_stores_joint_values_in_cotton_state(self, client):
        """POST /api/cotton/spawn stores joint_values in CottonState with finite float values."""
        import math
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
        for jname in ("j3", "j4", "j5"):
            val = cs.joint_values[jname]
            assert isinstance(val, float), (
                f"{jname} must be a float, got {type(val).__name__}: {val!r}"
            )
            assert math.isfinite(val), (
                f"{jname} must be finite, got {val}"
            )
        self._reset_cotton_state()

    def test_cotton_list_includes_arm_coords_and_joint_values(self, client):
        """GET /api/cotton/list returns arm_coords and joint_values per cotton with valid j3."""
        import math
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
        j3 = c0["joint_values"]["j3"]
        assert isinstance(j3, float), (
            f"j3 in cotton list must be a float, got {type(j3).__name__}: {j3!r}"
        )
        assert math.isfinite(j3), f"j3 in cotton list must be finite, got {j3}"
        self._reset_cotton_state()


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
    def test_mark_picked_sets_cotton_status_to_picked(self, client):
        """POST /api/cotton/{name}/mark-picked sets cotton.status='picked'."""
        import testing_backend
        self._reset_cotton_state()
        name = self._spawn_one_cotton(client)

        # Compute-only pick (synchronous)
        resp = client.post("/api/cotton/pick", json={"arm": "arm1"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"

        # Mark as picked via new endpoint
        resp = client.post(f"/api/cotton/{name}/mark-picked")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        cotton = testing_backend._cottons[name]
        assert cotton.status == "picked", (
            f"Expected status 'picked', got '{cotton.status}'"
        )
        self._reset_cotton_state()

    # -- Task 3.2 --
    def test_compute_pick_does_not_call_gz_remove_model(self, client):
        """POST /api/cotton/pick (compute-only) must NOT call _gz_remove_model."""
        self._reset_cotton_state()
        self._spawn_one_cotton(client)

        with mock.patch("testing_backend._gz_remove_model") as mock_remove:
            resp = client.post("/api/cotton/pick", json={"arm": "arm1"})
            assert resp.status_code == 200

        mock_remove.assert_not_called()
        self._reset_cotton_state()

    # -- Task 3.4 --
    def test_pick_all_compute_does_not_call_gz_remove_model(self, client):
        """POST /api/cotton/pick-all (compute-only) must NOT call _gz_remove_model."""
        self._reset_cotton_state()

        # Spawn two cottons
        with mock.patch("testing_backend._gz_spawn_model"), \
             mock.patch("testing_backend._detect_gz_world_name", return_value="test"):
            for cx, cy, cz in [(0.494, -0.001, 0.004), (0.525, 0.020, 0.008)]:
                client.post(
                    "/api/cotton/spawn",
                    json={"cam_x": cx, "cam_y": cy, "cam_z": cz, "arm": "arm1"},
                )

        with mock.patch("testing_backend._gz_remove_model") as mock_remove:
            resp = client.post("/api/cotton/pick-all", json={"arm": "arm1"})
            assert resp.status_code == 200

        mock_remove.assert_not_called()
        self._reset_cotton_state()

    # -- Task 3.6 --
    def test_cotton_list_shows_picked_after_mark_picked(self, client):
        """GET /api/cotton/list shows cotton with status 'picked' after mark-picked."""
        self._reset_cotton_state()
        name = self._spawn_one_cotton(client)

        # Compute-only pick
        client.post("/api/cotton/pick", json={"arm": "arm1"})

        # Mark as picked
        resp = client.post(f"/api/cotton/{name}/mark-picked")
        assert resp.status_code == 200

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
# Frontend-driven pick animation: backend removal assertions (Group 1)
# ---------------------------------------------------------------------------
class TestBackendAnimationCodeRemoved:
    """Assert that all backend animation code has been removed."""

    def test_no_publish_joint_gz_function(self):
        """_publish_joint_gz function must not exist in the backend module."""
        import testing_backend
        assert not hasattr(testing_backend, "_publish_joint_gz"), (
            "_publish_joint_gz still exists — must be removed"
        )

    def test_no_execute_pick_sequence_function(self):
        """_execute_pick_sequence function must not exist."""
        import testing_backend
        assert not hasattr(testing_backend, "_execute_pick_sequence"), (
            "_execute_pick_sequence still exists — must be removed"
        )

    def test_no_execute_pick_all_sequence_function(self):
        """_execute_pick_all_sequence function must not exist."""
        import testing_backend
        assert not hasattr(testing_backend, "_execute_pick_all_sequence"), (
            "_execute_pick_all_sequence still exists — must be removed"
        )

    def test_no_arm_pick_state_class(self):
        """ArmPickState class must not exist."""
        import testing_backend
        assert not hasattr(testing_backend, "ArmPickState"), (
            "ArmPickState class still exists — must be removed"
        )

    def test_no_arm_pick_state_dict(self):
        """_arm_pick_state dictionary must not exist."""
        import testing_backend
        assert not hasattr(testing_backend, "_arm_pick_state"), (
            "_arm_pick_state dict still exists — must be removed"
        )

    def test_no_arm_joint_locks_dict(self):
        """_arm_joint_locks dictionary must not exist."""
        import testing_backend
        assert not hasattr(testing_backend, "_arm_joint_locks"), (
            "_arm_joint_locks dict still exists — must be removed"
        )

    def test_no_gz_topic_subprocess_in_pick_animation(self):
        """No _publish_joint_gz or subprocess 'gz topic' for pick animation."""
        import testing_backend
        # The E-STOP fallback legitimately uses 'gz topic' — we only check
        # that the pick-animation subprocess pathway is gone.
        assert not hasattr(testing_backend, "_publish_joint_gz"), (
            "_publish_joint_gz function still exists — pick animation "
            "subprocess pathway must be removed"
        )


# ---------------------------------------------------------------------------
# Frontend-driven pick animation: compute-only pick endpoint (Group 2)
# ---------------------------------------------------------------------------
class TestComputeOnlyPick:
    """POST /api/cotton/pick returns compute-only response, no threads."""

    def _reset_state(self):
        import testing_backend
        testing_backend._cotton_spawned = False
        testing_backend._cotton_name = ""
        testing_backend._last_cotton_cam = None
        testing_backend._last_cotton_arm = None
        testing_backend._last_cotton_j4 = 0.0
        testing_backend._cottons.clear()
        testing_backend._cotton_counter = 0

    def _spawn_one(self, client, cam=(0.494, -0.001, 0.004), arm="arm1"):
        with mock.patch("testing_backend._gz_spawn_model"), \
             mock.patch("testing_backend._detect_gz_world_name", return_value="test"):
            resp = client.post(
                "/api/cotton/spawn",
                json={"cam_x": cam[0], "cam_y": cam[1], "cam_z": cam[2], "arm": arm},
            )
        return resp

    def test_pick_returns_ready_with_joint_values(self, client):
        """POST /api/cotton/pick returns status 'ready' with j3, j4, j5, arm, cotton_name."""
        self._reset_state()
        self._spawn_one(client)
        resp = client.post(
            "/api/cotton/pick",
            json={"arm": "arm1", "enable_phi_compensation": False},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ready"
        assert "j3" in body
        assert "j4" in body
        assert "j5" in body
        assert "arm" in body
        assert "cotton_name" in body
        assert body["reachable"] is True
        self._reset_state()

    def test_pick_unreachable_returns_reachable_false(self, client):
        """POST /api/cotton/pick with out-of-range target returns reachable: false."""
        self._reset_state()
        # Bypass spawn endpoint (which validates reachability) and inject an
        # unreachable cotton directly into backend state.
        import testing_backend
        testing_backend._cotton_spawned = True
        testing_backend._cotton_name = "cotton_0"
        testing_backend._last_cotton_cam = (0.0, 0.0, 0.5)
        testing_backend._last_cotton_arm = "arm1"
        testing_backend._last_cotton_j4 = 0.0
        testing_backend._cottons["cotton_0"] = testing_backend.CottonState(
            name="cotton_0", cam_x=0.0, cam_y=0.0, cam_z=0.5,
            arm="arm1", j4_pos=0.0,
        )
        testing_backend._cotton_counter = 1
        resp = client.post(
            "/api/cotton/pick",
            json={"arm": "arm1", "enable_phi_compensation": False},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["reachable"] is False
        assert "reason" in body
        self._reset_state()

    def test_pick_no_spawned_cotton_returns_error(self, client):
        """POST /api/cotton/pick with no cotton returns error."""
        self._reset_state()
        resp = client.post(
            "/api/cotton/pick",
            json={"arm": "arm1"},
        )
        assert resp.status_code == 400

    def test_pick_does_not_spawn_thread(self, client):
        """POST /api/cotton/pick must NOT create a background thread."""
        self._reset_state()
        self._spawn_one(client)
        with mock.patch("threading.Thread") as mock_thread:
            resp = client.post(
                "/api/cotton/pick",
                json={"arm": "arm1", "enable_phi_compensation": False},
            )
        mock_thread.assert_not_called()
        assert resp.status_code == 200
        self._reset_state()

    def test_pick_does_not_change_cotton_status(self, client):
        """POST /api/cotton/pick must NOT change cotton status from 'spawned'."""
        import testing_backend
        self._reset_state()
        self._spawn_one(client)
        client.post(
            "/api/cotton/pick",
            json={"arm": "arm1", "enable_phi_compensation": False},
        )
        # Cotton should still be "spawned"
        for cotton in testing_backend._cottons.values():
            assert cotton.status == "spawned", (
                f"Cotton status changed to '{cotton.status}' — should remain 'spawned'"
            )
        self._reset_state()


# ---------------------------------------------------------------------------
# Frontend-driven pick animation: compute-only pick-all endpoint (Group 2)
# ---------------------------------------------------------------------------
class TestComputeOnlyPickAll:
    """POST /api/cotton/pick-all returns grouped compute-only response."""

    def _reset_state(self):
        import testing_backend
        testing_backend._cotton_spawned = False
        testing_backend._cotton_name = ""
        testing_backend._last_cotton_cam = None
        testing_backend._last_cotton_arm = None
        testing_backend._last_cotton_j4 = 0.0
        testing_backend._cottons.clear()
        testing_backend._cotton_counter = 0

    def _spawn_cottons(self, client, specs):
        """Spawn cottons. specs = [(cam_tuple, arm_str), ...]"""
        with mock.patch("testing_backend._gz_spawn_model"), \
             mock.patch("testing_backend._detect_gz_world_name", return_value="test"):
            for cam, arm in specs:
                client.post(
                    "/api/cotton/spawn",
                    json={"cam_x": cam[0], "cam_y": cam[1], "cam_z": cam[2], "arm": arm},
                )

    def test_pick_all_returns_ready_with_grouped_arms(self, client):
        """POST /api/cotton/pick-all returns {status: 'ready', arms: {...}}."""
        self._reset_state()
        self._spawn_cottons(client, [
            ((0.494, -0.001, 0.004), "arm1"),
            ((0.525, 0.020, 0.008), "arm1"),
        ])
        resp = client.post(
            "/api/cotton/pick-all",
            json={"enable_phi_compensation": False},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ready"
        assert "arms" in body
        assert "arm1" in body["arms"]
        arm1_cottons = body["arms"]["arm1"]
        assert len(arm1_cottons) == 2
        for item in arm1_cottons:
            assert "name" in item
            assert "j3" in item
            assert "j4" in item
            assert "j5" in item
        self._reset_state()

    def test_pick_all_nothing_to_pick(self, client):
        """POST /api/cotton/pick-all with no spawned cottons returns nothing_to_pick."""
        self._reset_state()
        resp = client.post(
            "/api/cotton/pick-all",
            json={"enable_phi_compensation": False},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "nothing_to_pick"

    def test_pick_all_excludes_unreachable_with_warnings(self, client):
        """POST /api/cotton/pick-all excludes unreachable cottons and includes warnings."""
        self._reset_state()
        # Spawn one reachable cotton via the API
        self._spawn_cottons(client, [
            ((0.494, -0.001, 0.004), "arm1"),  # reachable
        ])
        # Inject an unreachable cotton directly (bypassing spawn validation)
        import testing_backend
        testing_backend._cottons["cotton_bad"] = testing_backend.CottonState(
            name="cotton_bad", cam_x=0.0, cam_y=0.0, cam_z=0.5,
            arm="arm1", j4_pos=0.0,
        )
        resp = client.post(
            "/api/cotton/pick-all",
            json={"enable_phi_compensation": False},
        )
        assert resp.status_code == 200
        body = resp.json()
        # Should have at most 1 cotton in arm1 (the reachable one)
        assert body["status"] == "ready"
        total_cottons = sum(len(v) for v in body["arms"].values())
        assert total_cottons == 1
        assert "warnings" in body
        assert any("cotton_bad" in w for w in body["warnings"])
        self._reset_state()

    def test_pick_all_does_not_spawn_threads(self, client):
        """POST /api/cotton/pick-all must NOT create background threads."""
        self._reset_state()
        self._spawn_cottons(client, [
            ((0.494, -0.001, 0.004), "arm1"),
        ])
        with mock.patch("testing_backend.threading.Thread") as mock_thread:
            resp = client.post(
                "/api/cotton/pick-all",
                json={"enable_phi_compensation": False},
            )
        mock_thread.assert_not_called()
        assert resp.status_code == 200
        self._reset_state()

    def test_pick_all_does_not_change_cotton_status(self, client):
        """POST /api/cotton/pick-all must NOT change cotton status."""
        import testing_backend
        self._reset_state()
        self._spawn_cottons(client, [
            ((0.494, -0.001, 0.004), "arm1"),
        ])
        client.post(
            "/api/cotton/pick-all",
            json={"enable_phi_compensation": False},
        )
        for cotton in testing_backend._cottons.values():
            assert cotton.status == "spawned"
        self._reset_state()


# ---------------------------------------------------------------------------
# Frontend-driven pick animation: mark-picked endpoint (Group 3)
# ---------------------------------------------------------------------------
class TestMarkPicked:
    """POST /api/cotton/{name}/mark-picked endpoint tests."""

    def _reset_state(self):
        import testing_backend
        testing_backend._cotton_spawned = False
        testing_backend._cotton_name = ""
        testing_backend._last_cotton_cam = None
        testing_backend._last_cotton_arm = None
        testing_backend._last_cotton_j4 = 0.0
        testing_backend._cottons.clear()
        testing_backend._cotton_counter = 0

    def _spawn_one(self, client, arm="arm1"):
        with mock.patch("testing_backend._gz_spawn_model"), \
             mock.patch("testing_backend._detect_gz_world_name", return_value="test"):
            resp = client.post(
                "/api/cotton/spawn",
                json={"cam_x": 0.494, "cam_y": -0.001, "cam_z": 0.004, "arm": arm},
            )
        return resp

    def test_mark_picked_sets_status(self, client):
        """POST /api/cotton/{name}/mark-picked returns ok and sets status to picked."""
        self._reset_state()
        self._spawn_one(client)
        resp = client.post("/api/cotton/cotton_0/mark-picked")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        # Verify cotton status changed
        list_resp = client.get("/api/cotton/list")
        cottons = list_resp.json()["cottons"]
        assert len(cottons) == 1
        assert cottons[0]["status"] == "picked"
        self._reset_state()

    def test_mark_picked_not_found(self, client):
        """POST /api/cotton/{name}/mark-picked returns 404 for nonexistent cotton."""
        self._reset_state()
        resp = client.post("/api/cotton/nonexistent/mark-picked")
        assert resp.status_code == 404
        assert "not found" in resp.json()["error"].lower()

    def test_mark_picked_already_picked(self, client):
        """POST /api/cotton/{name}/mark-picked returns 409 for already-picked cotton."""
        import testing_backend
        self._reset_state()
        self._spawn_one(client)
        testing_backend._cottons["cotton_0"].status = "picked"
        resp = client.post("/api/cotton/cotton_0/mark-picked")
        assert resp.status_code == 409
        assert "already picked" in resp.json()["error"].lower()
        self._reset_state()


# ---------------------------------------------------------------------------
# Frontend-driven pick animation: pick/status endpoint removed (Group 4)
# ---------------------------------------------------------------------------
class TestPickStatusEndpointRemoved:
    """GET /api/cotton/pick/status must return 404 (removed)."""

    def test_pick_status_returns_404(self, client):
        """GET /api/cotton/pick/status endpoint must not exist."""
        resp = client.get("/api/cotton/pick/status")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Bug fix: _run_spawn_cotton must use arm-specific FK for world position
# ---------------------------------------------------------------------------
class TestRunSpawnCottonArmSpecificFK:
    """_run_spawn_cotton must use ARM_CONFIGS[arm_id] for FK, not hardcode arm1."""

    def test_spawn_cotton_arm2_uses_arm2_fk_config(self):
        """Cotton spawned for arm2 must use arm2's base frame, producing different
        world coordinates than arm1 for the same camera input."""
        from fk_chain import camera_to_world_fk, ARM_CONFIGS

        cam_x, cam_y, cam_z = 0.65, -0.001, 0.05

        arm1_pos = camera_to_world_fk(cam_x, cam_y, cam_z, j3=0.0, j4=0.0,
                                       arm_config=ARM_CONFIGS['arm1'])
        arm2_pos = camera_to_world_fk(cam_x, cam_y, cam_z, j3=0.0, j4=0.0,
                                       arm_config=ARM_CONFIGS['arm2'])

        # arm1 and arm2 have different base_xyz, so world positions must differ
        assert arm1_pos != arm2_pos, (
            "arm1 and arm2 should produce different world positions"
        )

        # Now verify _run_spawn_cotton actually uses arm-specific FK
        # by checking the model spawn position matches arm2's FK output
        import testing_backend
        spawn_positions = []
        original_spawn = testing_backend._gz_spawn_model

        def capture_spawn(name, sdf, wx, wy, wz, world_name):
            spawn_positions.append((wx, wy, wz))

        with mock.patch.object(testing_backend, '_gz_spawn_model', capture_spawn), \
             mock.patch.object(testing_backend, '_detect_gz_world_name', return_value='test'):
            testing_backend._run_spawn_cotton("arm2", cam_x, cam_y, cam_z, 0.0)

        assert len(spawn_positions) == 1
        actual_pos = spawn_positions[0]
        # Must match arm2's FK output, not arm1's
        assert abs(actual_pos[0] - arm2_pos[0]) < 1e-6, (
            f"x: spawn={actual_pos[0]}, arm2_fk={arm2_pos[0]}, arm1_fk={arm1_pos[0]}"
        )
        assert abs(actual_pos[1] - arm2_pos[1]) < 1e-6, (
            f"y: spawn={actual_pos[1]}, arm2_fk={arm2_pos[1]}, arm1_fk={arm1_pos[1]}"
        )
        assert abs(actual_pos[2] - arm2_pos[2]) < 1e-6, (
            f"z: spawn={actual_pos[2]}, arm2_fk={arm2_pos[2]}, arm1_fk={arm1_pos[2]}"
        )
