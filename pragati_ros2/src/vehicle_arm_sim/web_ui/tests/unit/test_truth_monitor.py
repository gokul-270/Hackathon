"""Tests for TruthMonitor - Group 4 Truth Monitor MVP."""
import pytest
from truth_monitor import TruthMonitor, StepTruthRecord, NEAR_COLLISION_THRESHOLD, COLLISION_THRESHOLD


def test_observe_records_minimum_j4_distance_for_step():
    monitor = TruthMonitor()
    monitor.observe(step_id=1, j4_arm1=0.5, j4_arm2=-0.3)
    record = monitor.get_step_record(1)
    assert record is not None
    assert abs(record.min_j4_distance - 0.2) < 1e-9


def test_observe_updates_minimum_when_lower_value_arrives():
    monitor = TruthMonitor()
    monitor.observe(step_id=1, j4_arm1=0.5, j4_arm2=-0.3)   # distance = 0.2
    monitor.observe(step_id=1, j4_arm1=0.45, j4_arm2=-0.36)  # distance = 0.09
    record = monitor.get_step_record(1)
    assert abs(record.min_j4_distance - 0.09) < 1e-9


def test_observe_does_not_update_minimum_when_higher_value_arrives():
    monitor = TruthMonitor()
    monitor.observe(step_id=1, j4_arm1=0.45, j4_arm2=-0.36)  # distance = 0.09
    monitor.observe(step_id=1, j4_arm1=0.5, j4_arm2=-0.3)    # distance = 0.2 (higher)
    record = monitor.get_step_record(1)
    assert abs(record.min_j4_distance - 0.09) < 1e-9


def test_observe_near_collision_is_true_when_min_distance_below_threshold():
    monitor = TruthMonitor()
    distance = NEAR_COLLISION_THRESHOLD - 0.01
    monitor.observe(step_id=1, j4_arm1=0.0, j4_arm2=-distance)
    record = monitor.get_step_record(1)
    assert record.near_collision is True


def test_observe_near_collision_is_false_when_min_distance_above_threshold():
    monitor = TruthMonitor()
    distance = NEAR_COLLISION_THRESHOLD + 0.01
    monitor.observe(step_id=1, j4_arm1=0.0, j4_arm2=-distance)
    record = monitor.get_step_record(1)
    assert record.near_collision is False


def test_observe_collision_is_true_when_min_distance_below_collision_threshold():
    monitor = TruthMonitor()
    distance = COLLISION_THRESHOLD - 0.01
    monitor.observe(step_id=1, j4_arm1=0.0, j4_arm2=-distance)
    record = monitor.get_step_record(1)
    assert record.collision is True


def test_get_step_record_returns_none_for_unobserved_step():
    monitor = TruthMonitor()
    assert monitor.get_step_record(99) is None


def test_reset_clears_all_records():
    monitor = TruthMonitor()
    monitor.observe(step_id=1, j4_arm1=0.5, j4_arm2=-0.3)
    monitor.observe(step_id=2, j4_arm1=0.6, j4_arm2=-0.4)
    monitor.reset()
    assert monitor.get_step_record(1) is None
    assert monitor.get_step_record(2) is None
    assert monitor.get_all_records() == []


def test_get_all_records_returns_sorted_by_step_id():
    monitor = TruthMonitor()
    monitor.observe(step_id=3, j4_arm1=0.5, j4_arm2=-0.3)
    monitor.observe(step_id=1, j4_arm1=0.6, j4_arm2=-0.4)
    monitor.observe(step_id=2, j4_arm1=0.7, j4_arm2=-0.5)
    records = monitor.get_all_records()
    assert [r.step_id for r in records] == [1, 2, 3]


# ---------------------------------------------------------------------------
# Group 3 (Phase 2): collision-distance also implies near_collision
# ---------------------------------------------------------------------------


def test_observe_collision_distance_also_sets_near_collision_true():
    """When distance < COLLISION_THRESHOLD, near_collision MUST also be True.

    Since COLLISION_THRESHOLD (0.05) < NEAR_COLLISION_THRESHOLD (0.110), any
    collision observation is also a near-collision.  Both flags must be True.
    """
    monitor = TruthMonitor()
    assert COLLISION_THRESHOLD < NEAR_COLLISION_THRESHOLD, (
        "Test precondition: COLLISION_THRESHOLD must be less than NEAR_COLLISION_THRESHOLD"
    )
    distance = COLLISION_THRESHOLD - 0.001  # strictly below both thresholds
    monitor.observe(step_id=1, j4_arm1=0.0, j4_arm2=-distance)
    record = monitor.get_step_record(1)
    assert record.collision is True
    assert record.near_collision is True, (
        "A collision-level distance must also set near_collision=True "
        f"(distance={distance:.4f}, COLLISION_THRESHOLD={COLLISION_THRESHOLD}, "
        f"NEAR_COLLISION_THRESHOLD={NEAR_COLLISION_THRESHOLD})"
    )


# ---------------------------------------------------------------------------
# Group 4 — Thread-safety
# ---------------------------------------------------------------------------


def test_truth_monitor_observe_is_thread_safe():
    """Two threads calling observe() concurrently must not raise exceptions."""
    import threading
    from truth_monitor import TruthMonitor

    monitor = TruthMonitor()
    errors = []

    def worker(step_start, j4_offset):
        for i in range(500):
            try:
                monitor.observe(
                    step_id=step_start + i,
                    j4_arm1=0.10 + j4_offset,
                    j4_arm2=-(0.20 + j4_offset),
                )
            except Exception as exc:
                errors.append(exc)

    t1 = threading.Thread(target=worker, args=(0, 0.0))
    t2 = threading.Thread(target=worker, args=(0, 0.001))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors, f"Thread safety errors in TruthMonitor.observe: {errors}"
    # At least one record must have been stored
    assert len(monitor.get_all_records()) > 0
