"""JSON reporter for dual-arm simulation run summaries - Group 5."""
import json
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class StepReport:
    step_id: int
    arm_id: str
    mode: str  # "unrestricted" | "baseline_j5_block_skip" | "geometry_block" | "overlap_zone_wait"
    candidate_joints: dict  # {"j3": float, "j4": float, "j5": float}
    applied_joints: dict    # after mode logic
    j5_blocked: bool
    near_collision: bool
    collision: bool
    min_j4_distance: Optional[float]  # None if only one arm active in this step
    skipped: bool = False  # True when overlap_zone_wait skips the step
    # Explicit terminal outcome fields (added by gazebo-scenario-execution change)
    terminal_status: str = "completed"  # "completed" | "blocked" | "skipped"
    pick_completed: bool = True
    executed_in_gazebo: bool = False


class JsonReporter:
    """Records per-step results and produces JSON run summaries."""

    def __init__(self) -> None:
        self._steps: list[StepReport] = []

    def add_step(self, step_report: StepReport) -> None:
        """Record a step result."""
        self._steps.append(step_report)

    def build_run_summary(self, mode: str, total_steps: int) -> dict:
        """Build per-run JSON summary dict."""
        j5_blocked_count = sum(1 for s in self._steps if s.j5_blocked)
        skipped_count = sum(1 for s in self._steps if s.skipped)
        completed_picks = sum(1 for s in self._steps if s.pick_completed)
        return {
            "mode": mode,
            "total_steps": total_steps,
            "steps_with_near_collision": sum(
                1 for s in self._steps if s.near_collision
            ),
            "steps_with_collision": sum(
                1 for s in self._steps if s.collision
            ),
            "steps_with_j5_blocked": j5_blocked_count,
            # Alias used by MarkdownReporter for unified three-mode comparison
            "steps_with_motion_blocked": j5_blocked_count,
            "steps_with_skipped": skipped_count,
            "steps_with_blocked_or_skipped": j5_blocked_count + skipped_count,
            "completed_picks": completed_picks,
            "step_reports": [asdict(s) for s in self._steps],
        }

    def to_json(self, mode: str, total_steps: int) -> str:
        """Return the run summary as a JSON string (indent=2)."""
        return json.dumps(self.build_run_summary(mode, total_steps), indent=2)

    def reset(self) -> None:
        """Clear all step reports."""
        self._steps = []
