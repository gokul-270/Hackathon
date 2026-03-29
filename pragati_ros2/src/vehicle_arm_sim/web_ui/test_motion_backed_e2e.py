#!/usr/bin/env python3
"""Group 5 — End-to-end motion-backed run flow tests.

Verifies the full round-trip from /api/run/start through to completed-pick reporting,
with Gazebo publish calls mocked to avoid real hardware dependency.

Covers:
5.1  Full E2E run with mocked publish verifies:
     - publish_fn is called for allowed arm-steps
     - JSON report includes terminal_status and pick_completed per step
     - JSON summary includes completed_picks count
     - Markdown report includes Completed picks row
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import testing_backend as tb
from testing_backend import app
from fastapi.testclient import TestClient

_PAIRED_SCENARIO = {
    "steps": [
        {"step_id": 0, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.10},
        {"step_id": 0, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.20},
        {"step_id": 1, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.12},
        {"step_id": 1, "arm_id": "arm2", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.22},
    ]
}

# Close j4 values: arms are ~0.02m apart, well within 0.05m block threshold
_BLOCKED_SCENARIO = {
    "steps": [
        {"step_id": 0, "arm_id": "arm1", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.25},
        {"step_id": 0, "arm_id": "arm2", "cam_x": 0.3, "cam_y": 0.3, "cam_z": 0.27},
    ]
}


class TestMotionBackedE2E:
    """End-to-end tests with mocked Gazebo publish."""

    def _run(self, scenario, mode=0):
        publish_calls = []

        def mock_popen(cmd, **kwargs):
            if len(cmd) >= 8 and cmd[0] == "gz" and cmd[1] == "topic":
                topic = cmd[3]
                val_str = cmd[7].replace("data: ", "")
                publish_calls.append((topic, float(val_str)))

        tb._current_run_result = None
        with (
            patch("testing_backend.subprocess.Popen", side_effect=mock_popen),
            patch("testing_backend._run_spawn_cotton", return_value="mock_cotton"),
            patch("testing_backend._run_remove_cotton"),
            patch("testing_backend._run_sleep", side_effect=lambda s: None),
        ):
            client = TestClient(app)
            resp = client.post("/api/run/start", json={"mode": mode, "scenario": scenario})

        return resp, publish_calls, client

    def test_e2e_motion_backed_run_publishes_joint_commands(self):
        """A motion-backed run must invoke gz topic publish for allowed arm-steps."""
        resp, publish_calls, _ = self._run(_PAIRED_SCENARIO, mode=0)
        assert resp.status_code == 200
        # 4 arm-steps × 3 joints = 12 publish calls expected
        assert len(publish_calls) >= 4  # at minimum one per arm-step

    def test_e2e_motion_backed_run_publishes_to_arm_specific_topics(self):
        """publish calls must reference arm1 and arm2 Gazebo topics."""
        resp, publish_calls, _ = self._run(_PAIRED_SCENARIO, mode=0)
        assert resp.status_code == 200
        topics = [t for t, _ in publish_calls]
        # arm1 uses /joint3_cmd, arm2 uses /joint3_copy_cmd (from ARM_CONFIGS)
        assert any("/joint3_cmd" == t for t in topics), (
            f"expected arm1 topic /joint3_cmd in {topics}"
        )
        assert any("_copy_cmd" in t for t in topics), (
            f"expected arm2 copy topic in {topics}"
        )

    def test_e2e_json_report_steps_include_terminal_status(self):
        """Every step in the JSON report must have terminal_status after a motion-backed run."""
        resp, _, client = self._run(_PAIRED_SCENARIO, mode=0)
        assert resp.status_code == 200
        data = client.get("/api/run/report/json").json()
        for step in data["steps"]:
            assert "terminal_status" in step, f"step missing terminal_status: {step}"

    def test_e2e_json_report_steps_include_pick_completed(self):
        """Every step in the JSON report must have pick_completed after a motion-backed run."""
        resp, _, client = self._run(_PAIRED_SCENARIO, mode=0)
        assert resp.status_code == 200
        data = client.get("/api/run/report/json").json()
        for step in data["steps"]:
            assert "pick_completed" in step, f"step missing pick_completed: {step}"

    def test_e2e_json_summary_includes_completed_picks(self):
        """JSON summary must include completed_picks after a motion-backed run."""
        resp, _, client = self._run(_PAIRED_SCENARIO, mode=0)
        assert resp.status_code == 200
        data = client.get("/api/run/report/json").json()
        assert "completed_picks" in data["summary"]
        assert data["summary"]["completed_picks"] > 0

    def test_e2e_unrestricted_mode_all_steps_completed(self):
        """In unrestricted mode, all steps should have terminal_status=completed."""
        resp, _, client = self._run(_PAIRED_SCENARIO, mode=0)
        assert resp.status_code == 200
        data = client.get("/api/run/report/json").json()
        for step in data["steps"]:
            assert step["terminal_status"] == "completed"
            assert step["pick_completed"] is True

    def test_e2e_blocked_mode_does_not_publish_j5_for_blocked_steps(self):
        """In baseline blocking mode with close j4 arms, j5 must not be published."""
        resp, publish_calls, _ = self._run(_BLOCKED_SCENARIO, mode=1)
        assert resp.status_code == 200
        # j5 publishes should be zero for blocked steps
        j5_nonzero = [v for topic, v in publish_calls if "j5" in topic and v > 0]
        assert len(j5_nonzero) == 0

    def test_e2e_blocked_mode_step_reports_reflect_blocked_outcome(self):
        """In baseline blocking mode with close j4, steps must have blocked terminal status."""
        resp, _, client = self._run(_BLOCKED_SCENARIO, mode=1)
        assert resp.status_code == 200
        data = client.get("/api/run/report/json").json()
        blocked = [s for s in data["steps"] if s["terminal_status"] == "blocked"]
        assert len(blocked) > 0

    def test_e2e_markdown_report_includes_completed_picks_row(self):
        """Markdown report must include a completed picks row after a run."""
        resp, _, client = self._run(_PAIRED_SCENARIO, mode=0)
        assert resp.status_code == 200
        md = client.get("/api/run/report/markdown").text
        assert "Completed picks" in md or "completed pick" in md.lower()

    def test_e2e_all_modes_include_completed_picks_in_summary(self):
        """All four modes must include completed_picks in the JSON summary."""
        for mode in range(4):
            resp, _, client = self._run(_PAIRED_SCENARIO, mode=mode)
            assert resp.status_code == 200, f"mode={mode} failed"
            data = client.get("/api/run/report/json").json()
            assert "completed_picks" in data["summary"], f"mode={mode} missing completed_picks"


class TestMotionBackedE2EWithSpawn:
    """End-to-end tests verifying cotton spawn and remove are driven by /api/run/start."""

    def _run_with_spawn_tracking(self, scenario, mode=0):
        publish_calls = []
        spawn_calls = []
        remove_calls = []

        def mock_popen(cmd, **kwargs):
            if len(cmd) >= 8 and cmd[0] == "gz" and cmd[1] == "topic":
                topic = cmd[3]
                val_str = cmd[7].replace("data: ", "")
                publish_calls.append((topic, float(val_str)))

        def mock_spawn(arm_id, cam_x, cam_y, cam_z, j4_pos):
            model_name = f"cotton_{len(spawn_calls)}"
            spawn_calls.append((arm_id, cam_x, cam_y, cam_z, j4_pos))
            return model_name

        def mock_remove(model_name: str):
            remove_calls.append(model_name)

        tb._current_run_result = None
        with (
            patch("testing_backend.subprocess.Popen", side_effect=mock_popen),
            patch("testing_backend._run_spawn_cotton", side_effect=mock_spawn),
            patch("testing_backend._run_remove_cotton", side_effect=mock_remove),
            patch("testing_backend._run_sleep", side_effect=lambda s: None),
        ):
            client = TestClient(app)
            resp = client.post("/api/run/start", json={"mode": mode, "scenario": scenario})

        return resp, publish_calls, spawn_calls, remove_calls, client

    def test_run_start_calls_spawn_once_per_allowed_arm_step(self):
        """For each allowed arm-step, /api/run/start must spawn one cotton model."""
        resp, _, spawn_calls, _, _ = self._run_with_spawn_tracking(_PAIRED_SCENARIO, mode=0)
        assert resp.status_code == 200
        # 4 arm-steps in PAIRED_SCENARIO, all unrestricted → 4 spawns
        assert len(spawn_calls) == 4

    def test_run_start_calls_remove_once_per_spawned_cotton(self):
        """For each spawned cotton, /api/run/start must call remove after the animation."""
        resp, _, spawn_calls, remove_calls, _ = self._run_with_spawn_tracking(_PAIRED_SCENARIO, mode=0)
        assert resp.status_code == 200
        assert len(remove_calls) == len(spawn_calls)

    def test_run_start_spawn_called_for_all_steps_including_blocked(self):
        """Upfront spawn is called for ALL steps (including blocked); remove is not called for blocked."""
        resp, _, spawn_calls, remove_calls, client = self._run_with_spawn_tracking(_BLOCKED_SCENARIO, mode=1)
        assert resp.status_code == 200
        data = client.get("/api/run/report/json").json()
        blocked_count = sum(1 for s in data["steps"] if s["terminal_status"] == "blocked")
        # Upfront spawn: spawn is called for ALL steps
        assert len(spawn_calls) == len(data["steps"])
        # Remove is NOT called for blocked steps (cotton stays visible)
        assert len(remove_calls) == len(data["steps"]) - blocked_count

    def test_run_start_unrestricted_reports_completed_picks_equal_step_count(self):
        """In unrestricted mode, completed_picks must equal number of arm-steps."""
        resp, _, spawn_calls, remove_calls, client = self._run_with_spawn_tracking(
            _PAIRED_SCENARIO, mode=0
        )
        assert resp.status_code == 200
        data = client.get("/api/run/report/json").json()
        assert data["summary"]["completed_picks"] == 4  # 4 arm-steps in PAIRED_SCENARIO
        assert len(spawn_calls) == 4
        assert len(remove_calls) == 4


class TestArmPairSupport:
    """Tests for arm_pair selection in /api/run/start."""

    def test_arm_pair_arm1_arm3_runs_successfully(self):
        """arm_pair=['arm1','arm3'] → 200 and step reports include arm1 and arm3 (not arm2)."""
        tb._current_run_result = None
        with (
            patch("testing_backend.subprocess.Popen", side_effect=lambda cmd, **kw: None),
            patch("testing_backend._run_spawn_cotton", return_value="mock_cotton"),
            patch("testing_backend._run_remove_cotton"),
            patch("testing_backend._run_sleep", side_effect=lambda s: None),
        ):
            client = TestClient(app)
            resp = client.post("/api/run/start", json={
                "mode": 0,
                "scenario": _PAIRED_SCENARIO,
                "arm_pair": ["arm1", "arm3"],
            })
        assert resp.status_code == 200
        data = client.get("/api/run/report/json").json()
        arm_ids = {s["arm_id"] for s in data["steps"]}
        assert "arm3" in arm_ids
        assert "arm2" not in arm_ids

    def test_arm_pair_duplicate_ids_returns_422(self):
        """arm_pair=['arm1','arm1'] (duplicate) → 422."""
        tb._current_run_result = None
        client = TestClient(app)
        resp = client.post("/api/run/start", json={
            "mode": 0,
            "scenario": _PAIRED_SCENARIO,
            "arm_pair": ["arm1", "arm1"],
        })
        assert resp.status_code == 422

    def test_arm_pair_invalid_arm_id_returns_422(self):
        """arm_pair=['arm1','arm99'] (unknown arm) → 422."""
        tb._current_run_result = None
        client = TestClient(app)
        resp = client.post("/api/run/start", json={
            "mode": 0,
            "scenario": _PAIRED_SCENARIO,
            "arm_pair": ["arm1", "arm99"],
        })
        assert resp.status_code == 422

    def test_arm_pair_defaults_to_arm1_arm2_when_not_provided(self):
        """Omitting arm_pair from request defaults to arm1+arm2 (backward compat)."""
        tb._current_run_result = None
        with (
            patch("testing_backend.subprocess.Popen", side_effect=lambda cmd, **kw: None),
            patch("testing_backend._run_spawn_cotton", return_value="mock_cotton"),
            patch("testing_backend._run_remove_cotton"),
            patch("testing_backend._run_sleep", side_effect=lambda s: None),
        ):
            client = TestClient(app)
            resp = client.post("/api/run/start", json={
                "mode": 0,
                "scenario": _PAIRED_SCENARIO,
                # no arm_pair field
            })
        assert resp.status_code == 200
        data = client.get("/api/run/report/json").json()
        arm_ids = {s["arm_id"] for s in data["steps"]}
        assert arm_ids == {"arm1", "arm2"}
