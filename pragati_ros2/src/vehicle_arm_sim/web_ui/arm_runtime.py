#!/usr/bin/env python3
"""Distributed arm runtime for the dual-arm cotton-picking scenario.

Loads a shared scenario JSON, filters steps for the configured arm_id, computes
candidate joints via the fk_chain FK pipeline, and builds peer-state packets for
inter-arm coordination.
"""

import time
from dataclasses import dataclass
from typing import Optional

from fk_chain import camera_to_arm, polar_decompose


@dataclass
class PeerStatePacket:
    arm_id: str
    step_id: int
    status: str  # "idle" | "computing" | "ready" | "executing" | "done" | "skipped"
    timestamp: float  # time.time()
    current_joints: dict  # {"j3": float, "j4": float, "j5": float}
    candidate_joints: Optional[dict]  # {"j3": float, "j4": float, "j5": float} or None


class ArmRuntime:
    """Per-arm runtime that filters scenario steps and computes FK-based candidate joints."""

    def __init__(self, arm_id: str) -> None:
        self._arm_id = arm_id
        self._steps: list = []

    def load_scenario(self, steps: list) -> None:
        """Store only the steps whose arm_id matches this runtime's arm_id.

        Args:
            steps: Full list of ScenarioStep objects from the shared scenario JSON.
        """
        self._steps = [s for s in steps if s.arm_id == self._arm_id]

    def get_own_steps(self) -> list:
        """Return the filtered list of steps belonging to this arm."""
        return list(self._steps)

    def compute_candidate_joints(self, step, j4_current: float = 0.0) -> dict:
        """Compute candidate j3/j4/j5 joints from a scenario step's camera point.

        Uses fk_chain.camera_to_arm to transform the camera-frame point into the
        arm (yanthra_link) frame, then fk_chain.polar_decompose to derive joint
        commands.

        Args:
            step: ScenarioStep with cam_x, cam_y, cam_z fields.
            j4_current: Current J4 position in metres (default 0.0).

        Returns:
            dict with keys j3, j4, j5, reachable (and r, theta, phi from polar_decompose).
        """
        ax, ay, az = camera_to_arm(step.cam_x, step.cam_y, step.cam_z, j4_pos=j4_current)
        return polar_decompose(ax, ay, az)

    def run_step(
        self,
        step_id: int,
        peer_state: Optional["PeerStatePacket"],
        mode: int,
        baseline_mode_obj: object,
        current_joints: dict,
    ) -> tuple[dict, bool, dict]:
        """Execute one scenario step and return the result as a self-contained unit.

        Looks up the step by step_id from the loaded steps, computes candidate joints
        via FK, applies mode logic via baseline_mode_obj, and returns the outcome.

        Args:
            step_id: The step to execute (must have been loaded via load_scenario).
            peer_state: PeerStatePacket from the peer arm, or None if peer is inactive.
            mode: One of BaselineMode constants (UNRESTRICTED=0, BASELINE_J5_BLOCK_SKIP=1, …).
            baseline_mode_obj: A BaselineMode instance used to apply mode logic.
            current_joints: The arm's current joint positions {"j3", "j4", "j5"}.

        Returns:
            (applied_joints, skipped, candidate_joints) where:
              - applied_joints: joints after mode logic has been applied.
              - skipped: True only when sequential_pick times out and skips the pick.
              - candidate_joints: raw FK result before mode logic.
        """
        step = next((s for s in self._steps if s.step_id == step_id), None)
        if step is None:
            raise ValueError(f"Step {step_id} not found for arm {self._arm_id}")

        j4_current = current_joints.get("j4", 0.0)
        candidate_joints = self.compute_candidate_joints(step, j4_current=j4_current)

        applied_joints, skipped = baseline_mode_obj.apply_with_skip(
            mode, candidate_joints, peer_state, step_id=step_id, arm_id=self._arm_id
        )
        return applied_joints, skipped, candidate_joints

    def build_peer_state(
        self,
        step_id: int,
        status: str,
        current_joints: dict,
        candidate_joints: Optional[dict],
    ) -> PeerStatePacket:
        """Create a PeerStatePacket for broadcasting to peer arms.

        Args:
            step_id: The scenario step being processed.
            status: One of "idle", "computing", "ready", "executing", "done", "skipped".
            current_joints: Dict {"j3": float, "j4": float, "j5": float}.
            candidate_joints: Dict {"j3": float, "j4": float, "j5": float} or None.

        Returns:
            PeerStatePacket populated with this arm's identity and a current timestamp.
        """
        return PeerStatePacket(
            arm_id=self._arm_id,
            step_id=step_id,
            status=status,
            timestamp=time.time(),
            current_joints=current_joints,
            candidate_joints=candidate_joints,
        )
