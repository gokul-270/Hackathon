"""Tests for JsonReporter - Group 5 JSON reporting (TDD Red phase)."""
import json
import pytest
from dataclasses import dataclass
from typing import Optional

# Minimal local StepReport for testing (parallel agent owns truth_monitor.py)
from json_reporter import StepReport, JsonReporter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_step(
    step_id: int = 1,
    arm_id: str = "arm_a",
    mode: str = "unrestricted",
    candidate_joints: Optional[dict] = None,
    applied_joints: Optional[dict] = None,
    j5_blocked: bool = False,
    near_collision: bool = False,
    collision: bool = False,
    min_j4_distance: Optional[float] = None,
) -> StepReport:
    return StepReport(
        step_id=step_id,
        arm_id=arm_id,
        mode=mode,
        candidate_joints=candidate_joints or {"j3": 0.1, "j4": 0.2, "j5": 0.3},
        applied_joints=applied_joints or {"j3": 0.1, "j4": 0.2, "j5": 0.3},
        j5_blocked=j5_blocked,
        near_collision=near_collision,
        collision=collision,
        min_j4_distance=min_j4_distance,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_json_reporter_add_step_records_the_step():
    reporter = JsonReporter()
    step = make_step(step_id=1)
    reporter.add_step(step)
    summary = reporter.build_run_summary(mode="unrestricted", total_steps=1)
    assert len(summary["step_reports"]) == 1


def test_json_reporter_build_run_summary_counts_near_collision_steps_correctly():
    reporter = JsonReporter()
    reporter.add_step(make_step(step_id=1, near_collision=True))
    reporter.add_step(make_step(step_id=2, near_collision=False))
    reporter.add_step(make_step(step_id=3, near_collision=True))
    summary = reporter.build_run_summary(mode="unrestricted", total_steps=3)
    assert summary["steps_with_near_collision"] == 2


def test_json_reporter_build_run_summary_counts_collision_steps_correctly():
    reporter = JsonReporter()
    reporter.add_step(make_step(step_id=1, collision=True))
    reporter.add_step(make_step(step_id=2, collision=False))
    summary = reporter.build_run_summary(mode="unrestricted", total_steps=2)
    assert summary["steps_with_collision"] == 1


def test_json_reporter_build_run_summary_counts_j5_blocked_steps_correctly():
    reporter = JsonReporter()
    reporter.add_step(make_step(step_id=1, j5_blocked=True))
    reporter.add_step(make_step(step_id=2, j5_blocked=True))
    reporter.add_step(make_step(step_id=3, j5_blocked=False))
    summary = reporter.build_run_summary(mode="baseline_j5_block_skip", total_steps=3)
    assert summary["steps_with_j5_blocked"] == 2


def test_json_reporter_build_run_summary_includes_step_reports_list():
    reporter = JsonReporter()
    reporter.add_step(make_step(step_id=10))
    reporter.add_step(make_step(step_id=20))
    summary = reporter.build_run_summary(mode="unrestricted", total_steps=2)
    assert "step_reports" in summary
    assert isinstance(summary["step_reports"], list)
    assert len(summary["step_reports"]) == 2


def test_json_reporter_to_json_returns_valid_json_string():
    reporter = JsonReporter()
    reporter.add_step(make_step(step_id=1))
    result = reporter.to_json(mode="unrestricted", total_steps=1)
    # Must not raise
    parsed = json.loads(result)
    assert isinstance(parsed, dict)


def test_json_reporter_to_json_output_deserializes_to_dict_with_mode_key():
    reporter = JsonReporter()
    reporter.add_step(make_step(step_id=1, mode="baseline_j5_block_skip"))
    result = reporter.to_json(mode="baseline_j5_block_skip", total_steps=1)
    parsed = json.loads(result)
    assert "mode" in parsed
    assert parsed["mode"] == "baseline_j5_block_skip"


def test_json_reporter_reset_clears_step_reports():
    reporter = JsonReporter()
    reporter.add_step(make_step(step_id=1))
    reporter.add_step(make_step(step_id=2))
    reporter.reset()
    summary = reporter.build_run_summary(mode="unrestricted", total_steps=0)
    assert summary["step_reports"] == []


# ---------------------------------------------------------------------------
# Group 4 — Thread-safety
# ---------------------------------------------------------------------------


def test_json_reporter_add_step_is_thread_safe():
    """Two threads each adding 500 steps concurrently must produce all 1000 in summary."""
    import threading
    from json_reporter import JsonReporter

    reporter = JsonReporter()
    errors = []

    def worker(arm_id):
        for i in range(500):
            try:
                reporter.add_step(make_step(step_id=i, arm_id=arm_id))
            except Exception as exc:
                errors.append(exc)

    t1 = threading.Thread(target=worker, args=("arm1",))
    t2 = threading.Thread(target=worker, args=("arm2",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors, f"Thread safety errors in JsonReporter.add_step: {errors}"
    summary = reporter.build_run_summary(mode="unrestricted", total_steps=1000)
    assert len(summary["step_reports"]) == 1000, (
        f"All 1000 step reports must be present; got {len(summary['step_reports'])}"
    )
