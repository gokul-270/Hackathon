"""Arm runtime registry — single source of truth for the dual-arm hackathon system.

This module documents the two arm runtimes and their configuration, making the
launched system shape explicit in code. It acts as the runtime manifest for the
dual-arm architecture (C4: UI/Backend --> Run Controller --> Arm1 + Arm2 runtimes).
"""

from dataclasses import dataclass

ARM_RUNTIME_IDS = ("arm1", "arm2")

HACKATHON_BACKEND_PORT = 8081


@dataclass
class ArmRuntimeDescriptor:
    """Descriptor for a single arm runtime in the dual-arm system."""

    arm_id: str
    port: int
    role: str


def get_runtime_manifest() -> list[ArmRuntimeDescriptor]:
    """Return the manifest of all arm runtimes in the dual-arm system.

    Returns a list of ArmRuntimeDescriptor objects, one per arm. This is the
    canonical reference for what arms exist and how they are configured.
    """
    # Both arms share the same backend port: the hackathon implementation is a single
    # in-process server. In a distributed deployment each arm would bind a distinct port.
    return [
        ArmRuntimeDescriptor(arm_id="arm1", port=HACKATHON_BACKEND_PORT, role="primary"),
        ArmRuntimeDescriptor(arm_id="arm2", port=HACKATHON_BACKEND_PORT, role="secondary"),
    ]
