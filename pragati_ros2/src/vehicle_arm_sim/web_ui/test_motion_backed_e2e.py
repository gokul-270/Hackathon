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

        def mock_run(cmd, **kwargs):
            if len(cmd) >= 8 and cmd[0] == "gz" and cmd[1] == "topic":
                topic = cmd[3]
                val_str = cmd[7].replace("data: ", "")
                publish_calls.append((topic, float(val_str)))
            return type("CompletedProcess", (), {"returncode": 0})()

        tb._current_run_result = None
        with (
            patch("testing_backend.subprocess.run", side_effect=mock_run),
            patch("testing_backend._run_spawn_cotton", return_value="mock_cotton"),
            patch("testing_backend._run_remove_cotton"),
            patch("testing_backend._run_sleep", side_effect=lambda s: None),
            patch("testing_backend.time.sleep", side_effect=lambda s: None),
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

        def mock_run(cmd, **kwargs):
            if len(cmd) >= 8 and cmd[0] == "gz" and cmd[1] == "topic":
                topic = cmd[3]
                val_str = cmd[7].replace("data: ", "")
                publish_calls.append((topic, float(val_str)))
            return type("CompletedProcess", (), {"returncode": 0})()

        def mock_spawn(arm_id, cam_x, cam_y, cam_z, j4_pos):
            model_name = f"cotton_{len(spawn_calls)}"
            spawn_calls.append((arm_id, cam_x, cam_y, cam_z, j4_pos))
            return model_name

        def mock_remove(model_name: str):
            remove_calls.append(model_name)

        tb._current_run_result = None
        with (
            patch("testing_backend.subprocess.run", side_effect=mock_run),
            patch("testing_backend._run_spawn_cotton", side_effect=mock_spawn),
            patch("testing_backend._run_remove_cotton", side_effect=mock_remove),
            patch("testing_backend._run_sleep", side_effect=lambda s: None),
            patch("testing_backend.time.sleep", side_effect=lambda s: None),
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
            patch("testing_backend.subprocess.run",
                  return_value=type("CompletedProcess", (), {"returncode": 0})()),
            patch("testing_backend._run_spawn_cotton", return_value="mock_cotton"),
            patch("testing_backend._run_remove_cotton"),
            patch("testing_backend._run_sleep", side_effect=lambda s: None),
            patch("testing_backend.time.sleep", side_effect=lambda s: None),
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
            patch("testing_backend.subprocess.run",
                  return_value=type("CompletedProcess", (), {"returncode": 0})()),
            patch("testing_backend._run_spawn_cotton", return_value="mock_cotton"),
            patch("testing_backend._run_remove_cotton"),
            patch("testing_backend._run_sleep", side_effect=lambda s: None),
            patch("testing_backend.time.sleep", side_effect=lambda s: None),
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


_SOLO_SCENARIO = {
    "steps": [
        {"step_id": 0, "arm_id": "arm1", "cam_x": 0.65, "cam_y": 0.0, "cam_z": 0.10},
    ]
}


class TestTriplePublish:
    """RED → GREEN tests for triple-publish behavior in _gz_publish (tasks 2.1–2.3).

    These tests verify that:
    - subprocess.run is called 3× per joint command (not subprocess.Popen)
    - time.sleep(0.150) is called between each publish
    - subprocess.Popen is NOT used for joint commands
    """

    def test_gz_publish_calls_subprocess_run_three_times_per_command(self):
        """_gz_publish SHALL call subprocess.run exactly 3 times per joint command."""
        run_calls = []

        def mock_run(cmd, **kwargs):
            if cmd and len(cmd) >= 2 and cmd[0] == "gz" and cmd[1] == "topic":
                run_calls.append(cmd[3])  # capture topic
            return type("CompletedProcess", (), {"returncode": 0})()

        tb._current_run_result = None
        with (
            patch("testing_backend.subprocess.run", side_effect=mock_run),
            patch("testing_backend.subprocess.Popen", side_effect=lambda *a, **k: None),
            patch("testing_backend._run_spawn_cotton", return_value="mock_cotton"),
            patch("testing_backend._run_remove_cotton"),
            patch("testing_backend._run_sleep", side_effect=lambda s: None),
            patch("testing_backend.time.sleep", side_effect=lambda s: None),
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/run/start", json={"mode": 0, "scenario": _SOLO_SCENARIO}
            )
        assert resp.status_code == 200
        # 1 step × 6 joint commands × 3 publishes = 18 subprocess.run calls
        assert len(run_calls) == 18, (
            f"expected 18 subprocess.run calls (3 per command × 6 commands), got {len(run_calls)}"
        )

    def test_gz_publish_sleeps_150ms_between_publishes(self):
        """_gz_publish SHALL sleep 150ms between each of the 3 publish calls (2 gaps per command)."""
        sleep_args = []

        def mock_sleep(s):
            sleep_args.append(s)

        tb._current_run_result = None
        with (
            patch(
                "testing_backend.subprocess.run",
                return_value=type("CompletedProcess", (), {"returncode": 0})(),
            ),
            patch("testing_backend.subprocess.Popen", side_effect=lambda *a, **k: None),
            patch("testing_backend._run_spawn_cotton", return_value="mock_cotton"),
            patch("testing_backend._run_remove_cotton"),
            patch("testing_backend._run_sleep", side_effect=lambda s: None),
            patch("testing_backend.time.sleep", side_effect=mock_sleep),
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/run/start", json={"mode": 0, "scenario": _SOLO_SCENARIO}
            )
        assert resp.status_code == 200
        # 1 step × 6 joint commands × 2 inter-publish gaps = 12 sleep(0.150) calls
        gap_sleeps = [s for s in sleep_args if abs(s - 0.150) < 0.001]
        assert len(gap_sleeps) == 12, (
            f"expected 12 time.sleep(0.150) calls, got {len(gap_sleeps)}; all sleeps: {sleep_args}"
        )

    def test_gz_publish_does_not_use_subprocess_popen(self):
        """_gz_publish SHALL use subprocess.run (blocking), NOT subprocess.Popen."""
        popen_gz_calls = []

        def track_popen(cmd, **kwargs):
            if cmd and len(cmd) >= 2 and cmd[0] == "gz" and cmd[1] == "topic":
                popen_gz_calls.append(cmd)

        tb._current_run_result = None
        with (
            patch(
                "testing_backend.subprocess.run",
                return_value=type("CompletedProcess", (), {"returncode": 0})(),
            ),
            patch("testing_backend.subprocess.Popen", side_effect=track_popen),
            patch("testing_backend._run_spawn_cotton", return_value="mock_cotton"),
            patch("testing_backend._run_remove_cotton"),
            patch("testing_backend._run_sleep", side_effect=lambda s: None),
            patch("testing_backend.time.sleep", side_effect=lambda s: None),
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/run/start", json={"mode": 0, "scenario": _SOLO_SCENARIO}
            )
        assert resp.status_code == 200
        assert len(popen_gz_calls) == 0, (
            f"_gz_publish must use subprocess.run, not Popen; "
            f"got {len(popen_gz_calls)} Popen calls to gz topic"
        )


# ---------------------------------------------------------------------------
# Task 5 — E-STOP integration in testing_backend (tasks 5.1–5.4)
# ---------------------------------------------------------------------------

def _patched_run(scenario, mode=0):
    """Helper: POST /api/run/start with all Gazebo side-effects patched out."""
    tb._current_run_result = None
    with (
        patch(
            "testing_backend.subprocess.run",
            return_value=type("CompletedProcess", (), {"returncode": 0})(),
        ),
        patch("testing_backend.subprocess.Popen", side_effect=lambda *a, **k: None),
        patch("testing_backend._run_spawn_cotton", return_value="mock_cotton"),
        patch("testing_backend._run_remove_cotton"),
        patch("testing_backend._run_sleep", side_effect=lambda s: None),
        patch("testing_backend.time.sleep", side_effect=lambda s: None),
    ):
        client = TestClient(app)
        resp = client.post("/api/run/start", json={"mode": mode, "scenario": scenario})
    return resp, client


class TestEstopIntegration:
    """RED → GREEN tests for E-STOP wiring in testing_backend (tasks 5.1–5.4)."""

    def test_estop_event_is_cleared_at_start_of_new_run(self):
        """_estop_event MUST be cleared at the start of /api/run/start so a prior E-STOP
        does not bleed into the next run."""
        # Pre-arm the event as if a prior E-STOP fired
        tb._estop_event.set()  # will AttributeError until _estop_event is added → RED
        resp, _ = _patched_run(_SOLO_SCENARIO, mode=0)
        assert resp.status_code == 200
        # A normal run should complete without estop_aborted steps
        steps = tb._current_run_result.get("steps", []) if tb._current_run_result else []
        estop_steps = [s for s in steps if s.get("terminal_status") == "estop_aborted"]
        assert estop_steps == [], (
            f"_estop_event was NOT cleared at run start; {len(estop_steps)} steps aborted: {estop_steps}"
        )

    def test_post_estop_sets_estop_event(self):
        """POST /api/estop MUST set the module-level _estop_event so RunStepExecutor
        can observe it via the estop_check callable."""
        tb._estop_event.clear()  # will AttributeError until _estop_event is added → RED
        with (
            patch("testing_backend.estop_node") as mock_node,
        ):
            mock_node.execute_estop.return_value = True
            client = TestClient(app)
            resp = client.post("/api/estop")
        assert resp.status_code == 200
        assert tb._estop_event.is_set(), (
            "POST /api/estop must call _estop_event.set() so in-flight runs can observe it"
        )

    def test_post_estop_returns_200_while_run_is_in_progress(self):
        """POST /api/estop MUST return HTTP 200 even while /api/run/start is blocking.
        This requires asyncio.to_thread() so the event loop is not blocked."""
        import threading

        # We need _estop_event to exist to be able to signal across threads
        assert hasattr(tb, "_estop_event"), (
            "_estop_event not found in testing_backend — add it (task 5.5)"
        )

        estop_result = {}
        run_started = threading.Event()

        def slow_sleep(s):
            """First call signals run has started, then blocks briefly."""
            run_started.set()

        tb._current_run_result = None
        tb._estop_event.clear()

        def do_run():
            with (
                patch(
                    "testing_backend.subprocess.run",
                    return_value=type("CompletedProcess", (), {"returncode": 0})(),
                ),
                patch("testing_backend.subprocess.Popen", side_effect=lambda *a, **k: None),
                patch("testing_backend._run_spawn_cotton", return_value="mock_cotton"),
                patch("testing_backend._run_remove_cotton"),
                patch("testing_backend._run_sleep", side_effect=slow_sleep),
                patch("testing_backend.time.sleep", side_effect=lambda s: None),
            ):
                client = TestClient(app)
                client.post("/api/run/start", json={"mode": 0, "scenario": _SOLO_SCENARIO})

        run_thread = threading.Thread(target=do_run)
        run_thread.start()
        run_started.wait(timeout=5.0)

        # While the run is in progress, POST /api/estop must not block
        with patch("testing_backend.estop_node") as mock_node:
            mock_node.execute_estop.return_value = True
            client2 = TestClient(app)
            resp = client2.post("/api/estop")

        estop_result["status"] = resp.status_code
        run_thread.join(timeout=10.0)

        assert estop_result["status"] == 200, (
            f"POST /api/estop returned {estop_result['status']} — "
            "event loop is blocked (asyncio.to_thread not used in run_start)"
        )

    def test_preset_estop_event_causes_estop_aborted_step(self):
        """If _estop_event is set while a run is in progress (after run start clears it),
        at least one step MUST have terminal_status='estop_aborted'.

        We simulate this by replacing _run_sleep with a callable that sets the event
        on the first call — mimicking a concurrent /api/estop arriving mid-run.
        """
        tb._estop_event.clear()  # ensure clean state at start
        call_count = [0]

        def sleep_that_fires_estop(s):
            call_count[0] += 1
            if call_count[0] == 1:
                tb._estop_event.set()

        tb._current_run_result = None
        with (
            patch(
                "testing_backend.subprocess.run",
                return_value=type("CompletedProcess", (), {"returncode": 0})(),
            ),
            patch("testing_backend.subprocess.Popen", side_effect=lambda *a, **k: None),
            patch("testing_backend._run_spawn_cotton", return_value="mock_cotton"),
            patch("testing_backend._run_remove_cotton"),
            patch("testing_backend._run_sleep", side_effect=sleep_that_fires_estop),
            patch("testing_backend.time.sleep", side_effect=lambda s: None),
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/run/start", json={"mode": 0, "scenario": _SOLO_SCENARIO}
            )
        assert resp.status_code == 200
        steps = tb._current_run_result.get("steps", []) if tb._current_run_result else []
        estop_steps = [s for s in steps if s.get("terminal_status") == "estop_aborted"]
        assert len(estop_steps) >= 1, (
            f"Expected at least one estop_aborted step when _estop_event fires mid-run; "
            f"got steps: {steps}"
        )

    def test_run_status_returns_200_while_run_is_in_progress(self):
        """GET /api/run/status MUST return HTTP 200 while /api/run/start is executing.
        With asyncio.to_thread, the event loop is unblocked for status requests mid-run."""
        import threading

        assert hasattr(tb, "_estop_event"), "_estop_event not in testing_backend"

        run_started = threading.Event()

        def slow_sleep(s):
            run_started.set()

        tb._current_run_result = None
        tb._estop_event.clear()

        status_result = {}

        def do_run():
            with (
                patch(
                    "testing_backend.subprocess.run",
                    return_value=type("CompletedProcess", (), {"returncode": 0})(),
                ),
                patch("testing_backend.subprocess.Popen", side_effect=lambda *a, **k: None),
                patch("testing_backend._run_spawn_cotton", return_value="mock_cotton"),
                patch("testing_backend._run_remove_cotton"),
                patch("testing_backend._run_sleep", side_effect=slow_sleep),
                patch("testing_backend.time.sleep", side_effect=lambda s: None),
            ):
                client = TestClient(app)
                client.post("/api/run/start", json={"mode": 0, "scenario": _SOLO_SCENARIO})

        run_thread = threading.Thread(target=do_run)
        run_thread.start()
        run_started.wait(timeout=5.0)

        client2 = TestClient(app)
        resp = client2.get("/api/run/status")
        status_result["status"] = resp.status_code

        run_thread.join(timeout=10.0)

        assert status_result["status"] == 200, (
            f"GET /api/run/status returned {status_result['status']} while run in progress — "
            "event loop may be blocked (asyncio.to_thread not working)"
        )
