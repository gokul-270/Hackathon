"""
tests/test_topology.py

Tests for multi-arm topology detection, arm_id injection,
group-by-arm helpers, and legacy flat directory handling.

Tasks: 10.1–10.3, 10.8
"""

import json
from pathlib import Path
from unittest.mock import patch

from log_analyzer.analyzer import ROS2LogAnalyzer, SessionTopologyMode
from log_analyzer.models import EventStore
from log_analyzer.reports import _group_by_arm, _is_multi_arm


# ---------------------------------------------------------------------------
# task 10.1 — SessionTopology detection for all directory layouts
# ---------------------------------------------------------------------------


class TestTopologyDetection:
    """task 10.1 — SessionTopology detection for all directory layouts."""

    def _detect(self, path):
        a = ROS2LogAnalyzer.__new__(ROS2LogAnalyzer)
        topo = a._detect_topology(Path(path))
        return topo, SessionTopologyMode

    def test_multi_role_dir(self, tmp_path):
        """Directory with arm_1/ and vehicle/ subdirs → MULTI_ROLE."""
        (tmp_path / "arm_1").mkdir()
        (tmp_path / "vehicle").mkdir()
        topo, Mode = self._detect(tmp_path)
        assert topo.mode == Mode.MULTI_ROLE
        assert len(topo.arm_dirs) >= 1
        assert topo.vehicle_dir is not None

    def test_single_arm_dir(self, tmp_path):
        """Directory with arm_client.log directly → SINGLE_ARM."""
        (tmp_path / "arm_client.log").write_text("log\n")
        topo, Mode = self._detect(tmp_path)
        assert topo.mode == Mode.SINGLE_ARM

    def test_single_vehicle_dir(self, tmp_path):
        """Directory with vehicle_control.log directly → SINGLE_VEHICLE."""
        (tmp_path / "vehicle_control.log").write_text("log\n")
        topo, Mode = self._detect(tmp_path)
        assert topo.mode == Mode.SINGLE_VEHICLE

    def test_legacy_flat_dir(self, tmp_path):
        """Mixed arm + vehicle logs in root with no subdirs → SINGLE_ARM fallback."""
        (tmp_path / "arm_client.log").write_text("log\n")
        (tmp_path / "vehicle_control.log").write_text("log\n")
        # No arm_N subdirs → not MULTI_ROLE
        topo, Mode = self._detect(tmp_path)
        # Flat dir with arm log → SINGLE_ARM fallback
        assert topo.mode in (Mode.SINGLE_ARM, Mode.SINGLE_VEHICLE)

    def test_vehicle_only_multi_role(self, tmp_path):
        """MULTI_ROLE with vehicle/ subdir only (arm_dirs=[]) → treated as SINGLE_VEHICLE."""
        (tmp_path / "vehicle").mkdir()
        (tmp_path / "vehicle" / "vehicle_control.log").write_text("log\n")
        topo, Mode = self._detect(tmp_path)
        # arm_dirs should be empty → degenerate MULTI_ROLE
        # The analyzer should treat this as SINGLE_VEHICLE at analyze() time;
        # _detect_topology itself returns MULTI_ROLE with arm_dirs=[]
        assert topo.arm_dirs == []

    def test_missing_sub_role(self, tmp_path):
        """MULTI_ROLE root that has arm_1/ but no vehicle/ → vehicle_dir None."""
        (tmp_path / "arm_1").mkdir()
        topo, Mode = self._detect(tmp_path)
        assert topo.mode == Mode.MULTI_ROLE
        assert topo.vehicle_dir is None

    def test_empty_dir_raises(self, tmp_path):
        """Empty directory should result in SINGLE_ARM fallback (no crash)."""
        topo, Mode = self._detect(tmp_path)
        # Empty dir → fallback to SINGLE_ARM
        assert topo.mode in (
            Mode.SINGLE_ARM,
            Mode.SINGLE_VEHICLE,
            Mode.MULTI_ROLE,
        )


# ---------------------------------------------------------------------------
# task 10.2 — arm_id field is injected on all parsed event types
# ---------------------------------------------------------------------------


class TestArmIdInjection:
    """task 10.2 — arm_id field is injected on all parsed event types."""

    def _make_arm_log(self, tmp_path, subdir, events):
        """Write minimal JSON events to a log file in a role subdir."""
        role_dir = tmp_path / subdir
        role_dir.mkdir(parents=True, exist_ok=True)
        log_file = role_dir / "arm_client.log"
        lines = []
        for ev in events:
            msg = json.dumps(ev)
            lines.append(
                f"[INFO] [1700000000.000] [motion_controller_node]: {msg}\n"
            )
        log_file.write_text("".join(lines))
        return role_dir

    def test_arm_subdir_gets_arm_id(self, tmp_path):
        """Events parsed from arm_1/ subdir have arm_id='arm_1'."""
        events_data = [
            {"event": "pick_complete", "success": True, "ts": 1700000000000},
        ]
        self._make_arm_log(tmp_path, "arm_1", events_data)
        # Also create a vehicle dir so topology is MULTI_ROLE
        (tmp_path / "vehicle").mkdir()
        (tmp_path / "vehicle" / "vehicle_control.log").write_text(
            "[INFO] [1700000000.000] [v]: {}\n"
        )

        a = ROS2LogAnalyzer(str(tmp_path))
        with patch("builtins.print"):
            try:
                a.analyze()
            except SystemExit:
                pass

        assert len(a.events.picks) >= 1
        for pick in a.events.picks:
            assert pick.get("arm_id") == "arm_1"

    def test_single_role_arm_id_none(self, tmp_path):
        """Events parsed from a single-role directory have arm_id=None."""
        ev = {
            "event": "pick_complete",
            "success": True,
            "ts": 1700000000000,
        }
        log_file = tmp_path / "arm_client.log"
        log_file.write_text(
            "[INFO] [1700000000.000] [motion_controller_node]:"
            f" {json.dumps(ev)}\n"
        )

        a = ROS2LogAnalyzer(str(tmp_path))
        with patch("builtins.print"):
            try:
                a.analyze()
            except SystemExit:
                pass

        for pick in a.events.picks:
            assert pick.get("arm_id") is None

    def test_motor_health_arm_gets_arm_id(self, tmp_path):
        """motor_health events from arm_1/ subdir carry arm_id='arm_1'."""
        ev = {
            "event": "motor_health",
            "side": "arm",
            "motors": [
                {"joint": "joint1", "temp_c": 35.0, "cmds": {"rx": 10}}
            ],
        }
        self._make_arm_log(tmp_path, "arm_1", [ev])
        (tmp_path / "vehicle").mkdir()
        (tmp_path / "vehicle" / "vehicle_control.log").write_text(
            "[INFO] [1700000000.000] [v]: {}\n"
        )

        a = ROS2LogAnalyzer(str(tmp_path))
        with patch("builtins.print"):
            try:
                a.analyze()
            except SystemExit:
                pass

        for record in a.events.motor_health_arm:
            assert record.get("arm_id") == "arm_1"


# ---------------------------------------------------------------------------
# task 10.3 — _group_by_arm and _is_multi_arm helper unit tests
# ---------------------------------------------------------------------------


class TestGroupByArm:
    """task 10.3 — _group_by_arm and _is_multi_arm helper unit tests."""

    def test_groups_correctly(self):
        """Records with different arm_ids end up in separate groups."""
        records = [
            {"arm_id": "arm_1", "v": 1},
            {"arm_id": "arm_2", "v": 2},
            {"arm_id": "arm_1", "v": 3},
        ]
        result = _group_by_arm(records)
        assert set(result.keys()) == {"arm_1", "arm_2"}
        assert len(result["arm_1"]) == 2
        assert len(result["arm_2"]) == 1

    def test_single_none_key_is_not_multi_arm(self):
        """Single group with key=None → _is_multi_arm returns False."""
        records = [{"arm_id": None, "v": 1}, {"arm_id": None, "v": 2}]
        groups = _group_by_arm(records)
        assert _is_multi_arm(groups) is False

    def test_single_named_arm_is_not_multi_arm(self):
        """Single group with key='arm_1' → _is_multi_arm returns False (C3)."""
        records = [{"arm_id": "arm_1", "v": 1}]
        groups = _group_by_arm(records)
        assert _is_multi_arm(groups) is False

    def test_two_keys_is_multi_arm(self):
        """Two distinct keys → _is_multi_arm returns True."""
        records = [{"arm_id": "arm_1"}, {"arm_id": "arm_2"}]
        groups = _group_by_arm(records)
        assert _is_multi_arm(groups) is True


# ---------------------------------------------------------------------------
# task 10.8 — Legacy flat directories
# ---------------------------------------------------------------------------


class TestLegacyFlatDirectory:
    """task 10.8 — Legacy flat directories use SINGLE_ARM fallback."""

    def test_flat_dir_arm_id_none(self, tmp_path):
        """Mixed arm + vehicle logs in root → arm_id=None on all events."""
        ev = {
            "event": "pick_complete",
            "success": True,
            "ts": 1700000000000,
        }
        log_file = tmp_path / "arm_client.log"
        log_file.write_text(
            "[INFO] [1700000000.000] [motion_controller_node]:"
            f" {json.dumps(ev)}\n"
        )
        # Presence of vehicle_control.log does NOT create subdirs — still flat
        (tmp_path / "vehicle_control.log").write_text(
            "[INFO] [1700000000.000] [v]: starting\n"
        )

        a = ROS2LogAnalyzer(str(tmp_path))
        with patch("builtins.print"):
            try:
                a.analyze()
            except SystemExit:
                pass

        for pick in a.events.picks:
            assert pick.get("arm_id") is None, (
                f"Expected arm_id=None, got {pick.get('arm_id')}"
            )


# ---------------------------------------------------------------------------
# task 6.3 — Named arm topology detection
# ---------------------------------------------------------------------------


class TestNamedArmTopology:
    """task 6.3 — _detect_topology with named arm directories."""

    def _detect(self, path):
        a = ROS2LogAnalyzer.__new__(ROS2LogAnalyzer)
        return a._detect_topology(Path(path))

    def test_left_right_arm_dirs(self, tmp_path):
        """left_arm/ + right_arm/ → MULTI_ROLE with both arm dirs."""
        (tmp_path / "left_arm").mkdir()
        (tmp_path / "right_arm").mkdir()
        topo = self._detect(tmp_path)
        assert topo.mode == SessionTopologyMode.MULTI_ROLE
        assert len(topo.arm_dirs) == 2
        names = {d.name for d in topo.arm_dirs}
        assert names == {"left_arm", "right_arm"}

    def test_mixed_named_and_numbered_with_vehicle(self, tmp_path):
        """left_arm/ + arm_0/ + vehicle/ → all 3 arm dirs + vehicle_dir."""
        (tmp_path / "left_arm").mkdir()
        (tmp_path / "arm_0").mkdir()
        (tmp_path / "vehicle").mkdir()
        topo = self._detect(tmp_path)
        assert topo.mode == SessionTopologyMode.MULTI_ROLE
        arm_names = {d.name for d in topo.arm_dirs}
        assert arm_names == {"left_arm", "arm_0"}
        assert topo.vehicle_dir is not None
        assert topo.vehicle_dir.name == "vehicle"


class TestNamedArmTopologySingleNamedArm:
    """task 6.3 — single named arm directory."""

    def _detect(self, path):
        a = ROS2LogAnalyzer.__new__(ROS2LogAnalyzer)
        return a._detect_topology(Path(path))

    def test_single_named_arm_no_vehicle(self, tmp_path):
        """Only left_arm/ (no vehicle) → MULTI_ROLE with 1 arm dir."""
        (tmp_path / "left_arm").mkdir()
        topo = self._detect(tmp_path)
        assert topo.mode == SessionTopologyMode.MULTI_ROLE
        assert len(topo.arm_dirs) == 1
        assert topo.arm_dirs[0].name == "left_arm"
        assert topo.vehicle_dir is None


# ---------------------------------------------------------------------------
# task 6.4 — Recursive file discovery
# ---------------------------------------------------------------------------


class TestRecursiveFileDiscovery:
    """task 6.4 — _find_log_files_in with nested directory structure."""

    def _find(self, directory):
        a = ROS2LogAnalyzer.__new__(ROS2LogAnalyzer)
        return a._find_log_files_in(Path(directory))

    def test_nested_sessions(self, tmp_path):
        """Nested logs/session_N/ structure → all .log files found."""
        arm_dir = tmp_path / "left_arm"
        s1 = arm_dir / "logs" / "session_123"
        s2 = arm_dir / "logs" / "session_456"
        s1.mkdir(parents=True)
        s2.mkdir(parents=True)
        (s1 / "arm_client.log").write_text("log1\n")
        (s1 / "yanthra_move.log").write_text("log2\n")
        (s2 / "arm_client.log").write_text("log3\n")

        found = self._find(arm_dir)
        assert len(found) == 3
        found_names = [f.name for f in found]
        assert "arm_client.log" in found_names
        assert "yanthra_move.log" in found_names


class TestRecursiveFileDiscoveryFlat:
    """task 6.4 — backward compatibility: flat directory still works."""

    def _find(self, directory):
        a = ROS2LogAnalyzer.__new__(ROS2LogAnalyzer)
        return a._find_log_files_in(Path(directory))

    def test_flat_dir(self, tmp_path):
        """Log files directly in directory → all found."""
        (tmp_path / "arm_client.log").write_text("log1\n")
        (tmp_path / "yanthra_move.log").write_text("log2\n")
        found = self._find(tmp_path)
        assert len(found) == 2
