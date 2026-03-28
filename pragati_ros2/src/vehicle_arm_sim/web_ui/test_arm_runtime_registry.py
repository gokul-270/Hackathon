"""Tests for arm_runtime_registry module — dual-arm launch/runtime manifest."""

import pytest


def test_arm_runtime_registry_can_be_imported():
    import arm_runtime_registry  # noqa: F401


def test_arm_runtime_ids_is_tuple_with_arm1_and_arm2():
    from arm_runtime_registry import ARM_RUNTIME_IDS

    assert isinstance(ARM_RUNTIME_IDS, tuple)
    assert "arm1" in ARM_RUNTIME_IDS
    assert "arm2" in ARM_RUNTIME_IDS


def test_arm_runtime_ids_contains_exactly_two_entries():
    from arm_runtime_registry import ARM_RUNTIME_IDS

    assert len(ARM_RUNTIME_IDS) == 2


def test_hackathon_backend_port_is_8081():
    from arm_runtime_registry import HACKATHON_BACKEND_PORT

    assert HACKATHON_BACKEND_PORT == 8081


def test_get_runtime_manifest_returns_list_of_two_descriptors():
    from arm_runtime_registry import get_runtime_manifest

    manifest = get_runtime_manifest()
    assert isinstance(manifest, list)
    assert len(manifest) == 2


def test_manifest_contains_descriptor_for_arm1():
    from arm_runtime_registry import get_runtime_manifest

    manifest = get_runtime_manifest()
    arm_ids = [d.arm_id for d in manifest]
    assert "arm1" in arm_ids


def test_manifest_contains_descriptor_for_arm2():
    from arm_runtime_registry import get_runtime_manifest

    manifest = get_runtime_manifest()
    arm_ids = [d.arm_id for d in manifest]
    assert "arm2" in arm_ids


def test_each_descriptor_has_arm_id_attribute():
    from arm_runtime_registry import get_runtime_manifest

    for descriptor in get_runtime_manifest():
        assert hasattr(descriptor, "arm_id")


def test_each_descriptor_has_port_attribute():
    from arm_runtime_registry import get_runtime_manifest

    for descriptor in get_runtime_manifest():
        assert hasattr(descriptor, "port")


def test_each_descriptor_has_role_attribute():
    from arm_runtime_registry import get_runtime_manifest

    for descriptor in get_runtime_manifest():
        assert hasattr(descriptor, "role")


def test_arm_runtime_descriptor_is_a_dataclass():
    from dataclasses import fields
    from arm_runtime_registry import ArmRuntimeDescriptor

    field_names = {f.name for f in fields(ArmRuntimeDescriptor)}
    assert field_names == {"arm_id", "port", "role"}
