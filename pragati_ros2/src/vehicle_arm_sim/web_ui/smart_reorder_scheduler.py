"""Smart Reorder Scheduler for Mode 4: SMART_REORDER.

Rearranges cotton picking order for both arms to maximize the minimum j4 gap
across all paired steps, eliminating contention so all steps run in parallel.

Uses brute-force permutation search for N <= 8 steps per arm,
greedy (sort-by-j4) for N > 8.

FK formula: j4 = 0.1005 - cam_z
"""

import copy
from itertools import permutations

from collision_math import j4_collision_gap


FK_OFFSET = 0.1005
BRUTE_FORCE_LIMIT = 8


class SmartReorderScheduler:
    """Stateless scheduler that reorders arm steps to maximize min j4 gap."""

    def reorder(
        self,
        step_map: dict,
        arm1_steps: list[int],
        arm2_steps: list[int],
        primary_id: str = "arm1",
        secondary_id: str = "arm2",
    ) -> dict:
        """Reorder steps to maximize the minimum j4 gap across paired steps.

        Args:
            step_map: dict mapping step_id -> {arm_id: {...}}
            arm1_steps: list of step IDs for the primary arm
            arm2_steps: list of step IDs for the secondary arm
            primary_id: key used for the primary arm in step_map (default "arm1")
            secondary_id: key used for the secondary arm in step_map (default "arm2")

        Returns:
            New step_map with sequential integer keys (0..N-1), paired steps
            first, then solo-tail steps.
        """
        # Separate paired vs solo step data for each arm
        arm1_paired_data = []
        arm2_paired_data = []
        arm1_solo_data = []
        arm2_solo_data = []

        paired_count = min(len(arm1_steps), len(arm2_steps))

        for i, sid in enumerate(arm1_steps):
            step_data = step_map[sid].get(primary_id)
            if step_data is None:
                continue
            if i < paired_count:
                arm1_paired_data.append(copy.deepcopy(step_data))
            else:
                arm1_solo_data.append(copy.deepcopy(step_data))

        for i, sid in enumerate(arm2_steps):
            step_data = step_map[sid].get(secondary_id)
            if step_data is None:
                continue
            if i < paired_count:
                arm2_paired_data.append(copy.deepcopy(step_data))
            else:
                arm2_solo_data.append(copy.deepcopy(step_data))

        # If no paired steps, return solo steps with sequential IDs
        if paired_count == 0:
            return self._build_solo_only(
                arm1_solo_data, arm2_solo_data,
                arm1_steps, arm2_steps,
                primary_id=primary_id, secondary_id=secondary_id,
            )

        # Compute j4 values for paired steps
        arm1_j4s = [self._cam_z_to_j4(d["cam_z"]) for d in arm1_paired_data]
        arm2_j4s = [self._cam_z_to_j4(d["cam_z"]) for d in arm2_paired_data]

        # Find optimal pairing
        if paired_count <= BRUTE_FORCE_LIMIT:
            best_perm = self._brute_force(arm1_j4s, arm2_j4s)
        else:
            best_perm = self._greedy(arm1_j4s, arm2_j4s)

        # Build new step_map with sequential IDs
        new_step_map = {}

        # Paired steps first (IDs 0..paired_count-1)
        for i in range(paired_count):
            new_step_map[i] = {
                primary_id: arm1_paired_data[i],
                secondary_id: arm2_paired_data[best_perm[i]],
            }

        # Solo-tail steps
        solo_id = paired_count
        for data in arm1_solo_data:
            new_step_map[solo_id] = {primary_id: data}
            solo_id += 1
        for data in arm2_solo_data:
            new_step_map[solo_id] = {secondary_id: data}
            solo_id += 1

        return new_step_map

    @staticmethod
    def _cam_z_to_j4(cam_z: float) -> float:
        """Convert cam_z to j4 world position via FK formula."""
        return FK_OFFSET - cam_z

    @staticmethod
    def _min_gap_for_perm(
        arm1_j4s: list[float],
        arm2_j4s: list[float],
        perm: tuple[int, ...],
    ) -> float:
        """Compute minimum j4 collision gap across all pairs."""
        return min(j4_collision_gap(arm1_j4s[i], arm2_j4s[perm[i]]) for i in range(len(arm1_j4s)))

    def _brute_force(
        self, arm1_j4s: list[float], arm2_j4s: list[float]
    ) -> tuple[int, ...]:
        """Try all permutations of arm2 indices, return the one with max min gap."""
        n = len(arm2_j4s)
        best_perm = tuple(range(n))
        best_min_gap = self._min_gap_for_perm(arm1_j4s, arm2_j4s, best_perm)

        for perm in permutations(range(n)):
            mg = self._min_gap_for_perm(arm1_j4s, arm2_j4s, perm)
            if mg > best_min_gap:
                best_min_gap = mg
                best_perm = perm

        return best_perm

    def _greedy(
        self, arm1_j4s: list[float], arm2_j4s: list[float]
    ) -> tuple[int, ...]:
        """Greedy approach: sort arm1 ascending, pair with arm2 in reverse order.

        Sort both arms' j4s, then pair arm1[i] with arm2[N-1-i] to maximize
        minimum gap for sorted sequences.
        """
        n = len(arm1_j4s)

        # Create indexed lists and sort
        arm1_indexed = sorted(enumerate(arm1_j4s), key=lambda x: x[1])
        arm2_indexed = sorted(enumerate(arm2_j4s), key=lambda x: x[1])

        # Build the permutation: arm1 sorted ascending pairs with arm2 sorted
        # descending (reverse pairing maximizes min gap for sorted sequences)
        # perm[arm1_original_index] = arm2_original_index
        perm = [0] * n
        for i in range(n):
            arm1_orig_idx = arm1_indexed[i][0]
            arm2_orig_idx = arm2_indexed[n - 1 - i][0]
            perm[arm1_orig_idx] = arm2_orig_idx

        greedy_perm = tuple(perm)

        # Safety: greedy must never degrade the original ordering.
        # If the greedy result is worse than the identity permutation, keep
        # the original order rather than making things worse.
        identity_perm = tuple(range(n))
        greedy_gap = self._min_gap_for_perm(arm1_j4s, arm2_j4s, greedy_perm)
        identity_gap = self._min_gap_for_perm(arm1_j4s, arm2_j4s, identity_perm)

        return greedy_perm if greedy_gap >= identity_gap else identity_perm

    def _build_solo_only(
        self,
        arm1_solo_data: list[dict],
        arm2_solo_data: list[dict],
        arm1_steps: list[int],
        arm2_steps: list[int],
        primary_id: str = "arm1",
        secondary_id: str = "arm2",
    ) -> dict:
        """Build step_map when there are no paired steps (one arm is empty)."""
        new_step_map = {}
        sid = 0

        for data in arm1_solo_data:
            new_step_map[sid] = {primary_id: data}
            sid += 1

        for data in arm2_solo_data:
            new_step_map[sid] = {secondary_id: data}
            sid += 1

        return new_step_map
