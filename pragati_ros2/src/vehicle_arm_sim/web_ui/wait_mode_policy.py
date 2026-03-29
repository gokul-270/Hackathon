"""Backward-compatibility shim — real implementation moved to sequential_pick_policy.py."""

from sequential_pick_policy import SequentialPickPolicy as WaitModePolicy  # noqa: F401

__all__ = ["WaitModePolicy"]
