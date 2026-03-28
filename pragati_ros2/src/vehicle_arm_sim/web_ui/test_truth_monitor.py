"""Tests for TruthMonitor - Group 4 Truth Monitor MVP."""
import pytest
from truth_monitor import TruthMonitor, StepTruthRecord, NEAR_COLLISION_THRESHOLD, COLLISION_THRESHOLD


def test_observe_records_minimum_j4_distance_for_step():
    monitor = TruthMonitor()
    monitor.observe(step_id=1, j4_arm1=0.5, j4_arm2=0.3)
    record = monitor.get_step_record(1)
    assert record is not None
    assert abs(record.min_j4_distance - 0.2) < 1e-9


def test_observe_updates_minimum_when_lower_value_arrives():
    monitor = TruthMonitor()
    monitor.observe(step_id=1, j4_arm1=0.5, j4_arm2=0.3)   # distance = 0.2
    monitor.observe(step_id=1, j4_arm1=0.45, j4_arm2=0.36)  # distance = 0.09
    record = monitor.get_step_record(1)
    assert abs(record.min_j4_distance - 0.09) < 1e-9


def test_observe_does_not_update_minimum_when_higher_value_arrives():
    monitor = TruthMonitor()
    monitor.observe(step_id=1, j4_arm1=0.45, j4_arm2=0.36)  # distance = 0.09
    monitor.observe(step_id=1, j4_arm1=0.5, j4_arm2=0.3)    # distance = 0.2 (higher)
    record = monitor.get_step_record(1)
    assert abs(record.min_j4_distance - 0.09) < 1e-9


def test_observe_near_collision_is_true_when_min_distance_below_threshold():
    monitor = TruthMonitor()
    distance = NEAR_COLLISION_THRESHOLD - 0.01
    monitor.observe(step_id=1, j4_arm1=0.0, j4_arm2=distance)
    record = monitor.get_step_record(1)
    assert record.near_collision is True


def test_observe_near_collision_is_false_when_min_distance_above_threshold():
    monitor = TruthMonitor()
    distance = NEAR_COLLISION_THRESHOLD + 0.01
    monitor.observe(step_id=1, j4_arm1=0.0, j4_arm2=distance)
    record = monitor.get_step_record(1)
    assert record.near_collision is False


def test_observe_collision_is_true_when_min_distance_below_collision_threshold():
    monitor = TruthMonitor()
    distance = COLLISION_THRESHOLD - 0.01
    monitor.observe(step_id=1, j4_arm1=0.0, j4_arm2=distance)
    record = monitor.get_step_record(1)
    assert record.collision is True


def test_get_step_record_returns_none_for_unobserved_step():
    monitor = TruthMonitor()
    assert monitor.get_step_record(99) is None


def test_reset_clears_all_records():
    monitor = TruthMonitor()
    monitor.observe(step_id=1, j4_arm1=0.5, j4_arm2=0.3)
    monitor.observe(step_id=2, j4_arm1=0.6, j4_arm2=0.4)
    monitor.reset()
    assert monitor.get_step_record(1) is None
    assert monitor.get_step_record(2) is None
    assert monitor.get_all_records() == []


def test_get_all_records_returns_sorted_by_step_id():
    monitor = TruthMonitor()
    monitor.observe(step_id=3, j4_arm1=0.5, j4_arm2=0.3)
    monitor.observe(step_id=1, j4_arm1=0.6, j4_arm2=0.4)
    monitor.observe(step_id=2, j4_arm1=0.7, j4_arm2=0.5)
    records = monitor.get_all_records()
    assert [r.step_id for r in records] == [1, 2, 3]
