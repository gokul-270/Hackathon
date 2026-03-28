"""Tests for the analysis API response schemas.

Validates endpoint status codes, response structure, and alias fields
that the frontend depends on for compatibility.
"""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.analysis_api import analysis_router
import backend.analysis_api as _mod

# -----------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_module_state(tmp_path):
    """Point results dir and field_logs dir to tmp, reset jobs."""
    orig_results = _mod._results_dir
    orig_field_logs = _mod.FIELD_LOGS_DIR
    orig_jobs = _mod._jobs.copy()

    _mod._results_dir = tmp_path / "results"
    _mod._results_dir.mkdir()
    _mod.FIELD_LOGS_DIR = tmp_path / "field_logs"

    yield

    _mod._results_dir = orig_results
    _mod.FIELD_LOGS_DIR = orig_field_logs
    _mod._jobs.clear()
    _mod._jobs.update(orig_jobs)


@pytest.fixture()
def client():
    """FastAPI test client with only the analysis router."""
    app = FastAPI()
    app.include_router(analysis_router)
    return TestClient(app)


@pytest.fixture()
def completed_job(tmp_path):
    """Create a completed job with all result files on disk.

    Returns the job_id.
    """
    job_id = "test-job-001"
    job_dir = _mod._results_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "job_id": job_id,
        "log_directory": "/tmp/fake_logs",
        "date_run": "2026-01-15T10:00:00+00:00",
        "status": "completed",
        "key_findings_summary": ["High motor temp"],
        "success_rate_pct": 85.0,
        "total_picks": 120,
        "session_duration_s": 3600,
    }
    (job_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    summary = {
        "executive_summary": "Good session",
        "status": "completed",
        "overall_health": "good",
        "duration": 3600,
        "total_picks": 120,
        "success_rate": 0.85,
        "error_count": 1,
        "key_findings": ["High motor temp"],
        "critical_issues": [],
        "pick_performance": {
            "total_picks": 120,
            "success_rate_pct": 85.0,
            "picks_per_hour": 120,
            "cycle_time_ms": 3000,
        },
        "session_health": {
            "overall_health": "good",
            "duration_seconds": 3600,
            "duration_s": 3600,
        },
        "issues": [],
        "level_counts": {"critical": 0, "high": 1},
    }
    (job_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")

    detection = {
        "total_raw_detections": 200,
        "total_accepted": 150,
        "acceptance_rate_pct": 75.0,
        "acceptance_rate": 0.75,
        "border_skip_rate_pct": 5.0,
        "border_skip_rate": 0.05,
        "detection_timing_ms": {"mean": 45.0, "p95": 80.0},
        "timing": {"mean": 45.0, "p95": 80.0},
        "scan_effectiveness": None,
        "confidence_distribution": {
            "high": 100,
            "medium": 40,
            "low": 10,
        },
    }
    (job_dir / "detection.json").write_text(json.dumps(detection), encoding="utf-8")

    timeline = {
        "events": [
            {"time": "10:00:01", "type": "pick_start"},
            {"time": "10:00:05", "type": "pick_end"},
        ],
        "total_events": 2,
        "total": 2,
        "truncated": False,
    }
    (job_dir / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")

    failures = {
        "failure_by_phase": {"approach": 2},
        "top_failure_reasons": ["motor_stall"],
        "emergency_shutdowns": 0,
        "recovery_overhead_pct": 10.0,
        "recovery_overhead": 0.1,
        "correlated_events": [],
        "shutdown_details": {},
    }
    (job_dir / "failures.json").write_text(json.dumps(failures), encoding="utf-8")

    # Register in module-level _jobs dict
    _mod._jobs[job_id] = {
        "job_id": job_id,
        "status": "completed",
        "log_directory": "/tmp/fake_logs",
    }

    return job_id


@pytest.fixture()
def second_job(tmp_path, completed_job):
    """Create a second completed job for comparison tests.

    Returns the second job_id.
    """
    job_id = "test-job-002"
    job_dir = _mod._results_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "job_id": job_id,
        "log_directory": "/tmp/fake_logs_2",
        "date_run": "2026-01-16T10:00:00+00:00",
        "status": "completed",
        "success_rate_pct": 90.0,
        "total_picks": 150,
        "session_duration_s": 4000,
    }
    (job_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    summary = {
        "executive_summary": "Better session",
        "status": "completed",
        "overall_health": "good",
        "duration": 4000,
        "total_picks": 150,
        "success_rate": 0.90,
        "error_count": 0,
        "key_findings": [],
        "critical_issues": [],
        "pick_performance": {
            "total_picks": 150,
            "success_rate_pct": 90.0,
            "picks_per_hour": 135,
            "cycle_time_ms": 2800,
        },
        "session_health": {
            "overall_health": "good",
            "duration_seconds": 4000,
            "duration_s": 4000,
        },
        "issues": [],
        "level_counts": {},
    }
    (job_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")

    detection = {
        "total_raw_detections": 250,
        "total_accepted": 200,
        "acceptance_rate_pct": 80.0,
        "acceptance_rate": 0.80,
        "border_skip_rate_pct": 3.0,
        "border_skip_rate": 0.03,
        "detection_timing_ms": {"mean": 40.0, "p95": 70.0},
        "timing": {"mean": 40.0, "p95": 70.0},
        "scan_effectiveness": None,
        "confidence_distribution": {"high": 150, "medium": 40},
    }
    (job_dir / "detection.json").write_text(json.dumps(detection), encoding="utf-8")

    timeline = {
        "events": [{"time": "10:00:01", "type": "pick_start"}],
        "total_events": 1,
        "total": 1,
        "truncated": False,
    }
    (job_dir / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")

    motors = {"joints": [], "motor_trending": None}
    (job_dir / "motors.json").write_text(json.dumps(motors), encoding="utf-8")

    _mod._jobs[job_id] = {
        "job_id": job_id,
        "status": "completed",
        "log_directory": "/tmp/fake_logs_2",
    }

    return job_id


# -----------------------------------------------------------------
# 1. History endpoint
# -----------------------------------------------------------------


class TestHistoryEndpoint:
    """GET /api/analysis/history"""

    def test_returns_list(self, client):
        resp = client.get("/api/analysis/history")
        assert resp.status_code == 200
        data = resp.json()
        assert "history" in data
        assert isinstance(data["history"], list)

    def test_empty_when_no_results(self, client):
        resp = client.get("/api/analysis/history")
        assert resp.json()["history"] == []

    def test_entries_have_created_alias(self, client, completed_job):
        resp = client.get("/api/analysis/history")
        data = resp.json()
        assert len(data["history"]) >= 1
        entry = data["history"][0]
        assert "created" in entry
        assert entry["created"] == entry["date_run"]

    def test_entries_have_success_rate_alias(self, client, completed_job):
        resp = client.get("/api/analysis/history")
        entry = resp.json()["history"][0]
        assert "success_rate" in entry
        assert isinstance(entry["success_rate"], float)
        # success_rate should be 0..1 scale (pct / 100)
        assert 0.0 <= entry["success_rate"] <= 1.0

    def test_history_sorted_newest_first(self, client, second_job):
        resp = client.get("/api/analysis/history")
        history = resp.json()["history"]
        assert len(history) >= 2
        dates = [e["date_run"] for e in history]
        assert dates == sorted(dates, reverse=True)


# -----------------------------------------------------------------
# 2. Log-dirs endpoint
# -----------------------------------------------------------------


class TestLogDirsEndpoint:
    """GET /api/analysis/log-dirs"""

    def test_returns_directories_list(self, client, tmp_path):
        _mod.FIELD_LOGS_DIR = tmp_path / "field_logs"
        _mod.FIELD_LOGS_DIR.mkdir()
        resp = client.get("/api/analysis/log-dirs")
        assert resp.status_code == 200
        data = resp.json()
        assert "directories" in data
        assert isinstance(data["directories"], list)

    def test_missing_dir_returns_warning(self, client):
        # FIELD_LOGS_DIR is already set to non-existent path
        resp = client.get("/api/analysis/log-dirs")
        assert resp.status_code == 200
        data = resp.json()
        assert "warning" in data
        assert data["directories"] == []


# -----------------------------------------------------------------
# 3. Summary endpoint
# -----------------------------------------------------------------


class TestSummaryEndpoint:
    """GET /api/analysis/{job_id}/summary"""

    def test_nonexistent_job_returns_404(self, client):
        resp = client.get("/api/analysis/nonexistent-job/summary")
        assert resp.status_code == 404

    def test_completed_job_returns_summary(self, client, completed_job):
        resp = client.get(f"/api/analysis/{completed_job}/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"

    def test_summary_has_success_rate_alias(self, client, completed_job):
        resp = client.get(f"/api/analysis/{completed_job}/summary")
        data = resp.json()
        assert "success_rate" in data
        assert isinstance(data["success_rate"], float)

    def test_summary_has_pick_performance(self, client, completed_job):
        resp = client.get(f"/api/analysis/{completed_job}/summary")
        data = resp.json()
        assert "pick_performance" in data
        pp = data["pick_performance"]
        assert "total_picks" in pp
        assert "success_rate_pct" in pp

    def test_summary_has_session_health(self, client, completed_job):
        resp = client.get(f"/api/analysis/{completed_job}/summary")
        data = resp.json()
        assert "session_health" in data


# -----------------------------------------------------------------
# 4. Detection endpoint
# -----------------------------------------------------------------


class TestDetectionEndpoint:
    """GET /api/analysis/{job_id}/detection"""

    def test_nonexistent_job_returns_404(self, client):
        resp = client.get("/api/analysis/nonexistent-job/detection")
        assert resp.status_code == 404

    def test_completed_job_returns_detection(self, client, completed_job):
        resp = client.get(f"/api/analysis/{completed_job}/detection")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_raw_detections" in data

    def test_detection_has_acceptance_rate_alias(self, client, completed_job):
        resp = client.get(f"/api/analysis/{completed_job}/detection")
        data = resp.json()
        assert "acceptance_rate" in data
        assert isinstance(data["acceptance_rate"], float)
        assert 0.0 <= data["acceptance_rate"] <= 1.0

    def test_detection_has_border_skip_rate_alias(self, client, completed_job):
        resp = client.get(f"/api/analysis/{completed_job}/detection")
        data = resp.json()
        assert "border_skip_rate" in data
        assert isinstance(data["border_skip_rate"], float)

    def test_detection_has_confidence_distribution(self, client, completed_job):
        resp = client.get(f"/api/analysis/{completed_job}/detection")
        data = resp.json()
        assert "confidence_distribution" in data
        assert isinstance(data["confidence_distribution"], dict)

    def test_detection_has_timing_alias(self, client, completed_job):
        resp = client.get(f"/api/analysis/{completed_job}/detection")
        data = resp.json()
        assert "timing" in data


# -----------------------------------------------------------------
# 5. Timeline endpoint
# -----------------------------------------------------------------


class TestTimelineEndpoint:
    """GET /api/analysis/{job_id}/timeline"""

    def test_nonexistent_job_returns_404(self, client):
        resp = client.get("/api/analysis/nonexistent-job/timeline")
        assert resp.status_code == 404

    def test_completed_job_returns_timeline(self, client, completed_job):
        resp = client.get(f"/api/analysis/{completed_job}/timeline")
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert isinstance(data["events"], list)

    def test_timeline_has_total_alias(self, client, completed_job):
        resp = client.get(f"/api/analysis/{completed_job}/timeline")
        data = resp.json()
        assert "total" in data
        assert data["total"] == data["total_events"]


# -----------------------------------------------------------------
# 6. Failures endpoint
# -----------------------------------------------------------------


class TestFailuresEndpoint:
    """GET /api/analysis/{job_id}/failures"""

    def test_nonexistent_job_returns_404(self, client):
        resp = client.get("/api/analysis/nonexistent-job/failures")
        assert resp.status_code == 404

    def test_completed_job_returns_failures(self, client, completed_job):
        resp = client.get(f"/api/analysis/{completed_job}/failures")
        assert resp.status_code == 200
        data = resp.json()
        assert "failure_by_phase" in data

    def test_failures_has_recovery_overhead_alias(self, client, completed_job):
        resp = client.get(f"/api/analysis/{completed_job}/failures")
        data = resp.json()
        assert "recovery_overhead" in data
        assert isinstance(data["recovery_overhead"], float)

    def test_failures_has_shutdown_details(self, client, completed_job):
        resp = client.get(f"/api/analysis/{completed_job}/failures")
        data = resp.json()
        assert "shutdown_details" in data


# -----------------------------------------------------------------
# 7. Compare endpoint
# -----------------------------------------------------------------


class TestCompareEndpoint:
    """GET /api/analysis/compare"""

    def test_missing_params_returns_422(self, client):
        resp = client.get("/api/analysis/compare")
        assert resp.status_code == 422

    def test_missing_one_param_returns_422(self, client, completed_job):
        resp = client.get(
            "/api/analysis/compare",
            params={"a": completed_job},
        )
        assert resp.status_code == 422

    def test_nonexistent_job_returns_400(self, client, completed_job):
        resp = client.get(
            "/api/analysis/compare",
            params={"a": completed_job, "b": "no-such-job"},
        )
        assert resp.status_code == 400

    def test_valid_compare_returns_flat_objects(
        self, client, completed_job, second_job
    ):
        resp = client.get(
            "/api/analysis/compare",
            params={"a": completed_job, "b": second_job},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Flat per-job objects for frontend
        assert "a" in data
        assert "b" in data
        assert isinstance(data["a"], dict)
        assert isinstance(data["b"], dict)

    def test_compare_flat_objects_have_success_rate(
        self, client, completed_job, second_job
    ):
        resp = client.get(
            "/api/analysis/compare",
            params={"a": completed_job, "b": second_job},
        )
        data = resp.json()
        assert "success_rate" in data["a"]
        assert "success_rate" in data["b"]
        assert isinstance(data["a"]["success_rate"], float)

    def test_compare_has_deltas(self, client, completed_job, second_job):
        resp = client.get(
            "/api/analysis/compare",
            params={"a": completed_job, "b": second_job},
        )
        data = resp.json()
        assert "deltas" in data
        assert isinstance(data["deltas"], dict)

    def test_compare_has_structured_sections(self, client, completed_job, second_job):
        resp = client.get(
            "/api/analysis/compare",
            params={"a": completed_job, "b": second_job},
        )
        data = resp.json()
        assert "pick_performance" in data
        assert "motor_health" in data
        assert "detection_performance" in data
        assert "session_health" in data


# -----------------------------------------------------------------
# 8. Run endpoint
# -----------------------------------------------------------------


class TestRunEndpoint:
    """POST /api/analysis/run"""

    def test_missing_body_returns_422(self, client):
        resp = client.post("/api/analysis/run")
        assert resp.status_code == 422

    def test_empty_body_returns_400(self, client):
        resp = client.post("/api/analysis/run", json={})
        assert resp.status_code == 400

    def test_nonexistent_directory_returns_403(self, client):
        # Absolute paths outside FIELD_LOGS_DIR are rejected with 403
        resp = client.post(
            "/api/analysis/run",
            json={"log_directory": "/no/such/path"},
        )
        assert resp.status_code == 403


# -----------------------------------------------------------------
# 9. Graceful failure handling (dashboard-tab-wiring-fix task 10.2)
# -----------------------------------------------------------------


class TestGracefulFailureHandling:
    """Verify endpoints return empty/null on partial failures, not 500."""

    def test_summary_with_missing_file_returns_graceful_error(self, client, tmp_path):
        """If summary.json is missing but job exists, should not 500."""
        job_id = "broken-job-001"
        job_dir = _mod._results_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        # Create metadata but NOT summary.json
        metadata = {"job_id": job_id, "status": "completed"}
        (job_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        _mod._jobs[job_id] = {
            "job_id": job_id,
            "status": "completed",
        }

        resp = client.get(f"/api/analysis/{job_id}/summary")
        # Should return 404 or an empty/default response, NOT 500
        assert resp.status_code != 500

    def test_detection_with_missing_file_returns_graceful_error(self, client, tmp_path):
        """If detection.json is missing but job exists, should not 500."""
        job_id = "broken-job-002"
        job_dir = _mod._results_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        metadata = {"job_id": job_id, "status": "completed"}
        (job_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        _mod._jobs[job_id] = {
            "job_id": job_id,
            "status": "completed",
        }

        resp = client.get(f"/api/analysis/{job_id}/detection")
        assert resp.status_code != 500

    def test_timeline_with_missing_file_returns_graceful_error(self, client, tmp_path):
        """If timeline.json is missing but job exists, should not 500."""
        job_id = "broken-job-003"
        job_dir = _mod._results_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        metadata = {"job_id": job_id, "status": "completed"}
        (job_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        _mod._jobs[job_id] = {
            "job_id": job_id,
            "status": "completed",
        }

        resp = client.get(f"/api/analysis/{job_id}/timeline")
        assert resp.status_code != 500

    def test_failures_with_missing_file_returns_graceful_error(self, client, tmp_path):
        """If failures.json is missing but job exists, should not 500."""
        job_id = "broken-job-004"
        job_dir = _mod._results_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        metadata = {"job_id": job_id, "status": "completed"}
        (job_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        _mod._jobs[job_id] = {
            "job_id": job_id,
            "status": "completed",
        }

        resp = client.get(f"/api/analysis/{job_id}/failures")
        assert resp.status_code != 500

    def test_corrupted_json_does_not_500(self, client, tmp_path):
        """If a result file has invalid JSON, should not 500."""
        job_id = "corrupted-job-001"
        job_dir = _mod._results_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        metadata = {"job_id": job_id, "status": "completed"}
        (job_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        (job_dir / "summary.json").write_text("NOT VALID JSON{{{", encoding="utf-8")
        _mod._jobs[job_id] = {
            "job_id": job_id,
            "status": "completed",
        }

        resp = client.get(f"/api/analysis/{job_id}/summary")
        assert resp.status_code != 500
