#!/usr/bin/env python3
"""Central run controller for the cotton-picking simulation.

Coordinates a full replay run across the selected arm runtimes, applying mode logic,
recording truth monitor observations, and generating a JSON run summary.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from arm_runtime import ArmRuntime
from baseline_mode import BaselineMode
from json_reporter import JsonReporter, StepReport
from peer_transport import LocalPeerTransport
from run_step_executor import _noop_spawn, _noop_remove, RunStepExecutor
from scenario_json import ScenarioStep
from truth_monitor import TruthMonitor

_MODE_NAMES = {
    BaselineMode.UNRESTRICTED: "unrestricted",
    BaselineMode.BASELINE_J5_BLOCK_SKIP: "baseline_j5_block_skip",
    BaselineMode.GEOMETRY_BLOCK: "geometry_block",
    BaselineMode.OVERLAP_ZONE_WAIT: "overlap_zone_wait",
}

_SAFE_HOME = {"j3": 0.0, "j4": 0.0, "j5": 0.0}


def _noop_publish(topic: str, value: float) -> None:
    """No-op publish function used when no executor is injected."""


class RunController:
    """Coordinates a full scenario replay run across the selected arm runtimes."""

    def __init__(
        self,
        mode: int = BaselineMode.UNRESTRICTED,
        executor: Optional[object] = None,
        arm_pair: tuple = ("arm1", "arm2"),
        spawn_fn=None,
        remove_fn=None,
    ) -> None:
        """
        Args:
            mode: 0=unrestricted, 1=baseline_j5_block_skip, 2=geometry_block,
                  3=overlap_zone_wait
            executor: Optional RunStepExecutor (or duck-typed compatible) instance.
                      If None, a no-op executor is created (no Gazebo publishing).
                      Inject a real RunStepExecutor for motion-backed runs.
            arm_pair: Tuple of (primary_arm_id, secondary_arm_id). Scenario "arm1" slots
                      are loaded onto primary_arm; "arm2" slots onto secondary_arm.
                      Default ("arm1", "arm2") preserves existing behaviour.
            spawn_fn: Callable(arm_id, cam_x, cam_y, cam_z, j4_pos) -> model_name.
                      Called upfront for every step before execution begins.
                      Defaults to _noop_spawn (no-op, backward-compatible).
            remove_fn: Callable(model_name) -> None.
                       Passed through to a default executor when no executor is injected.
                       Defaults to _noop_remove.
        """
        self._mode = mode
        self._primary_id, self._secondary_id = arm_pair

        # Always create all three named runtimes for backward compatibility.
        # _arm1/_arm2/_arm3 attributes must be accessible (coherence tests check them).
        _arm_runtimes = {
            "arm1": ArmRuntime("arm1"),
            "arm2": ArmRuntime("arm2"),
            "arm3": ArmRuntime("arm3"),
        }
        self._arm1 = _arm_runtimes["arm1"]
        self._arm2 = _arm_runtimes["arm2"]
        self._arm3 = _arm_runtimes["arm3"]

        # The active pair used for scenario loading and run execution.
        self._primary_arm = _arm_runtimes[self._primary_id]
        self._secondary_arm = _arm_runtimes[self._secondary_id]

        self._truth_monitor = TruthMonitor()
        self._reporter = JsonReporter()
        self._baseline = BaselineMode()
        self._transport = LocalPeerTransport()
        self._last_summary: dict = {}
        self._spawn_fn = spawn_fn if spawn_fn is not None else _noop_spawn
        self._remove_fn = remove_fn if remove_fn is not None else _noop_remove
        if executor is None:
            # No-op executor: no real Gazebo publishing, no real delays.
            self._executor = RunStepExecutor(
                publish_fn=_noop_publish,
                sleep_fn=lambda _: None,
            )
        else:
            self._executor = executor

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
        # Remap scenario canonical slots to the active arm pair:
        # "arm1" slots → primary arm, "arm2" slots → secondary arm.
        primary_steps = [
            ScenarioStep(
                step_id=s.step_id,
                arm_id=self._primary_id,
                cam_x=s.cam_x,
                cam_y=s.cam_y,
                cam_z=s.cam_z,
            )
            for s in steps if s.arm_id == "arm1"
        ]
        secondary_steps = [
            ScenarioStep(
                step_id=s.step_id,
                arm_id=self._secondary_id,
                cam_x=s.cam_x,
                cam_y=s.cam_y,
                cam_z=s.cam_z,
            )
            for s in steps if s.arm_id == "arm2"
        ]
        self._primary_arm.load_scenario(primary_steps + secondary_steps)
        self._secondary_arm.load_scenario(primary_steps + secondary_steps)

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
        for step in self._primary_arm.get_own_steps():
            step_map.setdefault(step.step_id, {})[self._primary_id] = step
        for step in self._secondary_arm.get_own_steps():
            step_map.setdefault(step.step_id, {})[self._secondary_id] = step

        total_steps = len(step_map)

        # Upfront cotton spawn: spawn once per (step_id, arm_id) before any execution begins.
        cotton_models: dict = {}
        for step_id, arm_steps in step_map.items():
            for arm_id, step in arm_steps.items():
                model_name = self._spawn_fn(arm_id, step.cam_x, step.cam_y, step.cam_z, 0.0)
                cotton_models[(step_id, arm_id)] = model_name

        # Track "previous applied joints" per arm to use as current_joints
        prev_joints: dict[str, dict] = {
            self._primary_id: dict(_SAFE_HOME),
            self._secondary_id: dict(_SAFE_HOME),
        }

        for step_id in sorted(step_map.keys()):
            arm_steps = step_map[step_id]
            both_active = self._primary_id in arm_steps and self._secondary_id in arm_steps

            # Compute candidate joints for each active arm
            candidates: dict[str, dict] = {}
            for arm_id, step in arm_steps.items():
                rt = self._primary_arm if arm_id == self._primary_id else self._secondary_arm
                j4_current = prev_joints[arm_id]["j4"]
                candidates[arm_id] = rt.compute_candidate_joints(step, j4_current=j4_current)

            # Reachability check: arms whose FK yields out-of-limit joints are skipped entirely.
            # Sending out-of-limit values to Gazebo would cause silent clipping/ignoring and
            # leave the arm frozen at its last real position with no error indication.
            unreachable_flags: dict[str, bool] = {
                arm_id: not candidates[arm_id]["reachable"]
                for arm_id in candidates
            }

            # Apply mode logic and build peer state packets
            applied: dict[str, dict] = {}
            skipped_flags: dict[str, bool] = {}
            # Publish every active arm's state to the transport (solo or paired).
            # Solo arms publish so their state is available if queried; the peer's
            # receive() will return None at solo steps — correct "peer not active" result.
            for arm_id in arm_steps:
                rt = self._primary_arm if arm_id == self._primary_id else self._secondary_arm
                packet = rt.build_peer_state(
                    step_id=step_id,
                    status="ready",
                    current_joints=prev_joints[arm_id],
                    candidate_joints=candidates[arm_id],
                )
                self._transport.publish(packet)
            for arm_id in arm_steps:
                own_cand = candidates[arm_id]
                peer_id = self._secondary_id if arm_id == self._primary_id else self._primary_id
                peer_state = None
                if both_active:
                    peer_state = self._transport.receive(peer_id)
                # Unreachable arms are skipped before mode logic — out-of-limit joints
                # must not be passed through apply_with_skip or sent to the executor.
                if unreachable_flags.get(arm_id, False):
                    applied[arm_id] = own_cand  # pass-through (not used for Gazebo)
                    skipped_flags[arm_id] = True
                    continue
                result_joints, skipped = self._baseline.apply_with_skip(
                    self._mode, own_cand, peer_state, step_id=step_id, arm_id=arm_id
                )
                applied[arm_id] = result_joints
                skipped_flags[arm_id] = skipped

            # Truth monitor observation (only when both arms active).
            # Feed *candidate* (pre-mode) j4 values so the truth record reflects
            # the raw FK geometry, independent of any planner/mode decision.
            min_j4_dist: float | None = None
            near_col = False
            col = False
            if both_active:
                j4_primary = candidates[self._primary_id]["j4"]
                j4_secondary = candidates[self._secondary_id]["j4"]
                self._truth_monitor.observe(step_id, j4_primary, j4_secondary)
                record = self._truth_monitor.get_step_record(step_id)
                if record is not None:
                    min_j4_dist = record.min_j4_distance
                    near_col = record.near_collision
                    col = record.collision

            # Record StepReport for each active arm — dispatch in parallel via ThreadPoolExecutor
            # All mode logic (candidates, applied, j5_blocked) must be computed BEFORE dispatch.
            arm_execute_args: dict = {}
            for arm_id in arm_steps:
                own_cand = candidates[arm_id]
                own_applied = applied[arm_id]
                own_skipped = skipped_flags[arm_id]
                # j5_blocked: any blocking mode that zeroed j5 when candidate was non-zero
                # (does not include overlap_zone_wait skips — those are tracked separately)
                j5_blocked = (
                    self._mode in (BaselineMode.BASELINE_J5_BLOCK_SKIP, BaselineMode.GEOMETRY_BLOCK)
                    and own_applied["j5"] == 0.0
                    and own_cand["j5"] > 0.0
                )
                own_step = arm_steps[arm_id]
                arm_execute_args[arm_id] = {
                    "cand": own_cand,
                    "applied": own_applied,
                    "skipped": own_skipped,
                    "j5_blocked": j5_blocked,
                    "step": own_step,
                }

            # Dispatch all executor calls in parallel (max 2 workers for a pair of arms)
            outcomes: dict = {}
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = {
                    arm_id: pool.submit(
                        self._executor.execute,
                        arm_id=arm_id,
                        applied_joints=args["applied"],
                        blocked=args["j5_blocked"],
                        skipped=args["skipped"],
                        cam_x=args["step"].cam_x,
                        cam_y=args["step"].cam_y,
                        cam_z=args["step"].cam_z,
                        j4_pos=args["applied"]["j4"],
                        cotton_model=cotton_models.get((step_id, arm_id), ""),
                    )
                    for arm_id, args in arm_execute_args.items()
                }
                for arm_id in futures:
                    outcomes[arm_id] = futures[arm_id].result()

            # Add step reports in sorted arm_id order
            for arm_id in sorted(arm_execute_args.keys()):
                args = arm_execute_args[arm_id]
                outcome = outcomes[arm_id]
                own_cand = args["cand"]
                own_applied = args["applied"]
                own_skipped = args["skipped"]
                j5_blocked = args["j5_blocked"]

                # Override outcome for unreachable steps so the report clearly identifies
                # them as "unreachable" rather than the generic "skipped".
                if unreachable_flags.get(arm_id, False):
                    outcome = {
                        "terminal_status": "unreachable",
                        "pick_completed": False,
                        "executed_in_gazebo": False,
                    }

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
                        skipped=own_skipped,
                        terminal_status=outcome["terminal_status"],
                        pick_completed=outcome["pick_completed"],
                        executed_in_gazebo=outcome["executed_in_gazebo"],
                    )
                )
                # Update previous joints only when the step was actually executed in Gazebo.
                # Blocked/skipped steps must NOT update prev_joints — the arm never moved,
                # so the next step's FK must compute from the last real position.
                if outcome["executed_in_gazebo"]:
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
        # Recreate all named runtimes and re-wire the active pair.
        _arm_runtimes = {
            "arm1": ArmRuntime("arm1"),
            "arm2": ArmRuntime("arm2"),
            "arm3": ArmRuntime("arm3"),
        }
        self._arm1 = _arm_runtimes["arm1"]
        self._arm2 = _arm_runtimes["arm2"]
        self._arm3 = _arm_runtimes["arm3"]
        self._primary_arm = _arm_runtimes[self._primary_id]
        self._secondary_arm = _arm_runtimes[self._secondary_id]
        self._truth_monitor.reset()
        self._reporter.reset()
        self._transport.reset()
        self._last_summary = {}
