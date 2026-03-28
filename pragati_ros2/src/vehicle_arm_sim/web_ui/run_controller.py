#!/usr/bin/env python3
"""Central run controller for the dual-arm cotton-picking simulation.

Coordinates a full replay run across both arm runtimes, applying mode logic,
recording truth monitor observations, and generating a JSON run summary.
"""

from __future__ import annotations

from arm_runtime import ArmRuntime
from baseline_mode import BaselineMode
from json_reporter import JsonReporter, StepReport
from scenario_json import ScenarioStep
from truth_monitor import TruthMonitor

_MODE_NAMES = {
    BaselineMode.UNRESTRICTED: "unrestricted",
    BaselineMode.BASELINE_J5_BLOCK_SKIP: "baseline_j5_block_skip",
}

_SAFE_HOME = {"j3": 0.0, "j4": 0.0, "j5": 0.0}


class RunController:
    """Coordinates a full scenario replay run across both arm runtimes."""

    def __init__(self, mode: int = BaselineMode.UNRESTRICTED) -> None:
        """
        Args:
            mode: 0=unrestricted, 1=baseline_j5_block_skip
        """
        self._mode = mode
        self._arm1 = ArmRuntime("arm1")
        self._arm2 = ArmRuntime("arm2")
        self._truth_monitor = TruthMonitor()
        self._reporter = JsonReporter()
        self._baseline = BaselineMode()
        self._last_summary: dict = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_scenario(self, data: dict) -> None:
        """Parse scenario JSON and load into both arm runtimes.

        Note: this intentionally bypasses scenario_json.parse_scenario() because
        parse_scenario() enforces globally-unique step_ids across the whole file.
        Dual-arm paired execution requires both arms to share the same step_id
        (e.g. step_id=0 for arm1 AND step_id=0 for arm2 means they run simultaneously).
        parse_scenario() would reject that as a duplicate. RunController constructs
        ScenarioStep objects directly so the paired-step contract is preserved.
        """
        raw_steps = data.get("steps", [])
        steps = [
            ScenarioStep(
                step_id=int(r["step_id"]),
                arm_id=str(r["arm_id"]),
                cam_x=float(r["cam_x"]),
                cam_y=float(r["cam_y"]),
                cam_z=float(r["cam_z"]),
            )
            for r in raw_steps
        ]
        self._arm1.load_scenario(steps)
        self._arm2.load_scenario(steps)

    def run(self) -> dict:
        """Execute the full scenario and return the run summary dict.

        Execution logic:
        1. Group all steps by step_id (sorted ascending).
        2. For each unique step_id, determine which arms are active.
        3. Compute candidate joints for each active arm.
        4. Apply mode logic (pass peer candidate_joints if peer is also active).
        5. Record truth monitor observation when both arms are active at a step_id.
        6. Record a StepReport for each active arm.
        7. Return the run summary dict.
        """
        mode_name = _MODE_NAMES[self._mode]

        # Build step_id -> {arm_id: step} map
        step_map: dict[int, dict[str, object]] = {}
        for step in self._arm1.get_own_steps():
            step_map.setdefault(step.step_id, {})["arm1"] = step
        for step in self._arm2.get_own_steps():
            step_map.setdefault(step.step_id, {})["arm2"] = step

        total_steps = len(step_map)

        # Track "previous applied joints" per arm to use as current_joints
        prev_joints: dict[str, dict] = {
            "arm1": dict(_SAFE_HOME),
            "arm2": dict(_SAFE_HOME),
        }

        for step_id in sorted(step_map.keys()):
            arm_steps = step_map[step_id]
            both_active = "arm1" in arm_steps and "arm2" in arm_steps

            # Compute candidate joints for each active arm
            candidates: dict[str, dict] = {}
            for arm_id, step in arm_steps.items():
                rt = self._arm1 if arm_id == "arm1" else self._arm2
                j4_current = prev_joints[arm_id]["j4"]
                candidates[arm_id] = rt.compute_candidate_joints(step, j4_current=j4_current)

            # Apply mode logic and build peer state packets
            applied: dict[str, dict] = {}
            for arm_id in arm_steps:
                own_cand = candidates[arm_id]
                peer_id = "arm2" if arm_id == "arm1" else "arm1"
                peer_state = None
                if both_active:
                    peer_rt = self._arm1 if peer_id == "arm1" else self._arm2
                    peer_state = peer_rt.build_peer_state(
                        step_id=step_id,
                        status="ready",
                        current_joints=prev_joints[peer_id],
                        candidate_joints=candidates[peer_id],
                    )
                applied[arm_id] = self._baseline.apply(self._mode, own_cand, peer_state)

            # Truth monitor observation (only when both arms active).
            # Feed *candidate* (pre-mode) j4 values so the truth record reflects
            # the raw FK geometry, independent of any planner/mode decision.
            min_j4_dist: float | None = None
            near_col = False
            col = False
            if both_active:
                j4_arm1 = candidates["arm1"]["j4"]
                j4_arm2 = candidates["arm2"]["j4"]
                self._truth_monitor.observe(step_id, j4_arm1, j4_arm2)
                record = self._truth_monitor.get_step_record(step_id)
                if record is not None:
                    min_j4_dist = record.min_j4_distance
                    near_col = record.near_collision
                    col = record.collision

            # Record StepReport for each active arm
            for arm_id in arm_steps:
                own_cand = candidates[arm_id]
                own_applied = applied[arm_id]
                j5_blocked = (
                    self._mode == BaselineMode.BASELINE_J5_BLOCK_SKIP
                    and own_applied["j5"] == 0.0
                    and own_cand["j5"] > 0.0
                )
                self._reporter.add_step(
                    StepReport(
                        step_id=step_id,
                        arm_id=arm_id,
                        mode=mode_name,
                        candidate_joints={
                            "j3": own_cand["j3"],
                            "j4": own_cand["j4"],
                            "j5": own_cand["j5"],
                        },
                        applied_joints={
                            "j3": own_applied["j3"],
                            "j4": own_applied["j4"],
                            "j5": own_applied["j5"],
                        },
                        j5_blocked=j5_blocked,
                        near_collision=near_col,
                        collision=col,
                        min_j4_distance=min_j4_dist,
                    )
                )
                # Update previous joints for this arm
                prev_joints[arm_id] = {
                    "j3": own_applied["j3"],
                    "j4": own_applied["j4"],
                    "j5": own_applied["j5"],
                }

        self._last_summary = self._reporter.build_run_summary(mode_name, total_steps)
        return self._last_summary

    def get_json_report(self) -> str:
        """Return the JSON report string after run() completes."""
        mode_name = _MODE_NAMES[self._mode]
        total_steps = self._last_summary.get("total_steps", 0)
        return self._reporter.to_json(mode_name, total_steps)

    def reset(self) -> None:
        """Reset all state for a new run."""
        self._arm1 = ArmRuntime("arm1")
        self._arm2 = ArmRuntime("arm2")
        self._truth_monitor.reset()
        self._reporter.reset()
        self._last_summary = {}
