"""
Command deduplication for vehicle control position commands.

Prevents publishing redundant ROS2 position messages when the target
position has not changed beyond a configurable epsilon threshold.
"""

import logging
from typing import Optional


class CommandDedup:
    """Deduplicates position commands per joint.

    Tracks the last commanded position for each joint and skips publishing
    when the new target is within DEDUP_EPSILON of the cached value.
    The epsilon is in the command's native unit (rotations for steering
    motors, meters for drive motors) — applied after unit conversion,
    on the value actually published to the ROS2 topic.

    For steering: 0.01 rotations ≈ 3.6 degrees (filters jitter).
    For drive: 0.01 meters (filters sub-cm noise).

    Attributes:
        DEDUP_EPSILON: Maximum position difference in command-native units
            considered identical. Default 0.01.
    """

    DEDUP_EPSILON = 0.01  # command-native units (rotations or meters)

    def __init__(self, epsilon: float = None, logger: Optional[logging.Logger] = None):
        """Initialize command dedup.

        Args:
            epsilon: Override default epsilon (command-native units). None uses DEDUP_EPSILON.
            logger: Logger instance for dedup skip messages. None disables logging.
        """
        self._epsilon = epsilon if epsilon is not None else self.DEDUP_EPSILON
        self._cache: dict[str, float] = {}
        self._skip_counts: dict[str, int] = {}
        self._logger = logger

    def should_send(self, joint_name: str, position: float) -> bool:
        """Check if a position command should be sent.

        Args:
            joint_name: Name of the joint (e.g., 'steering_left').
            position: Target position in command-native units (rotations for
                steering, meters for drive) — the value actually published
                to the ROS2 topic.

        Returns:
            True if the command should be sent (first command or position
            changed beyond epsilon). False if duplicate.
        """
        if joint_name not in self._cache:
            # First command for this joint — always send
            self._cache[joint_name] = position
            self._skip_counts[joint_name] = 0
            return True

        diff = abs(position - self._cache[joint_name])
        if diff < self._epsilon:
            # Duplicate — skip
            self._skip_counts[joint_name] = self._skip_counts.get(joint_name, 0) + 1

            # Log every 100 skips
            if self._logger is not None and self._skip_counts[joint_name] % 100 == 0:
                self._logger.debug(
                    f"[DEDUP] {joint_name}: skipped {self._skip_counts[joint_name]} "
                    f"redundant commands (last={self._cache[joint_name]:.4f}, "
                    f"new={position:.4f}, diff={diff:.6f})"
                )
            return False

        # Position changed — send and update cache
        self._cache[joint_name] = position
        self._skip_counts[joint_name] = 0
        return True

    def reset(self, joint_name: str = None):
        """Reset dedup cache.

        Args:
            joint_name: Reset specific joint. None resets all joints.
        """
        if joint_name is None:
            self._cache.clear()
            self._skip_counts.clear()
        else:
            self._cache.pop(joint_name, None)
            self._skip_counts.pop(joint_name, None)

    def get_skip_count(self, joint_name: str) -> int:
        """Get cumulative skip count for a joint."""
        return self._skip_counts.get(joint_name, 0)
