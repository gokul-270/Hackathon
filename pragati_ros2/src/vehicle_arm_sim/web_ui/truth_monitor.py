"""Truth monitor - passive observer that records near-collision and collision outcomes."""
import threading
from dataclasses import dataclass

from collision_math import j4_collision_gap

NEAR_COLLISION_THRESHOLD = 0.08  # meters, j4_collision_gap(j4_arm1, j4_arm2)
COLLISION_THRESHOLD = 0.05       # meters


@dataclass
class StepTruthRecord:
    step_id: int
    min_j4_distance: float
    near_collision: bool
    collision: bool


class TruthMonitor:
    """Passive observer that records j4 distance outcomes per step."""

    def __init__(self) -> None:
        self._records: dict[int, StepTruthRecord] = {}
        self._lock = threading.Lock()

    def observe(self, step_id: int, j4_arm1: float, j4_arm2: float) -> None:
        """Record an observation for a step. Can be called multiple times per step."""
        distance = j4_collision_gap(j4_arm1, j4_arm2)
        with self._lock:
            existing = self._records.get(step_id)
            if existing is None or distance < existing.min_j4_distance:
                self._records[step_id] = StepTruthRecord(
                    step_id=step_id,
                    min_j4_distance=distance,
                    near_collision=distance < NEAR_COLLISION_THRESHOLD,
                    collision=distance < COLLISION_THRESHOLD,
                )

    def get_step_record(self, step_id: int) -> StepTruthRecord | None:
        """Get the truth record for a step. Returns None if not observed."""
        return self._records.get(step_id)

    def get_all_records(self) -> list[StepTruthRecord]:
        """Get all step truth records, sorted by step_id."""
        return sorted(self._records.values(), key=lambda r: r.step_id)

    def reset(self) -> None:
        """Clear all records."""
        self._records.clear()
